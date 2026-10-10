#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_pool.py —— 选题池合并 / 排序 / 出 HTML（正式脚本，2026-10-08 进仓库）

用法：
    python build_pool.py <数据.json> [--out 输出路径] [--date 2026-10-08]

数据.json 结构：
    {
      "date": "2026-10-08",
      "sources": [
        {"id": "74Kvx59dkx", "name": "IT之家", "heat_kind": "评论数"},
        ...
      ],
      "items": [
        {"title": "...", "src": "74Kvx59dkx", "url": "...",
         "heat": 561, "track": "消费电子", "cat": "科技",
         "angles": ["...", "..."], "risk": "..."}
      ],
      "missing": [{"name": "某源", "reason": "网络不可达"}]
    }

排序规则（2026-10-08 用户明确，四维度，顺序不可换）：
    ⓪ AI : 科技 ≈ 1:1     —— 全池两类各占约一半；推荐区 AI 占 1/3~1/2；AI 每天至少 2 条
    ① 平台数量（主排序） —— N 源命中；单源统一沉底标「单源待核」
    ② 热度（次排序）     —— 同源数内微调，口径不可横向比较
    ③ 条数上限           —— 单源条目总共只写前 20 条；多源不限

去重规则（2026-10-08 用户明确）：
    **不在选题阶段剔除已做过的内容**，只标「可能做过」。判定靠 --done 传入的成品标题清单。
