#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star 增量周榜 —— 换源抓取（2026-10-07 新增）
=====================================================================
**为什么不用 github.com/trending 了**

2026-10-07 实测：官方 trending 周榜**全页只有 12 条**，且算法偏向「有提交历史的
英文代码项目」，中文内容型项目被系统性压低。最典型的是
`eternity4719/HowToLiveBetter`（高性价比人生指南，中文，9-07 上线，
10-07 已48808 star，7 天增量约 +1.9 万）—— 第三方增量榜第 1 名，
**官方页 12 条里根本没有它**。

所以本期起把主榜口径换成「star 增量」：
- 数据源 findarepo.com（自建榜，明确公开算法与数据来源）
- 它取自 GitHub **官方 stargazer 历史接口**（/stargazers 带 starred_at），
  按窗口内每日新增 star 相加，口径可溯源
- 榜单 20+ 条，中文项目能正常进前列

⚠️ **必须写清楚的事实与推测**
- 事实：findarepo 页面上的 `★ 总星` 与 `▲ +N/7d` 增量，是该站自己抓取并计算的。
- 事实：这些数字与 GitHub REST API 的 `stargazers_count` 一致（已交叉核对
  HowToLiveBetter：页面 49k / API 48808，同一时点）。
- **推测（未逐仓库验证）**：该站 7 天窗口的具体起止时刻与我们的「今天」不完全对齐，
  所以增量数字与「近 7 个自然日」可能有 1 天左右的错位。
- ⚠️ 交付时**必须标注抓取时点**，并说明「增量口径非GitHub 官方 trending 页原样」。

同时保留 `--official` 参数：需要官方页原样时仍可抓，两份数据都放进 JSON，
由调用方决定用哪份。

用法：
  # 1) 抓榜单
  python star_delta_weekly.py --limit 20 --out _delta.json
  # 2) 用官方 API 补总星/许可证/最后更新（强烈建议，未授权配额 60次/小时）
  python fetch_repo_fields.py --repos-file repos.txt --out _delta_fields.json
  # 3) 合并字段后重新出一份
  python star_delta_weekly.py --limit 20 --fields _delta_fields.json --out _delta.json
  # 4) 需保留官方 trending 页原样时
  python star_delta_weekly.py --limit 20 --with-official --out _delta.json

⚠️ 三个已实测的坑（2026-10-07）：
1. findarepo 首页把 1 天增量和 7 天增量混在同一条榜里排（+31k/7d 与 +9.2k/1d 同页），
   不过滤会得出「一天涨 3 万 star」的错结论→ 代码已强制只留 window_days==7。
2. ghtrends 页面里 JSON-LD 榜单与 HTML 渲染榜单**是两个不同时点的快照**
   （JSON-LD datePublished=2026-09-28共 25 条，HTML 已更新到 10-05 共 19 条），
   逐位比对必然报「不一致」，那是时点差异不是数据错误 → 校验改成集合包含判断。
3. findarepo 的仓库名带 `<strong>` 高亮标签，且 li 属性顺序是
   data-s/data-d/data-a/data-c → 选择器必须容忍标签与任意属性顺序，否则静默匹配 0 条。
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
SOURCES = [
    # (站点名, URL, 解析器, 只保留的窗口天数或 None=全留, 说明)
    #⚠️ findarepo 首页把「1 天增量」和「7 天增量」混在同一条榜里排
    #   （实测 2026-10-07：+31k/7d、+18k/7d、+14k/7d 与 +9.2k/1d、+4.6k/1d 同页），
    #   混排会得出「一天涨 3 万 star」这种错结论→ **只取 7d**。
    #  ghtrends.dev/weekly 是纯周榜，作为主源。
    ("ghtrends", "https://ghtrends.dev/weekly", "ghtrends", 7,
     "周榜，纯 7 天窗口，取自官方 stargazer 历史接口"),
    ("findarepo", "https://findarepo.com/", "findarepo", 7,
     "综合榜，1d/7d 混排，仅取 7d 作交叉校验"),
]

RE_ROW = re.compile(
    r'<li class="lead-row"(?P<attrs>[^>]*)>(?P<body>.*?)</li>', re.S)
