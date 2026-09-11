# -*- coding: utf-8 -*-
"""频道规范库（唯一真源 / Single Source of Truth）。

作用：把 10 多个上游 m3u 里五花八门的频道名（CCTV1 / CCTV-1 (1080p) / CCTV-1 综合 / 央视一套 …）
收敛成统一的「规范频道」，并给出固定分组、频道号与排序依据。

字段：
  key    规范频道唯一键（大写、无空格）
  name   展示用规范名
  group  12 大类之一（顺序见 GROUPS，与 App 端 GroupRules.kt 一致）
  chno   频道号（用于组内排序 + 电视端左侧数字方块）
  must   True=必选频道（即使当前所有路线体检失败也保留占位，电视端灰显）
  alias  别名列表（匹配时按「名称包含别名」判定，长别名优先）
"""

GROUPS = ["央视频道", "卫视频道", "地方频道", "港澳台频道", "影视综艺", "体育频道",
          "少儿动画", "新闻财经", "纪录人文", "音乐戏曲", "国际频道", "其他频道"]

# ---------------------------------------------------------------- 央视
CCTV_MAIN = [
    ("CCTV1", "CCTV-1 综合", 1, ["CCTV1", "CCTV-1", "中央1套", "央视一套", "CCTVONE"]),
    ("CCTV2", "CCTV-2 财经", 2, ["CCTV2", "CCTV-2", "中央2套"]),
    ("CCTV3", "CCTV-3 综艺", 3, ["CCTV3", "CCTV-3", "中央3套"]),
    ("CCTV4", "CCTV-4 中文国际", 4, ["CCTV4", "CCTV-4", "中央4套"]),
    ("CCTV5", "CCTV-5 体育", 5, ["CCTV5", "CCTV-5", "中央5套"]),
    ("CCTV6", "CCTV-6 电影", 6, ["CCTV6", "CCTV-6", "中央6套"]),
    ("CCTV7", "CCTV-7 国防军事", 7, ["CCTV7", "CCTV-7", "中央7套"]),
    ("CCTV8", "CCTV-8 电视剧", 8, ["CCTV8", "CCTV-8", "中央8套"]),
    ("CCTV9", "CCTV-9 纪录", 9, ["CCTV9", "CCTV-9", "中央9套"]),
    ("CCTV10", "CCTV-10 科教", 10, ["CCTV10", "CCTV-10", "中央10套"]),
    ("CCTV11", "CCTV-11 戏曲", 11, ["CCTV11", "CCTV-11", "中央11套"]),
    ("CCTV12", "CCTV-12 社会与法", 12, ["CCTV12", "CCTV-12", "中央12套"]),
    ("CCTV13", "CCTV-13 新闻", 13, ["CCTV13", "CCTV-13", "中央13套"]),
    ("CCTV14", "CCTV-14 少儿", 14, ["CCTV14", "CCTV-14", "中央14套"]),
    ("CCTV15", "CCTV-15 音乐", 15, ["CCTV15", "CCTV-15", "中央15套"]),
    ("CCTV16", "CCTV-16 奥林匹克", 16, ["CCTV16", "CCTV-16", "中央16套"]),
    ("CCTV17", "CCTV-17 农业农村", 17, ["CCTV17", "CCTV-17", "中央17套"]),
    ("CCTV5PLUS", "CCTV-5+ 体育赛事", 18, ["CCTV5+", "CCTV-5+", "CCTV5PLUS", "CCTV-5PLUS"]),
    ("CCTV4K", "CCTV-4K 超高清", 19, ["CCTV4K", "CCTV-4K"]),
    ("CCTV8K", "CCTV-8K 超高清", 20, ["CCTV8K", "CCTV-8K"]),
    ("CCTV4EU", "CCTV-4 欧洲", 21, ["CCTV4欧洲", "CCTV-4 EUROPE", "CCTV4EUROPE"]),
    ("CCTV4AM", "CCTV-4 美洲", 22, ["CCTV4美洲", "CCTV-4 AMERICA", "CCTV4AMERICA"]),
]