"""
import argparse
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ---------- 归一化：用于跨源判重 ----------
_NOISE = re.compile(r'[\s\u3000·、，,。．\.!！?？:：;；\-—–_“”"\'\'‘’()（）\[\]【】<>《》|/\\]')
CAT_MAP = {'AI': 'AI', '科技': '科技'}


def norm(s):
    """去掉噪声字符，用于跨源标题匹配。"""
    return _NOISE.sub('', (s or '')).lower()


def tokens(s):
    """抽取可比对的关键词集合（中文按 3-gram，英文按词）。"""
    n = norm(s)
    out = set()
    for seg in re.findall(r'[a-z0-9]{3,}', s.lower()):
        out.add(seg)
    zh = re.sub(r'[a-z0-9]+', '', s)
    for i in range(max(0, len(zh) - 2)):
        out.add(zh[i:i + 3])
    return out


def same_event(a, b):
    """两条是否同一事件（用于跨源合并）。关键词 Jaccard 达阈值即判同。"""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb)) >= 0.42


# 实体词：英文/数字代号（OpenAI、iPhone18、28天）+ 中文品牌词
_ENT_EN = re.compile(r'[a-z][a-z0-9]*(?:\s?[0-9]+(?:\.[0-9]+)?)*', re.I)
_BRANDS = {
    '小米', '华为', '苹果', '三星', '谷歌', 'openai', '字节', '腾讯', '阿里', '百度',
    '京东', 'meta', '微软', '特斯拉', '小鹏', '蔚来', '理想', '比亚迪', '大疆',
    'amd', 'nvidia', '英伟达', 'anthropic', 'claude', 'chatgpt', 'gemini',
    'deepseek', 'qwen', 'kimi', 'grok', 'mistral', '宇树', '智元', '库卡',
    '美团', '淘宝', '拼多多', '快手', '网易', '搜狐', 'spacex', 'manus',
}
_ENT_ZH = re.compile('|'.join(sorted(_BRANDS, key=len, reverse=True)))
_STOP_EN = {'the', 'a', 'an', 'of', 'in', 'on', 'and', 'or', 'to', 'for', 'is', 'are',
            'ai', 'with', 'by', 'at', 'from', 'be', 'it', 'this', 'that', 'new',
            'how', 'why', 'what', 'will', 'can', 'did', 'its'}


def ents(s):
    """抽实体词集合：英文词/型号代号 + 中文品牌词。用于判「是否做过同一件事」。

    ⚠️ **裸数字不是实体**（实测踩坑）：「英伟达逼近 6 万亿美元」会因为 `6`
    撞上 GPT-6，「苹果 10 月 13 日发布会」会因为 `10` 撞上周榜日期 —— 全是误报。
    **数字必须紧跟字母（型号/版本）才算实体**：iPhone18、gpt6、mate90、5.5、28天。
    """
    s = s or ''
    out = set()
    for m in _ENT_ZH.findall(s):
        out.add(m.lower())
    # 英文词 / 型号代号：字母开头、可含内部数字与点
    for m in re.findall(r'[A-Za-z][A-Za-z0-9]*(?:\.[0-9]+)?', s):
        t = m.lower().strip('.')
        if len(t) < 2 or t in _STOP_EN:
            continue
        out.add(t)
        # ⚠️ **必须补前缀形**（实测踩坑）：`gemini4` 与 `gemini`、`mate90` 与 `mate`、
        # `iphone18` 与 `iphone` 是同一实体的不同写法。不补前缀 → 撞题全漏判。
        pre = re.match(r'([a-z]+?)[0-9]', t)
        if pre and len(pre.group(1)) >= 3:
            out.add(pre.group(1))
    # 数字量词：数字后紧跟中文「天/岁/亿/万/倍/次」才算（28天、96岁），单独的数字不算
    for m in re.findall(r'[0-9]+(?:\.[0-9]+)?(?:天|岁|亿|万倍|倍|次|年|月)', s):
        out.add(m)
        out.add(re.sub(r'(?:天|岁|亿|万倍|倍|次|年|月)$', '', m))
    return out


# ---------- 读入 ----------
def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_done(paths):
    """读已成品标题，用于标「可能做过」。扫不到就返回空，绝不猜。

    ⚠️ **成品标题的真实位置**（2026-10-08 实测）：目录里**没有** `card.json`，
    标题在 `meta_<平台>.json` 的 `titles[].text` 里（多条，取最长的那条做比对）。
    只扫目录名会漏掉「同产品不同角度」的情况 —— 目录名是 `20261008_GPT6智能界面`，
    标题才是「GPT-6 上线：回答变成能点的界面」。两者都收。
    """
    done = []
    for root in paths:
        if not os.path.isdir(root):
            print(f"[warn] 成品目录不存在，跳过：{root}", file=sys.stderr)
            continue
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if not os.path.isdir(p):
                continue
            # 目录名本身也作为一条线索
            done.append((name, name))
            for fn in os.listdir(p):
                if not fn.startswith('meta_') or not fn.endswith('.json'):
                    continue
                try:
                    with open(os.path.join(p, fn), encoding='utf-8') as f:
                        m = json.load(f)
                except Exception:
                    continue
                cands = []
                if isinstance(m, dict):
                    for t in (m.get('titles') or []):
                        if isinstance(t, dict) and t.get('text'):
                            cands.append(t['text'])
                    if isinstance(m.get('title'), str):
                        cands.append(m['title'])
                elif isinstance(m, list):
                    for c in m:
                        if isinstance(c, dict) and c.get('title'):
                            cands.append(c['title'])
                if cands:
                    best = max(cands, key=len)
                    done.append((name, best))
    return done


# ---------- 合并 ----------
def merge(data):
    src_name = {s['id']: s['name'] for s in data.get('sources', [])}
    src_heat = {s['id']: s.get('heat_kind', '') for s in data.get('sources', [])}
    groups = []          # 每组 = 一个事件
    by_key = {}
    for it in data['items']:
        t = it['title']
        placed = False
        for g in groups:
            if same_event(g['title'], t):
                g['members'].append(it)
                placed = True
                break
        if not placed:
            groups.append({'title': t, 'members': [it]})
    # 汇总每组
    out = []
    for g in groups:
        ms = g['members']
        srcs = []
        for m in ms:
            if m['src'] not in srcs:
                srcs.append(m['src'])
        heats = [(m.get('heat'), m['src']) for m in ms if isinstance(m.get('heat'), (int, float))]
        best = max(heats)[0] if heats else None
        best_src = max(heats)[1] if heats else None
        head = ms[0]
        out.append({
            'title': head['title'],
            'cat': head.get('cat', '科技'),
            'track': head.get('track', '其他'),
            'url': head.get('url', ''),
            'srcs': srcs,
            'src_names': [src_name.get(s, s) for s in srcs],
            'n_src': len(srcs),
            'heat': best,
            'heat_src': src_name.get(best_src, best_src) if best_src else None,
            'heat_kind': src_heat.get(best_src, '') if best_src else '',
            'angles': head.get('angles', []),
            'risk': head.get('risk', ''),
        })
    return out


def sort_and_limit(items, single_cap=20):
    """四维度排序 + 单源上限截断。返回 (保留列表, 截掉数)。

    ⚠️ **单源上限必须在大类内部分配**（2026-10-08 实测踩坑）：
    热度值只有消费电子源给得出（威锋/IT之家/虎嗅），AI 条目多来自无热度字段的源
    （Readhub/极客公园/爱范儿），直接按热度取前 20 会把 AI 全部砍光 →
    同时违反「AI:科技 ≈ 1:1」。所以单源池按 AI / 科技各取一半，
    某类不足时另一类补齐并如实标注。
    """
    multi = [x for x in items if x['n_src'] >= 2]
    single = [x for x in items if x['n_src'] == 1]

    def key(x):
        #2026-10-09 实测踩坑：**只按热度排会选中小版本更新类条目**。
        #威锋 / IT之家 给了大量「iOS 27.0.1 修复若干错误」这种有热度值但没钩子的条目，
        # 热度 5377/4214 一律排在前面 → 真正有钩子的（尊界 V800 多方回应、诺奖、
        # AI 数学证明、AI 能力成本降数千倍）全被单源上限截掉。
        # 加「可做度」维度：**有条目角度的优先于纯信息条目**，热度降为同层内微调。
        h = x['heat'] if isinstance(x['heat'], (int, float)) else -1
        has_ang = 1 if x.get('angles') else 0
        # 同事件（done_kind=同事件）沉底：已做过一次的题再排前面没有增量价值，
        # 但「换角度」（仅品牌重合）是新方向，仍按正常序位。
        dup = 1 if x.get('done_kind') == '同事件' else 0
        return (-x['n_src'], -has_ang, dup, -h, x['title'])

    multi.sort(key=key)
    single.sort(key=key)

    si_ai = [x for x in single if x['cat'] == 'AI']
    si_tk = [x for x in single if x['cat'] == '科技']
    quota_ai = single_cap // 2
    quota_tk = single_cap - quota_ai

    keep_ai = si_ai[:quota_ai]
    keep_tk = si_tk[:quota_tk]
    # 某类不足，用另一类补齐
    short = single_cap - len(keep_ai) - len(keep_tk)
    if short > 0:
        pool = si_tk[quota_tk:] if len(keep_ai) >= quota_ai else si_ai[quota_ai:]
        keep_tk = keep_tk + pool[:short] if len(keep_ai) >= quota_ai else keep_ai + pool[:short]
    # ⓪ 类别配比要在**赛道配额之前**生效，否则 AI 类有10 条候选、赛道配额按 AI=1 组算，
    # 直接把 AI 类以外的全部名额吃光（2026-10-09 实测：改赛道配额后20 条仍全是苹果+AI）。
    # 正确顺序：① 先按赛道配额取候选 → ② 再按 ⓪ 类别配比与上限收口 → ③ 不足再回填。
    per_track = max(2, single_cap // 4)
    AI_SUB = [('AI模型', ('gpt', 'openai', 'anthropic', 'claude', 'gemini', 'deepseek',
                          'jev', '数学', 'aigc', '模型')),
              ('AI应用', ('agent', '机器人', '客服', '陪伴', '画', '视频', '搜索',
                          '办公', '自动', '智能体')),
              ('AI行业', ('融资', '估值', 'ipo', '裁员', '收费', '开放',
                          '监管', '政策', '上市', '收购'))]

    def sub_track(x):
        if x['track'] != 'AI':
            return x['track']
        t = (x['title'] or '').lower()
        for name, kws in AI_SUB:
            if any(k in t for k in kws):
                return 'AI/' + name
        return 'AI/其他'

    # ① 赛道配额是**主约束**，⓪ 类别配比是次约束（2026-10-09 反复返工后定稿）。
    #    踩过的坑：先按热度取前 20 再裁赛道 → 威锋 15 条苹果 + 10 条 AI 把有热度的名额吃满，
    #    基础科学 / 消费电子 / 智能汽车全被挤掉。改成**赛道轮转取**，任何一步都不替换已入选条目。
    pool_all = sorted(items, key=key)
    buckets = defaultdict(list)
    for x in pool_all:
        buckets[sub_track(x)].append(x)
    order = sorted(buckets, key=lambda t: (-len(buckets[t]), t))  # 条目多的赛道先走

    keep, taken = [], set()
    used = defaultdict(int)
    ai_left, tk_left = quota_ai, quota_tk

    def take(x):
        nonlocal ai_left, tk_left
        if x['cat'] == 'AI':
            ai_left -= 1
        else:
            tk_left -= 1
        used[sub_track(x)] += 1
        keep.append(x)
        taken.add(id(x))

    def budget_ok(x):
        return ai_left > 0 if x['cat'] == 'AI' else tk_left > 0

    # 轮转：每轮每个赛道最多取 1 条
    while len(keep) < single_cap:
        progressed = False
        for t in order:
            if len(keep) >= single_cap:
                break
            if used[t] >= per_track:
                continue
            nxt = next((x for x in buckets[t] if id(x) not in taken), None)
            if nxt is None or not budget_ok(nxt):
                continue          # 赛道名额让给别的赛道，不替换
            take(nxt)
            progressed = True
        if not progressed:
            break
    # 补位：赛道配额放宽到 per_track+2，仍守类别预算
    for t in order:
        if len(keep) >= single_cap:
            break
        for x in buckets[t]:
            if len(keep) >= single_cap:
                break
            if id(x) in taken or used[t] > per_track or not budget_ok(x):
                continue
            take(x)
    keep.sort(key=key)
    dropped = max(0, len(single) - len(keep))
    return multi + keep, dropped


def pick_recommends(items, n=5):
    """推荐区：AI 类占 1/3~1/2，至少 2 条 AI（不足则放宽到 1/3）。"""
    pool = sorted(items, key=lambda x: (-x['n_src'], -(x['heat'] or -1), x['title']))
    n = min(n, len(pool))
    if n == 0:
        return []
    ai_quota = max(2, round(n / 3))       # 1/3~1/2
    ai_quota = min(ai_quota, n)
    picked, rest = [], [x for x in pool]
    # 先按源数挑满 AI 配额
    for want in (ai_quota, max(2, n // 2)):
        picked = []
        for x in rest:
            if sum(1 for p in picked if p['cat'] == 'AI') >= want:
                break
            if x['cat'] == 'AI' and x not in picked:
                picked.append(x)
        if len(picked) >= want:
            break
    for x in rest:
        if len(picked) >= n:
            break
        if x not in picked:
            picked.append(x)
    picked = picked[:n]
    picked.sort(key=lambda x: (-x['n_src'], -(x['heat'] or -1), x['title']))
    return picked


def mark_done(items, done):
    """标「可能做过」，**不剔除**（2026-10-08 用户明确）。

    ⚠️ **不要用字符 n-gram 相似度做这件事**（实测全错）：
    「OpenAI 宣布 28 天计划」vs「OpenAI28天承诺」的 3-gram Jaccard 只有 0.25，
    而「OpenAI 文字水印」vs完全无关的标题也有 0.25 —— **阈值怎么调都不干净**。

    正确判据是**实体词重合**：产品名 / 数字代号 / 公司名。
    「OpenAI + 28」重合 = 同一件事；只有「OpenAI」重合 = 同一公司不同事件
    （标「换角度」更准，但不必然是撞题）。
    """
    if not done:
        return items
    ent_done = [(d, ents(t)) for d, t in done]
    for x in items:
        xe = ents(x['title'])
        if not xe:
            continue
        best = None   # (重合实体数, 是否含数字代号, 目录名)
        for d, de in ent_done:
            if not de:
                continue
            common = xe & de
            if not common:
                continue
            has_num = any(any(c.isdigit() for c in e) for e in common)
            score = len(common) + (2 if has_num else 0)
            if best is None or score > best[0]:
                best = (score, has_num, d, common)
        if best:
            score, has_num, d, common = best
            # 判定口径（2026-10-08 实测校准）：
            #   型号代号重合（如 gemini4 ↔ Gemini4Argon、mate90 ↔ 麒麟9050）= 同事件
            #   仅品牌/公司名重合（如 苹果、OpenAI、华为）= 同公司不同事件 → 标「换角度」
            #   代价：会多标一些「换角度」。**这是刻意选的偏保守方向** ——
            #   备注只是提示、不影响排序，多标几条让用户自己判断，比漏标成「没做过」安全。
            key_ent = [e for e in common
                       if any(ch.isdigit() for ch in e) or e in _BRANDS]
            if key_ent:
                x['done_flag'] = d
                x['done_kind'] = '同事件' if any(
                    any(ch.isdigit() for ch in e) for e in key_ent) else '换角度'
    return items


# ---------- 出 HTML ----------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Microsoft YaHei","PingFang SC",sans-serif;
background:#f5f6f8;color:#1f2328;line-height:1.75;padding:28px 20px 60px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:27px;font-weight:800;letter-spacing:-.4px}
.sub{color:#656d76;font-size:13px;margin:8px 0 22px}
.meta{background:#fff;border:1px solid #d8dee4;border-radius:10px;padding:16px 20px;margin-bottom:20px}
.meta table{width:100%;border-collapse:collapse;font-size:13px}
.meta td{padding:5px 0;vertical-align:top}
.meta td:first-child{color:#656d76;width:110px;white-space:nowrap}
.sec{font-size:16px;font-weight:700;margin:26px 0 12px;padding-left:9px;border-left:4px solid #1f6feb}
.picks{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
.card{background:#fff;border:1px solid #d8dee4;border-radius:10px;padding:14px 16px}
.card.p{background:#f0f6ff;border-color:#a9c9f5}
.ct{font-size:15px;font-weight:700;margin-bottom:7px;line-height:1.5}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px}
.tg{font-size:11px;padding:1px 7px;border-radius:20px;font-weight:600}
.tg.ai{background:#ddf4e4;color:#116329}
.tg.tk{background:#e8ecf0;color:#3d4450}
.tg.hit{background:#fff3cd;color:#7a5b00}
.tg.one{background:#f0f0f4;color:#6a737d}
.tg.done{background:#ffe0e0;color:#a12b2b}
.heat{font-size:12px;color:#656d76;margin-bottom:6px}
.ang{margin:0;padding-left:17px;font-size:13px;color:#3d4450}
.ang li{margin:2px 0}
.risk{font-size:12px;color:#8b6d1f;background:#fff8e6;border-left:3px solid #e3b341;
padding:5px 8px;border-radius:4px;margin-top:7px}
.src{font-size:11px;color:#8b949e;margin-top:7px}
.note{background:#fff;border:1px solid #d8dee4;border-left:4px solid #8250df;
border-radius:8px;padding:13px 17px;font-size:13px;color:#3d4450;margin-top:10px}
.note b{color:#1f2328}
.miss{font-size:13px;color:#656d76}
.miss li{margin:3px 0}
footer{margin-top:30px;font-size:11px;color:#8b949e;text-align:center}
"""