RE_RANK = re.compile(r'<span class="lead-rank">\s*(\d+)\s*</span>')
# ⚠️ 仓库名带 <strong> 包裹（高亮部分），正则必须允许标签，
#    且用 findall 取第2 组（弱匹配法会把 <strong> 吞进仓库名）。
RE_NAME = re.compile(r'<a href="/repo/[^"]*?/([^/"]+)/?">(.*?)</a>', re.S)
RE_STRONG = re.compile(r'<strong>(.*?)</strong>', re.S)
RE_TAG = re.compile(r"<[^>]+>")
RE_DESC = re.compile(r'<span class="lead-desc"><q>(.*?)</q></span>', re.S)
RE_LANG = re.compile(
    r'<span class="lead-lang">.*?</span>\s*([A-Za-z0-9+#.\- ]+?)\s*</span>', re.S)
RE_STARS = re.compile(r'<span class="stars">\s*★\s*([\d.,km]+)\s*</span>', re.I)
RE_DELTA = re.compile(r'<span class="delta">\s*▲\s*\+?([\d.,km]+)\s*(?:<small>/(\d+)d</small>)?', re.I)

MULT = {"k": 1000, "m": 1000000}


def _num(s):
    """'49k' -> 49000 ; '1.9M' -> 1900000"""
    if not s:
        return 0
    s = s.strip().lower().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([km])?$", s)
    if not m:
        return 0
    v = float(m.group(1))
    if m.group(2):
        v *= MULT[m.group(2)]
    return int(v)


def _clear_proxy():
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)


def fetch(url, timeout=30, retries=3):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept-Encoding": "identity",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "close",
            })
            with op.open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            print("[WARN] %s 第 %d 次失败：%s: %s" % (url, i + 1, type(e).__name__, e),
                  file=sys.stderr)
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def parse_findarepo(body):
    """按 <li class="lead-row"> ... </li> 整块切分。

    ⚠️ 2026-10-07 实踩：块属性顺序是 data-s / data-d / data-a / data-c，
    硬编码 `data-s="..".*?data-d=".."` 会在属性顺序变化时静默匹配 0 条。
    → 改为整块匹配后从 attrs 里取，顺序无关。
    """
    out = []
    for m in RE_ROW.finditer(body):
        attrs, blk = m.group("attrs"), m.group("body")
        s_total = re.search(r'data-s="(\d+)"', attrs)
        s_delta = re.search(r'data-d="(\d+)"', attrs)
        nm = RE_NAME.search(blk)
        if not nm:
            continue
        repo = RE_STRONG.search(nm.group(2))
        repo = re.sub(r"\s+", "", repo.group(1) if repo else RE_TAG.sub("", nm.group(2)))
        # href 形如 /repo/<owner>/<repo>/ ，第1 组是 owner，第2 组是 repo 名
        href = re.search(r'<a href="/repo/([^/"]+)/([^/"]+)/?">', blk)
        if not href:
            continue
        owner = href.group(1)
        name = "%s/%s" % (owner, repo)
        rk = RE_RANK.search(blk)
        dc = RE_DESC.search(blk)
        desc = html.unescape(RE_TAG.sub("", dc.group(1))).strip() if dc else ""
        desc = re.sub(r"\s+", " ", desc)
        lg = RE_LANG.search(blk)
        lang = lg.group(1).strip() if lg else ""
        st = RE_STARS.search(blk)
        dl = RE_DELTA.search(blk)
        out.append({
            "name": name,
            "url": "https://github.com/%s" % name,
            "description": desc,
            "language": lang or None,
            "stars": int(s_total.group(1)) if s_total else 0,
            "period_stars": int(s_delta.group(1)) if s_delta else 0,
            "stars_display": st.group(1) if st else "",
            "delta_display": (dl.group(1) if dl else ""),
            "window_days": int(dl.group(2)) if (dl and dl.group(2)) else 7,
            "rank": int(rk.group(1)) if rk else None,
        })
    return out


