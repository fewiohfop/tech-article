#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 热榜（官方 trending 页口径）

与 github-trending-cn 的关键差别：
  github-trending-cn 走 Search API + sort=stars（总 star 排序），
  返回的是「最近有提交的历史最大仓库」，不是热榜。
  本脚本抓 https://github.com/trending 官方页，取 **stars today / this week**
  增量字段，这才是「热」的口径。

仅使用 Python 标准库，无第三方依赖。
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


def _clear_stale_proxy():
    """环境变量里的代理端口常常是失效的旧值（换VPN 节点后会变），
    urllib 会照着它走并返回 502，导致重试退避白烧几十秒。

    但不能一刀切清空 —— 2026-10-06 实测：
      - github.com（trending 页）**直连被 SSL 中断**，必须走代理
      - api.github.com **直连 200**，走代理反而 403/502
    所以按域名分别决定：代理不健康就只给 github.com 装上。
    手动强制：PROXY_PASSTHROUGH=1 保留原样，PROXY_MODE=direct 清空。
    """
    mode = os.environ.get("PROXY_MODE", "auto").lower()
    if mode == "direct" or os.environ.get("PROXY_PASSTHROUGH") == "1":
        return

    def _alive(p):
        if not p:
            return False
        try:
            import socket
            host, _, port = p.rpartition(":")
            with socket.create_connection((host or "127.0.0.1", int(port)), timeout=2):
                return True
        except Exception:
            return False

    bad = [os.environ[k] for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
           if os.environ.get(k)]
    bad = [p for p in bad if not _alive(p)]
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if os.environ.get(k) in bad:
            os.environ.pop(k, None)
    if bad:
        print("[INFO] 代理端口不通，已清空：%s" % ", ".join(sorted(set(bad))), file=sys.stderr)
        print("[INFO] github.com 走直连；若 SSL 中断可设 PROXY_MODE=passthrough 手动指定可用代理",
              file=sys.stderr)


_clear_stale_proxy()

BASE = "https://github.com/trending"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
PERIOD_LABEL = {
    "daily": "日榜",
    "weekly": "周榜",
    "monthly": "月榜",
}
PERIOD_SUFFIX = {
    "daily": "stars today",
    "weekly": "stars this week",
    "monthly": "stars this month",
}

