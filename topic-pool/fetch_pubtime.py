#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fetch_pubtime.py —— 给池内每条外链取「发布时间」。

背景（2026-10-12）：选题池此前完全没有时间字段 —— tophub 节点页只给
标题与热度，HN 的 time 也没被带上。结果是「必抓更新」表里混进了很旧的
新闻，页面上也没法标出「这条到底多久了」。

⚠️ 为什么不能只用通用 meta：
   36氪是 SPA，<meta article:published_time> 写的是**页面渲染那一刻** ——
   同一时刻抓 4 条不同文章，取到的值完全相同（实测）。必须改用页内 JSON
   里的 publishTime（毫秒，每条不同）。所以**站点专用规则优先于通用规则**。

⚠️ AIbase（2026-10-12 二次修正，前一次判断错了）：
   池内 AIbase 条目全是「AI日报」页（`/zh/daily/<编号>`）。**这些是永久链接**，
   各家标题各不相同（实测 31235 / 31542 的 h1 完全不一样），不是同一个页面。
   但**日报页正文里的条目时间全部渲染成「今天」**（31235 是 9-21 那期，
   页内 10 条却都写 2026年10月12号 9:05–10:29）→ 页内时间不可信，不能用。
   ✅ 可靠来源是**日报列表页** `https://www.aibase.com/zh/daily`：每张卡是
   `href="/daily/<编号>"` → `2026年10月10号 16:00` → 标题，可直接配出
   「编号 → 该期真实日期」。实测 31235 = 9-21（距今 21 天）、31508 = 10-09。
   ⚠️ 这解释了用户最初的抱怨：「必抓」里混着很旧的新闻 —— 池内 16 条必抓里
   有 14 条唯一来源就是这些日报，最老的 21 天，而旧实现把它们的日期标成
   「未取到」→ 时间窗 fail-open → 全部留在表里。所以**必须按编号取真实日期**。

用法：python fetch_pubtime.py
输入：tophub_items.json + hn_items.json
输出：pubtime.json  {url: {"day": "2026-10-11", "iso": ..., "src": ...}}
缓存：_pubtime_cache.json（同一 URL 不重复抓；失败的不写缓存，下次重试）
      _aibase_dates.json（编号 → 日期，只增不减，跨天累积）
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
CST = timezone(timedelta(hours=8))          # 全部按北京时间展示

# ---- 站点专用规则（优先于通用规则）----
SITE_RULES = [
    ('36kr.com',   r'"publishTime"\s*:\s*(\d{10,13})',                 'epoch_ms'),
    ('qbitai.com', r'class="date"[^>]*>\s*(20\d{2}-\d{2}-\d{2})',      'date_only'),
    ('aibase.com', r'(20\d{2})年(\d{1,2})月(\d{1,2})号',                'cn_date'),
    ('ithome.com', r'"pubDate"\s*:\s*"([^"]+)"',                       'iso'),
]

# ---- 故意不取时间的站 ----
# ⚠️ 这里只放「页面级时间确实不可信、且没有可靠替代来源」的站。
#    AIbase 曾列在这里，2026-10-12 已改为走**日报列表页映射**取真实日期（见 AIBASE_*）。
NO_TIME_HOSTS = []

# ---- AIbase 日报：编号 → 日期（必须走列表页，不能用日报页正文时间）----
AIBASE_INDEX = 'https://www.aibase.com/zh/daily'
AIBASE_RE = re.compile(r'aibase\.com/(?:[a-z]{2}/)?daily/(\d+)')
# ⚠️ 列表页里的链接是**相对路径**（`href="/daily/31542"`），不能复用上面的带域名正则
AIBASE_IDX_RE = re.compile(r'href="(?:https?://[^"]*?)?/daily/(\d+)"')
AIBASE_DATES = {}          # {'31235': {'day','iso','epoch','src'}}

