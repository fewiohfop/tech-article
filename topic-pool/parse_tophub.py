#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""parse_tophub.py —— 把 tophub 节点页解析成结构化条目。

tophub 节点页结构（2026-10-09 实测）：
  <div class="cc-cd-cb-l">
    <a href="<原始链接>" ...><div class="t">标题</div>...</a>
    <div class="s">热度值</div>
    <div class="b">来源媒体名</div>
条目按 <div class="cc-cd-is"></div> 或 item 块切分。
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# node_id -> (显示名, 大类, 热度口径)
NODES = {
    # AI 线
    'x9oz2O1oXb': ('36氪AI频道', 'AI', ''),
    'MZd7azPorO': ('量子位', 'AI', ''),
    'ENeYylkeY4': ('AIbase', 'AI', ''),
    '8Rv2NjnvLw': ('AI工具集', 'AI', ''),
    'rYqoXz8dOD': ('掘金', 'AI', ''),
    '7GdabqLeQy': ('MIT Tech Review', 'AI', ''),
    'proPKWkeq6': ('AI产品榜', 'AI', ''),
    # 科技线
    '74Kvx59dkx': ('IT之家日榜', '科技', '评论数'),
    'n4qv90roaK': ('威锋网', '科技', '站内值'),
    '74KvxK7okx': ('爱范儿', '科技', ''),
    '20MdK2vw1q': ('果壳科学人', '科技', ''),
    'Y3QeLMPo7k': ('Readhub', '科技', ''),
    'Y2KeDGQdNP': ('少数派', '科技', ''),
    '5VaobgvAj1': ('虎嗅热文', '科技', '阅读量万'),
    'Q1Vd5Ko85R': ('36氪24h', '科技', ''),
    'NRrvWYDe5z': ('极客公园', '科技', ''),
    'NaEdZZXdrO': ('少数派最新', '科技', ''),
}

_TAG = re.compile(r'<[^>]+>')
_NUM = re.compile(r'^\s*([0-9][0-9,.]*\s*[wW万]?)\s*$')


def clean(s):
    s = _TAG.sub('', s or '')
    return html.unescape(s).replace('', '').strip()


def parse(path):
    """从节点页 HTML 里抽出条目列表。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        s = f.read()
    items = []
    # 真实结构（2026-10-09 实测）：<table class="table"><tbody><tr>…</tr></tbody></table>
    # 每行：<td align="center">排名</td><td class="al">缩略图</td>
    #       <td class="al"><div><a href="URL">标题</a></div><div class="item-desc">热度</div></td>
    # 热度在 <div class="item-desc">；来源媒体名在该行之后单独的 <div class="b"> 或行尾文本。
    for m in re.finditer(r'<tr>(.*?)</tr>', s, re.S):
        blk = m.group(1)
        a = re.search(r'<td class="al">\s*<div>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not a:
            a = re.search(r'<a\s+href="(https?://(?!tophub\.today)[^"]+)"[^>]*>(.*?)</a>', blk, re.S)
            if not a:
                continue
        url = html.unescape(a.group(1))
        title = clean(a.group(2))
        if not title or 'tophub.today' in url:
            continue
        heat = None
        hs = re.search(r'<div class="item-desc">(.*?)</div>', blk, re.S)
        if hs:
            raw = clean(hs.group(1)).replace(' ', '')
            hm = re.match(r'^([0-9][0-9,.]*)\s*([wW万]?)', raw)
            if hm:
                v = hm.group(1).replace(',', '')
                mult = 10000 if hm.group(2) else 1
                try:
                    heat = float(v) * mult
                except ValueError:
                    heat = None
        items.append({'title': title, 'url': url, 'heat': heat, 'media': ''})
    # 来源媒体名：节点页里 <div class="b">…</div> 紧跟节点名，或条目前的灰色小字
    for m in re.finditer(r'<div class="gg-z">\s*(.*?)\s*</div>', s, re.S):
        pass
    return items


def main():
    out = []
    missing = []
    for nid, (name, cat, hk) in NODES.items():
        for pfx in ('ai_', 'tk_'):
            p = os.path.join(HERE, f'{pfx}{nid}.html')
            if os.path.exists(p) and os.path.getsize(p) > 2000:
                break
        else:
            p = None
        if not p:
            missing.append({'name': name, 'reason': '未抓到节点页'})
            continue
        its = parse(p)
        if not its:
            missing.append({'name': name, 'reason': '节点页解析出 0 条（可能已停更）'})
        for it in its:
            it.update({'src': nid, 'src_name': name, 'cat': cat, 'heat_kind': hk})
            out.append(it)
        print(f'{name:16s} {len(its):3d} 条   {p.split("/")[-1]}')
    print(f'--- 合计 {len(out)} 条，未采到 {len(missing)} 个源')
    dst = os.path.join(HERE, 'tophub_items.json')
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump({'items': out, 'missing': missing}, f, ensure_ascii=False, indent=1)
    print('OUT', dst)
    for m in missing:
        print('  MISS', m['name'], m['reason'])


if __name__ == '__main__':
    main()
