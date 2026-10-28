#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
article_qa.py — 公众号文章常驻机械校验器（通用版，只检测、不落稿）
============================================================
用途：对任意公众号成稿做机械指标终审——**由写作Agent在交稿前自己跑**。
      - 不写文章、不改文章、不落任何成稿文件，只读入->检测->打印报告。
      - 写作Agent 写完草稿后必须亲自执行本脚本，读真实输出，FAIL>0 自己改、循环到 0，
        并把脚本真实 stdout 贴进交付消息作为"真跑过"的证据（杜绝"脚本全绿"凭记忆编）。
      - 退出码：FAIL>0 时返回 1，便于自动化卡死。

通用性（2026-10-26 重构为全主题通用，适用国内/新疆/瑞士/欧洲/川西青甘西北西藏等所有目的地）：
      - 支持单篇 / 多篇文章（任意篇数），每篇用一级标题 `# 标题` 分隔。
      - 通用检查（所有文章必跑）：标题基础格式、SEO（若有）、加粗小标题（若有）、
        段落长度、违禁词、破折号密度、跨篇逐字复读（多篇时）。
      - 主题词（目的地标签）【必带】：缴稿核验必须带主题——国内/新疆/瑞士/欧洲/川西青甘
        西北西藏等。运行脚本须用 `--theme 词` 指定（如 --theme 新疆），或标题/篇名含目的地
        标签；每条标题须含该主题词。未带主题词直接报错退出（杜绝"无主题裸稿"）。
      - 主题专项（仅该主题有专属硬卡时启用）：目前仅「瑞士」实现了专属检查
        （年份=0/月份锚点/ESOP双数）；其它目的地暂无专属硬卡，只跑通用层。可用 --swiss 强制瑞士模式。
      - 字数：默认不卡；用 --minlen/--maxlen 才启用（如某篇需卡字数可显式传参）。

输入格式约定（宽松解析）：
      # 篇名或任意一级标题
      **标题（6）**：            （可选；有则校验数量与格式）
      1. 第一条
      2. 第二条 ...
      **SEO 词组**（字数说明）：关键词、关键词、...   （可选；有则校验）
      正文……（小标题用整行 **文字** 包裹）

运行：python article_qa.py <文章文件.md> --theme 词 [--swiss] [--minlen N] [--maxlen N] [--minbold N] [-o 报告.txt]
      （--theme 必填：目的地标签，如 瑞士/新疆/欧洲/国内；瑞士文加 --swiss 启用年份/月份/ESOP 专项）
