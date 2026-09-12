# -*- coding: utf-8 -*-
"""自动测源：抓取多个 m3u 源 -> 并发实测 -> 输出 playable.m3u + report.json
用法: python test_sources.py [--in sources.txt] [--out dist] [--workers 24] [--timeout 8]
"""
import argparse, collections, json, os, re, socket, ssl, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Linux; Android 11; TV) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

# 已知被运营商 DNS 污染/黑洞的域名（可继续追加）
BAD_HOSTS = set()

# ---------- IPv6 感知 -------------------------------------------------------
# GitHub Actions 免费 runner 没有 IPv6 出站（本机开发环境同样没有）。
# 云端体检绝不能把 v6 线路"判死"：无 v6 出口时统一标 skip_env_no_v6 ——
# 不计失败、不进 bad_hosts、不计入 ok、不影响 gate，也**不从 playable.m3u 剔除**
# （用户在自家宽带有 v6，这些线路可能正是最稳的）。
SKIP_NO_V6 = "skip_env_no_v6"
# 真实 TCP 探测目标（IPv6 字面量，不依赖 DNS）：国内公共 DNS 的 53 端口
V6_ENV_TARGETS = [("2400:3200::1", 53), ("2400:3200:baba::1", 53), ("240e:4c:4008::1", 53)]

_FAMILY_CACHE = {}
_V6_ENV_CACHE = {}


def url_family(url):
    """线路地址的协议族：v6_literal(URL host 是 IPv6 字面量) / has_aaaa(host 有 AAAA 记录) / v4_only"""
    host = urllib.parse.urlparse(url).hostname or ""
    if ":" in host:                      # urlparse 已去掉方括号，v6 字面量 host 里一定有冒号
        return "v6_literal"
    if not host:
        return "v4_only"
    if host in _FAMILY_CACHE:
        return _FAMILY_CACHE[host]
    fam = "v4_only"
    try:
        if socket.getaddrinfo(host, None, socket.AF_INET6):
            fam = "has_aaaa"
    except Exception:
        pass
    _FAMILY_CACHE[host] = fam
    return fam


def detect_v6_env(targets=None, timeout=3.0):
    """本运行环境是否有 IPv6 出站：对 v6 目标做**真实 TCP 连接**。
    注意：能解析出 AAAA 记录 != 有 v6 出口（DNS 结果不代表可用路由），所以只认连接成功。"""
    for host, port in (targets or V6_ENV_TARGETS):
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
        except Exception:
            continue
        for _fam, _typ, _proto, _cn, sa in infos:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                s.connect(sa)
                return True
            except Exception:
                continue
            finally:
                try:
                    s.close()
                except Exception:
                    pass
    return False


def get_v6_env(force=False):
    """带缓存的环境探测结果（单测注入 detect_v6_env 后用 force=True 刷新）。"""
    if force or "v" not in _V6_ENV_CACHE:
        try:
            _V6_ENV_CACHE["v"] = bool(detect_v6_env())
        except Exception:
            _V6_ENV_CACHE["v"] = False
    return _V6_ENV_CACHE["v"]


EXTINF = re.compile(r"#EXTINF:\s*(-?\d+(?:\.\d+)?)\s*(.*?),(.*)", re.I)
ATTR = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')
try:
    import channels_cn as REG
except Exception:                                     # 允许独立运行（无规范库时退化为旧行为）
    REG = None
try:
    import classify_table as CLS
except Exception:
    CLS = None
GROUP_ORDER = {g: i for i, g in enumerate(REG.GROUPS)} if REG else {}

DEFAULT_SOURCES = [
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
]