# 央视付费/中数传媒频道（chno 从 30 起）
CCTV_PAY = [
    ("CCTVBILLIARDS", "央视台球", 30, ["台球", "BILLIARDS"]),
    ("CCTVGOLF", "央视高网", 31, ["高网", "GOLF TENNIS", "GOLFTENNIS", "高尔夫网球", "央视高网"]),
    ("STORMFOOTBALL", "风云足球", 32, ["风云足球", "STORMFOOTBALL", "STORM FOOTBALL"]),
    ("STORMMUSIC", "风云音乐", 33, ["风云音乐", "STORMMUSIC", "STORM MUSIC"]),
    ("STORMTHEATER", "风云剧场", 34, ["风云剧场", "STORMTHEATER", "STORM THEATER"]),
    ("FIRSTTHEATER", "第一剧场", 35, ["第一剧场", "FIRSTTHEATER", "FIRST THEATER"]),
    ("NOSTALGIA", "怀旧剧场", 36, ["怀旧剧场", "NOSTALGIA", "怀旧"]),
    ("WORLDGEO", "世界地理", 37, ["世界地理", "WORLDGEO", "WORLD GEOGRAPHY"]),
    ("WOMENFASHION", "女性时尚", 38, ["女性时尚", "WOMENSFASHION", "WOMEN'S FASHION"]),
    ("CULTUREQ", "文化精品", 39, ["文化精品", "CULTUREOFQUALITY", "CULTURE OF QUALITY", "央视精品"]),
    ("TVGUIDE", "电视指南", 40, ["电视指南", "TVGUIDE", "TV GUIDE"]),
    ("OLDSTORY", "老故事", 41, ["老故事", "OLDSTORY"]),
    ("DISCOVERYCN", "发现之旅", 42, ["发现之旅", "DISCOVERYCN"]),
    ("MIDDLESCHOOL", "中学生", 43, ["中学生", "MIDDLESCHOOL", "MIDDLE SCHOOL"]),
    ("HEALTHCN", "卫生健康", 44, ["卫生健康", "HEALTHCHANNEL", "CCTVHEALTH"]),
    ("WEAPON", "兵器科技", 45, ["兵器科技", "WEAPON", "WEAPON&TECHNOLOGY", "WEAPON AND TECHNOLOGY"]),
    ("CCTVOPERA", "央视戏曲", 46, ["央视戏曲", "CCTVOPERA", "CCTV-OPERA", "戏曲频道", "CCTV戏曲"]),
    ("CCTVSHOP", "中视购物", 47, ["中视购物", "CCTVSHOPPING", "CHINATELEVISIONSHOPPING"]),
    ("CCTVENT", "央视娱乐", 48, ["央视娱乐", "CCTVENTERTAINMENT", "CCTV-ENTERTAINMENT"]),
    ("CCTVGUIDETV", "央视精品", 49, ["央视精品", "CCTV精品"]),
    ("CCTVPRO", "央视证券资讯", 50, ["证券资讯", "CCTVPRO"]),
]

