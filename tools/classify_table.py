# -*- coding: utf-8 -*-
"""分组重分类规则原型: 把混乱的上游 group-title 重分类为 12 个稳定大类。
词表与本脚本是唯一真源, 生产 Kotlin (GroupRules.kt) 由 gen_kotlin() 导出, 保证两侧一致。
"""
import re, collections

PROV = '北京 上海 天津 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 广西 海南 四川 贵州 云南 陕西 甘肃 青海 宁夏 新疆 西藏 内蒙古 延边 伊犁 大理 西双版纳 红河 文山 楚雄 凉山 甘孜 阿坝 康巴'.split()
CITY = ('广州 深圳 珠海 汕头 佛山 韶关 湛江 肇庆 江门 茂名 惠州 梅州 汕尾 河源 阳江 清远 东莞 中山 潮州 揭阳 云浮 南宁 桂林 柳州 北海 钦州 贵港 玉林 百色 贺州 河池 来宾 崇左 '
        '海口 三亚 儋州 琼海 文昌 万宁 成都 自贡 攀枝花 泸州 德阳 绵阳 广元 遂宁 内江 乐山 南充 眉山 宜宾 广安 达州 雅安 巴中 资阳 西昌 萧山 萧山 餘姚 余姚 萬州 万州 三峡 贵阳 六盘水 遵义 安顺 毕节 铜仁 凯里 都匀 兴义 万州 '
        '昆明 曲靖 玉溪 保山 昭通 丽江 普洱 临沧 拉萨 日喀则 昌都 林芝 西安 铜川 宝鸡 咸阳 渭南 延安 汉中 榆林 安康 商洛 兰州 嘉峪关 金昌 白银 天水 武威 张掖 平凉 酒泉 庆阳 定西 陇南 '
        '西宁 海东 银川 石嘴山 吴忠 固原 中卫 乌鲁木齐 克拉玛依 吐鲁番 哈密 昌吉 伊宁 阿克苏 喀什 和田 库尔勒 呼和浩特 包头 乌海 赤峰 通辽 鄂尔多斯 呼伦贝尔 巴彦淖尔 乌兰察布 '
        '沈阳 大连 鞍山 抚顺 本溪 丹东 锦州 营口 阜新 辽阳 盘锦 铁岭 朝阳 葫芦岛 长春 四平 辽源 通化 白山 松原 白城 延吉 哈尔滨 齐齐哈尔 鸡西 鹤岗 双鸭山 大庆 伊春 佳木斯 七台河 牡丹江 黑河 绥化 '
        '石家庄 唐山 秦皇岛 邯郸 邢台 保定 张家口 承德 沧州 廊坊 衡水 太原 大同 阳泉 长治 晋城 朔州 晋中 运城 忻州 临汾 吕梁 郑州 开封 洛阳 平顶山 安阳 鹤壁 新乡 焦作 濮阳 许昌 漯河 三门峡 南阳 商丘 信阳 周口 驻马店 '
        '武汉 黄石 十堰 宜昌 襄阳 鄂州 荆门 孝感 荆州 黄冈 咸宁 随州 长沙 株洲 湘潭 衡阳 邵阳 岳阳 常德 张家界 益阳 郴州 永州 怀化 娄底 南昌 景德镇 萍乡 九江 新余 鹰潭 赣州 吉安 宜春 抚州 上饶 '
        '南京 无锡 徐州 常州 苏州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁 杭州 宁波 温州 嘉兴 湖州 绍兴 金华 衢州 舟山 台州 丽水 合肥 芜湖 蚌埠 淮南 马鞍山 淮北 铜陵 安庆 黄山 滁州 阜阳 宿州 六安 亳州 池州 宣城 '
        '福州 厦门 莆田 三明 泉州 漳州 南平 龙岩 宁德 济南 青岛 淄博 枣庄 东营 烟台 潍坊 济宁 泰安 威海 日照 临沂 德州 聊城 滨州 菏泽 上虞 义乌 慈溪 余姚 诸城 寿光 海宁 桐乡 平湖 嵊州 新昌 温岭 临海 瑞安 乐清 苍南 象山 宁海 奉化 富阳 临安 建德 淳安 武进 江阴 宜兴 溧阳 金坛 丹阳 句容 江都 仪征 高邮 兴化 靖江 泰兴 如皋 海门 启东 海安 东台 大丰 邳州 新沂 沭阳 泗阳 盱眙 金湖 涟水 灌云 东海 郯城 兰陵 沂水 平邑 费县 莒南 临沭 曹县 单县 郓城 鄄城 梁山 汶上 泗水 邹城 滕州 微山 鱼台 金乡 嘉祥 钱江 南国').split()