def _fetch_raw(url, timeout, referer, ua):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Referer": referer or url,
        "Accept": "*/*",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def http_get(url, timeout=15, referer=None, ua=UA):
    """抓取文本。GitHub raw 直连在本机ISP下常被 DPI 阻断/RST（实测），
    自动回退到公共镜像，保证云端与本地都能稳定抓到源。"""
    urls = [url]
    if "raw.githubusercontent.com" in url:
        for m in ("https://gh-proxy.com/", "https://ghfast.top/",
                  "https://ghproxy.net/", "https://raw.gitmirror.com/"):
            urls.append(m + url)
    raw, last = None, None
    for u in urls:
        try:
            raw = _fetch_raw(u, timeout, (None if u == url else u), ua)
            if u != url:
                print("  [mirror] %s" % u.split('/')[2])
            break
        except Exception as e:
            last = e
    if raw is None:
        raise last
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def parse_m3u(text, source_name=""):
    out = []
    ua, ref = None, None
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTVLCOPT"):
            m = re.search(r"(http-user-agent|http-referrer)\s*=\s*(.+)", line, re.I)
            if m:
                k, v = m.group(1).lower(), m.group(2).strip()
                # 上游有的源把整行 #EXTVLCOPT:… 当成值写进来（形成双层前缀）。
                # 不剥离的话 UA 会变成 "#EXTVLCOPT:http-user-agent=…"，播放器发出非法
                # User-Agent 会被部分 CDN 直接拒绝（403/400），表现为「清单里有源但播不了」。
                for _ in range(4):
                    nv = re.sub(r"^\s*#?\s*EXTVLCOPT\s*:\s*[A-Za-z0-9_.-]+\s*=\s*", "", v, flags=re.I)
                    if nv == v:
                        break
                    v = nv.strip()
                if "user-agent" in k:
                    ua = v
                else:
                    ref = v
            continue
        if line.upper().startswith("#KODIPROP"):
            m = re.search(r"(inputstream\.adaptive[^=]*)\s*=\s*(.+)", line, re.I)
            continue
        if line.upper().startswith("#EXTINF"):
            m = EXTINF.match(line)
            if m:
                attrs = dict((k.lower(), v) for k, v in ATTR.findall(m.group(2)))
                cur = {
                    "name": m.group(3).strip(),
                    "group": attrs.get("group-title", "") or "未分组",
                    "logo": attrs.get("tvg-logo", ""),
                    "tvg_id": attrs.get("tvg-id", ""),
                    "ua": ua or attrs.get("http-user-agent") or UA,
                    "referer": ref or attrs.get("http-referrer") or "",
                    "source": source_name,
                }
            continue
        if line.startswith("#"):
            continue
        if cur is not None:
            cur["url"] = line
            out.append(cur)
            cur = None
    return out


# ---------- 深度测速：真下载分片，按实测吞吐判定 -----------------------------
# 教训（2026-09-12 真机复现）：只验「能建连 / 能拿到 m3u8 开头」会把
# 「清单秒回、分片拉不动」的源当成可用源。CCTV5+ 某线路 m3u8 只有 545 B 却
# 0.1 KB/s，续拉 ts 分片直接超时 —— 电视端表现就是「播 3 秒画面不动、
# 飞速切 3 条线路全挂」。所以 ok 判定必须基于真实吞吐。
HARD_MIN_KBPS = 40.0     # 硬底线(≈320 kbps)：低于此值视为不能播 -> 判失败
GOOD_KBPS = 120.0        # 优选线(≈960 kbps)：排序优先，低于此值仍保留但排后面
SEG_CAP = 384 * 1024     # 单个分片最多读这么多字节就够估速率
DEEP_SEGS = 2            # 连续拉几个分片
MAX_HOPS = 3             # master playlist -> media playlist 最多跳几层
SEG_BUDGET = 6.0         # 单条线路下载分片的总时间预算(秒)，防止慢源拖垮体检