# ---------------------------------------------------------------- 卫视（chno 101+，按常见机顶盒顺序）
SATELLITE = [
    ("BJTV", "北京卫视", 101, ["北京卫视", "BRTV北京", "BTV北京"]),
    ("DFTV", "东方卫视", 102, ["东方卫视", "上海东方卫视"]),
    ("JSTV", "江苏卫视", 103, ["江苏卫视"]),
    ("ZJTV", "浙江卫视", 104, ["浙江卫视"]),
    ("HNTV", "湖南卫视", 105, ["湖南卫视"]),
    ("GDTV", "广东卫视", 106, ["广东卫视"]),
    ("SZTV", "深圳卫视", 107, ["深圳卫视"]),
    ("SDTV", "山东卫视", 108, ["山东卫视"]),
    ("AHTV", "安徽卫视", 109, ["安徽卫视"]),
    ("TJTV", "天津卫视", 110, ["天津卫视"]),
    ("CQTV", "重庆卫视", 111, ["重庆卫视"]),
    ("SCTV", "四川卫视", 112, ["四川卫视"]),
    ("HUBTV", "湖北卫视", 113, ["湖北卫视"]),
    ("HNTV2", "河南卫视", 114, ["河南卫视"]),
    ("HEBTV", "河北卫视", 115, ["河北卫视"]),
    ("JXTV", "江西卫视", 116, ["江西卫视"]),
    ("FJTV", "东南卫视", 117, ["东南卫视", "福建东南卫视"]),
    ("LNTV", "辽宁卫视", 118, ["辽宁卫视"]),
    ("HLJTV", "黑龙江卫视", 119, ["黑龙江卫视", "黑龙卫视", "黑龙江台"]),
    ("JLTV", "吉林卫视", 120, ["吉林卫视"]),
    ("SXTV", "山西卫视", 121, ["山西卫视"]),
    ("SHTV", "陕西卫视", 122, ["陕西卫视"]),
    ("GXTV", "广西卫视", 123, ["广西卫视"]),
    ("YNTV", "云南卫视", 124, ["云南卫视"]),
    ("GZTV", "贵州卫视", 125, ["贵州卫视"]),
    ("GSTV", "甘肃卫视", 126, ["甘肃卫视"]),
    ("QHTV", "青海卫视", 127, ["青海卫视"]),
    ("NXTV", "宁夏卫视", 128, ["宁夏卫视"]),
    ("XJTV", "新疆卫视", 129, ["新疆卫视"]),
    ("XZTV", "西藏卫视", 130, ["西藏卫视"]),
    ("NMGTV", "内蒙古卫视", 131, ["内蒙古卫视"]),
    ("HITV", "海南卫视", 132, ["海南卫视", "旅游卫视"]),
    ("XMTV", "厦门卫视", 133, ["厦门卫视"]),
    ("YBTV", "延边卫视", 134, ["延边卫视"]),
    ("BTTV", "兵团卫视", 135, ["兵团卫视"]),
    ("KBTV", "康巴卫视", 136, ["康巴卫视"]),
    ("SSTV", "三沙卫视", 137, ["三沙卫视"]),
    ("NFTV", "南方卫视", 138, ["南方卫视", "大湾区卫视"]),
    ("HAIXIA", "海峡卫视", 139, ["海峡卫视"]),
    ("YNNTV", "云南澜湄", 140, ["澜湄国际"]),
    ("SDTV2", "山东教育卫视", 141, ["山东教育"]),
    ("CETV1", "中国教育1台", 142, ["中国教育1", "CETV1", "中国教育电视台1"]),
    ("CETV2", "中国教育2台", 143, ["中国教育2", "CETV2"]),
    ("CETV4", "中国教育4台", 144, ["中国教育4", "CETV4"]),
]