PHRASES = {
    'hmt': ['NOW NEWS', 'NOW TV', 'NOW NEWS', 'NOW TV', 'TVB'],
    'sat': ['DRAGON TV', 'SATELLITE'],
    'intl': ['AL JAZEERA', 'ALJAZEERA', 'FOX NEWS', 'FOX WEATHER', 'RT '],
}
PY_PROV = 'anhui hebei hunan hubei henan jiangsu zhejiang guangdong guangxi sichuan yunnan guizhou shandong shanxi shaanxi fujian jiangxi gansu qinghai ningxia xinjiang xizang tibet neimonggol liaoning jilin heilongjiang hainan chongqing tianjin beijing shanghai'.split()
PY_CITY = 'harbin guangzhou lanzhou qingdao qtv chifeng chuxiong siping anshun wanzhou kangba hohhot urumqi kunming nanning fuzhou xiamen shenzhen dalian suzhou wuxi ningbo wenzhou nanchang changsha zhengzhou jinan taiyuan hefei guiyang haikou sanya yantai weifang linyi huizhou jiangmen zhaoqing shantou foshan dongguan zhongshan zhuhai'.split()
GENERIC_LOCAL = '公共 都市 综合 新闻综合 电视台 有线 文旅 民生 生活资讯 影视娱乐 经济生活 科教 农村 城市 一套 二套 三套 四套 新闻频道 文化娱乐 文化生活 文化影院 生活频道 影视生活'.split()

K = {
    'cctv': 'CCTV 央视 中央电视 总台 CGTN 中国环球电视网 中学生频道'.split(),
    'hmt': ('翡翠 明珠 无线 TVB HOY VIUTV ViuTV 香港 澳门 澳视 莲花 MACAU 台湾 台视 中视 华视 民视 东森 三立 TVBS 中天 纬来 龙华 龙祥 八大 公视 寰宇 凤凰 RTHK 港台电视 开电视 NowTV J2 Viu 大爱 人间卫视 非凡 年代 高点 澳亚 美亚').split(),
    'sat': '卫视'.split(),
    'sports': '体育 足球 篮球 NBA 英超 西甲 德甲 意甲 法甲 中超 CBA 赛事 高尔夫 网球 羽毛球 乒乓 台球 搏击 拳击 电竞 运动 健身 赛车 摩托 冰雪 排球 游泳 田径 棋 钓鱼 武术 跆拳 解说'.split(),
    'kids': '少儿 卡通 动漫 动画 儿童 宝贝 亲子 优漫 KAKU 幼教 小伶 巧虎 EBS 金鹰 童 萌 龙珠 柯南 宝可梦 哆啦A梦 喜羊羊 灌篮高手 中华小当家 海绵宝宝 猫和老鼠 熊出没 奥特曼 火影 海贼 米老鼠 变形金刚 数码宝贝 小猪佩奇 汪汪队'.split(),
    'film': '电影 影视 剧场 影院 电视剧 片场 剧集 美剧 韩剧 港剧 泰剧 日剧 经典 怀旧 好莱坞 CHC 春晚 综艺 小品 相声 喜剧 邵氏 埋堆堆 连续剧 古装 武侠 玄幻 偶像 刑侦 悬疑 情感 影剧'.split(),
    'news': '财经 经济 股市 证券 资讯 第一财经 CNBC Bloomberg 东方财经 时事 议会'.split(),
    'intl': ('国际 海外 NHK BBC CNN KBS MBC SBS ABC CBS NBC FOX RT DW ARTE France Aljazeera Al-Jazeera Arirang Bloomberg Sky Euro TRT RAI TV5 澳大利亚 美国 英国 法国 德国 俄罗斯 日本 韩国 印度 越南 泰国 意大利 西班牙 葡萄牙 阿拉伯 土耳其 以色列 加拿大 巴西 阿根廷 非洲 欧洲 美洲 亚洲 英语 双语 塞尔维亚 Newsmax Wion astro 八度空间 新加坡 mediacorp'.split()),
    'doc': '纪录 纪实 人文 探索 地理 科学 历史 自然 动物 Discovery 国家地理 考古 文化 讲堂 百家 人与自然 地球 宇宙 风光 全景 景区 旅游 世界遗产 博物馆 观景 实景 航拍 直播中国 生态环境 特产'.split(),
    'music': '音乐 MV 演唱会 歌曲 MTV 咪咕 戏曲 曲艺 京剧 评剧 越剧 豫剧 黄梅戏 秦腔 昆曲 音乐会 歌舞'.split(),
    'local': PROV + CITY + PY_PROV + PY_CITY + GENERIC_LOCAL,
}
# 匹配顺序 = 优先级
PRIORITY = ['cctv', 'hmt', 'sat', 'sports', 'kids', 'film', 'news', 'intl', 'local', 'doc', 'music']
ORDER = [('cctv', '央视频道'), ('sat', '卫视频道'), ('local', '地方频道'), ('hmt', '港澳台频道'), ('film', '影视综艺'),
         ('sports', '体育频道'), ('kids', '少儿动画'), ('news', '新闻财经'), ('doc', '纪录人文'), ('music', '音乐戏曲'),
         ('intl', '国际频道'), ('other', '其他频道')]