def _http_open(url, timeout, ua=None, referer=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua or UA,
        "Referer": referer or url,
        "Accept": "*/*",
        "Connection": "close",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def _read_capped(resp, cap, deadline=None):
    """最多读 cap 字节。resp.read(n) 返回短块即代表流结束，必须 break，
    否则遇到短响应（或测试打桩）会死循环。"""
    buf = b""
    while len(buf) < cap:
        if deadline is not None and time.time() > deadline:
            break
        n = min(65536, cap - len(buf))
        chunk = resp.read(n)
        if not chunk:
            break
        buf += chunk
        if len(chunk) < n:
            break
    return buf


def measure_stream(item, timeout, deep_segs=DEEP_SEGS, cap=SEG_CAP, budget=SEG_BUDGET):
    """真实吞吐测速 -> (speed_kbps, segs_ok, note)

    HLS：逐层解开 master playlist（选最低 BANDWIDTH 的子清单，电视端要的是不卡），
          然后真下载前 N 个分片；直链(ts)：直接限读一段估速率。
    speed 只按「下载耗时」计（不含首次建连），避免把网络时延算成带宽。
    """
    ua, ref = item.get("ua") or UA, item.get("referer") or ""
    url = item["url"]
    for _hop in range(MAX_HOPS):
        t0 = time.time()
        try:
            with _http_open(url, timeout, ua, ref) as r:
                body = _read_capped(r, 512 * 1024)
        except Exception as e:
            return 0.0, 0, "open_fail:" + type(e).__name__
        if b"#EXTM3U" not in body[:512]:
            if not body:
                return 0.0, 0, "empty"
            return (len(body) / 1024.0 / max(time.time() - t0, 0.001), 1, "direct")
        lines = [l.strip() for l in body.decode("utf-8", "ignore").splitlines() if l.strip()]
        sub, best = None, None
        for i, l in enumerate(lines):
            if l.upper().startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                m = re.search(r"BANDWIDTH=(\d+)", l, re.I)
                bw = int(m.group(1)) if m else 0
                if sub is None or bw < (best or 0):
                    sub, best = lines[i + 1], bw
        if sub:                                  # master playlist -> 下一层
            url = urllib.parse.urljoin(url, sub)
            continue
        segs = [urllib.parse.urljoin(url, l) for l in lines if not l.startswith("#")]
        if not segs:
            return 0.0, 0, "no_seg"
        total, ok, t_dl = 0, 0, 0.0
        for su in segs[:deep_segs]:
            t = time.time()
            try:
                with _http_open(su, min(timeout, budget), ua, ref) as r:
                    d = _read_capped(r, cap, deadline=t + budget)
            except Exception:
                continue
            if d:
                total += len(d)
                ok += 1
                t_dl += time.time() - t
        if not ok:
            return 0.0, 0, "seg_fail"
        return (total / 1024.0 / max(t_dl, 0.001), ok, "hls")
    return 0.0, 0, "hops_exceeded"


def deep_verify(rec, timeout, min_kbps=None, force=False):
    """对「快速摸底已通过」的记录做深度测速，就地更新 ok/status/speed_kbps。
    返回是否仍可用。本环境无 v6 出口而 skip 的线路不适用（没测就是不判死）。
    force=True 专供「慢源复测」：允许对首轮已判 slow 的记录重新测一次。"""
    if rec.get("skip"):
        return False
    if not force and not rec.get("ok"):
        return bool(rec.get("ok"))
    min_kbps = HARD_MIN_KBPS if min_kbps is None else min_kbps
    sp, segs, note = measure_stream(rec, timeout)
    rec["speed_kbps"] = round(sp, 1)
    rec["segs"] = segs
    rec["speed_note"] = note
    if segs == 0 or sp < min_kbps:
        rec["ok"] = False
        rec["status"] = "slow"
        rec["reason"] = "slow:%sKB/s,segs=%d,%s" % (round(sp, 1), segs, note)
        return False
    rec["ok"] = True
    rec["status"] = "ok"
    rec["reason"] = "ok"
    return True


def probe(item, timeout, v6_env=None):
    """探测单个流：先建连，再拉一段数据，判断是否真的能出流。
    v6_env=False（本环境无 v6 出口）时，非 v4_only 的线路不做网络探测，
    直接标 skip_env_no_v6：不算失败、不算 ok，但仍保留进 playable.m3u。"""
    url = item["url"]
    host = urllib.parse.urlparse(url).hostname or ""
    family = url_family(url)
    if host in BAD_HOSTS:
        return dict(item, ok=False, reason="blacklist", family=family)
    if v6_env is None:
        v6_env = get_v6_env()
    if not v6_env and family != "v4_only":
        return dict(item, ok=False, skip=True, family=family,
                    status=SKIP_NO_V6, reason=SKIP_NO_V6)
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": item.get("ua") or UA,
            "Referer": item.get("referer") or (url if url.startswith("http") else ""),
            "Accept": "*/*",
            "Connection": "close",
        })
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            code = r.getcode()
            first = r.read(2048)
            r.close()
        dt = time.time() - t0
        if code != 200 or not first:
            return dict(item, ok=False, family=family, status="http_error",
                        reason="http_%s_or_empty" % code)
        # m3u8 分片索引 / ts 流
        head = first[:512]
        if b"#EXTM3U" in first:
            kind = "hls"
        elif head[:1] == b"G" or b"\x47" == head[:1] or len(first) >= 188:
            kind = "ts"
        else:
            kind = "binary"
        return dict(item, ok=True, reason="ok", kind=kind, family=family, status="ok",
                    ttf=round(dt, 3), kbps=round(len(first) * 8 / max(dt, 0.001) / 1000, 1))
    except Exception as e:
        return dict(item, ok=False, family=family, status="error",
                    reason=type(e).__name__ + ":" + str(e)[:60])


QUALITY_RE = re.compile(r"[\(\[（【][^\)\]）】]{0,24}[\)\]）】]\s*$")
QUALITY_WORDS = ["高清", "超清", "标清", "蓝光", "4K", "4k", "8K", "HD", "FHD", "SD",
                 "2160P", "1080P", "720P", "576P", "480P", "IPV6", "备用", "线路", "测试"]
TAIL_WORDS = ["电视台", "广播电视台", "综合频道", "频道", "电视"]
CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8",
          "九": "9", "十": "10", "十一": "11", "十二": "12", "十三": "13", "十四": "14", "十五": "15",
          "十六": "16", "十七": "17", "十八": "18"}
