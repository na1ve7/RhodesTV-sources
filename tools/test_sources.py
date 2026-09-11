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


def probe(item, timeout):
    """探测单个流：先建连，再拉一段数据，判断是否真的能出流"""
    url = item["url"]
    host = urllib.parse.urlparse(url).hostname or ""
    if host in BAD_HOSTS:
        return dict(item, ok=False, reason="blacklist")
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
            return dict(item, ok=False, reason="http_%s_or_empty" % code)
        # m3u8 分片索引 / ts 流
        head = first[:512]
        if b"#EXTM3U" in first:
            kind = "hls"
        elif head[:1] == b"G" or b"\x47" == head[:1] or len(first) >= 188:
            kind = "ts"
        else:
            kind = "binary"
        return dict(item, ok=True, reason="ok", kind=kind,
                    ttf=round(dt, 3), kbps=round(len(first) * 8 / max(dt, 0.001) / 1000, 1))
    except Exception as e:
        return dict(item, ok=False, reason=type(e).__name__ + ":" + str(e)[:60])


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

def line_score(r):
    """线路排序：优先 HLS / 低码率 / 低首帧耗时（与全量模式同一套规则）"""
    kind_rank = {"hls": 0, "ts": 1, "binary": 2}
    t = r.get("ttf")
    nm = (r.get("name") or "").lower()
    heavy = 1 if ("4k" in nm or "2160" in nm or "8k" in nm) else 0
    return (kind_rank.get(r.get("kind"), 3), heavy, 9e9 if t is None else t,
            -(r.get("kbps") or 0))


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

    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(a.workers, len(cands)))) as ex:
        for fu in as_completed([ex.submit(probe, c, a.timeout) for c in cands]):
            results.append(fu.result())
    good = [r for r in results if r.get("ok")]
    good.sort(key=line_score)
    head = good[0] if good else cands[0]

    picked, seen_host, seen_u = [], set(), set()
    for it in good:                                   # 先取不同主机
        if len(picked) >= a.max_lines:
            break
        h = urllib.parse.urlparse(it["url"]).hostname or "?"
        if h in seen_host or it["url"] in seen_u:
            continue
        picked.append(it); seen_host.add(h); seen_u.add(it["url"])
    for it in good:                                   # 再补齐
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
                           "candidates": len(cands), "ok": len(good), "lines": len(picked)}
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)

    print("[recheck] %s: 候选 %d, 可用 %d, 写入线路 %d"
          % (key, len(cands), len(good), len(picked)))
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
    a = ap.parse_args()
    if a.recheck:
        sys.exit(recheck(a, a.recheck))

    sources = []
    if os.path.exists(a.infile):
        with open(a.infile, encoding="utf-8") as f:
            sources = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not sources:
        sources = DEFAULT_SOURCES
    print("源数量:", len(sources))

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
        futs = [ex.submit(probe, c, a.timeout) for c in uniq]
        for i, fu in enumerate(as_completed(futs), 1):
            results.append(fu.result())
            if i % 100 == 0:
                print("  探测进度 %d/%d" % (i, len(futs)), flush=True)

    good = [r for r in results if r.get("ok")]
    good.sort(key=lambda r: (r["group"], r["name"]))
    print("可用: %d / %d" % (len(good), len(results)))

    # ---- 多线路聚合：同一频道保留最快的 N 条线路（优先不同主机，避免同一挂全挂）----
    KIND_RANK = {"hls": 0, "ts": 1, "binary": 2}

    def score(r):
        t = r.get("ttf")
        nm = (r.get("name") or "").lower()
        heavy = 1 if ("4k" in nm or "2160" in nm or "8k" in nm) else 0   # 电视端优先低码率/低带宽线路
        return (KIND_RANK.get(r.get("kind"), 3), heavy, 9e9 if t is None else t, -(r.get("kbps") or 0))

    # 按「规范频道 key」聚合：同一频道在多个源里的线路合并，形成多线路备用
    by_key = {}
    for r in good:
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

    bad_hosts = {}
    for r in results:
        if not r.get("ok"):
            h = urllib.parse.urlparse(r["url"]).hostname or "?"
            bad_hosts[h] = bad_hosts.get(h, 0) + 1
    with open(os.path.join(a.outdir, "report.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(results),
            "ok": len(good),
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