NAME = dict(ORDER)
# 上游 group-title -> 大类 (名称规则无命中时兜底, None = 其他)
HINT = {'直播中国': 'doc', '地方频道': 'local', '国际时事': 'intl', '港澳代理': 'hmt', '春晚频道': 'film', '埋堆堆频道': 'film',
        '虎牙影视': 'film', '斗鱼影视': 'film', '音乐频道': 'music', '体育频道': 'sports', '动画频道': 'kids', '儿童频道': 'kids',
        '电影频道': 'film', '电视剧频道': 'film', '纪录频道': 'doc', '国际频道': 'intl', '央视频道': 'cctv', '央视IPV4': 'cctv',
        '卫视频道': 'sat', '电视剧': 'film', '电影': 'film', '少儿': 'kids', '体育': 'sports'}
QUALITY = r'[（(][^）)]*(1080|720|576|2160|4K|HD|高清|超清|FHD|fps)[^）)]*[）)]|[\[［][^\]］]*(Not 24/7|1080|720|576|2160|4K|HD|fps)[^\]］]*[\]］]'


def norm(n):
    """合并同名频道用的归一化名: 去画质/离线标记、统一 CCTV 写法、去空格、转小写。"""
    s = re.sub(QUALITY, '', n, flags=re.I)
    s = s.replace('CCTV-', 'CCTV').replace('CCTV_', 'CCTV')
    return re.sub(r'\s+', '', s).strip().lower()


def clean(n):
    """显示名: 只去掉画质/离线标记, 保留原写法。"""
    s = re.sub(QUALITY, '', n, flags=re.I).replace('  ', ' ').strip()
    return s or n.strip()


def hit(s, kws):
    for k in kws:
        if k and k in s:
            return k
    return None


FORCE = {'直播中国': 'doc', '春晚频道': 'film', '历年春晚': 'film', '埋堆堆频道': 'film', '虎牙影视': 'film',
         '斗鱼影视': 'film', '动画频道': 'kids', '儿童频道': 'kids', '电影频道': 'film', '电视剧频道': 'film',
         '音乐频道': 'music', '体育频道': 'sports', '国际频道': 'intl', '国际时事': 'intl', '央视IPV4': 'cctv',
         '央视频道': 'cctv', '卫视频道': 'sat', '少儿': 'kids', '电视剧': 'film', '电影': 'film', '体育': 'sports'}


def classify(name, up):
    f = FORCE.get(re.sub(r'[^\w\u4e00-\u9fa5]', '', up))
    if f:
        return NAME[f]
    for key in PRIORITY:
        up_ = name.upper()
        if hit(name, K[key]) or hit(up_, [k.upper() for k in K[key]]) or hit(up_, [k.upper() for k in PHRASES.get(key, [])]):
            return NAME[key]
    h = HINT.get(re.sub(r'[^\w\u4e00-\u9fa5]', '', up))
    return NAME[h] if h else NAME['other']


def load(path):
    items = []
    for line in open(path, encoding='utf-8', errors='ignore'):
        if line.startswith('#EXTINF'):
            m = re.search(r'group-title="([^"]*)"', line)
            items.append(((m.group(1) if m else ''), line.split(',')[-1].strip()))
    return items


if __name__ == '__main__':
    items = load(r'C:\Users\cjlst\GenericAgent\temp\iptv_research\LIVE_playable.m3u')
    cnt, names = collections.Counter(), collections.Counter()
    ex = collections.defaultdict(list)
    for up, n in items:
        c = classify(n, up)
        cnt[c] += 1
        names[norm(n)] += 1
        if len(ex[c]) < 8:
            ex[c].append(clean(n))
    print('上游条目 %d  归一化后 %d 个频道 (%d 条被合并为多线路)' % (len(items), len(names), len(items) - len(names)))
    for k, label in ORDER:
        print('%-8s %4d | %s' % (label, cnt[label], ' '.join(ex[label])))
    other = [clean(n) for up, n in items if classify(n, up) == NAME['other']]
    print('\n### 卫视频道名单: %s' % ' '.join([clean(n) for up, n in items if classify(n, up) == NAME['sat']]))
    print('\n### 其他频道 %d 条: %s' % (len(other), ' | '.join(other[:60])))
