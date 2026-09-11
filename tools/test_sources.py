# -*- coding: utf-8 -*-
"""自动测源：抓取多个 m3u 源 -> 并发实测 -> 输出 playable.m3u + report.json
用法: python test_sources.py [--in sources.txt] [--out dist] [--workers 24] [--timeout 8]
"""
import argparse, json, os, re, socket, ssl, sys, time, urllib.request, urllib.parse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default="sources.txt")
    ap.add_argument("--out", dest="outdir", default="dist")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--timeout", type=float, default=8.0)
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

    # 去重（同名同 URL）
    seen = set()
    uniq = []
    for c in chans:
        k = (c["name"], c["url"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    print("去重后:", len(uniq))

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

    os.makedirs(a.outdir, exist_ok=True)
    with open(os.path.join(a.outdir, "playable.m3u"), "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for r in good:
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
            "bad_hosts": sorted(bad_hosts.items(), key=lambda x: -x[1])[:50],
            "channels": results,
        }, f, ensure_ascii=False, indent=1)
    print("输出:", os.path.join(a.outdir, "playable.m3u"))


if __name__ == "__main__":
    main()