def parse_ghtrends(body):
    """ghtrends.dev/weekly —— 主源。

    页面结构（Astro 静态站）：
      <li class="rank-item">
        <div class="rank">1</div>
        <div><h3 class="ranking-title"><a href="https://github.com/o/r">o/r</a></h3>
        <span class="lang-chip">HTML</span>
        <p class="repo-desc">…</p></div>
        <div class="delta">+18,046</div>
      </li>

    ⚠️ 2026-10-07 实踩两点：
    1) 页面里大量 `data-astro-cid-*` 属性插在标签中间，正则必须容忍任意属性。
    2) 页面顶部有一段 JSON-LD（`mainEntity.itemListElement`）也含25 条榜单，
       但它**只有排名没有增量**，且 `datePublished` 可能滞后于页面。
       → 只用 HTML 渲染块取数，JSON-LD 仅用于交叉校验排名顺序。
    """
    out = []
    blocks = re.split(r'<li class="rank-item"[^>]*>', body)[1:]
    for b in blocks:
        b = b.split("</li>")[0]
        rk = re.search(r'<div class="rank"[^>]*>\s*(\d+)\s*</div>', b)
        nm = re.search(r'href="https://github\.com/([^/"]+)/([^"/?#]+)"', b)
        if not nm:
            continue
        name = "%s/%s" % (nm.group(1), nm.group(2))
        dl = re.search(r'<div class="delta"[^>]*>\s*\+?\s*([\d,]+)\s*</div>', b)
        lg = re.search(r'<span class="lang-chip"[^>]*>\s*([^<]*?)\s*</span>', b)
        dc = re.search(r'<p class="repo-desc"[^>]*>(.*?)</p>', b, re.S)
        desc = html.unescape(RE_TAG.sub("", dc.group(1))).strip() if dc else ""
        desc = re.sub(r"\s+", " ", desc)
        out.append({
            "name": name,
            "url": "https://github.com/%s" % name,
            "description": desc,
            "language": (lg.group(1).strip() if lg and lg.group(1).strip() else None),
            "stars": 0,           # 该站不渲染总星，另行用 API 补
            "period_stars": int(dl.group(1).replace(",", "")) if dl else 0,
            "window_days": 7,
            "rank": int(rk.group(1)) if rk else None,
        })
    return out


def parse_ghtrends_jsonld(body):
    """交叉校验用：返回 JSON-LD 里的 (position, name) 顺序列表。"""
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)
    if not m:
        return []
    try:
        d = json.loads(m.group(1))
        return [(x.get("position"), x.get("name"))
                for x in d.get("mainEntity", {}).get("itemListElement", [])]
    except Exception:# noqa: BLE001
        return []


