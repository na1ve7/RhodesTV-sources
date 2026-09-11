# -*- coding: utf-8 -*-
"""把 dist/report.json 渲染成一份自包含的 HTML 频道清单（离线可看、可搜索、可筛选）。

用法: python tools/channel_report.py [--in dist/report.json] [--out dist/channels.html]
      [--title 罗德岛TV 频道清单] [--sub URL]

设计目标:
- 零外部依赖(不引 CDN)，单文件，双击即看
- 顶部: 汇总卡片(候选/可播/唯一频道/线路数/平均线路)
- 中部: 分组筛选 + 搜索框 + 排序
- 主体: 每个频道一行，可展开看全部线路(延迟/类型/主机)
- 尾部: 不可用频道统计(死因 TOP) 便于排查
"""
import argparse, collections, html, json, os, time, urllib.parse

try:  # 与 App 端 GroupRules.kt 同源的 12 大类分类表
    from classify_table import classify as _cls, norm as _norm, ORDER as _ORDER
except Exception:  # 单独运行/缺文件时退化为上游分组
    _cls = None; _norm = lambda n: (n or "").strip().lower(); _ORDER = []

CSS = """
:root{--bg:#0f1420;--card:#171e2e;--line:#26304a;--fg:#e8eefc;--dim:#8fa0c4;--ok:#3ddc84;--bad:#ff6b6b;--warn:#ffcc66;--acc:#4d9bff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 "Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:22px 18px 60px}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:16px;word-break:break-all}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}
.card b{display:block;font-size:20px;margin-top:2px}
.card span{color:var(--dim);font-size:12px}
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
input,select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
input{min-width:240px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:4px 12px;font-size:13px;cursor:pointer;user-select:none}
.chip.on{background:var(--acc);border-color:var(--acc);color:#04101f;font-weight:700}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#1d2740;font-size:13px;color:#cfe0ff;position:sticky;top:0;cursor:pointer}
tr:hover td{background:#1b2334}
td.n{color:var(--dim);width:52px}
td.g{color:var(--warn);white-space:nowrap}
td.l{white-space:nowrap;font-weight:700}
td.t{white-space:nowrap;color:var(--dim);font-size:13px}
td.u{font-size:12px;color:var(--dim);word-break:break-all;max-width:420px}
details summary{cursor:pointer;color:var(--acc);font-size:12px}
.lines{margin:4px 0 0;padding-left:0;list-style:none;font-size:12px;color:var(--dim)}
.lines li{padding:2px 0;word-break:break-all}
.pill{display:inline-block;border-radius:6px;padding:0 6px;font-size:11px;margin-right:6px;background:#22304d;color:#a8c6ff}
.ok{color:var(--ok)}.bad{color:var(--bad)}
.foot{margin-top:18px;color:var(--dim);font-size:12px;line-height:1.8}
.note{background:#1b2740;border-left:3px solid var(--acc);padding:8px 12px;border-radius:6px;font-size:12px;color:#c7d6f5;margin:10px 0 14px}
"""

