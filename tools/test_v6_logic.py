# -*- coding: utf-8 -*-
"""v6 感知逻辑单测（针对 tools/test_sources.py 的改动）

两条分支：
  A) 本环境【无 v6 出口】: v6 线路标 skip_env_no_v6 —— 不建连、不算 ok、不算失败、
     不进 bad_hosts，但**保留进 playable.m3u**；同时证明 ok 计数与「源里根本没有 v6 线路」时完全一致。
  B) 【注入】一个"有 v6 出口"的假探测函数: v6 线路正常参与体检(ok=True, 无 skip 标记)。

跑法: python tools/test_v6_logic.py     （不需要真实网络：http_get / urlopen 全部打桩）
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import test_sources as ts

FAILED = []


def check(name, cond, extra=""):
    print(("  PASS " if cond else "  FAIL ") + name + (" | %s" % (extra,) if extra else ""))
    if not cond:
        FAILED.append(name)


V4 = "http://v4.test/live/cctv1.m3u8"
V6 = "http://[240e:e1:aa00::26]:8080/live/cctv1.m3u8"
V6_B = "http://[2409:8080:0:4:3:5:2:1]:8080/live/cctv2.m3u8"


def item(url, name="CCTV-1 综合"):
    return {"name": name, "group": "央视", "logo": "", "tvg_id": "", "ua": ts.UA,
            "referer": "", "source": "unit-test", "url": url}


class FakeResp(object):
    BODY = b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:-1,CCTV1\nseg.ts\n"

    def __init__(self, body=None):
        self._body = body or FakeResp.BODY

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def getcode(self):
        return 200

    def read(self, n=-1):
        return self._body[:n] if n and n > 0 else self._body

    def close(self):
        pass


class Net(object):
    """urlopen 打桩：记录被访问的 url，可用于证明"没有发起网络请求" """

    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=None, context=None):
        url = getattr(req, "full_url", req)
        self.calls.append(url)
        return FakeResp()


def patch_net():
    net = Net()
    ts.urllib.request.urlopen = net          # 进程内替换 stdlib 引用（测试进程专用）
    return net


REAL_URLOPEN = ts.urllib.request.urlopen


# ---------------------------------------------------------------- 分支 A
def test_A_no_v6_env():
    print("[A] 本环境无 v6 出口 -> v6 线路被跳过(不算失败/不算 ok)，v4 正常体检")
    net = patch_net()
    r_v6 = ts.probe(item(V6), 3, v6_env=False)
    check("A1 v6 线路标 skip_env_no_v6", r_v6.get("skip") is True
          and r_v6.get("status") == ts.SKIP_NO_V6 and r_v6.get("ok") is False, r_v6.get("status"))
    check("A2 v6 线路被识别为 v6_literal", r_v6.get("family") == "v6_literal", r_v6.get("family"))
    check("A3 跳过时【没有发起任何网络请求】", net.calls == [], net.calls)

    r_v4 = ts.probe(item(V4), 3, v6_env=False)
    check("A4 v4 线路不受影响，正常 ok", r_v4.get("ok") is True and not r_v4.get("skip"),
          r_v4.get("status"))
    check("A5 v4 线路判定为 v4_only", r_v4.get("family") == "v4_only", r_v4.get("family"))
    check("A6 只有 v4 真的建连了", net.calls == [V4], net.calls)

    # has_aaaa 的域名（解析出 v6 但本环境无 v6 出口）同样跳过
    ts._FAMILY_CACHE["hasaaaa.test"] = "has_aaaa"
    r_aaaa = ts.probe(item("http://hasaaaa.test/live.m3u8"), 3, v6_env=False)
    check("A7 has_aaaa 域名也无 v6 出口时跳过", r_aaaa.get("skip") is True, r_aaaa.get("status"))


# ---------------------------------------------------------------- 分支 B
def test_B_inject_v6_env():
    print("[B] 注入「有 v6 出口」的假探测函数 -> v6 线路正常参与体检")
    ts.detect_v6_env = lambda *a, **k: True      # 注入式假探测：不改被测代码，只替换探测函数
    ts._V6_ENV_CACHE.clear()
    env = ts.get_v6_env(force=True)
    check("B1 注入后 get_v6_env() 为 True", env is True, env)

    net = patch_net()
    r = ts.probe(item(V6), 3, v6_env=True)
    check("B2 v6 线路正常体检 ok", r.get("ok") is True and not r.get("skip"), r.get("status"))
    check("B3 v6 线路 kind 正常识别", r.get("kind") == "hls", r.get("kind"))
    check("B4 v6 线路真的发起了请求", net.calls == [V6], net.calls)
    ts.detect_v6_env = lambda *a, **k: False     # 还原
    ts._V6_ENV_CACHE.clear()


# ---------------------------------------------------------------- 端到端
SRC_V4_ONLY = "# test\nhttp://src.test/v4only.m3u\n"
SRC_V4_V6 = "# test\nhttp://src.test/v4only.m3u\nhttp://src.test/v6mix.m3u\n"

FAKE_V4 = ('#EXTM3U\n'
           '#EXTINF:-1 tvg-id="CCTV1" group-title="央视",CCTV-1 综合\n%s\n'
           '#EXTINF:-1 tvg-id="CCTV2" group-title="央视",CCTV-2 财经\n'
           'http://v4.test/live/cctv2.m3u8\n' % V4)
FAKE_V6 = ('#EXTM3U\n'
           '#EXTINF:-1 tvg-id="CCTV1" group-title="央视",CCTV-1 综合\n%s\n'
           '#EXTINF:-1 tvg-id="CCTV2" group-title="央视",CCTV-2 财经\n%s\n' % (V6, V6_B))


def run_main(sources_text, v6_env, tmp):
    net = patch_net()
    ts.http_get = lambda url, *a, **k: (FAKE_V4 if "v4only" in url else FAKE_V6)
    ts.get_v6_env = lambda *a, **k: v6_env
    indir = tempfile.mkdtemp(dir=tmp)
    inf = os.path.join(indir, "sources.txt")
    with open(inf, "w", encoding="utf-8") as f:
        f.write(sources_text)
    out = os.path.join(indir, "dist")
    argv = sys.argv
    sys.argv = ["test_sources.py", "--in", inf, "--out", out, "--workers", "4", "--timeout", "2"]
    try:
        ts.main()
    finally:
        sys.argv = argv
    rep = json.load(open(os.path.join(out, "report.json"), encoding="utf-8"))
    m3u = open(os.path.join(out, "playable.m3u"), encoding="utf-8").read()
    return rep, m3u, net


def test_C_end_to_end():
    print("[C] 端到端：无 v6 环境跑 main()，v6 线路不被剔除、ok 计数不因此改变")
    tmp = tempfile.mkdtemp(prefix="rhodes_v6_")
    rep_off, m3u_off, net_off = run_main(SRC_V4_V6, False, tmp)
    rep_v4, m3u_v4, _ = run_main(SRC_V4_ONLY, False, tmp)
    rep_on, m3u_on, net_on = run_main(SRC_V4_V6, True, tmp)

    check("C1 report.v6_env 记录为 False", rep_off.get("v6_env") is False, rep_off.get("v6_env"))
    check("C2 skip_env_no_v6 计数=2(两条 v6 线路)", rep_off.get("skip_env_no_v6") == 2,
          rep_off.get("skip_env_no_v6"))
    check("C3 skip 线路不计入 bad_hosts",
          all("[240e" not in str(h) for h, _ in rep_off.get("bad_hosts", [])),
          rep_off.get("bad_hosts"))
    check("C4 v6 线路仍保留在 playable.m3u", V6 in m3u_off and V6_B in m3u_off)
    check("C5 无 v6 出口时 ok 计数与「源里没有 v6」完全一致",
          rep_off["ok"] == rep_v4["ok"], (rep_off["ok"], rep_v4["ok"]))
    check("C6 未对 v6 地址发起网络请求", not any(u.startswith("http://[") for u in net_off.calls),
          net_off.calls)
    check("C7 频道数不因跳过而减少", rep_off["channels_unique"] >= rep_v4["channels_unique"],
          (rep_off["channels_unique"], rep_v4["channels_unique"]))

    check("C8 注入 v6 环境后 v6 线路正常体检", rep_on.get("v6_env") is True
          and rep_on.get("skip_env_no_v6") == 0 and rep_on["ok"] == rep_off["ok"] + 2,
          (rep_on.get("v6_env"), rep_on.get("skip_env_no_v6"), rep_on["ok"], rep_off["ok"]))
    fam = rep_on.get("family_counts") or {}
    check("C9 有 v6 环境时 v6 线路被真实建连", fam.get("v6_literal", 0) == 2, fam)
    check("C10 v6 环境下 v6 线路出现在清单", V6 in m3u_on and V6_B in m3u_on)
    print("      干跑输出目录:", tmp)


if __name__ == "__main__":
    print("=" * 72)
    test_A_no_v6_env()
    test_B_inject_v6_env()
    test_C_end_to_end()
    print("=" * 72)
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ALL PASS")
