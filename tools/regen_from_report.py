#!/usr/bin/env python3
"""从已有 report.json 离线重导清单（不重跑网络体检）。

用途：修掉两个产物级 bug 后快速重出 dist/playable.m3u
  1) 上游把整行 #EXTVLCOPT:... 当值写进源里 -> UA 字段带双层前缀（播放器发非法 UA 被 CDN 拒）
  2) 无 v6 出口环境测不了的 IPv6 线路被当成可用写进主清单（家庭宽带绝大多数没有 v6 出口，
     电视端会先卡超时再换线，体感「全都播不了」）

输出：
  dist/playable.m3u      仅 v4 实测可用线路（+ 必选频道占位）
  dist/ipv6_pending.m3u  仅 IPv6 线路（供有 v6 出口的播放端）
  dist/_regen_backup_*/  原文件备份

用法: python tools/regen_from_report.py [--report dist/report.json] [--outdir dist]
                                         [--max-lines 3] [--include-v6]
"""
import argparse, json, os, re, shutil, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_sources as ts          # 复用 UA / order_key / line_score / extinf_block / REG

CLEAN_PREFIX = re.compile(r"^\s*#?\s*EXTVLCOPT\s*:\s*[A-Za-z0-9_.-]+\s*=\s*", re.I)


def clean_url_opts(d):
    """剥掉 ua/referer 里被上游污染进去的 #EXTVLCOPT:… 前缀"""
    for k in ("ua", "referer"):
        v = (d.get(k) or "").strip()
        for _ in range(4):
            nv = CLEAN_PREFIX.sub("", v)
            if nv == v:
                break
            v = nv.strip()
        d[k] = v
    return d


def pick(rows, max_lines):
    """按频道 key 聚合，每频道最多 max_lines 条，优先不同主机"""
    by = {}
    for r in rows:
        by.setdefault(r.get("key") or (r.get("name") or "").strip(), []).append(r)
    kept = []
    for key, items in by.items():
        items.sort(key=ts.line_score)
        head = items[0]
        picked, hosts, urls = [], set(), set()
        for it in items:
            if len(picked) >= max_lines:
                break
            h = urllib.parse.urlparse(it["url"]).hostname or "?"
            if it["url"] in urls or h in hosts:
                continue
            picked.append(it); hosts.add(h); urls.add(it["url"])
        for it in items:
            if len(picked) >= max_lines:
                break
            if it["url"] in urls:
                continue
            picked.append(it); urls.add(it["url"])
        for it in picked:
            it["kept"] = True
            it["name"] = head["name"]
            it["group"] = head["group"]
            it["chno"] = head.get("chno")
            kept.append(it)
    kept.sort(key=ts.order_key)
    return kept, by


def write_m3u(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for r in rows:
            f.write(ts.extinf_block(r))
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(HERE, "..", "dist", "report.json"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "..", "dist"))
    ap.add_argument("--max-lines", dest="max_lines", type=int, default=3)
    ap.add_argument("--include-v6", action="store_true", help="把 v6 线路也塞回主清单")
    a = ap.parse_args()

    rep = json.load(open(a.report, encoding="utf-8"))
    rows = rep["channels"]
    print("report: %s | 候选 %d 条 | 生成于 %s" % (a.report, len(rows), rep.get("generated")))

    v4 = [clean_url_opts(dict(r)) for r in rows if r.get("status") == "ok"]
    v6 = [clean_url_opts(dict(r)) for r in rows if r.get("status") == "skip_env_no_v6"]
    for r in v6:
        r["skip"] = True
    print("  实测可用(v4): %d | v6待测: %d" % (len(v4), len(v6)))

    main_rows = v4 + v6 if a.include_v6 else v4
    kept, by = pick(main_rows, a.max_lines)

    # 必选频道：本轮完全没有线路 -> 输出占位（电视端灰显，频道不消失）
    dead = []
    have = {r.get("key") for r in kept}
    seen = set()
    for r in rows:
        k = r.get("key")
        if not r.get("must") or not k or k in have or k in seen:
            continue
        seen.add(k)
        dead.append({"key": k, "name": r.get("name") or k, "group": r.get("group") or "其他",
                     "chno": r.get("chno"), "tvg_id": k, "dead": True,
                     "url": "dead://" + k, "logo": "", "ua": ts.UA, "referer": ""})
    dead.sort(key=ts.order_key)

    os.makedirs(a.outdir, exist_ok=True)
    bdir = os.path.join(a.outdir, "_regen_backup_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(bdir, exist_ok=True)
    for f in ("playable.m3u", "ipv6_pending.m3u"):
        src = os.path.join(a.outdir, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(bdir, f))
    print("  原文件已备份 ->", bdir)

    n1 = write_m3u(os.path.join(a.outdir, "playable.m3u"), kept + dead)
    v6_rows, _ = pick(v6, a.max_lines)
    n2 = write_m3u(os.path.join(a.outdir, "ipv6_pending.m3u"), v6_rows)
    print("\n[OK] playable.m3u      : %d 条（含 %d 个 dead 占位），频道 %d 个" % (n1, len(dead), len({r.get("key") for r in kept})))
    print("[OK] ipv6_pending.m3u  : %d 条" % n2)


if __name__ == "__main__":
    main()
