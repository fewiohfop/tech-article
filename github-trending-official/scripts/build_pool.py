#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推荐类选题池生成器（`github-trending-official` skill 用）
=====================================================================
把「方向 A 榜单 + 方向 B 推荐」拼成一张单文件 HTML 选题池，两平台各落一份。

为什么要这个脚本：
  选题池的**数据抓取**只有三步是机械的（trending 页 / GitHub API / 三个推荐源），
  但**介绍文案**必须人写。所以本脚本把两者拆开——
  机械部分由 `github_trending_official.py` + api.github.com 产出 JSON，
  文案部分放进一个 data.json，本脚本只负责**拼版**，避免每次重排 HTML。

工作目录约定（--work 指向）：
  _gh_daily.json     ← github_trending_official.py --period daily  --json
  _gh_weekly.json    ← github_trending_official.py --period weekly --json
  _gh_fields.json    ← 逐个打 api.github.com/repos/<owner>/<repo> 的汇总
  _pool_desc.json    ← 本脚本需要的文案与清单（见 references/pool-data.sample.json）

用法：
  python build_pool.py --work <工作目录> --out "<小红书选题目录>" --out "<抖音选题目录>"
  python build_pool.py --work <目录> --out <目录> --date 2026-09-30
  （--out 可给多个，两平台各一个；目录不存在会直接报错，需先创建）

硬规则（来自 SKILL.md，不要绕过）：
  - 星标一律用 GitHub API 实时值；没抓到的退回 trending 页快照，**兜底不能是 0**，
    实在没有就留「—」，宁缺毋假。
  - 「最后更新」= API `pushed_at`，未抓的留「—」，**不猜**。
  - 介绍不写「—」了事；非仓库条目（Collections / Marketplace / Product Hunt）该字段不适用，需写明原因。
"""
import argparse
import json
import os
from datetime import datetime

VOID = {"meta", "br", "img", "hr", "input", "link", "source"}

CSS = """:root{
  --bg:#F7F8FA;--card:#FFFFFF;--line:#E3E6EB;--tx:#1A1D23;--tx2:#5B6270;--tx3:#8A909C;
  --blue:#1D6FE0;--blue-bg:#EAF2FE;--green:#1F8A5B;--green-bg:#E9F7F0;
  --amber:#9A6510;--amber-bg:#FDF3E3;--red:#C0392B;
}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 64px;background:var(--bg);color:var(--tx);
  font-family:"Microsoft YaHei","微软雅黑",-apple-system,"Segoe UI",sans-serif;line-height:1.7}
