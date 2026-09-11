# -*- coding: utf-8 -*-
"""生成/合并 XMLTV：抓取多个 EPG 源 -> 合并去重 -> 只保留 playable.m3u 里出现的频道 -> epg.xml(.gz)
用法: python gen_epg.py --m3u dist/playable.m3u --out dist --days 2
"""
import argparse, gzip, os, re, ssl, sys, time, urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (Linux; Android 11; TV) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
DEFAULT_EPG = [
    "https://epg.pw/xmltv/epg_CN.xml",
]


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def read_ids(m3u):
    ids = set()
    if not m3u or not os.path.exists(m3u):
        return ids
    with open(m3u, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("#EXTINF"):
                m = re.search(r'tvg-id="([^"]+)"', line)
                if m and m.group(1):
                    ids.add(m.group(1))
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m3u", default="dist/playable.m3u")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--epg", nargs="*", default=DEFAULT_EPG)
    a = ap.parse_args()

    keep = read_ids(a.m3u)
    print("需要 EPG 的频道数:", len(keep))

    out = ET.Element("tv")
    out.set("generator-info-name", "RhodesTV-gen_epg")
    seen_ch, seen_prog = set(), set()
    horizon = time.time() + a.days * 86400

    for url in a.epg:
        try:
            raw = fetch(url)
            print("  [ok] %s -> %.1f KB" % (url, len(raw) / 1024))
            root = ET.fromstring(raw)
        except Exception as e:
            print("  [fail] %s %s" % (url, type(e).__name__))
            continue
        for ch in root.findall("channel"):
            cid = ch.get("id") or ""
            if cid in seen_ch:
                continue
            if keep and cid not in keep:
                continue
            seen_ch.add(cid)
            out.append(ch)
        for pr in root.findall("programme"):
            cid = pr.get("channel") or ""
            if keep and cid not in keep:
                continue
            st = pr.get("start") or ""
            key = (cid, st, (pr.findtext("title") or ""))
            if key in seen_prog:
                continue
            seen_prog.add(key)
            out.append(pr)

    print("频道 %d, 节目 %d" % (len(seen_ch), len(seen_prog)))
    os.makedirs(a.out, exist_ok=True)
    xml_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(out, encoding="utf-8")
    with open(os.path.join(a.out, "epg.xml"), "wb") as f:
        f.write(xml_bytes)
    with gzip.open(os.path.join(a.out, "epg.xml.gz"), "wb") as f:
        f.write(xml_bytes)
    print("输出:", os.path.join(a.out, "epg.xml"))


if __name__ == "__main__":
    main()