JS = r"""
var DATA=window.__DATA__;
var groups={}, cur='全部分组', q='', sortKey='name', sortDir=1;
DATA.forEach(function(c){groups[c.group]=(groups[c.group]||0)+1;});
function fmtMs(t){return (t==null)?'-':Math.round(t*1000)+' ms';}
function renderChips(){
  var box=document.getElementById('chips'); var ORD=window.__ORDER__||[]; var arr=Object.keys(groups).sort(function(a,b){var ia=ORD.indexOf(a),ib=ORD.indexOf(b);if(ia<0)ia=999;if(ib<0)ib=999;return ia-ib;});
  var h='<div class="chip on" data-g="全部分组">全部分组 ('+DATA.length+')</div>';
  arr.forEach(function(g){h+='<div class="chip" data-g="'+g+'">'+g+' ('+groups[g]+')</div>';});
  box.innerHTML=h;
  Array.prototype.forEach.call(box.querySelectorAll('.chip'),function(el){
    el.onclick=function(){cur=el.getAttribute('data-g');
      Array.prototype.forEach.call(box.querySelectorAll('.chip'),function(x){x.classList.remove('on');});
      el.classList.add('on'); render();};
  });
}
function render(){
  var rows=DATA.filter(function(c){
    if(cur!=='全部分组'&&c.group!==cur) return false;
    if(q&&(c.name+c.group+(c.best||'')).toLowerCase().indexOf(q)<0) return false;
    return true;});
  rows.sort(function(a,b){
    var x,y;
    if(sortKey==='lines'){x=a.lines.length;y=b.lines.length;}
    else if(sortKey==='ttf'){x=a.ttf==null?9e9:a.ttf;y=b.ttf==null?9e9:b.ttf;}
    else if(sortKey==='group'){x=a.group;y=b.group;}
    else {x=a.name;y=b.name;}
    if(x<y)return -1*sortDir; if(x>y)return 1*sortDir; return a.name<b.name?-1:1;});
  var h='';
  rows.forEach(function(c,i){
    var bad=c.lines.length===0;
    h+='<tr><td class="n">'+(i+1)+'</td>'
      +'<td><b>'+c.name+'</b></td>'
      +'<td class="g">'+c.group+'</td>'
      +'<td class="l'+(bad?' bad':' ok')+'">'+c.lines.length+'</td>'
      +'<td class="t">'+fmtMs(c.ttf)+'</td>'
      +'<td class="t">'+(c.kinds||'-')+'</td>'
      +'<td class="u">'+(c.lines[0]?c.lines[0]:'（无可用线路）');
    if(c.lines.length>1){
      h+='<details><summary>展开全部 '+c.lines.length+' 条线路</summary><ul class="lines">';
      c.lines.forEach(function(u,j){h+='<li><span class="pill">L'+(j+1)+'</span>'+u+'</li>';});
      h+='</ul></details>';
    }
    h+='</td></tr>';
  });
  document.getElementById('tbody').innerHTML=h;
  document.getElementById('count').textContent=rows.length;
}
window.addEventListener('DOMContentLoaded',function(){
  renderChips();
  document.getElementById('q').oninput=function(e){q=e.target.value.toLowerCase();render();};
  Array.prototype.forEach.call(document.querySelectorAll('th[data-k]'),function(th){
    th.onclick=function(){var k=th.getAttribute('data-k');
      if(sortKey===k)sortDir=-sortDir; else {sortKey=k;sortDir=1;} render();};
  });
  render();
});
"""


def norm_host(u):
    try:
        return urllib.parse.urlparse(u).hostname or "?"
    except Exception:
        return "?"


