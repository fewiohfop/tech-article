#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fetch_hn.py —— 用 HN 官方 Firebase API 抓 top stories 条目详情。

api.github.com 与 github.com 整站在本机代理下不通（实测 000），
但 news.ycombinator.com 的官方 API（firebaseio）稳定可用 → 走它。
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = 'https://hacker-news.firebaseio.com/v0/item/{}.json'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def get(url, tries=4):
    for _ in range(tries):
        cmd = ['curl', '-s', '-m', '20', '--socks5-hostname', '127.0.0.1:10808',
               '-H', f'User-Agent: {UA}', url, '-w', '\n%{http_code}']
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=28)
            txt = r.stdout.decode('utf-8', 'replace')
            body, _, code = txt.rpartition('\n')
            if code.strip() == '200' and body.strip():
                return json.loads(body)
        except Exception:
            pass
        time.sleep(1.0)
    return None


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    ids_file = os.path.join(HERE, 'hn_top.json')
    if not os.path.exists(ids_file):
        ids = get('https://hacker-news.firebaseio.com/v0/topstories.json') or []
    else:
        ids = json.load(open(ids_file, encoding='utf-8'))
    ids = ids[:n]

    # ⚠️ 串行 30 次请求会超时（实测 SIGTERM）→ 必须并发。
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        details = list(ex.map(lambda sid: get(API.format(sid), tries=3), ids))

    out = []
    for sid, d in zip(ids, details):
        if not d or d.get('type') != 'story':
            continue
        out.append({
            'title': d.get('title', ''),
            'url': d.get('url') or f'https://news.ycombinator.com/item?id={sid}',
            'score': d.get('score', 0),
            'descendants': d.get('descendants', 0),
            'hn_id': sid,
        })
        print(f'[{d.get("score",0):5d}分 {d.get("descendants",0):4d}评] {d.get("title","")[:80]}')
    p = os.path.join(HERE, 'hn_items.json')
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'--- {len(out)} 条 -> {p}')


if __name__ == '__main__':
    main()