ART_SPLIT = re.compile(r'<article class="Box-row"')
RE_HREF = re.compile(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', re.S)
RE_DESC = re.compile(r'<p class="col-9 color-fg-muted[^"]*">\s*(.*?)\s*</p>', re.S)
RE_LANG = re.compile(r'<span itemprop="programmingLanguage">([^<]+)</span>')
RE_STAR_A = re.compile(r'<a href="[^"]*/stargazers"[^>]*>(.*?)</a>', re.S)
RE_FORK_A = re.compile(r'<a href="[^"]*/forks"[^>]*>(.*?)</a>', re.S)
RE_PERIOD = re.compile(r"([\d,]+)\s+stars\s+(today|this week|this month)")
RE_NUM = re.compile(r"([\d,]+)")
RE_TAG = re.compile(r"<[^>]+>")


def last_num(m) -> int:
    if not m:
        return 0
    nums = RE_NUM.findall(m.group(1))
    return to_int(nums[-1]) if nums else 0


def fetch(url: str, timeout: int = 30, retries: int = 5) -> str:
    """带重试的抓取。

    实测坑：GitHub trending 页偶发 http.client.IncompleteRead
    （服务端 chunked 传输被提前截断，多次连续出现）。两点应对：
      1. 显式 Accept-Encoding: identity —— 绕开 gzip 分块解压引发的截断
      2. 递增退避重试 5 次
    """
    last_exc = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            body = data.decode("utf-8", errors="replace")
            if "</html>" not in body:
                raise IOError(f"响应不完整（{len(data)} 字节，未见 </html>）")
            return body
        except Exception as e:  # noqa: BLE001
            last_exc = e
            # 代理不通 / DNS 失败是「硬错误」，重试再多次也是同样结果。
            # 2026-10-06 实测：失效代理下 5 次退避白烧 90 秒后仍失败。
            # 只对「偶发」错误（超时、连接被重置、5xx）退避重试。
            msg = str(e).lower()
            hard = ("tunnel connection failed" in msg
                    or "name or service not known" in msg
                    or "nodename nor servname" in msg
                    or "getaddrinfo failed" in msg)
            if hard:
                print("[ERROR] 硬错误（多为 DNS 不通），不再重试：%s: %s"
                      % (type(e).__name__, e), file=sys.stderr)
                raise
            print("[WARN] 第 %d/%d 次失败：%s: %s" % (i + 1, retries, type(e).__name__, e),
                  file=sys.stderr)
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise last_exc


def to_int(s: str) -> int:
    return int(s.replace(",", "")) if s else 0


def parse(html_text: str) -> list:
    blocks = ART_SPLIT.split(html_text)[1:]
    out = []
    for b in blocks:
        m = RE_HREF.search(b)
        if not m:
            continue
        name = m.group(1).strip()
        if name.count("/") != 1:
            continue

        d = RE_DESC.search(b)
        desc = ""
        if d:
            desc = html.unescape(RE_TAG.sub("", d.group(1))).strip()
            desc = re.sub(r"\s+", " ", desc)

        lm = RE_LANG.search(b)
        pm = RE_PERIOD.search(b)

        out.append({
            "name": name,
            "url": f"https://github.com/{name}",
            "description": desc,
            "language": lm.group(1).strip() if lm else None,
            "stars": last_num(RE_STAR_A.search(b)),
            "forks": last_num(RE_FORK_A.search(b)),
            "period_stars": to_int(pm.group(1)) if pm else 0,
        })
    return out


def fmt(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def build_url(period: str, language: str = "") -> str:
    lang = f"/{language.strip().lower()}" if language.strip() else ""
    return f"{BASE}{lang}?since={period}"


def render_md(repos: list, period: str, language: str = "") -> str:
    label = PERIOD_LABEL.get(period, period)
    inc = "今日" if period == "daily" else ("本周" if period == "weekly" else "本月")
    head = f"GitHub {label}"
    if language:
        head += f" · {language}"
    lines = [f"## {head}（{len(repos)} 项，按 {inc} star 增量排序）", ""]
    lines.append("| # | 项目 | 语言 | 总星 | " + f"{inc}增量" + " | 一句话 |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(repos, 1):
        desc = r["description"][:80] + ("…" if len(r["description"]) > 80 else "")
        lines.append(
            f"| {i} | [{r['name']}]({r['url']}) | {r['language'] or '-'} | "
            f"{fmt(r['stars'])} | **+{fmt(r['period_stars'])}** | {desc} |"
        )
    return "\n".join(lines)


TOOL_KW = re.compile(
    r"(skill|agent|cli|mcp|template|plugin|harness|copilot|prompt|workflow|memory|tool)",
    re.I,
)

REPORT_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--tx:#1a1a1a;--mut:#6b7280;--bd:#e5e7eb;
--up:#d92b2b;--acc:#185FA5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:14px/1.6 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:28px 20px 64px}
h1{font-size:23px;margin:0 0 6px;font-weight:600}
.meta{color:var(--mut);font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:960px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px 18px}
.card h2{font-size:15px;margin:0 0 10px;padding-bottom:8px;
border-bottom:1px solid var(--bd);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--mut);font-weight:500;padding:5px 7px;
border-bottom:1px solid var(--bd);white-space:nowrap}
td{padding:8px 7px;border-bottom:1px solid #f1f2f4;vertical-align:top}
tr:last-child td{border-bottom:none}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
.inc{font-weight:600;color:var(--up);white-space:nowrap;text-align:right}
.num{color:var(--mut);white-space:nowrap;text-align:right}
.lang{color:var(--mut);font-size:12px;white-space:nowrap}
.desc{color:#4b5563;font-size:12px;margin-top:3px}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:99px;
background:#E1F5EE;color:#085041;border:1px solid #9FE1CB;margin-left:6px;
white-space:nowrap;vertical-align:middle}
.note{font-size:12px;color:var(--mut);margin-top:16px;line-height:1.8;
background:#fff;border:1px solid var(--bd);border-radius:12px;padding:14px 18px}
.note b{font-weight:600;color:var(--tx)}
"""


def get_repos(period: str, limit: int, language: str = "") -> list:
    url = build_url(period, language)
    print(f"[INFO] GET {url}", file=sys.stderr)
    repos = parse(fetch(url))
    if not repos:
        raise RuntimeError("解析到 0 个项目，页面结构可能已变，需要重新校准选择器")
    repos.sort(key=lambda r: r["period_stars"], reverse=True)
    repos = repos[:limit]
    for i, r in enumerate(repos, 1):
        r["rank"] = i
        r["is_tool"] = bool(
            TOOL_KW.search(f"{r['name']} {r['description'] or ''}")
        )
    return repos


def rows_html(repos: list) -> str:
    out = []
    for r in repos:
        desc = html.escape(r["description"] or "")
        if len(desc) > 108:
            desc = desc[:105] + "…"
        tag = '<span class="tag">技能/工具</span>' if r.get("is_tool") else ""
        out.append(
            f'<tr><td class="num">{r["rank"]}</td>'
            f'<td><a href="{r["url"]}" target="_blank" rel="noopener">'
            f'{html.escape(r["name"])}</a>{tag}'
            f'<div class="desc">{desc or "（无描述）"}</div></td>'
            f'<td class="lang">{html.escape(r["language"] or "-")}</td>'
            f'<td class="num">{fmt(r["stars"])}</td>'
            f'<td class="inc">+{fmt(r["period_stars"])}</td></tr>'
        )
    return "\n".join(out)


def render_html(daily: list, weekly: list, language: str = "") -> str:
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    lang_tag = f" · {html.escape(language)}" if language else ""

    def thead(col: str) -> str:
        return "".join(f"<th>{h}</th>" for h in ["#", "项目", "语言", "总星", col])

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub 热榜 · {now}</title>
<style>{REPORT_CSS}</style></head><body><div class="wrap">
<h1>GitHub 热榜{lang_tag}</h1>
<div class="meta">抓取时间：{now}（北京时间） ｜ 数据源：github.com/trending 官方页
｜ 口径：按 star <b>增量</b>排序，非总星数</div>
<div class="grid">
<div class="card"><h2>日榜 · 按今日 star 增量</h2>
<table><thead><tr>{thead("今日增量")}</tr></thead>
<tbody>{rows_html(daily)}</tbody></table></div>
<div class="card"><h2>周榜 · 按本周 star 增量</h2>
<table><thead><tr>{thead("本周增量")}</tr></thead>
<tbody>{rows_html(weekly)}</tbody></table></div>
</div>
<div class="note">
<b>关于「技能/工具」标记</b>：按项目名与描述中的关键词（skill / agent / cli / mcp /
template / plugin / harness / memory 等）做启发式打标，<b>不是官方分类</b>，
仅用于筛选出「可直接上手用的工具或技能类项目」这一新栏目素材。
<br><b>关于口径</b>：本页增量数字取自 GitHub 官方 trending 页，
与 GitHub Search API 按总 star 排序的结果完全不同——
后者的前几名长期被 public-apis、freeCodeCamp 这类历史大盘占据，不代表当日热度。
<br><b>关于条目数</b>：日榜条目数由官方页面决定，本页不做补位。
</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="GitHub 官方 trending 页（star 增量口径）")
    ap.add_argument("--period", "-p", choices=["daily", "weekly", "monthly"], default="daily")
    ap.add_argument("--limit", "-n", type=int, default=15)
    ap.add_argument("--language", "-l", default="", help="如 python / go / rust")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--html",
        action="store_true",
        help="输出日榜+周榜合一的单文件 HTML 报告（需配合 --out）",
    )
    ap.add_argument("--out", default="", help="写入该路径（UTF-8），避免 Windows 控制台编码问题")
    a = ap.parse_args()

    try:
        if a.html:
            text = render_html(
                get_repos("daily", a.limit, a.language),
                get_repos("weekly", a.limit, a.language),
                a.language,
            )
        else:
            repos = get_repos(a.period, a.limit, a.language)
            text = (
                json.dumps(repos, ensure_ascii=False, indent=2)
                if a.json
                else render_md(repos, a.period, a.language)
            )
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[INFO] 已写入 {a.out}", file=sys.stderr)
    else:
        try:
            print(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(text.encode("utf-8"))


if __name__ == "__main__":
    main()