def build(rep, title, sub, generated_note=""):
    chans = rep.get("channels", [])
    ok = [c for c in chans if c.get("ok")]
    fail = [c for c in chans if not c.get("ok")]

    # 按 (频道名归一化, App 12 大类分组) 聚合出 App 视角的"频道"（同 key 的多条 URL = 多线路）
    agg = {}
    for c in ok:
        raw = c.get("group") or ""
        grp = _cls(c.get("name") or "", raw) if _cls else (c.get("canonical_group") or raw or "未分组")
        key = (_norm(c.get("name") or ""), grp)
        it = agg.setdefault(key, {"name": c.get("name"), "group": grp, "lines": [], "ttf": None,
                                  "kinds": set(), "_names": collections.Counter()})
        it["_names"][(c.get("name") or "").strip()] += 1
        it["lines"].append(c.get("url"))
        t = c.get("ttf")
        if t is not None and (it["ttf"] is None or t < it["ttf"]):
            it["ttf"] = t
        it["kinds"].add(c.get("kind") or "?")

    order = [lbl for _k, lbl in _ORDER] or []
    rows = []
    for it in agg.values():
        # 展示名：取出现次数最多、最短的写法（与云端/App 的展示名一致）
        it["name"] = sorted(it.pop("_names").items(), key=lambda x: (-x[1], len(x[0])))[0][0]
        it["kinds"] = "/".join(sorted(it["kinds"]))
        rows.append(it)
    rows.sort(key=lambda r: (order.index(r["group"]) if r["group"] in order else 99, r["name"]))

    multi = sum(1 for r in rows if len(r["lines"]) > 1)
    total_lines = sum(len(r["lines"]) for r in rows)
    avg_lines = round(total_lines / max(len(rows), 1), 2)
    fail_hosts = collections.Counter()
    fail_reasons = collections.Counter()
    for c in fail:
        fail_hosts[norm_host(c.get("url", ""))] += 1
        fail_reasons[str(c.get("reason", "?"))[:40]] += 1

    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    html_parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>", html.escape(title), "</title><style>", CSS, "</style></head><body><div class='wrap'>",
        "<h1>", html.escape(title), "</h1>",
        "<div class='sub'>数据时间：", html.escape(str(rep.get("generated", "?"))),
        "　·　订阅地址：", html.escape(sub), "</div>",
        "<div class='cards'>",
        "<div class='card'><span>候选源</span><b>", str(rep.get("total", 0)), "</b></div>",
        "<div class='card'><span>实测可播</span><b class='ok'>", str(rep.get("ok", 0)), "</b></div>",
        "<div class='card'><span>电视频道（去重）</span><b>", str(len(rows)), "</b></div>",
        "<div class='card'><span>线路总数</span><b>", str(total_lines), "</b></div>",
        "<div class='card'><span>平均线路/频道</span><b>", str(avg_lines), "</b></div>",
        "<div class='card'><span>多线路频道</span><b>", str(multi), "</b></div>",
        "<div class='card'><span>不可播</span><b class='bad'>", str(len(fail)), "</b></div>",
        "</div>",
        "<div class='note'>“线路”= 同一频道有多条不同的直播地址。电视端播放时，若当前线路连续缓冲超过 15 秒，"
        "会自动切到下一条线路；因此<b>多线路频道的抗卡顿能力最强</b>。本表按分组列出全部频道及线路数。</div>",
        ("<div class='note'>" + generated_note + "</div>") if generated_note else "",
        "<div class='tools'><input id='q' placeholder='搜索频道名 / 分组…'><span style='color:#8fa0c4'>当前显示 <b id='count'>0</b> 个频道</span></div>",
        "<div class='chips' id='chips'></div>",
        "<table><thead><tr>",
        "<th style='width:52px'>#</th><th data-k='name'>频道名</th><th data-k='group'>分组</th>",
        "<th data-k='lines'>线路数</th><th data-k='ttf'>最佳延迟</th><th>类型</th><th>线路（点开看全部）</th>",
        "</tr></thead><tbody id='tbody'></tbody></table>",
        "<div class='foot'>",
        "<div>不可播 TOP 主机（剔除数）：",
        html.escape(", ".join("%s×%d" % (h, n) for h, n in fail_hosts.most_common(12)) or "无"),
        "</div><div>不可播原因 TOP：",
        html.escape(", ".join("%s×%d" % (r, n) for r, n in fail_reasons.most_common(8)) or "无"),
        "</div><div>本页由 tools/channel_report.py 自动生成（数据源 dist/report.json）。</div>",
        "</div></div>",
        "<script>window.__ORDER__=", json.dumps(order, ensure_ascii=False), ";window.__DATA__=", payload, ";</script><script>", JS, "</script>",
        "</body></html>",
    ]
    return "".join(html_parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default=os.path.join("dist", "report.json"))
    ap.add_argument("--out", dest="outfile", default=os.path.join("dist", "channels.html"))
    ap.add_argument("--title", default="罗德岛TV · 频道清单")
    ap.add_argument("--sub", default="https://cdn.jsdelivr.net/gh/na1ve7/RhodesTV-sources@main/dist/playable.m3u")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    with open(a.infile, encoding="utf-8") as f:
        rep = json.load(f)
    page = build(rep, a.title, a.sub, a.note)
    os.makedirs(os.path.dirname(a.outfile) or ".", exist_ok=True)
    with open(a.outfile, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("输出:", a.outfile, len(page.encode("utf-8")), "字节")


if __name__ == "__main__":
    main()