# 央视各频道的常见中文别名 -> 统一编号（爷爷最常看的那几个台，必须能合并线路）
ALIAS = {
    "CCTV综合": "CCTV1", "CCTV财经": "CCTV2", "CCTV综艺": "CCTV3", "CCTV中文国际": "CCTV4",
    "CCTV体育": "CCTV5", "CCTV电影": "CCTV6", "CCTV军事农业": "CCTV7", "CCTV电视剧": "CCTV8",
    "CCTV纪录": "CCTV9", "CCTV科教": "CCTV10", "CCTV戏曲": "CCTV11", "CCTV社会与法": "CCTV12",
    "CCTV新闻": "CCTV13", "CCTV少儿": "CCTV14", "CCTV音乐": "CCTV15", "CCTV奥林匹克": "CCTV16",
    "CCTV农业农村": "CCTV17", "CCTV5PLUS": "CCTV5PLUS", "CCTV风云剧场": "CCTV风云剧场",
}


def norm_key(name):
    """频道名归一化：不同源对同一频道的写法不同(如 CCTV-1 / CCTV1综合 / CCTV-1(1080p))，
    归并成一个 key，才能真正把多条线路挂到同一个频道下。
    只影响"聚合用的 key"，不影响展示名与分组。"""
    s = (name or "").strip()
    for _ in range(3):
        t = QUALITY_RE.sub("", s).strip()
        if t == s:
            break
        s = t
    s = s.replace("（", "(").replace("）", ")").replace("：", ":")
    for w in QUALITY_WORDS:
        s = s.replace(w, "")
    s = re.sub(r"中央(?:电视台)?([一二三四五六七八九十\d]+)套",
               lambda m: "CCTV" + CN_NUM.get(m.group(1), m.group(1)), s)
    s = s.replace("中央电视台", "CCTV").replace("中央台", "CCTV").replace("央视", "CCTV")
    s = re.sub(r"[\s\u3000\-_|·:]+", "", s)
    s = s.upper()
    if s in ALIAS:
        return ALIAS[s]
    m = re.match(r"^CCTV(\d+)\+?(PLUS)?", s)
    if m:
        return "CCTV%s%s" % (m.group(1), "PLUS" if (m.group(2) or "+" in s[:8]) else "")
    for w in TAIL_WORDS:
        if len(s) > len(w) + 1 and s.endswith(w.upper()):
            s = s[: -len(w)]
    return s or (name or "").strip().upper()


def canon(item):
    """把上游频道名映射到规范频道（唯一真源 tools/channels_cn.py）。"""
    raw = (item.get("name") or "").strip()
    if REG:
        m = REG.match(raw)
        if m:
            return {"key": m[0], "name": m[1], "group": m[2], "chno": m[3], "must": m[4]}
    grp = item.get("group") or "其他频道"
    if CLS:
        try:
            grp = CLS.classify(raw, grp)
        except Exception:
            pass
    return {"key": norm_key(raw), "name": raw, "group": grp, "chno": None, "must": False}


def order_key(r):
    """组内排序：组顺序 -> 频道号 -> 名称（无频道号的排在本组最后）。"""
    return (GROUP_ORDER.get(r.get("group"), 99),
            r.get("chno") or 9999,
            r.get("name") or "")


# ---------- 单频道重体检（手机端「这个台卡了 → 立刻换一批线路」） ----------

def speed_band(r):
    """实测吞吐分档：0=优选(>=GOOD_KBPS) 1=够用(>=HARD_MIN_KBPS) 2=未测到速度 3=本环境无 v6 未测"""
    sp = r.get("speed_kbps") or 0
    if r.get("skip"):
        return 3
    if sp >= GOOD_KBPS:
        return 0
    if sp >= HARD_MIN_KBPS:
        return 1
    return 2


def line_score(r):
    """线路排序：先按实测吞吐分档（快 > 够用 > 未测），再优先 HLS / 低码率 / 低首帧"""
    kind_rank = {"hls": 0, "ts": 1, "binary": 2}
    t = r.get("ttf")
    nm = (r.get("name") or "").lower()
    heavy = 1 if ("4k" in nm or "2160" in nm or "8k" in nm) else 0
    return (speed_band(r), kind_rank.get(r.get("kind"), 3), heavy,
            9e9 if t is None else t, -(r.get("speed_kbps") or 0))