# ---------------------------------------------------------------- 体育（chno 201+）
SPORTS = [
    ("GDTVSPORT", "广东体育", 201, ["广东体育", "GDTVSPORT"]),
    ("WUXINGSPORT", "五星体育", 202, ["五星体育", "WUXING"]),
    ("JJSPORT", "劲爆体育", 203, ["劲爆体育", "JJSPORT"]),
    ("VLSPORT", "纬来体育", 204, ["纬来体育", "VIDEOLAND SPORT"]),
    ("MACAUSPORT", "澳门体育", 205, ["澳门体育"]),
    ("JINGCAI", "睛彩篮球", 206, ["睛彩篮球", "睛彩"]),
    ("FOOTBALL", "足球频道", 207, ["足球频道", "FOOTBALLCHANNEL"]),
    ("TIANYUAN", "天元围棋", 208, ["天元围棋", "围棋频道"]),
    ("FISHING", "快乐垂钓", 209, ["快乐垂钓", "垂钓频道"]),
    ("BRTVSPORT", "北京体育休闲", 210, ["BRTV体育", "北京体育", "体育休闲"]),
    ("TJSPORT", "天津体育", 211, ["天津体育"]),
    ("SDSPORT", "山东体育", 212, ["山东体育"]),
    ("JSSPORT", "江苏体育休闲", 213, ["江苏体育"]),
    ("HUBSPORT", "湖北体育", 214, ["湖北体育", "楚风体育"]),
    ("LNSPORT", "辽宁体育", 215, ["辽宁体育"]),
    ("SZSPORT", "深圳体育", 216, ["深圳体育"]),
    ("GZSPORT", "广州竞赛", 217, ["广州竞赛", "竞赛频道"]),
    ("SUPERSPORT", "超级体育", 218, ["超级体育", "SUPERSPORT", "NEWTV超级体育"]),
    ("JPSPORT", "精品体育", 219, ["精品体育", "JINGPINSPORT"]),
    ("WUSHU", "武术世界", 220, ["武术世界", "武术频道"]),
    ("TRACESPORTS", "Trace Sports", 221, ["TRACE SPORTS", "TRACESPORTS"]),
    ("DAZN1", "DAZN 体育1", 222, ["DAZN体育1", "DAZN 1"]),
    ("DAZN2", "DAZN 体育2", 223, ["DAZN体育2", "DAZN 2"]),
    ("ELEVEN1", "ELEVEN 体育1", 224, ["ELEVEN体育1", "ELEVEN 1"]),
    ("ELEVEN2", "ELEVEN 体育2", 225, ["ELEVEN体育2", "ELEVEN 2"]),
    ("ELEVEN3", "ELEVEN 体育3", 226, ["ELEVEN体育3", "ELEVEN 3"]),
    ("IHOTSPORT", "爱体育", 227, ["爱体育", "IHOT"]),
    ("FENGHUANGSPORT", "凤凰体育", 228, ["凤凰体育"]),
    ("MANUTD", "曼联官方频道", 229, ["曼联", "MUTV"]),
    ("LALIGA", "西甲频道", 230, ["西甲", "LALIGA"]),
]