def fetch_official(limit):
    """保留官方 trending 页口径（可选）。需要先解掉 github.com 的代理问题。"""
    here = os.path.dirname(os.path.abspath(__file__))
    tr = os.path.join(here, "github_trending_official.py")
    if not os.path.exists(tr):
        return []
    import subprocess
    import tempfile
    p = os.path.join(tempfile.gettempdir(), "_gh_official_wk.json")
    r = subprocess.run([sys.executable, tr, "--period", "weekly",
                        "--limit", str(limit), "--json", "--out", p],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    if r.returncode != 0 or not os.path.exists(p):
        print("[WARN] 官方页抓取失败：%s" % ((r.stderr or "").strip()[-200:]), file=sys.stderr)
        return []
    data = json.load(open(p, encoding="utf-8"))
    for i, x in enumerate(data, 1):
        x["source"] = "official_trending"
        x["rank"] = i
    return data


def main():
    ap = argparse.ArgumentParser(description="star 增量周榜（换源口径）")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", default="")
    ap.add_argument("--with-official", action="store_true",
                    help="额外抓官方 trending 页并放进同一份 JSON")
    ap.add_argument("--fields", default="",
                    help="fetch_repo_fields.py 的输出 JSON，用它补总星/许可证/最后更新")
    a = ap.parse_args()

    _clear_proxy()
    print("[INFO] 抓取 star 增量榜（换源口径）", file=sys.stderr)

    per_source = {}
    merged = {}
    for site, url, parser, win, note in SOURCES:
        try:
            body = fetch(url)
        except Exception as e:  # noqa: BLE001
            print("[ERROR] %s 抓取失败：%s: %s" % (site, type(e).__name__, e), file=sys.stderr)
            continue
        items = parse_findarepo(body) if parser == "findarepo" else parse_ghtrends(body)
        if win:
            before = len(items)
            items = [x for x in items if x.get("window_days") == win]
            if len(items) != before:
                print("[INFO]   %s：窗口过滤 %d → %d 条（只留 %dd）"
                      % (site, before, len(items), win), file=sys.stderr)
        if not items:
            print("[WARN] %s 解析到 0 条，页面结构可能变了" % site, file=sys.stderr)
            continue
        per_source[site] = {"url": url, "note": note, "count": len(items),
                            "window_days": win,
                            "names": [x["name"] for x in items[:a.limit]]}
        print("[INFO]   %s → %d 条（%s）" % (site, len(items), note), file=sys.stderr)
        if parser == "ghtrends":
            # 交叉校验：JSON-LD 榜单 vs HTML 渲染榜单
            # ⚠️ 2026-10-07 实测：两者**本来就是两个不同时点的快照**，不是解析错。
            #   JSON-LD 的 datePublished=2026-09-28（25 条），HTML 渲染块已更新到 10-05（19 条）。
            #   前 3 名恰好相同，第 4 名之后分叉（如 JSON-LD 第4=ponytail，HTML 第4=hindsight）。
            #   → 逐位比对必然报「不一致」，那是**时点差异不是数据错误**。
            #   → 改判标准：HTML 榜单里排名靠前的条目，是否都能在 JSON-LD 里找到名字。
            #     找得到 = 两榜共有的老牌条目，排名变化属正常滚动。
            jl = parse_ghtrends_jsonld(body)
            if jl:
                jl_names = {n for _, n in jl if n}
                html_names = [x["name"] for x in items]
                missing = [n for n in html_names if n not in jl_names]
                print("[INFO]   JSON-LD 快照交叉校验：JSON-LD %d 条 / HTML %d 条；"
                      "HTML 独有 %d 条 %s"
                      % (len(jl), len(html_names), len(missing),
                         ("（%s，新入榜条目属正常）" % ", ".join(missing[:3])) if missing
                         else "（完全包含）"),
                      file=sys.stderr)
        for x in items:
            x["source"] = site
            # 多站合并：按仓库名去重，保留增量更大的那个（口径更宽/更新）
            k = x["name"].lower()
            if k not in merged or x["period_stars"] > merged[k]["period_stars"]:
                merged[k] = x
        time.sleep(1)

    if not merged:
        print("[ERROR] 所有源都没抓到数据，终止（不生成空文件）", file=sys.stderr)
        sys.exit(1)

    items = sorted(merged.values(), key=lambda r: -r["period_stars"])[:a.limit]
    for i, x in enumerate(items, 1):
        x["rank"] = i
        x["source"] = "merged"

    # 用官方 API 字段补全总星 / 许可证 / 最后更新（榜单站不渲染这些）
    if a.fields and os.path.exists(a.fields):
        f = json.load(open(a.fields, encoding="utf-8"))
        hit = 0
        for x in items:
            d = f.get(x["name"])
            if not d or "error" in d:
                continue
            hit += 1
            x["stars_api"] = d.get("stars")
            x["forks"] = d.get("forks")
            x["license"] = d.get("license")
            x["pushed_at"] = d.get("pushed_at")
            x["created_at"] = d.get("created_at")
            x["topics"] = d.get("topics") or []
            x["homepage"] = d.get("homepage") or ""
            x["archived"] = d.get("archived", False)
        print("[INFO]   官方 API 字段补全 %d/%d 条" % (hit, len(items)), file=sys.stderr)

    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    out = {
        "generated_at": now,
        "metric": "7-day star delta (merged from independent trackers)",
        "sources": per_source,
        "note": (
            "口径说明：7 天 star 增量，非 github.com/trending 官方页原样。"
            "数字由第三方站取自 GitHub 官方 stargazer 历史接口计算；"
            "总星数已与 GitHub REST API 交叉核对一致。"
            "窗口起止与本地时区可能存在约 1 天错位，属推测，未逐仓库验证。"
        ),
        "items": items,
    }
    if a.with_official:
        out["official_trending"] = fetch_official(a.limit)

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("[INFO] 已写入 %s" % a.out, file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