输出：每篇逐项 PASS/FAIL + 末尾总 FAIL 数。
"""
import sys, re, io

# ---------- 工具 ----------
CN = re.compile(r'[\u4e00-\u9fff]')
def cn_len(s: str) -> int:
    return len(CN.findall(s))

def strip_punct(s: str) -> str:
    return re.sub(r'[\s，。、；：:？?！!（）()【】""\'\'《》.,;:!?—·]', '', s)

def split_sentences(s: str):
    return [p for p in re.split(r'[。！？!?；;\n]', s) if p.strip()]

# ---------- 违禁词（通用 AI 味 / 低级衔接词；圈层黑话单独列）----------
# 通用违禁：所有文章都查（仅 AI 腔 / 低级衔接词，不查营销词以免误伤正常表达）
FORBIDDEN = [
    '首先','其次','此外','总之','另外说','再说',
    '标志着','彰显','赋能','格局','见证了','不仅仅是','深入探讨','值得注意的是',
    '综上所述','令人叹为观止','独特的魅力','在这个.*时代',
    '天花板','顶级','重新定义','史上最','绝绝子',
]
# 瑞士圈层黑话（仅瑞士主题额外查，避免误伤其它主题的表达）
SWISS_FORBID = ['申瑞士','申瑞','起算','HS27','倒推','两套路','颗粒度','锚点']
# 施工标记黑名单（2026-10-27 新增：内部/大纲说法混进正文=FAIL，源自实战复盘）
WORKMARK = ['一节讲完','存疑属性','成稿前核实','推论口径','待核实','待确认','待补齐','都点到了','后面细说','后面说','后面讲','分开算','只有一件','就一段','一条顺的',
            '占位','本篇大纲','写作建议','（推论','（待','（内部']
# 标题专用违禁（压缩词/圈层黑话/AI腔，标题一律清零）
TITLE_FORBID = [
    '申瑞士','申瑞','起算','上岸','踩坑','HS27','倒推','两套路','首先','其次',
    '此外','综上所述','值得注意的是','标志着','彰显','赋能','格局','见证了',
    '深入探讨','令人叹为观止','独特的魅力',
    '半价窟','空窗期','全场景','回池',
]
# 黑话/官方词/超长专名黑名单（2026-10-27 新增，源自实战复盘：
# 白话判据＝这句话放饭桌上真有人这么讲吗；超长专名一律用简称）
# 注：只收「发明式黑话/圈层自造词」，不收日常口语常用词（如 口径/入场券），
# 否则通用稿会被误杀；与闸门规则「口径四件套」概念冲突的词一律不进此表。
JARGON = ['退票回池','半价窟','空窗期','全场景','合资质','漏口','冬季限定',
          '把两样东西放进同一条沟','俄罗斯民族文化旅游区','三兄弟','氛围感拉满','站机位','一张牌','动线','加分项','这条线也硬']
# 前言 AI 元叙述句式（2026-10-27 新增：同批多篇"这篇文章就讲/这篇一处一处说"批量产出=FAIL）
# 仅收「AI 批量产出指纹」（非正常口语会出现的句式）；常见序列词（一样一样/一步一步/
# 先说一句/接着是/最后是）在日常游记里高频合法出现，移除以免误杀通用稿。
# 「先说」×2 的模板罗列仍由 ai_meta_hits 专查（L280），此处不重复卡。
AI_META = ['这篇文章就', '这篇一处', '这篇就按', '这篇文章，就', '给你摆开', '按值得去的顺序', '钱上的事说完了', '要交代的还有几件', '挨个给你捋', '一条线就顺了', '画风一转', '三档摆在一起', '还要知道几件事']
# 废话衔接/硬切句黑名单（2026-10-28 新增，源自批量复盘：为衔接而衔接的总结式·预告式·公式式句子，出现即删）
FILLER_PHRASES = ['穿衣公式照抄', '公式照抄', '账算到这里', '一条条说清', '下面一条条',
                  '串在这条线上', '这三头都看明白', '刚好补上']
# 模糊路线指引黑名单（2026-10-28 新增：路线方位必须量化，绕一点→开约一小时）
FUZZY_ROUTE = ['绕一点']
# 小标题自问自答检测（2026-10-27 新增：答案词黑名单，源自实战复盘）
SUBTITLE_ANSWER = ['头牌', '独一份', '才有的', '收个尾', '底气', '看得更透', '正确打开',
                   '一处一处', '说清楚', '照着走', '都在等', '把这三', '两件小事']
# 标题组内重复检查的停用词（双字功能词；主题词单独剔除）
TITLE_STOP_WORDS = ['冬天', '冬季', '夏天', '到底', '真的', '什么', '怎么', '多少', '哪些',
                    '哪里', '值得', '适合', '合适', '更好', '时机', '出发', '时间', '地方',
                    '玩法', '行程', '假期', '一样']
TITLE_STOP_CHARS = set('的了吗呢啊吧呀是在去能才都更最还和与把被有一不玩看说走天里得你我他这那就也太很挺会要想该别没从上下中前后左右个条座晚月日年块了又再先')

# ---------- 解析 ----------
def parse_articles(text: str):
    lines = text.splitlines()
    # 一级标题行作为每篇分隔
    heads = [(i, ln[1:].strip()) for i, ln in enumerate(lines) if re.match(r'^#\s+\S', ln)]
    if not heads:
        return [{'name': '未命名文章', 'titles': [], 'title_nums': [], 'n_title_block': 0,
                 'seo': '', 'body': text, 'raw': text}]
    arts = []
    for k, (i, head) in enumerate(heads):
        start = i + 1
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        block = '\n'.join(lines[start:end])
        # 标题块（逐行提取，避免贪婪正则吞掉正文）
        lines_block = block.splitlines()
        titles = []
        title_nums = []
        n_expected = 0
        title_line_idx = -1
        bi = 0
        for li, ln in enumerate(lines_block):
            m = re.match(r'\*{0,2}\s*标题\s*[（(]\s*(\d+)\s*[）)]\s*\**\s*[:：]?\s*\**\s*$', ln.strip())
            if m:
                title_line_idx = li
                n_expected = int(m.group(1))
                bi = li + 1
                while bi < len(lines_block) and not lines_block[bi].strip():
                    bi += 1
                while bi < len(lines_block):
                    s = lines_block[bi].strip()
                    if ('SEO' in s) or ('词组' in s) or s.startswith('**') or ('。' in s):
                        break
                    mm = re.match(r'(?:(\d+)[.、]\s*)?(.+)$', s)
                    if mm:
                        titles.append(mm.group(2).strip())
                        title_nums.append(int(mm.group(1)) if mm.group(1) else 0)
                    bi += 1
                    if len(titles) >= n_expected:
                        break
                break
        if title_line_idx >= 0:
            block = '\n'.join(lines_block[:title_line_idx] + lines_block[bi:])
        seo = ''
        sm = re.search(r'\*{0,2}\s*SEO\s*词组[^\n]*?[：:]\s*(.+)', block)
        if sm:
            seo = sm.group(1).strip()
        body = block
        if sm:
            body = body.replace(sm.group(0), '\n')
        arts.append({'name': head, 'titles': titles, 'title_nums': title_nums, 'n_title_block': n_expected,
                     'seo': seo, 'body': body, 'raw': '\n'.join(lines[i:end])})
    return arts

def count_bold_headings(body: str):
    bold = re.findall(r'(?m)^\s*\*\*.+?\*\*\s*$', body)
    lines = body.splitlines()
    candidates = []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        if re.match(r'^\*\*.+\*\*$', s):
            continue
        if len(s) <= 1 or len(s) > 22:
            continue
        if s[-1] in '，。；：:、':
            continue
        if '。' in s:
            continue
        if s.startswith('*') or s == '---':
            continue
        if re.match(r'^(你|一|二|三|四|五|六|第|\d)', s):
            continue
        candidates.append(s)
    return bold, candidates

def para_metrics(body: str):
    """段落三查（2026-10-27 收紧，源自实战复盘"该分段没分段/标点乱用"批量挑刺）：
    ① 段落上限 200→120 中文字（一段只装1-2个维度，禁文字墙）；
    ② 分号≥2/段 = FAIL（分号串不同维度＝该拆句拆段），1个 = 提醒；
    ③ 单段句号≥5 = 提醒（句号太多像流水账）。"""
    paras = [p for p in re.split(r'\n\s*\n', body) if p.strip()]
    over = []
    semi_fail = []
    semi_warn = []
    period_heavy = []
    for idx, p in enumerate(paras):
        n = cn_len(p)
        if n > 120:
            over.append((idx + 1, n))
        sc = p.count('；') + p.count(';')
        if sc >= 2:
            semi_fail.append((idx + 1, sc))
        elif sc == 1:
            semi_warn.append(idx + 1)
        pn = p.count('。')
        if pn >= 5:
            period_heavy.append((idx + 1, pn))
    return over, semi_fail, semi_warn, period_heavy, len(paras)

def pronoun_density(body: str):
    """人称「你」密度提醒（2026-10-26 新增，源自作者复盘：人称要用在需要的地方，
    堆多了反而假）。提醒级：单段「你」≥2 视为堆人称嫌疑。"""
    paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    hits = []
    for idx, p in enumerate(paras, 1):
        n = p.count('你')
        if n >= 2:
            hits.append((idx, n))
    return hits

def bracket_check(body: str):
    """括号检查（2026-10-27，源自标点专题复盘）：全文括号≤3且只装硬注释；
    "X（即Y）"式自我定义单独 FAIL。"""
    full = re.findall(r'（[^（）]*）', body)
    half = re.findall(r'\([^()]*\)', body)
    selfdef = re.findall(r'（即[^（）]{0,20}）|（也就是[^（）]{0,20}）', body)
    return len(full) + len(half), selfdef

def numspace_hits(body: str):
    """数字与汉字之间的空格（2026-10-27，作者定稿规范：数字前后不加空格，如"36到66人"）"""
    return re.findall(r'[\u4e00-\u9fff] +\d|\d +[\u4e00-\u9fff]', body)

def ppt_runs(body: str):
    """PPT气口段（2026-10-27，源自标点专题复盘：连续≥3个≤10字短句各带句号=机器节奏，提醒级）"""
    paras = [p for p in re.split(r'\n\s*\n', body) if p.strip()]
    hits = []
    for idx, p in enumerate(paras, 1):
        sents = [s.strip() for s in re.split(r'[。；！？]', p) if s.strip()]
        run = best = 0
        for s in sents:
            if cn_len(s) <= 10 and not s.startswith('**') and not s.startswith('#'):
                run += 1
                best = max(best, run)
            else:
                run = 0
        if best >= 3:
            hits.append((idx, best))
    return hits

def subtitle_echo(body: str):
    """子标签正文复读检测（2026-10-26 新增，源自跨环境复盘「模块孤立生成」病根）：
    加粗小标签的文字原样出现在紧跟正文段的首句开头（标签复读式凑字）→ FAIL 级。
    例：标签「手套帽面罩」紧跟段以「手套帽面罩：触屏手套…」开头，或正文首句以标签名开头。
    返回 [(标签, 复读句片段), ...]"""
    lines = body.splitlines()
    hits = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.match(r'^\*\*(.+?)\*\*$', s)
        if m:
            label = re.sub(r'[\s，。：:、？?！!]', '', m.group(1))
            if len(label) >= 3:
                # 找标签后第一个非空正文段
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    nxt = re.sub(r'\s+', '', lines[j].strip())
                    nxt = re.sub(r'^[\*#]+', '', nxt)
                    nxt_clean = re.sub(r'[\s，。：:、？?！!]', '', nxt)
                    if nxt_clean.startswith(label):
                        hits.append((m.group(1), lines[j].strip()[:30]))
        i += 1
    return hits

def subtitle_selfanswer(body: str):
    """小标题自问自答检测（2026-10-27 新增，源自实战复盘）：
    加粗小标题禁——①冒号（"一张净账：五天七天十天"冒号+答案式）；②答案词
    （"冬天的头牌/全国独一份/冬天的底气"这类把结论剧透进标题）；③多问并列
    （"怎么串、注意什么、花多少"三问连排）。小标题只准写纯维度名。"""
    hits = []
    for m in re.finditer(r'(?m)^\s*\*\*(.+?)\*\*\s*$', body):
        t = m.group(1).strip()
        if len(t) > 30:
            continue
        if '：' in t or ':' in t:
            hits.append(('冒号式', t))
            continue
        for w in SUBTITLE_ANSWER:
            if w in t:
                hits.append(('答案词:' + w, t))
                break
        if t.count('怎么') >= 2:
            hits.append(('多问并列(三个及以上并列问)', t))
        qw = [w for w in ('哪','吗','几') if w in t]
        if qw and not t.startswith('怎么'):
            hits.append(('疑问词式(问句小标题=自问自答变体):' + '/'.join(qw), t))
        if '这一侧' in t:
            hits.append(('方位词式(读者不知指什么)', t))
        if len(re.findall(r'[和与、]', t)) >= 2:
            hits.append(('罗列式(小标题应是维度不是清单)', t))
    return hits

def ai_meta_hits(body: str):
    """前言元叙述句式（2026-10-27 新增）："这篇文章就讲…"是 AI 批量产出指纹。
    2026-10-27 第六轮补：同词复现检测——"先说"一篇出现>=2次=模板式批量产出（FAIL）。"""
    hits = [w for w in AI_META if w in body]
    n = body.count('先说')
    if n >= 2:
        hits.append(f'先说×{n}(同词复现=模板罗列)')
    # 序号混用检测（2026-10-27 第七轮：头一样→还有一样→第二样=三套序号混在一起）
    if ('头一样' in body or '第二样' in body or '第三样' in body) and '还有一样' in body:
        hits.append('序号混用(头一样/还有一样/第二样不是一套序号)')
    return hits

def title_gram_repeat(titles, theme):
    """标题组内实词 2-gram 重复检测（2026-10-27 新增，铁律"组内不共用卖点"的机检化，
    源自实战复盘：两条标题都落在同一景点/价格词上＝重复）。
    返回 {重复2-gram: [出现在哪几条标题]}。"""
    from collections import defaultdict
    owner = {}
    dup = defaultdict(set)
    for idx, t in enumerate(titles, 1):
        s = re.sub(r'[（(].*?[)）]', '', t)
        s = re.sub(r'[\s，。、；：:？?！!（）()【】""\'\'《》.,;:!?—·]', '', s)
        if theme:
            s = s.replace(theme, ' ')
        for w in TITLE_STOP_WORDS:
            s = s.replace(w, ' ')
        s = ''.join(ch if ch not in TITLE_STOP_CHARS else ' ' for ch in s)
        grams = set()
        for frag in s.split():
            if len(frag) >= 2:
                for i in range(len(frag) - 1):
                    grams.add(frag[i:i + 2])
        for g in grams:
            if g in owner and owner[g] != idx:
                dup[g].add(owner[g])
                dup[g].add(idx)
            elif g not in owner:
                owner[g] = idx
    return {g: sorted(v) for g, v in dup.items()}

def para_prefix_repeats(body: str):
    """段首4字开头重复检测（句式模板腔提醒，如两段都以「有人冲着」开头）"""
    from collections import Counter
    paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    c = Counter()
    ex = {}
    for p in paras:
        s = re.sub(r'\s+', '', p.split('\n', 1)[0])
        if not s or s.startswith('**') or s.startswith('#'):
            continue
        if re.match(r'^(你|我|[一二三四五六七八九十]，|一是|二是|三是|第一|第二|第三|\d)', s):
            continue
        if len(s) < 4:
            continue
        pre = s[:4]
        c[pre] += 1
        ex.setdefault(pre, s[:14])
    return {k: (v, ex[k]) for k, v in c.items() if v >= 2}

def title_checks(titles, swiss, theme, n_expected):
    """返回 (results, q_total, shoutui_count, has_block)"""
    if not titles:
        return [], 0, 0, False
    res = []
    q_total = 0
    shoutui_count = 0
    for i, t in enumerate(titles, 1):
        s = strip_punct(t)
        L = cn_len(s)
        is_shoutui = ('首推' in t)
        if is_shoutui:
            shoutui_count += 1
        has_theme = (theme is None) or (theme in t)
        has_colon = ('：' in t) or (':' in t)
        has_me = ('我' in t)
        has_year = bool(re.search(r'20\d\d', t))
        has_fulldate = bool(re.search(r'\d{1,2}月\d{1,2}日', t))
        q = t.count('？') + t.count('?')
        q_total += 1 if q > 0 else 0
        tf = any(re.search(w, t) for w in TITLE_FORBID)
        if is_shoutui:
            # 首推：允许爆款陈述钩子 + 冒号；仍卡 字数/零我/零年/零日期/≤1问号/零黑话/含主题词
            ok = (15 <= L <= 25) and (not has_me) and (not has_year) \
                 and (not has_fulldate) and (q <= 1) and (not tf) and has_theme
        else:
            # 其余：必须为强场景问句（q>=1）+ 零冒号 + 含主题词
            ok = (15 <= L <= 25) and (not has_colon) and (not has_me) \
                 and (not has_year) and (not has_fulldate) and (q >= 1) and (q <= 1) \
                 and (not tf) and has_theme
        res.append({
            'no': i, 'title': t, 'cn_len': L, 'len_ok': 15 <= L <= 25,
            'theme': has_theme, 'colon': has_colon, 'me': has_me, 'tf': tf,
            'year': has_year, 'fulldate': has_fulldate, 'q': q, 'ok': ok,
            'shoutui': is_shoutui
        })
    return res, q_total, shoutui_count, True

def seo_checks(seo: str):
    # L 含标点：SEO 字数 111-119 以「含标点字符数」计（2026-10-27 作者定稿口径）
    L = len(re.sub(r'\s', '', seo))
    pure = re.sub(r'[\s，。、；：:？?！!（）()【】""\'\'《》.,;:!?]', '', seo)
    grams = [pure[i:i+2] for i in range(len(pure)-1)]
    from collections import Counter
    c = Counter(grams)
    # 收紧：任何 2-gram 出现≥2次（第二次即重复）＝FAIL（作者 2026-10-27 定）
    repeat = {g: n for g, n in c.items() if n > 1 and CN.match(g[0]) and CN.match(g[1])}
    return L, repeat

def cross_article(body1, body2):
    def frags(b):
        out = set()
        for s in split_sentences(b):
            clean = re.sub(r'[\s，。、；：:？?！!（）()【】""\'\'《》.,;:!?]', '', s)
            if cn_len(clean) >= 8:
                out.add(clean)
        return out
    a, b = frags(body1), frags(body2)
    common = sorted(a & b, key=len, reverse=True)
    return common[:20]

def forbidden_hits(body: str, extra=None):
    hits = {}
    words = FORBIDDEN + (extra or [])
    for w in words:
        n = len(re.findall(w, body))
        if n:
            hits[w] = n
    return hits

def body_word_count(raw: str):
    total = 0
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith('**'):
            continue
        total += cn_len(s)
    return total

# 目的地标签（用于主题自动识别；显式 --theme 优先）
DESTINATIONS = ['瑞士', '新疆', '国内', '欧洲', '川西', '青甘', '甘青', '西北', '青藏', '西藏',
                '青海', '甘肃', '宁夏', '内蒙', '内蒙古', '云南', '东北', '海南', '东南亚']

def detect_theme(arts, force_swiss, force_theme):
    all_titles = [t for a in arts for t in a['titles']]
    blob = ' '.join(all_titles + [a['name'] for a in arts])
    if force_theme:
        theme = force_theme
    else:
        hit = [d for d in DESTINATIONS if d in blob]
        theme = hit[0] if hit else None
    # 瑞士专项只在主题=瑞士时触发（--swiss 可强制）。
    # 不用「正文出现瑞士二字」判定：欧洲/国内等主题的文章也会提到瑞士，
    # 若据此误触发年份=0/月份锚点专项，会把合法带年份的稿子判死。
    swiss = force_swiss or (theme == '瑞士')
    return swiss, theme

# ---------- 主流程 ----------
def qa_article(art, idx, others, swiss, theme, minlen, maxlen, minbold):
    name = art['name']
    print(f"\n{'='*60}\n【{name}】\n{'='*60}")
    fails = 0
    def chk(label, cond, detail=''):
        nonlocal fails
        mark = 'PASS' if cond else 'FAIL'
        if not cond:
            fails += 1
        print(f"  [{mark}] {label}" + (f"  -> {detail}" if detail else ''))

    titles = art['titles']
    n_block = art['n_title_block']
    seo = art['seo']
    body = art['body']

    # 1) 标题结构（有「标题（N）」块才校验）
    if n_block > 0:
        chk(f"标题数={n_block}（实得 {len(titles)}）", len(titles) == n_block, str(len(titles)))
        tc, q_total, shoutui_count, _ = title_checks(titles, swiss, theme, n_block)
        for r in tc:
            tag = " [首推:允许陈述+冒号]" if r['shoutui'] else " [须为问句+零冒号]"
            extra = f" 主题词={r['theme']}" if theme else ""
            chk(f"标题{r['no']} 字数15-25/零我/零日期/≤1问号/零黑话{tag}", r['ok'],
                 f"len={r['cn_len']} 主题={r['theme']} 冒号={r['colon']} 我={r['me']} 黑话={r['tf']} 年={r['year']} 全日期={r['fulldate']} 问={r['q']} | {r['title']}")
        chk("标题行独占且编号连续1-6（防撞行/截断/合并）", art['title_nums'] == list(range(1, len(titles) + 1)), str(art['title_nums']))
        chk(f"首推标题数=1（实得 {shoutui_count}）", shoutui_count == 1, str(shoutui_count))
        chk(f"标题问句数（首推可陈述，其余须问句，上限6/篇）（问句 {q_total}/6）", q_total <= 6, str(q_total))
        dup = title_gram_repeat(titles, theme)
        chk("标题组内实词不重复（禁共用卖点/细节词复读）", len(dup) == 0, str(dup) if dup else '无')
    else:
        print("  [跳过] 未检测到「标题（N）」结构，跳过标题/首推专项检查（正文通用层照常）")

    # 2) SEO（有才校验）
    if seo:
        seoL, seoRep = seo_checks(seo)
        chk(f"SEO 字数 111-119（含标点，实得 {seoL}）", 111 <= seoL <= 119, str(seoL))
        chk("SEO 2-gram 零重复（出现≥2次即FAIL）", len(seoRep) == 0, str(seoRep) if seoRep else '无')
    else:
        print("  [跳过] 未检测到 SEO 词组，跳过 SEO 检查")

    # 3) 加粗小标题（有才校验）
    bold, cand = count_bold_headings(body)
    if bold:
        chk(f"小标题加粗计数（检测到 {len(bold)} 个整行**）", len(bold) >= minbold, str(len(bold)))
        if cand:
            print(f"        [提醒] 疑似未加粗小标题候选：{cand[:8]}")
    else:
        print("  [跳过] 未检测到整行 ** 小标题，跳过加粗计数")

    # 4) 段落长度 / 分号 / 句号密度（2026-10-27 收紧）
    over, semi_f, semi_w, ph, np = para_metrics(body)
    chk("段落≤120中文字（一段1-2个维度，禁文字墙）", len(over) == 0, str(over) if over else '无')
    chk("分号<2/段（分号串不同维度＝该拆句拆段）", len(semi_f) == 0, str(semi_f) if semi_f else '无')
    if semi_w:
        print(f"        [提醒] 含1个分号的段落（确认是逻辑连续才保留）：{semi_w}")
    if ph:
        print(f"        [提醒] 单段句号≥5（句号太密像流水账，确认每句各占一个维度）：{ph}")
    echo = subtitle_echo(body)
    chk("子标签不正文复读（标签名不得原样出现在紧跟段首句）", len(echo) == 0,
        str(echo) if echo else '无')
    pref = para_prefix_repeats(body)
    for k, (n, sample) in pref.items():
        print(f"        [提醒] 段首「{k}…」重复{n}次（句式模板腔，建议改写其一），如：{sample}…")
    pron = pronoun_density(body)
    if pron:
        print(f"        [提醒] 单段「你」≥2 的人称堆砌嫌疑段落（段号,个数）：{pron}（人称要用在需要的地方）")

    # 5) 违禁词（通用 + 瑞士专属）
    extra = SWISS_FORBID if swiss else None
    fh = forbidden_hits(body, extra)
    chk("违禁词清零（含绝对化词）", len(fh) == 0, str(fh) if fh else '无')

    # 5b) 施工标记黑名单（2026-10-27：内部/大纲说法混进正文=FAIL）
    wm = [w for w in WORKMARK if w in body]
    chk("无内部施工标记/大纲腔混进正文", len(wm) == 0, str(wm) if wm else '无')

    # 5b2) 黑话/官方词/超长专名（2026-10-27 新增）
    jg = [w for w in JARGON if w in body]
    chk("黑话/官方词清零（白话判据：饭桌上有人这么讲）", len(jg) == 0, str(jg) if jg else '无')

    # 5b3) 前言AI元叙述句式（2026-10-27 新增）
    am = ai_meta_hits(body)
    chk("无“这篇文章就讲/这篇一处一处说”式元叙述", len(am) == 0, str(am) if am else '无')

    # 5b3b) 废话衔接/硬切句 + 模糊路线指引（2026-10-28 新增，第十轮复盘沉淀）
    fl = [w for w in FILLER_PHRASES if w in body]
    chk("废话衔接/硬切句清零（总结式·预告式·公式式，出现即删）", len(fl) == 0, str(fl) if fl else '无')
    fz = [w for w in FUZZY_ROUTE if w in body]
    chk("模糊路线指引清零（绕一点→写具体车程/距离）", len(fz) == 0, str(fz) if fz else '无')

    # 5b4) 小标题自问自答（2026-10-27 新增）
    sa = subtitle_selfanswer(body)
    chk("小标题不自问自答（禁冒号/答案词/多问并列）", len(sa) == 0, str(sa) if sa else '无')

    # 5b5) 时效与口径（2026-10-27 第二轮：月份必带年份/预计惯例禁并列/人称跳提醒）
    bad_month = [mm.group(0) for mm in re.finditer(r'(?<![0-9年])(1[0-2]|[1-9])月起', body)]
    chk("月份表述必带年份（“11月起”→“2026年11月起”）", len(bad_month) == 0, str(bad_month) if bad_month else '无')
    mixed = [s.strip()[:60] for s in re.split(r'[。！？\n]', body) if '预计' in s and ('惯例' in s or '历年' in s)]
    chk("“预计”与“历年惯例”禁并列（须落“以当期公告为准”）", len(mixed) == 0, str(mixed) if mixed else '无')
    if '你如果' in body:
        print("        [提醒] 正文出现“你如果”，检查前面是否有人称铺垫（人称跳）")

    # 5c) 括号（标点专题：全文≤3且只装硬注释；"X（即Y）"自我定义禁）
    bn, sd = bracket_check(body)
    chk("括号≤3处（只装硬注释）", bn <= 3, f"{bn}处")
    chk("无“X（即Y）”式自我定义", len(sd) == 0, str(sd) if sd else '无')

    # 5d) 数字与汉字之间无空格（定稿口径：36到66人，不加空格）
    ns = numspace_hits(body)
    chk("数字与汉字之间无空格", len(ns) == 0, str(ns[:6]) if ns else '无')

    # 5e) PPT气口段（提醒级：连续≥3个≤10字短句号成段）
    pr = ppt_runs(body)
    if pr:
        print(f"        [提醒] 连续≥3个≤10字短句号成段（PPT气口，建议逗号连逻辑）：段号/连击数 {pr}")

    # 6) 跨篇逐字复读
    for j, o in enumerate(others, 1):
        common = cross_article(body, o['body'])
        common = [c for c in common if cn_len(c) >= 8]
        if common:
            print(f"        [FAIL] 与篇{j} 逐字复读≥8字：{common[:5]}")
            fails += 1
        else:
            print(f"  [PASS] 与篇{j} 逐字复读≥8字：空")

    # 7) 瑞士专项（仅 swiss 模式）
    # 年份=0 / 月份锚点 / ESOP双数 为「申请时间线 / 每年通用版」篇专属（篇1），
    # 其余瑞士文章（选校、签证等）合法含年份（2027 QS / 2025 学费等已核实事实），不卡此专项。
    is_general = ('时间线' in name) or ('ESOP' in body)
    if swiss and is_general:
        yrs = len(re.findall(r'20\d\d', body))
        chk("年份(20xx)=0", yrs == 0, str(yrs))
        anchors = ['11月1日','11月30日','3月31日','4月30日','2月28日','12月15日']
        miss = [a for a in anchors if a not in body]
        chk("月份锚点全在", len(miss) == 0, f"缺：{miss}" if miss else '全在')
        if 'ESOP' in body:
            has13 = ('13,500' in body) or ('13500' in body)
            has12 = ('12,000' in body) or ('12000' in body)
            chk("ESOP 双数（12,000 与 13,500 都标）", has13 and has12, f"13.5k={has13} 12k={has12}")

    # 8) 破折号密度（千字）
    em = body.count('——')
    per_k = em / max(1, cn_len(body)/1000)
    chk("破折号密度<2/千字", per_k < 2, f"{em}处 / {per_k:.2f}千字")

    # 9) 字数（仅显式传参才卡）
    if minlen is not None or maxlen is not None:
        wc = body_word_count(art['raw'])
        lo = minlen if minlen is not None else 0
        hi = maxlen if maxlen is not None else 10**9
        chk(f"正文纯中文字数 {lo}-{hi}（不含**行/SEO行，含标题列）", lo <= wc <= hi, str(wc))
    else:
        wc = body_word_count(art['raw'])
        print(f"  [跳过] 字数未设 --minlen/--maxlen，仅统计不卡：正文纯中文约 {wc} 字")

    print(f"  -> 本篇 FAIL 累计：{fails}")
    return fails

def main():
    if len(sys.argv) < 2:
        print("用法：python article_qa.py <文章文件.md> --theme 词 [--swiss] [--minlen N] [--maxlen N] [--minbold N] [-o 报告.txt]")
        print("      --theme 必填：目的地标签（瑞士/新疆/欧洲/国内/川西青甘西北西藏等），无主题词=拒绝核验")
        sys.exit(1)
    path = sys.argv[1]
    out = None
    force_swiss = '--swiss' in sys.argv
    force_theme = None
    minlen = maxlen = None
    minbold = 3  # 通用短文默认3；瑞士长文/深度攻略运行时传 --minbold 8
    if '-o' in sys.argv:
        out = sys.argv[sys.argv.index('-o')+1]
    if '--theme' in sys.argv:
        force_theme = sys.argv[sys.argv.index('--theme')+1]
    if '--minlen' in sys.argv:
        minlen = int(sys.argv[sys.argv.index('--minlen')+1])
    if '--maxlen' in sys.argv:
        maxlen = int(sys.argv[sys.argv.index('--maxlen')+1])
    if '--minbold' in sys.argv:
        minbold = int(sys.argv[sys.argv.index('--minbold')+1])
    try:
        with io.open(path, encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        print(f"读取失败：{e}")
        sys.exit(1)

    arts = parse_articles(text)
    if not arts:
        print("未解析到任何文章区块，请检查格式（需含 # 一级标题 作为每篇分隔）。")
        sys.exit(1)
    # 多篇多主题：--theme 西藏|川西|呼伦贝尔|青甘 → 按篇名/标题自动匹配各篇主题词
    per_themes = force_theme.split('|') if force_theme and '|' in force_theme else None
    def pick_theme(art):
        if not per_themes:
            return force_theme
        blob = art['name'] + ' ' + ' '.join(art['titles'])
        for t in per_themes:
            if t in blob:
                return t
        return None
    first_theme = per_themes[0] if per_themes else force_theme
    swiss, theme = detect_theme(arts, force_swiss, first_theme)
    if theme is None and not per_themes:
        print("【错误】缴稿核验必须带主题词（目的地标签）。")
        print("      请在标题/篇名中包含目的地标签（如 新疆/瑞士/欧洲/川西青甘西北西藏/国内），")
        print("      或运行脚本时显式指定：python article_qa.py 草稿.md --theme 新疆 [...]")
        print("      多篇多主题用 | 分隔：--theme 西藏|川西|呼伦贝尔|青甘")
        print("      无主题词的裸稿一律按未通过处理（exit 1）。")
        sys.exit(1)
    print(f"解析到 {len(arts)} 篇文章。主题模式：{'瑞士(swiss)' if swiss else '通用'}"
          + (f"（逐篇主题：{'|'.join(per_themes)}）" if per_themes else f"（主题词={theme}）"))

    old_stdout = sys.stdout
    buf = None
    if out:
        buf = io.StringIO()
        sys.stdout = buf

    total = 0
    for i, art in enumerate(arts):
        others = [a for k, a in enumerate(arts) if k != i]
        th = pick_theme(art)
        if th is None:
            print(f"\n【{art['name']}】\n{'='*60}")
            print(f"  [FAIL] 本篇标题/篇名中找不到 --theme 指定的任一主题词（{force_theme}）")
            total += 1
            continue
        total += qa_article(art, i, others, swiss and th == '瑞士', th, minlen, maxlen, minbold)

    print(f"\n{'#'*60}\n【总览】机械校验 FAIL 总数：{total}  （0 = 可进 LLM 裁判闸门）\n{'#'*60}")
    print(f"QA_RESULT: {'PASS' if total == 0 else 'FAIL ' + str(total)}")

    if out:
        sys.stdout = old_stdout
        with io.open(out, 'w', encoding='utf-8') as f:
            f.write(buf.getvalue())
        print(f"报告已写入：{out}（未落任何成稿文件）")

    sys.exit(1 if total > 0 else 0)

if __name__ == '__main__':
    main()