# ---------------------------------------------------------------- 少儿/纪录/新闻财经/音乐戏曲/影视综艺（目标频道，chno 301+）
KIDS = [
    ("CARTOON", "金鹰卡通", 301, ["金鹰卡通"]),
    ("KAKU", "卡酷少儿", 302, ["卡酷少儿", "卡酷"]),
    ("TOONMAX", "哈哈炫动", 303, ["哈哈炫动", "炫动卡通"]),
    ("YOUYOU", "优优宝贝", 304, ["优优宝贝"]),
    ("BBTV", "嘉佳卡通", 305, ["嘉佳卡通"]),
    ("ANIMAX", "优漫卡通", 306, ["优漫卡通"]),
]
DOCS = [
    ("DOCSH", "上海纪实", 310, ["上海纪实", "纪实人文"]),
    ("DOCBJ", "北京纪实科教", 311, ["北京纪实", "纪实科教"]),
    ("DOCJY", "金鹰纪实", 312, ["金鹰纪实"]),
    ("DOCCHN", "中国纪录", 313, ["中国纪录", "中国纪录片"]),
    ("DOCZJ", "之江纪录", 314, ["之江纪录"]),
]
FINANCE = [
    ("FINANCE1", "第一财经", 320, ["第一财经"]),
    ("DFFIN", "东方财经", 321, ["东方财经"]),
    ("FHFIN", "凤凰财经", 322, ["凤凰财经"]),
    ("FHINFO", "凤凰资讯", 323, ["凤凰资讯", "凤凰卫视资讯"]),
    ("BTVFIN", "BRTV财经", 324, ["BTV财经", "BRTV财经", "北京财经"]),
]
HKMO = [
    ("FHTV", "凤凰卫视", 330, ["凤凰卫视", "凤凰中文台", "凤凰中文"]),
    ("FHHK", "凤凰香港", 331, ["凤凰香港"]),
    ("TVBPEARL", "明珠台", 332, ["明珠台", "TVBPEARL"]),
    ("TVBJADE", "翡翠台", 333, ["翡翠台", "TVBJADE"]),
    ("TVBJ2", "TVB Plus", 334, ["TVBPLUS", "J2台", "无线J2"]),
    ("AUSTV", "澳视澳门", 335, ["澳视澳门", "澳门电视台"]),
    ("MACAUHD", "澳门综艺", 336, ["澳门综艺"]),
    ("HKSATV", "香港卫视", 337, ["香港卫视"]),
]
MUSIC = [
    ("MUSICLIVE", "音乐现场", 340, ["音乐现场"]),
    ("CZTV", "梨园频道", 341, ["梨园"]),
    ("XQYS", "七彩戏剧", 342, ["七彩戏剧"]),
]
MOVIE = [
    ("CHCACTION", "CHC 动作电影", 350, ["CHC动作电影", "CHC动作"]),
    ("CHCFAMILY", "CHC 家庭影院", 351, ["CHC家庭影院"]),
    ("CHCHD", "CHC 高清电影", 352, ["CHC高清电影"]),
    ("CHCSUSPENSE", "CHC 影迷电影", 353, ["CHC影迷电影"]),
    ("MEIYA", "美亚电影", 354, ["美亚电影"]),
    ("MDB", "埋堆堆", 355, ["埋堆堆"]),
    ("ZJSATV", "珠江频道", 356, ["珠江卫视", "珠江频道"]),
]
INTL = [
    ("CGTN", "CGTN", 360, ["CGTN英语", "CGTN主频", "CGTNENGLISH", "CGTN"]),
    ("CGTNDOC", "CGTN 纪录", 361, ["CGTN纪录", "CGTNDOCUMENTARY"]),
    ("CGTNAR", "CGTN 阿语", 362, ["CGTN阿语", "CGTNARABIC"]),
    ("CGTNSP", "CGTN 西语", 363, ["CGTN西语", "CGTNSPANISH"]),
    ("CGTNRU", "CGTN 俄语", 364, ["CGTN俄语", "CGTNRUSSIAN"]),
    ("CGTNFR", "CGTN 法语", 365, ["CGTN法语", "CGTNFRENCH"]),
]
_EXTRA_SPORTS = [
    ("MLFOOTBALL", "魅力足球", 231, ["魅力足球"]),
    ("XFPY", "先锋乒羽", 232, ["先锋乒羽"]),
    ("GOLFCH", "高尔夫网球", 233, ["高尔夫网球", "高尔夫频道"]),
    ("CSL", "足球赛事", 234, ["足球赛事"]),
]
SPORTS += _EXTRA_SPORTS

# ================================================================ 匹配引擎
import json
import os
import re

QUALITY_RE = re.compile(
    r"\((?:1080|720|576|540|480|360|240)[pi]?\)|\[(?:not\s*24/7|geo[- ]?blocked|dead)\]|"
    r"\b(?:1080p|720p|576p|540p|480p|4k|8k|fhd|uhd|hd|sd|h265|hevc)\b|"
    r"[（(][^）)]*(?:高清|超清|标清|蓝光|画质)[^）)]*[）)]",
    re.I)
DROP_WORDS = ["高清", "超清", "标清", "蓝光", "免费", "直播", "频道", "线路", "备用", "测试"]

CCTV_RE = re.compile(r"^CCTV([0-9]{1,2})(\+|PLUS)?(?:套)?(.*)$")
CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8",
          "九": "9", "十": "10", "十一": "11", "十二": "12", "十三": "13", "十四": "14", "十五": "15",
          "十六": "16", "十七": "17"}


