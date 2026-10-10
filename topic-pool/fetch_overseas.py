#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fetch_overseas.py —— 抓海外 + 直连权威源（经 SOCKS5 10808，带重试）。

⚠️ 本机代理是**按节点轮换**的 SOCKS5 端口，同一 URL 连续两次请求可能一次 200 一次 000。
   所以每个 URL 最多重试 4 次，成功即止。
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROXY = 'socks5h://127.0.0.1:10808'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'


def curl(url, out, tries=4, proxied=True, timeout=25):
    """下载到 out，返回 (ok, http_code)。失败重试。"""
    for i in range(tries):
        cmd = ['curl', '-s', '-m', str(timeout)]
        if proxied:
            cmd += ['--socks5-hostname', '127.0.0.1:10808']
        else:
            cmd += ['--noproxy', '*']
        cmd += ['-H', f'User-Agent: {UA}', url, '-o', out, '-w', '%{http_code}']
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout + 8)
            code = r.stdout.decode('utf-8', 'replace').strip()
        except subprocess.TimeoutExpired:
            code = 'timeout'
        if code == '200' and os.path.exists(out) and os.path.getsize(out) > 100:
            return True, code
        time.sleep(1.2)
    return False, code


JOBS = [
    # (文件名, URL, 源名, 大类, 是否走代理)
    ('hn_top.json', 'https://hacker-news.firebaseio.com/v0/topstories.json',
     'Hacker News', '海外AI', True),
    ('gh_trending.html', 'https://github.com/trending?since=daily',
     'GitHub Trending', '开源项目', True),
    ('hf_models.json', 'https://huggingface.co/api/models?sort=trendingScore&limit=30',
     'HuggingFace 热门模型', '海外AI', True),
    ('36kr_ai.html', 'https://www.36kr.com/information/AI/',
     '36氪AI频道', 'AI', False),
    ('qbitai.html', 'https://www.qbitai.com/',
     '量子位', 'AI', False),
    ('arxiv_ai.xml', 'http://export.arxiv.org/rss/cs.AI',
     'arXiv cs.AI', '论文', True),
    ('arxiv_lg.xml', 'http://export.arxiv.org/rss/cs.LG',
     'arXiv cs.LG', '论文', True),
]


def main():
    only = sys.argv[1:] or None
    result = {}
    for fn, url, name, cat, prox in JOBS:
        if only and not any(o in name for o in only):
            continue
        out = os.path.join(HERE, fn)
        ok, code = curl(url, out, proxied=prox)
        size = os.path.getsize(out) if os.path.exists(out) else 0
        result[name] = {'url': url, 'ok': ok, 'code': code, 'size': size, 'cat': cat}
        print(f'{"OK " if ok else "FAIL"} {code:8s} {size:>8d}  {name}')
    with open(os.path.join(HERE, 'fetch_log.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