def esc(s):
    return html.escape(str(s), quote=True)


def card_html(x, is_pick=False):
    tags = []
    if x['cat'] == 'AI':
        tags.append('<span class="tg ai">AI</span>')
    else:
        tags.append('<span class="tg tk">科技</span>')
    tags.append(f'<span class="tg tk">{esc(x["track"])}</span>')
    if x['n_src'] >= 2:
        tags.append(f'<span class="tg hit">{x["n_src"]} 源命中</span>')
    else:
        tags.append('<span class="tg one">单源待核</span>')
    if x.get('done_flag'):
        kind = x.get('done_kind', '换角度')
        lbl = '可能做过' if kind == '同事件' else '可能做过·换角度'
        tags.append(f'<span class="tg done">{lbl}（{esc(x["done_flag"])}）</span>')

    title = esc(x['title'])
    hot = []
    if isinstance(x.get('heat'), (int, float)):
        k = x.get('heat_kind') or '数值'
        hot.append(f'{esc(str(x["heat"]))}（{esc(k)}·{esc(str(x["heat_src"]))}）')
    if x['n_src'] >= 2:
        hot.append(f'命中 {x["n_src"]} 源：' + '、'.join(x['src_names']))
    else:
        hot.append('仅 1 源，缺交叉验证')

    ang = ''
    if x['angles']:
        lis = ''.join(f'<li>{esc(a)}</li>' for a in x['angles'])
        ang = f'<ul class="ang">{lis}</ul>'
    risk = f'<div class="risk">{esc(x["risk"])}</div>' if x.get('risk') else ''
    src = f'<div class="src">来源：{esc(x["url"])}</div>' if x.get('url') else ''

    return (f'<div class="card{" p" if is_pick else ""}">'
            f'<div class="ct">{title}</div>'
            f'<div class="tags">{"".join(tags)}</div>'
            f'<div class="heat">{" · ".join(hot)}</div>'
            f'{ang}{risk}{src}</div>')


