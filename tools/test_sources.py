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
DEFAULT_SOURCES = [
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
]


def http_get(url, timeout=15, referer=None, ua=UA):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Referer": referer or url,
        "Accept": "*/*",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read()
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default="sources.txt")
    ap.add_argument("--out", dest="outdir", default="dist")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--max-lines", dest="max_lines", type=int, default=3,
                    help="每个频道最多保留几条线路(电视端卡顿时会自动切换)")
    a = ap.parse_args()

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
        nk = norm_key(c.get("name") or "")
        if not u or not nk or u in seen_url or (nk, u) in seen:
            continue
        seen_url.add(u)
        seen.add((nk, u))
        c["key"] = nk
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
    print("去重后:", len(uniq), "（频道数 %d）" % len(cnt))

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

    # 按"归一化频道名"聚合：不同源写法不同，必须归并才能形成多线路（App 端按 name|group 合并线路）
    by_name = {}
    for r in good:
        by_name.setdefault(r.get("key") or (r.get("name") or "").strip(), []).append(r)

    kept = []
    for name, items in by_name.items():
        items.sort(key=score)
        canon = collections.Counter((i.get("group") or "未分组") for i in items).most_common(1)[0][0]
        # 展示名：取出现次数最多且最短的写法，保证同名同组在 App 端被合并为同一频道的多条线路
        disp = sorted(collections.Counter((i.get("name") or "").strip() for i in items).items(),
                      key=lambda x: (-x[1], len(x[0])))[0][0]
        picked, seen_host, seen_url = [], set(), set()
        for it in items:                                   # 第一轮：优先不同主机
            if len(picked) >= a.max_lines:
                break
            u = it["url"]
            h = urllib.parse.urlparse(u).hostname or "?"
            if u in seen_url or h in seen_host:
                continue
            picked.append(it); seen_host.add(h); seen_url.add(u)
        for it in items:                                   # 第二轮：主机去重后不足则补齐
            if len(picked) >= a.max_lines:
                break
            if it["url"] in seen_url:
                continue
            picked.append(it); seen_url.add(it["url"])
        for it in picked:
            it["kept"] = True
            it["canonical_group"] = canon
            it["name"] = disp
            if (it.get("group") or "未分组") != canon:      # 统一分组名，否则 App 会当成两个频道
                it["group_original"] = it.get("group")
                it["group"] = canon
            kept.append(it)
        for it in items:
            if not it.get("kept"):
                it["kept"] = False

    kept.sort(key=lambda r: (r["group"], r["name"]))
    n_chan = len(by_name)
    multi = sum(1 for v in by_name.values() if len([x for x in v if x.get("kept")]) > 1)
    print("频道(按名字去重): %d, 保留线路: %d (平均 %.2f), 多线路频道: %d"
          % (n_chan, len(kept), len(kept) / max(n_chan, 1), multi))

    os.makedirs(a.outdir, exist_ok=True)
    with open(os.path.join(a.outdir, "playable.m3u"), "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for r in kept:
            attrs = ' tvg-logo="%s"' % r.get("logo", "") if r.get("logo") else ""
            if r.get("tvg_id"):
                attrs += ' tvg-id="%s"' % r["tvg_id"]
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
            "bad_hosts": sorted(bad_hosts.items(), key=lambda x: -x[1])[:50],
            "channels": results,
        }, f, ensure_ascii=False, indent=1)
    print("输出:", os.path.join(a.outdir, "playable.m3u"))


if __name__ == "__main__":
    main()