def clean(name):
    s = (name or "").strip()
    s = s.replace("（", "(").replace("）", ")").replace("：", ":")
    for _ in range(3):
        t = QUALITY_RE.sub(" ", s)
        if t == s:
            break
        s = t
    s = re.sub(r"中央(?:电视台)?([一二三四五六七八九十]+)套", lambda m: "CCTV" + CN_NUM.get(m.group(1), "?"), s)
    s = s.replace("中央电视台", "CCTV").replace("中央台", "CCTV").replace("央视", "CCTV")
    s = re.sub(r"[\s\u3000\-_|·:、,，.]+", "", s)
    return s.upper()


def _entries():
    out = []
    for lst, grp in ((CCTV_MAIN, "央视频道"), (CCTV_PAY, "央视频道"), (SATELLITE, "卫视频道"),
                     (SPORTS, "体育频道"), (KIDS, "少儿动画"), (DOCS, "纪录人文"),
                     (FINANCE, "新闻财经"), (HKMO, "港澳台频道"), (MUSIC, "音乐戏曲"),
                     (MOVIE, "影视综艺"), (INTL, "国际频道")):
        for key, name, no, alias in lst:
            out.append((key, name, grp, no, True, alias))
    seen, res = set(), []
    for key, name, grp, no, must, alias in out:
        if key in seen:
            continue
        seen.add(key)
        al = sorted({clean(a) for a in alias} | {clean(name)}, key=len, reverse=True)
        res.append({"key": key, "name": name, "group": grp, "chno": no, "must": must, "alias": al})
    return res


REGISTRY = _entries()
# 主频道号 -> 条目（CCTV-N 快速通道）
_BY_NO = {}
for e in REGISTRY:
    _BY_NO.setdefault(e["chno"], e)
_EXACT, _CONTAINS = {}, []
for e in REGISTRY:
    for a in e["alias"]:
        _EXACT.setdefault(a, e)
        if not a.startswith("CCTV"):
            _CONTAINS.append((a, e))
_CONTAINS.sort(key=lambda x: -len(x[0]))


def match(name):
    """返回 (key, name, group, chno, must) 或 None。"""
    if not name:
        return None
    s = clean(name)
    if not s:
        return None
    # 1) CCTV 数字快速通道（避免 CCTV1 命中 CCTV10）
    if s.startswith("CCTV"):
        if s.startswith("CCTV4K") or s.startswith("CCTV8K"):
            e = _BY_NO[19 if s.startswith("CCTV4K") else 20]
            return _t(e)
        m = CCTV_RE.match(s)
        if m:
            n = int(m.group(1))
            plus = bool(m.group(2)) or "+" in s[:8]
            if n == 5 and plus:
                return _t(_BY_NO[18])
            if 1 <= n <= 17:
                rest = m.group(3) or ""
                if n == 4 and rest.startswith("欧洲"):
                    return _t(_BY_NO[21])
                if n == 4 and rest.startswith("美洲"):
                    return _t(_BY_NO[22])
                if n == 4 and rest.startswith("ASIA"):
                    return _t(_BY_NO[4])
                if plus and n != 5:
                    return None
                return _t(_BY_NO[n])
    # 2) 精确别名
    e = _EXACT.get(s)
    if e:
        return _t(e)
    # 3) 包含匹配（长别名优先）
    for a, e in _CONTAINS:
        if len(a) >= 2 and a in s:
            return _t(e)
    return None


def _t(e):
    return (e["key"], e["name"], e["group"], e["chno"], e["must"])


def dump(path):
    data = {"groups": GROUPS, "channels": REGISTRY}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return len(REGISTRY)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    n = dump(os.path.join(here, "channels_cn.json"))
    print("registry 条目:", n)
    sample = ["CCTV-1 (1080p)", "CCTV1综合", "CCTV-5+ 体育赛事", "CCTV-17 农业农村",
              "央视台球", "CCTV怀旧剧场", "风云足球", "湖南卫视 (1080p)", "广东体育", "睛彩篮球"]
    for s in sample:
        print("  %-22s -> %s" % (s, match(s)))