def extinf_block(r):
    """写出一条线路的 m3u 文本块（格式与全量输出完全一致）"""
    attrs = ' tvg-logo="%s"' % r.get("logo", "") if r.get("logo") else ""
    if r.get("key"):
        attrs += ' tvg-id="%s"' % r["key"]
    if r.get("chno"):
        attrs += ' tvg-chno="%d"' % r["chno"]
    if r.get("dead"):
        attrs += ' rhodes-dead="1"'
    out = '#EXTINF:-1%s group-title="%s",%s\n' % (attrs, r["group"], r["name"])
    if r.get("ua") and r["ua"] != UA:
        out += "#EXTVLCOPT:http-user-agent=%s\n" % r["ua"]
    if r.get("referer"):
        out += "#EXTVLCOPT:http-referrer=%s\n" % r["referer"]
    return out + r["url"] + "\n"


def split_blocks(text):
    """m3u 文本 → 条目块列表（每块 = 一条 #EXTINF + 可选 EXTVLCOPT + url 行）"""
    out, cur = [], []
    for ln in text.split("\n"):
        if ln.startswith("#EXTINF"):
            if cur:
                out.append(cur)
            cur = [ln]
        elif cur:
            cur.append(ln)
    if cur:
        out.append(cur)
    return ["\n".join(b).strip("\n") + "\n" for b in out if b]


def block_key(blk):
    m = re.search(r'tvg-id="([^"]*)"', blk)
    return m.group(1) if m else ""