.wrap{max-width:1220px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px;font-weight:600}
h2{font-size:18px;margin:38px 0 6px;font-weight:600;padding-left:10px;border-left:4px solid var(--blue)}
h3{font-size:15px;margin:24px 0 10px;font-weight:600;color:var(--tx2)}
.sub{font-size:13px;color:var(--tx3);margin:0 0 12px;padding-left:14px}
.meta{font-size:13px;color:var(--tx3);margin:0 0 22px}
.note{background:var(--amber-bg);border:1px solid #F0DCB8;border-radius:10px;padding:13px 16px;
  font-size:13.5px;color:#5E4410;margin:0 0 12px}
.note.green{background:var(--green-bg);border-color:#C6E7D6;color:#14563A}
.note.red{background:#FDEEEC;border-color:#F3CFC9;color:#7E2A20}
.note b{font-weight:700}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
  border-radius:12px;overflow:hidden;font-size:13.5px}
th{background:#F2F4F7;text-align:left;padding:10px 12px;font-weight:600;font-size:12.5px;
  color:var(--tx2);border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:11px 12px;border-bottom:1px solid #EFF1F4;vertical-align:top}
tr:last-child td{border-bottom:none}
td.n{color:var(--tx3);font-variant-numeric:tabular-nums;width:34px;text-align:right;padding-right:4px}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--tx2);font-size:12.5px}
td.up{font-variant-numeric:tabular-nums;white-space:nowrap;font-size:12.5px;color:var(--tx2)}
a{color:var(--blue);text-decoration:none;font-weight:600}
a:hover{text-decoration:underline}
.repo{font-family:Consolas,Monaco,monospace;font-size:12px;color:var(--tx3);font-weight:400;display:block;margin-top:2px}
.desc{color:var(--tx2);font-size:13px}
.delta{color:var(--red);font-weight:600;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:5px;margin:0 4px 2px 0;
  background:var(--blue-bg);color:var(--blue);font-weight:600;white-space:nowrap}
.tag.dead{background:#FDEEEC;color:#A33B2E}
.tag.rec{background:var(--green-bg);color:var(--green)}
.src{font-size:11.5px;color:var(--tx3);display:block;margin-top:3px}
code{background:#F2F4F7;border-radius:4px;padding:1px 5px;font-size:12.5px}
ol.pick{padding-left:22px}
ol.pick li{margin:8px 0}
footer{margin-top:40px;font-size:12.5px;color:var(--tx3);border-top:1px solid var(--line);padding-top:16px}
footer b{color:var(--tx2)}"""


def build(work, date, pull_a, pull_f):
    j = lambda n: json.load(open(os.path.join(work, n), encoding="utf-8"))
    daily = {x["name"]: x for x in j("_gh_daily.json")}
    weekly = {x["name"]: x for x in j("_gh_weekly.json")}
    F = j("_gh_fields.json")
    D = j("_pool_desc.json")

    def stars(repo, fallback=None):
        """优先 API 实时值；没抓到的退回 trending 页快照。兜底绝不是 0。"""
        v = F.get(repo)
        if v and "error" not in v and v.get("stars"):
            return "{:,}".format(v["stars"])
        if fallback:
            return "{:,}".format(fallback)
        return "—"

    def upcell(repo):
        v = F.get(repo)
        if not v or "error" in v or not v.get("pushed_at"):
            return '<td class="up">—</td>'
        d = v["pushed_at"]
        try:
            days = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days
        except Exception:
            days = 0
        if days > 60:
            return '<td class="up">%s<span class="tag dead">久未更新 %d 天</span></td>' % (d[5:], days)
        return '<td class="up">%s</td>' % d[5:]

    def lic(repo):
        v = F.get(repo)
        return v.get("license", "") if (v and "error" not in v) else ""

    def row_rank(i, name, src):
        w = src[name]
        return """<tr><td class="n">%d</td><td><a href="https://github.com/%s">%s</a><span class="repo">%s</span></td>
<td class="num">%s · %s</td><td class="delta">+%s</td>%s<td class="desc">%s</td></tr>""" % (
            i, name, name.split("/")[1], name, w.get("language") or "-",
            stars(name, w.get("stars")), "{:,}".format(w.get("period_stars") or 0),
            upcell(name), D["a_desc"].get(name, w.get("description") or ""))

    def row_b(it):
        repo, nick, lang, desc = it
        l = lic(repo)
        return """<tr><td><a href="https://github.com/%s">%s</a><span class="repo">%s</span></td>
<td class="num">%s</td><td class="num">%s</td>%s<td class="desc">%s%s</td></tr>""" % (
            repo, nick, repo, lang, stars(repo, None), upcell(repo), desc,
            ('<span class="src">许可证：%s</span>' % l) if l else "")

    A = [x["name"] for x in sorted(weekly.values(), key=lambda v: v["rank"])]
    A2 = [x["name"] for x in sorted(daily.values(), key=lambda v: v["rank"])]
    B1, B2, B3 = D["b1"], D["b2"], D["b3"]

    picks = "\n".join("<li>%s</li>" % p for p in D["picks"])
    extra = D.get("extra_notes", "")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub 选题池 · {DATE}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<h1>GitHub 选题池 · {DATE}</h1>
<p class="meta">榜单抓取 {PULL_A} ｜ 仓库字段与「最后更新」抓取 {PULL_F} ｜ 全部条目含介绍信息与原文跳转链接</p>

<div class="note green">
<b>这是「两条线」里的第 ② 条。</b>跑选题发现时应同时出
<b>① AI 科技选题池</b>（<code>今日AI科技选题池_{DATE}.html</code>）与
<b>② 推荐类选题池</b>（本页）。两条线两份文件、互不合并；②不是可选补充。
</div>

<div class="note">
<b>字段口径（先读再挑）：</b>
<b>增量</b>=官方 trending 页的 <code>stars today / this week</code>，<b>不是</b>总星；本页排序依据是<b>增量</b>。
<b>星标</b>=GitHub API <code>stargazers_count</code> 实时值（会随时间变）。
<b>「最后更新」</b>=API <code>pushed_at</code>，即<b>最后一次向仓库推送代码</b>的时间，已换算北京时间；
<b>不是</b> star 变化、也不是收录时间。未抓 API 的条目该列留 <code>—</code>，<b>不猜</b>。
</div>
{EXTRA}
<h2>A · GitHub 周榜（按本周增量排序，{NA} 条）</h2>
<p class="sub">数据源：github.com/trending?since=weekly ｜ 做成品时按「前 5 条」起（前 5 或前 10）｜ 前若干条已逐条抓「最后更新」</p>
<table>
<thead><tr><th>#</th><th>项目</th><th>语言 · 总星</th><th>本周增量</th><th>最后更新</th><th>介绍</th></tr></thead>
<tbody>
{ROWS_A}
</tbody>
</table>
<p class="sub">未逐条打 API 的条目：「最后更新」留 <code>—</code>，星标退回 trending 页总星快照（与 API 实时值可能有极小差异）。<b>未抓的不填，不猜。</b></p>

<h2>A2 · 今日日榜（按今日增量排序，{NA2} 条）</h2>
<p class="sub">数据源：github.com/trending?since=daily ｜ 供参考，正式成篇仍以周榜为主</p>
<table>
<thead><tr><th>#</th><th>项目</th><th>语言 · 总星</th><th>今日增量</th><th>最后更新</th><th>介绍</th></tr></thead>
<tbody>
{ROWS_A2}
</tbody>
</table>

<h2>B · 推荐型候选（好用的项目 / 工具）</h2>
<p class="sub">多个源并行采集 ｜ 星标为 GitHub 官方 API 实时值 ｜ 「最后更新」= 最后一次代码推送（北京时间）</p>

<h3>B1 · HelloGitHub 当期精选（{NB1} 条）</h3>
<table>
<thead><tr><th>项目</th><th>语言</th><th>星标</th><th>最后更新</th><th>介绍</th></tr></thead>
<tbody>
{ROWS_B1}
</tbody>
</table>
<p class="sub">⚠️ 星标一律取 GitHub 官方 API。<b>不要引用 HelloGitHub 页面上那个数字</b>——实测它与 GitHub 实际差一个数量级（口径不明，故不猜、直接换源）。</p>

<h3>B2 · GitHub Explore 官方页面（Trending + 精选合集 + 官方员工推荐）</h3>
<table>
<thead><tr><th>项目</th><th>语言</th><th>星标</th><th>最后更新</th><th>介绍</th></tr></thead>
<tbody>
{ROWS_B2}
</tbody>
</table>

<h3>B3 · Product Hunt（今日 Top，按票数）</h3>
<table>
<thead><tr><th>产品</th><th>票数</th><th>说明</th></tr></thead>
<tbody>
{ROWS_B3}
</tbody>
</table>
<p class="sub">⚠️ Product Hunt 今日页<b>大量为 Promoted 推广位</b>，页面没有统一的官方排名依据。<b>非 GitHub 仓库</b>，无「最后更新」字段。</p>

<h2>我的挑选建议</h2>
<ol class="pick">
{PICKS}
</ol>

<footer>
抓取时点：榜单 <b>{PULL_A}</b>｜仓库字段 <b>{PULL_F}</b>（均为 GMT+8）。<br>
数据源：<code>github.com/trending?since=weekly / daily</code>（增量口径）·
<code>api.github.com/repos/&lt;owner&gt;/&lt;repo&gt;</code>（星标 / pushed_at）·
<code>hellogithub.com</code> · <code>github.com/explore</code> · <code>producthunt.com</code>。<br>
口径说明：<b>增量 ≠ 总星</b>；增量取自官方 trending 页，会随页面缓存变动。<br>
本页为「抓取的选题资料」，不是成品图文。成品走 <code>article-to-social</code></code> 的 ①–⑧。
</footer>
</div>
</body>
</html>
""".format(
        DATE=date, CSS=CSS, PULL_A=pull_a, PULL_F=pull_f, EXTRA=extra,
        NA=len(A), NA2=len(A2), NB1=len(B1),
        ROWS_A="\n".join(row_rank(i, n, weekly) for i, n in enumerate(A, 1)),
        ROWS_A2="\n".join(row_rank(i, n, daily) for i, n in enumerate(A2, 1)),
        ROWS_B1="\n".join(row_b(x) for x in B1),
        ROWS_B2="\n".join(row_b(x) for x in B2),
        ROWS_B3="\n".join('<tr><td><b>%s</b></td><td class="num">%d</td><td class="desc">%s</td></tr>' % tuple(x)
                          for x in B3),
        PICKS=picks,
    )
    return html


def main():
    ap = argparse.ArgumentParser(description="生成 GitHub 推荐类选题池 HTML")
    ap.add_argument("--work", required=True, help="含 _gh_daily.json / _gh_weekly.json / _gh_fields.json / _pool_desc.json 的目录")
    ap.add_argument("--out", nargs="+", required=True, help="输出目录（可多个，两平台各一个）")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--pull-a", default="", help="榜单抓取时点，如 '2026-09-30 11:20（GMT+8）'")
    ap.add_argument("--pull-f", default="", help="仓库字段抓取时点")
    args = ap.parse_args()

    D = json.load(open(os.path.join(args.work, "_pool_desc.json"), encoding="utf-8"))
    pull_a = args.pull_a or D.get("pull_a", "")
    pull_f = args.pull_f or D.get("pull_f", "")

    html = build(args.work, args.date, pull_a, pull_f)
    for d in args.out:
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "选题池_GitHub周榜与推荐_%s.html" % args.date)
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)
        print("OUT", p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