def build_html(data, items, dropped, done_list, out_path):
    picks = pick_recommends(items, 5)
    pickset = {id(p) for p in picks}
    cat_cnt = Counter(x['cat'] for x in items)
    trk_cnt = Counter(x['track'] for x in items)
    multi = sum(1 for x in items if x['n_src'] >= 2)
    single = len(items) - multi

    p_html = ''.join(card_html(x, True) for x in picks)
    a_html = ''.join(card_html(x, False) for x in items if id(x) not in pickset)

    miss = data.get('missing', [])
    miss_html = ''
    if miss:
        lis = ''.join(f'<li><b>{esc(m["name"])}</b>：{esc(m["reason"])}</li>' for m in miss)
        miss_html = f'<div class="miss"><b>本轮未采到的源</b><ul>{lis}</ul></div>'

    ai_pick = sum(1 for p in picks if p['cat'] == 'AI')
    src_stat = ' · '.join(
        f'{esc(k)} {v}' for k, v in sorted(Counter(
            s for x in items for s in x['src_names']).items(), key=lambda kv: -kv[1]))

    meta_rows = [
        ('采集源', f'{len(data.get("sources", []))} 个'),
        ('候选条目', f'{len(items)} 条（多源 {multi} / 单源 {single}'
                     + (f'，单源按上限截掉 {dropped} 条' if dropped else '') + '）'),
        ('AI : 科技', f'{cat_cnt.get("AI", 0)} : {cat_cnt.get("科技", 0)}'
                     f'（推荐区 AI {ai_pick}/{len(picks)}）'),
        ('赛道分布', ' · '.join(f'{esc(k)} {v}' for k, v in trk_cnt.most_common())),
        ('排序规则', '⓪ AI:科技≈1:1 → ① 平台数量 → ② 热度（同源数内）→ ③ 单源条目最多 20 条'),
        ('来源统计', src_stat),
    ]
    meta = '<table>' + ''.join(
        f'<tr><td>{esc(k)}</td><td>{v}</td></tr>' for k, v in meta_rows) + '</table>'

    note = (
        '<div class="note"><b>怎么读这份池子</b><br>'
        '· <b>标签</b>：<span class="tg ai">AI</span> / <span class="tg tk">科技</span> 是大类，'
        '后面是赛道；<span class="tg hit">N 源命中</span> 表示被 N 个不同来源报道，'
        '<span class="tg one">单源待核</span> 表示只有一家中文源报道、缺交叉验证。<br>'
        '· <b>热度</b>：只有部分源提供，且口径互不相通（站内值／评论数／阅读量），'
        '<b>不能横向比较</b>，只在命中源数相同时作次级参考。<br>'
        '· <b>可能做过</b>：与已有成品撞题或同产品不同角度。<b>只是提示，不影响排序</b>，'
        '做不做由你决定。<br>'
        '· <b>单源上限</b>：单源条目冗余度最高、最不适合直接做图文，已按热度截到前 20 条；'
        '多源条目是交叉验证过的优先阅读区，<b>不限条数</b>。</div>'
    )

    d = esc(data['date'])
    doc = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>今日 AI 科技选题池 {d}</title><style>{CSS}</style></head><body>'
           f'<div class="wrap"><h1>今日 AI 科技选题池 · {d}</h1>'
           f'<div class="sub">AI 与科技合并混排 · 不分区 · 抓取时点 GMT+8 当日</div>'
           f'<div class="meta">{meta}</div>{note}'
           f'<div class="sec">推荐做的 {len(picks)} 条</div><div class="picks">{p_html}</div>'
           f'<div class="sec">全部候选（按平台数量 → 热度排序）</div>'
           f'<div class="picks">{a_html}</div>'
           f'<div class="sec">采源说明</div>{miss_html}'
           f'<footer>由 article-to-social / build_pool.py 生成 · 只做选题，不含图文</footer>'
           f'</div></body></html>')

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(doc)
    return picks, ai_pick


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('--out', default=None)
    ap.add_argument('--date', default=None)
    ap.add_argument('--done-root', action='append', default=[],
                    help='成品目录，可多次传；用于标「可能做过」')
    ap.add_argument('--single-cap', type=int, default=20)
    ap.add_argument('--check', action='store_true', help='只做校验不改文件')
    a = ap.parse_args()

    data = load(a.data)
    if a.date:
        data['date'] = a.date
    items = merge(data)
    done = load_done(a.done_root)
    items = mark_done(items, done)
    items, dropped = sort_and_limit(items, a.single_cap)

    n_ai = sum(1 for x in items if x['cat'] == 'AI')
    n_tk = len(items) - n_ai
    print(f'RESULT 条目={len(items)} 多源={sum(1 for x in items if x["n_src"]>=2)} '
          f'单源={sum(1 for x in items if x["n_src"]==1)} 截掉={dropped}')
    print(f'RATIO  AI={n_ai} 科技={n_tk}  ({n_ai/max(1,len(items)):.0%} AI)')
    if n_ai < 2:
        print('WARN AI 条目不足 2 条 —— 需补抓 AI 源', file=sys.stderr)
    fl = [x for x in items if x.get('done_flag')]
    print(f'DONE  已标「可能做过」{len(fl)} 条')
    if fl:
        for x in fl[:10]:
            print(f'      · {x["title"][:44]}  ← {x["done_flag"]}')

    if a.check:
        return
    out = a.out or os.path.join(
        os.environ.get('TOPIC_DIR', r'C:\选题'),
        f'今日AI科技选题池_{data["date"]}.html')
    picks, ai_pick = build_html(data, items, dropped, done, out)
    print(f'PICK  推荐 {len(picks)} 条，其中 AI {ai_pick} 条 '
          f'({ai_pick/max(1,len(picks)):.0%})')
    print(f'OUT   {out}')


if __name__ == '__main__':
    main()
