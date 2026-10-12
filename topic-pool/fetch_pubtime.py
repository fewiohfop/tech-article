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

用法：python fetch_pubtime.py
输入：tophub_items.json + hn_items.json
输出：pubtime.json  {url: {"day": "2026-10-11", "iso": ..., "src": ...}}
缓存：_pubtime_cache.json（同一 URL 不重复抓；失败的不写缓存，下次重试）
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
# ⚠️ AIbase（aibase.com）：链接是「AI日报」聚合页，**一页里多条新闻各带自己的时间**，
#    而池子里的标题是从日报标题（「AI日报：A；B；C」）拆出来的 → 用「页面第一个日期」
#    会给所有条目安上同一个假时间。实测还发现旧编号页会滚动成当日最新内容，
#    页面标题与正文已经对不上。这种宁可标「未取到」，也不能给错误时间。
NO_TIME_HOSTS = ['aibase.com']

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


def probe(item):
    url = item['url']
    low = url.lower()
    if low.startswith('https://github.com/'):
        return url, {'note': '榜单页无发布时间'}
    if any(h in low for h in NO_TIME_HOSTS):
        return url, {'note': '聚合页，时间不可信 → 不取'}
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