# ---- 通用兜底 ----
GENERIC = [
    (r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', 'iso'),
    (r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)',          'iso'),
    (r'"datePublished"\s*:\s*"([^"]+)"', 'iso'),
    (r'"dateCreated"\s*:\s*"([^"]+)"',   'iso'),
    (r'"pubDate"\s*:\s*"([^"]+)"',       'iso'),
    (r'<time[^>]+datetime=["\']([^"\']+)', 'iso'),
]


def fetch(url, tries=2):
    """抓页面主体。中文 URL 先编码（AI产品榜的链接带中文 query）。"""
    safe = ":/?&=#%[]@!$'()*,;+~"
    u = urllib.parse.quote(url, safe=safe)
    for _ in range(tries):
        try:
            req = urllib.request.Request(u, headers={
                'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})
            with urllib.request.urlopen(req, timeout=18) as r:
                raw = r.read(500000)
            return raw.decode('utf-8', 'ignore')
        except Exception:
            time.sleep(0.8)
    return None


def _mk(dt, src):
    dt = dt.astimezone(CST)
    return {'day': dt.strftime('%Y-%m-%d'), 'iso': dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'epoch': int(dt.timestamp()), 'src': src}


def parse_val(val, kind, now):
    """把命中的原文转成 datetime；无法解析或明显异常返回 None。"""
    try:
        if kind == 'epoch_ms':
            n = int(str(val))
            dt = datetime.fromtimestamp((n / 1000) if n > 1e11 else n, CST)
        elif kind == 'date_only':
            dt = datetime.strptime(val, '%Y-%m-%d').replace(tzinfo=CST)
        elif kind == 'cn_date':
            g = [int(x) for x in val]
            dt = datetime(g[0], g[1], g[2], tzinfo=CST)
        else:
            s = str(val).strip().replace('Z', '+00:00')
            s = re.sub(r'\.\d+', '', s)
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                dt = datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
    except Exception:
        return None
    # ---- 假阳性防护 ----
    dt = dt.astimezone(CST)
    if dt > now + timedelta(days=2):
        return None                      # 未来时间，多为页面里的促销/预告数据
    if dt < datetime(2024, 1, 1, tzinfo=CST):
        return None                      # 太旧，多半是正文里引用的历史日期
    if abs((now - dt).total_seconds()) < 180:
        return None                      # 与抓取时刻几乎同秒 → SPA 渲染时间
    return dt


def extract(url, html, now):
    low = url.lower()
    cand = []
    for key, pat, kind in SITE_RULES:
        if key in low:
            m = re.search(pat, html, re.I | re.S)
            if m:
                cand.append((m, kind, key))
            break                       # 站点规则命中即优先，不再看通用
    if not cand:
        for pat, kind in GENERIC:
            m = re.search(pat, html, re.I | re.S)
            if m:
                cand.append((m, kind, 'meta'))
                break
    for m, kind, src in cand:
        val = m.groups() if kind == 'cn_date' else m.group(1)
        dt = parse_val(val, kind, now)
        if dt:
            return _mk(dt, src)
    return None


def fetch_aibase_map():
    """抓 AIbase 日报**列表页**，配出「编号 → 该期真实日期」。

    结构（实测）：每张卡为 `<a href="/daily/31235">` …（约 1.5KB 内）
    `2026年9月21号 16:00` … `<h3>标题</h3>` —— href 在前、日期紧随其后，
    按出现顺序配对即可。返回新解出的 {id: meta}；一个都没解到返回 {}（不覆盖旧缓存）。
    """
    html = fetch(AIBASE_INDEX)
    if not html:
        return {}
    out = {}
    pos = [m for m in AIBASE_IDX_RE.finditer(html)]
    for m in pos:
        i = m.group(1)
        if i in out:
            continue
        # 日期紧跟在该 href 之后
        tail = html[m.end():m.end() + 2000]
        d = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})[号日]\s*(\d{1,2}):(\d{2})', tail)
        if not d:
            continue
        try:
            dt = datetime(int(d.group(1)), int(d.group(2)), int(d.group(3)),
                          int(d.group(4)), int(d.group(5)), tzinfo=CST)
        except Exception:
            continue
        if dt > NOW + timedelta(days=2) or dt < datetime(2024, 1, 1, tzinfo=CST):
            continue
        out[i] = _mk(dt, 'aibase_index')
    return out


def probe(item):
    url = item['url']
    low = url.lower()
    if low.startswith('https://github.com/'):
        return url, {'note': '榜单页无发布时间'}
    if any(h in low for h in NO_TIME_HOSTS):
        return url, {'note': '聚合页，时间不可信 → 不取'}
    # AIbase 日报：只认列表页映射出来的日期，**绝不用日报页正文时间**（那是「今天」）
    m = AIBASE_RE.search(low)
    if m:
        v = AIBASE_DATES.get(m.group(1))
        if v:
            return url, dict(v)
        return url, {'note': 'AIbase 日报：编号不在列表页映射内 → 未取到'}
    html = fetch(url)
    if html is None:
        return url, None
    got = extract(url, html, NOW)
    return url, got


NOW = datetime.now(CST)


def main():
    items = []
    p1 = os.path.join(HERE, 'tophub_items.json')
    if os.path.exists(p1):
        d = json.load(io.open(p1, encoding='utf-8'))
        items += (d['items'] if isinstance(d, dict) else d)
    p2 = os.path.join(HERE, 'hn_items.json')
    if os.path.exists(p2):
        items += json.load(io.open(p2, encoding='utf-8'))

    # ---- AIbase 日报：先读历史映射（只增不减），再抓列表页补新编号 ----
    ab_p = os.path.join(HERE, '_aibase_dates.json')
    if os.path.exists(ab_p):
        try:
            AIBASE_DATES.update(json.load(io.open(ab_p, encoding='utf-8')))
        except Exception:
            pass
    _ab_before = len(AIBASE_DATES)
    _ab_new = fetch_aibase_map()
    AIBASE_DATES.update(_ab_new)
    _ab_ids = {m.group(1) for m in (AIBASE_RE.search(i['url'].lower())
                                    for i in items) if m}
    _ab_hit = sum(1 for i in _ab_ids if i in AIBASE_DATES)
    json.dump(AIBASE_DATES, io.open(ab_p, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, sort_keys=True)
    print('AIbase 日报编号 %d 个（列表页新解 %d，历史累计 %d，命中 %d）'
          % (len(_ab_ids), len(_ab_new), len(AIBASE_DATES), _ab_hit))
    for _i in sorted(_ab_ids, key=int):
        _v = AIBASE_DATES.get(_i)
        print('   %s %s' % (_i, (_v['day'] + ' ' + _v['iso'][11:16]) if _v
                            else '❌ 未映射到日期'))

    # HN 自带 time（Unix 秒，UTC），不必抓页面
    hn_map = {}
    for it in items:
        if it.get('time'):
            dt = datetime.fromtimestamp(int(it['time']), timezone.utc).astimezone(CST)
            hn_map[it['url']] = _mk(dt, 'hn_api')

    cache_p = os.path.join(HERE, '_pubtime_cache.json')
    cache = {}
    if os.path.exists(cache_p):
        cache = json.load(io.open(cache_p, encoding='utf-8'))
    # 规则变更后，把不再采信的站从缓存里清掉，让它按新规则重判
    for _u in [u for u in cache if any(h in u.lower() for h in NO_TIME_HOSTS)]:
        del cache[_u]

    todo = []
    seen = set()
    for it in items:
        u = it['url']
        if u in seen:
            continue
        seen.add(u)
        if u in hn_map or (u in cache and cache[u].get('day')):
            continue
        if u in cache and cache[u].get('dead'):
            continue
        todo.append(it)

    print('待抓 %d 条（缓存命中 %d，HN 自带 %d）' % (len(todo), len(cache), len(hn_map)))
    got, miss = {}, []
    with ThreadPoolExecutor(8) as ex:
        for url, res in ex.map(probe, todo):
            if res is None:
                miss.append(url)
            else:
                got[url] = res
                cache[url] = res
    for u in miss:
        cache[u] = {'dead': 1}          # 本轮失败，本轮不重试；下次跑会清缓存重抓

    out = {}
    out.update(hn_map)
    for k, v in cache.items():
        if v.get('day'):
            out[k] = v
    json.dump(out, io.open(os.path.join(HERE, 'pubtime.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(cache, io.open(cache_p, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    n_ok = len(out)
    print('--- 取到时间 %d 条 / 总 %d 条（未取到 %d）' % (n_ok, len(seen), len(miss)))
    # 按源统计覆盖率
    by_src = {}
    for it in items:
        s = it.get('src_name', 'HN')
        by_src.setdefault(s, [0, 0])
        by_src[s][1] += 1
        if it['url'] in out:
            by_src[s][0] += 1
    for s, (ok, tot) in sorted(by_src.items(), key=lambda x: -x[1][1]):
        flag = '✅' if ok == tot else ('⚠️' if ok else '❌')
        print('   %s %-16s %d/%d' % (flag, s, ok, tot))
    print('OUT', os.path.join(HERE, 'pubtime.json'))


if __name__ == '__main__':
    main()