def recheck(a, key):
    """只重新体检指定频道：其余频道从现有 dist/playable.m3u 原样保留，
    本频道重新抓源→实测→挑最快几条写回。让手机端能对单个卡顿频道实时换源。"""
    base_path = os.path.join(a.outdir, "playable.m3u")
    if not os.path.exists(base_path):
        print("[recheck] 基线不存在: %s" % base_path)
        return 1
    base = open(base_path, encoding="utf-8").read()

    sources = []
    if os.path.exists(a.infile):
        with open(a.infile, encoding="utf-8") as f:
            sources = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not sources:
        sources = DEFAULT_SOURCES

    cands, seen_url, seen = [], set(), set()
    for s in sources:
        try:
            for c in parse_m3u(http_get(s), s):
                u = (c.get("url") or "").strip()
                c.update(canon(c))
                if not u or c.get("key") != key or u in seen_url or (c["key"], u) in seen:
                    continue
                seen_url.add(u)
                seen.add((c["key"], u))
                cands.append(c)
        except Exception as e:
            print("  [fail] %s %s" % (s, e))
    print("[recheck] %s 候选线路 %d 条" % (key, len(cands)))
    if not cands:
        print("[recheck] 上游暂无该频道线路，保持原状")
        return 2

    v6_env = get_v6_env()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(a.workers, len(cands)))) as ex:
        for fu in as_completed([ex.submit(probe, c, a.timeout, v6_env) for c in cands]):
            results.append(fu.result())
    good = [r for r in results if r.get("ok")]
    # 单频道重体检同样必须真测速：手机端「这个台卡了 → 立刻换源」最常走的路径，
    # 若只验建连，会出现「点了一次换源，新线路照样卡」的假成功。
    slow_killed = 0
    if good and not getattr(a, "no_deep", False):
        with ThreadPoolExecutor(max_workers=max(1, min(a.workers, len(good)))) as ex:
            for fu in as_completed([ex.submit(deep_verify, r, a.timeout, a.min_kbps)
                                    for r in good]):
                fu.result()
        slow_killed = sum(1 for r in good if not r.get("ok"))
        good = [r for r in results if r.get("ok")]
    skipped = [r for r in results if r.get("skip")]     # 本环境无 v6 出口 -> 保留、不判死
    usable = good + skipped
    usable.sort(key=line_score)
    head = usable[0] if usable else cands[0]

    picked, seen_host, seen_u = [], set(), set()
    for it in usable:                                 # 先取不同主机
        if len(picked) >= a.max_lines:
            break
        h = urllib.parse.urlparse(it["url"]).hostname or "?"
        if h in seen_host or it["url"] in seen_u:
            continue
        picked.append(it); seen_host.add(h); seen_u.add(it["url"])
    for it in usable:                                 # 再补齐
        if len(picked) >= a.max_lines:
            break
        if it["url"] in seen_u:
            continue
        picked.append(it); seen_u.add(it["url"])
    for it in picked:
        it["name"] = head["name"]
        it["group"] = head["group"]
        it["chno"] = head.get("chno")
        it["tvg_id"] = head["key"]

    if picked:
        new_blocks = [extinf_block(it) for it in picked]
    else:                                             # 全挂了：留占位灰显，等下一轮
        ph = dict(head)
        ph["dead"] = True
        ph["url"] = "dead://" + key
        new_blocks = [extinf_block(ph)]

    blocks, kept_blocks, inserted = split_blocks(base), [], False
    for blk in blocks:
        if block_key(blk) == key:
            if not inserted:
                kept_blocks.extend(new_blocks)
                inserted = True
            continue
        kept_blocks.append(blk)
    if not inserted:
        kept_blocks.extend(new_blocks)

    with open(base_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n" + "\n".join(b.rstrip("\n") for b in kept_blocks) + "\n")

    rp = os.path.join(a.outdir, "report.json")
    rep = {}
    if os.path.exists(rp):
        try:
            rep = json.load(open(rp, encoding="utf-8"))
        except Exception:
            rep = {}
    chs = [c for c in (rep.get("channels") or []) if c.get("key") != key]
    chs += results
    rep["channels"] = chs
    rep["total"] = len(chs)
    rep["ok"] = sum(1 for c in chs if c.get("ok"))
    rep["last_recheck"] = {"key": key, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "candidates": len(cands), "ok": len(good),
                           "slow_killed": slow_killed, "deep": not getattr(a, "no_deep", False),
                           "skip_env_no_v6": len(skipped), "lines": len(picked)}
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)

    print("[recheck] %s: 候选 %d, 可用 %d（深度测速剔除 %d 条「清单能拉/分片拉不动」）, "
          "跳过(无v6环境) %d, 写入线路 %d"
          % (key, len(cands), len(good), slow_killed, len(skipped), len(picked)))
    for it in picked:
        print("   · %7.1f KB/s  %s" % (it.get("speed_kbps") or 0, (it.get("url") or "")[:96]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recheck", default="",
                    help="只重新体检该频道(tvg-id/规范key)，其余频道从现有输出原样保留")
    ap.add_argument("--in", dest="infile", default="sources.txt")
    ap.add_argument("--out", dest="outdir", default="dist")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--max-lines", dest="max_lines", type=int, default=3,
                    help="每个频道最多保留几条线路(电视端卡顿时会自动切换)")
    ap.add_argument("--min-kbps", dest="min_kbps", type=float, default=HARD_MIN_KBPS,
                    help="深度测速吞吐低于此值(KB/s)的线路判为不可用（默认 %(default)s）")
    ap.add_argument("--include-v6", action="store_true",
                    help="把本环境测不了的 IPv6 线路也写进 playable.m3u（默认只写 ipv6_pending.m3u）")
    ap.add_argument("--no-deep", action="store_true",
                    help="关闭深度测速（退回 v2.0「能建连即可用」口径，仅用于快速排查）")
    a = ap.parse_args()
    if a.recheck:
        sys.exit(recheck(a, a.recheck))

    sources = []
    if os.path.exists(a.infile):
        with open(a.infile, encoding="utf-8") as f:
            sources = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not sources:
        sources = DEFAULT_SOURCES
    v6_env = get_v6_env()
    print("源数量:", len(sources), "| 本环境 IPv6 出站:", v6_env)

    chans = []
    for s in sources:
        try:
            chans += parse_m3u(http_get(s), s)
            print("  [ok] %s -> %d 条" % (s, len(chans)))
        except Exception as e:
            print("  [fail] %s %s" % (s, e))

    # 去重：先按 URL 全局去重（不同源常互相抄同一地址），再按 (归一化频道, URL) 去重
    seen_url, seen, uniq = set(), set(), []
    for c in chans:
        u = (c.get("url") or "").strip()
        info = canon(c)
        c.update(info)
        nk = c["key"]
        if not u or not nk or u in seen_url or (nk, u) in seen:
            continue
        seen_url.add(u)
        seen.add((nk, u))
        uniq.append(c)
    # 每个频道最多探测这么多个候选，控制总耗时
    MAX_CAND = 12
    cnt, limited = collections.Counter(), []
    for c in uniq:
        if cnt[c["key"]] >= MAX_CAND:
            continue
        cnt[c["key"]] += 1
        limited.append(c)
    uniq = limited
    print("去重后:", len(uniq), "（规范频道数 %d，规范库命中 %d）"
          % (len(cnt), sum(1 for c in uniq if REG and REG.match(c.get("name") or ""))))

    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(probe, c, a.timeout, v6_env) for c in uniq]
        for i, fu in enumerate(as_completed(futs), 1):
            results.append(fu.result())
            if i % 100 == 0:
                print("  探测进度 %d/%d" % (i, len(futs)), flush=True)

    good = [r for r in results if r.get("ok")]
    # ---- 阶段 2：对「快速摸底通过」的线路做「真下载分片」吞吐测速 ----
    # 阶段 1 只能证明「清单/首包能拿到」，证明不了「能持续播」。
    # 实测教训：CCTV5+ 某线路 m3u8 545 B 秒回，分片却 0.1 KB/s / 超时 ——
    # 电视端表现就是「播 3 秒画面不动、换线也全挂」。必须真下载才算数。
    slow_killed = 0
    if good and not a.no_deep:
        t0 = time.time()
        n_before = len(good)
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for fu in as_completed([ex.submit(deep_verify, r, a.timeout, a.min_kbps)
                                    for r in good]):
                fu.result()
        first_pass_ok = sum(1 for r in good if r.get("ok"))
        retried, revived = 0, 0
        # ---- 阶段 2b：慢源按 host 串行复测（消除「同 IP 并发被服务器限速」导致的误杀）----
        # 实测教训：湖北公共 SD 单独测 841 KB/s，但 48 并发时被压到 24 KB/s 而判慢 ——
        # 原因是同一 CDN 对同一 IP 的并发连接做了限速。复测时同 host 串行 + 重试 1 次。
        slow = [r for r in good if not r.get("ok")]
        if slow:
            groups = collections.OrderedDict()
            for r in slow:
                h = urllib.parse.urlparse(r["url"]).hostname or ""
                groups.setdefault(h, []).append(r)
            retried = len(slow)

            def _retest_host(rs):
                n = 0
                for r in rs:
                    for _ in range(2):              # 首测 + 1 次重试
                        deep_verify(r, a.timeout, a.min_kbps, force=True)
                        if r.get("ok"):
                            n += 1
                            break
                        time.sleep(0.4)
                return n

            with ThreadPoolExecutor(max_workers=max(2, a.workers // 8)) as ex:
                revived = sum(fu.result() for fu in
                              [ex.submit(_retest_host, rs) for rs in groups.values()])
        good = [r for r in results if r.get("ok")]
        slow_killed = n_before - len(good)
        spd = sorted((r.get("speed_kbps") or 0) for r in good)
        med = spd[len(spd) // 2] if spd else 0
        print("深度测速: %d 条通过摸底 -> %d 条真能播（首轮剔除 %d 条，慢源复测救回 %d 条，"
              "净剔除 %d 条「清单能拉/分片拉不动」），实测吞吐中位数 %.0f KB/s，耗时 %.0fs"
              % (n_before, len(good), n_before - first_pass_ok, revived, slow_killed,
                 med, time.time() - t0))
        print("  慢源复测: %d 条按 host 串行重测（避免同 IP 并发被 CDN 限速误杀）" % retried)
    # 本环境无 v6 出口时被跳过的线路：不算失败、不算 ok，但要保留进 playable.m3u
    skipped = [r for r in results if r.get("skip")]
    # 本环境无 IPv6 出口时被跳过的线路：默认**不**写进主清单。
    # 绝大多数家庭宽带没有 v6 出口，混进 playable.m3u 只会让电视端先超时再换线
    # （体感就是「点了没反应 / 好像全都播不了」）。需要时用 --include-v6 打开，
    # 或直接分发 dist/ipv6_pending.m3u 给有 v6 出口的播放端。
    usable = good + (skipped if getattr(a, "include_v6", False) else [])
    good.sort(key=lambda r: (r["group"], r["name"]))
    print("可用: %d / %d（另有 %d 条因本环境无 v6 出口跳过，保留待用户家里用）"
          % (len(good), len(results), len(skipped)))
    if a.no_deep:
        print("提示: --no-deep 已开启，本次沿用 v2.0「能建连即可用」口径（未做深度测速）")

    # ---- 多线路聚合：同一频道保留最快的 N 条线路（优先不同主机，避免同一挂全挂）----
    KIND_RANK = {"hls": 0, "ts": 1, "binary": 2}

    def score(r):
        t = r.get("ttf")
        nm = (r.get("name") or "").lower()
        heavy = 1 if ("4k" in nm or "2160" in nm or "8k" in nm) else 0   # 电视端优先低码率/低带宽线路
        return (KIND_RANK.get(r.get("kind"), 3), heavy, 9e9 if t is None else t, -(r.get("kbps") or 0))

    # 按「规范频道 key」聚合：同一频道在多个源里的线路合并，形成多线路备用
    # 注意：这里用 usable(=good+skipped)，即本环境测不了的 v6 线路也保留在清单里，
    # 只是排序时排在真·可用线路后面（score 对 skip 线路给 kind=3 + ttf=9e9）。
    by_key = {}
    for r in usable:
        by_key.setdefault(r.get("key") or (r.get("name") or "").strip(), []).append(r)

    kept = []
    for key, items in by_key.items():
        items.sort(key=score)
        head = items[0]
        picked, seen_host, seen_url = [], set(), set()
        for it in items:                                   # 第一轮：优先不同主机
            if len(picked) >= a.max_lines:
                break
            u = it["url"]
            h = urllib.parse.urlparse(u).hostname or "?"
            if u in seen_url or h in seen_host:
                continue
            picked.append(it); seen_host.add(h); seen_url.add(u)
        for it in items:                                   # 第二轮：补齐
            if len(picked) >= a.max_lines:
                break
            if it["url"] in seen_url:
                continue
            picked.append(it); seen_url.add(it["url"])
        for it in picked:
            it["kept"] = True
            it["name"] = head["name"]                      # 统一展示名为规范名
            it["group"] = head["group"]                    # 统一分组为规范分组
            it["chno"] = head.get("chno")
            it["canonical_group"] = head["group"]
            kept.append(it)
        for it in items:
            it.setdefault("kept", False)

    # 必选频道占位：规范库中 must=True 但本轮无可用线路 -> 输出 dead 条目（电视端灰显，不消失）
    placeholders = []
    if REG:
        for e in REG.REGISTRY:
            if not e.get("must"):
                continue
            got = [x for x in by_key.get(e["key"], []) if x.get("kept")]
            if got:
                continue
            placeholders.append({"key": e["key"], "name": e["name"], "group": e["group"],
                                 "chno": e["chno"], "tvg_id": e["key"], "dead": True,
                                 "url": "dead://" + e["key"], "logo": "", "ua": UA, "referer": ""})

    kept.sort(key=order_key)
    placeholders.sort(key=order_key)
    n_chan = len(by_key)
    multi = sum(1 for v in by_key.values() if len([x for x in v if x.get("kept")]) > 1)
    print("频道(规范聚合): %d, 保留线路: %d (平均 %.2f), 多线路频道: %d, 占位(暂不可用): %d"
          % (n_chan, len(kept), len(kept) / max(n_chan, 1), multi, len(placeholders)))

    os.makedirs(a.outdir, exist_ok=True)
    all_rows = sorted(kept + placeholders, key=order_key)      # 活跃线路与占位统一按 组→频道号 排序
    with open(os.path.join(a.outdir, "playable.m3u"), "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for r in all_rows:
            attrs = ' tvg-logo="%s"' % r.get("logo", "") if r.get("logo") else ""
            # 统一用规范 key 做 tvg-id：同一频道在多个上游的 id 写法不同(CCTV1 / CCTV1.cn@SD)，
            # 若照抄上游 id，电视端会把同一个台当成多个频道重复显示，也会丢掉多线路合并。
            if r.get("key"):
                attrs += ' tvg-id="%s"' % r["key"]
            if r.get("chno"):
                attrs += ' tvg-chno="%d"' % r["chno"]
            if r.get("dead"):
                attrs += ' rhodes-dead="1"'
            f.write('#EXTINF:-1%s group-title="%s",%s\n' % (attrs, r["group"], r["name"]))
            if r.get("ua") and r["ua"] != UA:
                f.write("#EXTVLCOPT:http-user-agent=%s\n" % r["ua"])
            if r.get("referer"):
                f.write("#EXTVLCOPT:http-referrer=%s\n" % r["referer"])
            f.write(r["url"] + "\n")

    spd_all = sorted((r.get("speed_kbps") or 0) for r in good)
    speed_median = round(spd_all[len(spd_all) // 2], 1) if spd_all else 0.0
    bad_hosts = {}
    for r in results:
        if r.get("ok") or r.get("skip"):        # skip=本环境无 v6 出口，不是线路的错
            continue
        h = urllib.parse.urlparse(r["url"]).hostname or "?"
        bad_hosts[h] = bad_hosts.get(h, 0) + 1
    fam_cnt = collections.Counter(r.get("family", "?") for r in results)
    with open(os.path.join(a.outdir, "report.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(results),
            # 云端 runner 通常没有 IPv6 出站；此时 v6 线路只跳过不判死，
            # ok 口径与改动前一致（skip 既不计 ok 也不计失败），CI gate 不受影响。
            "v6_env": bool(v6_env),
            "skip_env_no_v6": len(skipped),
            "family_counts": dict(fam_cnt),
            "ok": len(good),
            "deep": (not a.no_deep),
            "min_kbps": a.min_kbps,
            "good_kbps": GOOD_KBPS,
            "slow_killed": slow_killed,
            "slow_retried": retried,
            "slow_revived": revived,
            "speed_median_kbps": speed_median,
            "channels_unique": n_chan,
            "lines_kept": len(kept),
            "max_lines": a.max_lines,
            "multi_line_channels": multi,
            "placeholders": [{"key": p["key"], "name": p["name"], "group": p["group"],
                              "chno": p["chno"]} for p in placeholders],
            "bad_hosts": sorted(bad_hosts.items(), key=lambda x: -x[1])[:50],
            "channels": results,
        }, f, ensure_ascii=False, indent=1)
    print("输出:", os.path.join(a.outdir, "playable.m3u"))


if __name__ == "__main__":
    main()
