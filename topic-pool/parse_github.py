#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""parse_github.py —— 解析 GitHub Trending 日榜页（gh_trending.html）。

⚠️ 仓库名在 `<h2 class="h3 lh-condensed">` 里，**不是** `<a href>` 直取
（2026-10-09 实测：直取 href 会全部返回空，因为第一个 a 是 login 按钮）。
"""
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def clean(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s or '')).strip()


def main():
    p = os.path.join(HERE, 'gh_trending.html')
    if not os.path.exists(p) or os.path.getsize(p) < 5000:
        print('SKIP  gh_trending.html 缺失或过小（GitHub 需走代理，可能被节点挡）')
        json.dump([], open(os.path.join(HERE, 'gh_items.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False)
        return
    s = open(p, encoding='utf-8', errors='replace').read()
    out = []
    for a in re.findall(r'<article class="Box-row">(.*?)</article>', s, re.S):
        # ⚠️ `<a>` 标签里塞了 data-hydro-click 等一大堆属性，href 前面还有换行和空格 ——
        # 用 `<a[^>]*href="/(owner/repo)"` 宽松匹配，不能写死 `<a href="`（实测会全空）。
        m = re.search(r'<h2 class="h3 lh-condensed">(.*?)</h2>', a, re.S)
        repo = ''
        if m:
            mm = re.search(r'<a[^>]*href="/([^"?#]+)"', m.group(1), re.S)
            if mm:
                repo = html.unescape(mm.group(1)).strip()
        if not repo:
            continue
        d = re.search(r'<p class="col-9[^"]*">(.*?)</p>', a, re.S)
        desc = clean(d.group(1)) if d else ''
        st = re.search(r'stargazers">\s*([\d,]+)', a)
        td = re.search(r'([\d,]+)\s*stars today', a)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
        out.append({
            'repo': repo,
            'desc': desc,
            'stars': int(st.group(1).replace(',', '')) if st else 0,
            'today': int(td.group(1).replace(',', '')) if td else 0,
            'lang': clean(lang.group(1)) if lang else '',
            'url': f'https://github.com/{repo}',
        })
        print(f'  {repo:42s} ★{out[-1]["stars"]:>7d} 今日+{out[-1]["today"]:>6d} '
              f'{out[-1]["lang"]:12s} {desc[:52]}')
    json.dump(out, open(os.path.join(HERE, 'gh_items.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'--- {len(out)} 个仓库 -> gh_items.json')


if __name__ == '__main__':
    main()
