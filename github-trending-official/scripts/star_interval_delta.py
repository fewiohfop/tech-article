#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
star 区间增量（自算口径）—— github-trending-official skill
=====================================================================
## 口径（2026-10-12 定稿，硬规则，不要再改）

    窗口 = 上一周周一 00:00 → 本周一 00:00（Asia/Shanghai / GMT+8），固定 7 天
    增量 = 窗口终点该仓库的「总星数」 减 窗口起点该仓库的「总星数」

**这个减法必须由本脚本自己做。** 任何第三方（GitHub 官方 trending 页、各类增量榜站、
OSS Insight）直接给出的「本周增量」数字，都不作为榜单口径使用。

## 为什么必须自算（三条实测证据，2026-10-12）

1. `github.com/trending?since=weekly`
   - 事实：全页只有 12 条，且算法偏向「有提交历史的英文代码项目」，中文内容型项目被
     系统性压低（2026-10-07 实测：中文项目 `eternity4719/HowToLiveBetter` 7 天约 +1.9 万，
     第三方增量榜第 1，官方页 12 条里根本没有它）。
   - 事实：官方页顺序**不是**按增量降序。2026-10-12 实测页序为
     25,151 → 6,440 → 10,330 → 3,803 → 794 → 4,223 → 1,140 → ……（自己就不单调）。
   - 结论：官方页只能当**候选发现**用，不能当榜单口径。

2. OSS Insight `stargazers/history/`
   - 事实：该接口自己带 `data_quality` 字段，声明 event-derived 指标
     `suspect_since: 2025-05-23`、`severely_degraded_since: 2026-05-01`，
     原因是 GitHub 对 `/events` 事件流做了分区，他们的 ETL 只读到第一页，
     所以「事件派生的 star 计数是**下界**，不是精确值」。
   - 实测佐证：`torvalds/linux` 该接口 2026-10-12 累计值 233,852，
     而 GitHub 真实值 251,568 —— **低 17,716（7.0%）**。
   - 结论：**不可用作增量基准**。今天（2026-10-12）正落在「严重退化」区间内。

3. 其余备选（2026-10-12 实测）
   - `ghtrends.dev`、`findarepo.com`：本机不可达。
   - `star-history.com`：只出 SVG，不支持日期区间参数（不同 from/to 返回同一份文件），
     7 天窗口在多年尺度曲线上分辨率不足 → 不可用。
   - `web.archive.org` / `archive.org`：本机不可达。
   - GitHub `/repos/{o}/{r}/stargazers` 带 `Accept: application/vnd.github.star+json`
     （唯一能给每个 star 带时间戳的接口）：**未授权直接 401**，必须有 token。

## 数据通路（都只提供「某时刻的绝对总星」，增量由本脚本做差）

| 通路 | 说明 | 配额 |
|---|---|---|
| `ossinsight_gh` | `https://api.ossinsight.io/gh/repos/{o}/{r}/` —— 直连 GitHub 同源（接口自述 "Totals synced directly from GitHub"）。实测 `torvalds/linux` = 251,568，与 GitHub 完全一致 | 宽松，主源 |
| `github_api` | `https://api.github.com/repos/{o}/{r}` 官方 | 未授权 60 次/小时，作校验源 |
| `github_html` | `https://github.com/{o}/{r}` 页面内嵌 `"stargazerCount":N` | 无配额，兜底 |

## 精确回填（可选，需 GitHub token）

无历史快照时，用 `backfill` 子命令 + `GITHUB_TOKEN`/`--token`：
`/repos/{o}/{r}/stargazers?per_page=100&page=P`（`star+json`）的时间线是**按 star 时间升序**的，
对页号做二分即可定位窗口边界，直接数出窗口内落入的 star 数 —— 这是唯一能精确还原
「过去的某个 7 天窗口」的办法。无 token 时该子命令会明确报错退出，不做任何猜测。

## 用法

    # 0) 候选池（每行一个 owner/repo）
    #    <skill>/data/universe.txt

    # 1) 落快照（建议每期在周一 00:00 之后尽快跑；也可随时手动补）
    python star_interval_delta.py snapshot --universe ../data/universe.txt \
        --store ../data/star_snapshots

    # 2) 算窗口增量（默认 = 最近一个周一 00:00 往前 7 天）
    python star_interval_delta.py compute --universe ../data/universe.txt \
        --store ../data/star_snapshots --out _star_delta.json

    # 3) 指定窗口
    python star_interval_delta.py compute --from 2026-10-05 --to 2026-10-12 ...

    # 4) 精度自检（三条通路互相对数）
    python star_interval_delta.py verify --universe ../data/universe.txt --sample 5

    # 5) 有 token 时：精确回填某个历史窗口
    python star_interval_delta.py backfill --from 2026-10-05 --to 2026-10-12 \
        --universe ../data/universe.txt --out _delta_exact.json

输出 JSON 的 `items` **一律按 delta 降序**，`rank` 由本脚本生成 ——
下游拼版必须直接读这份文件，**不要再手写名次和数字**。
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

TZ = datetime.timezone(datetime.timedelta(hours=8), "Asia/Shanghai")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
WINDOW_DAYS = 7
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UNIVERSE = os.path.join(os.path.dirname(HERE), "data", "universe.txt")
DEFAULT_STORE = os.path.join(os.path.dirname(HERE), "data", "star_snapshots")


# ---------------------------------------------------------------- 时间 / 窗口

def now_tz():
    return datetime.datetime.now(TZ)


def boundary_of(dt):
    """返回 <= dt 的最近一个「周一 00:00」"""
    d = dt.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    d = d - datetime.timedelta(days=d.weekday())      # weekday(): 周一=0
    return d


def window_of(dt=None, days=WINDOW_DAYS):
    """(起点周一 00:00, 终点周一 00:00)，即 [T0, T1)"""
    t1 = boundary_of(dt or now_tz())
    return t1 - datetime.timedelta(days=days), t1


def parse_day(s):
    """'2026-10-05' -> 当天 00:00 (+08:00)"""
    d = datetime.datetime.strptime(s.strip()[:10], "%Y-%m-%d")
    return d.replace(tzinfo=TZ)


def iso(dt):
    return dt.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


# ---------------------------------------------------------------- HTTP

def _http(url, headers=None, timeout=30, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=dict(
                {"User-Agent": UA, "Accept-Encoding": "identity",
                 "Connection": "close"}, **(headers or {})))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 404):     # 认证/不存在，重试无意义
                raise
        except Exception as e:                                    # noqa: BLE001
            last = e
        if i < retries - 1:
            time.sleep(1.2 * (i + 1))
    raise last


STARGZ = re.compile(r'"stargazerCount"\s*:\s*(\d+)')


def fetch_total(repo, prefer=("ossinsight_gh", "github_api", "github_html"),
                verbose=True):
    """取某仓库「此刻」的绝对总星。返回 (stars, source)。

    三条通路都只回答「现在的总数」；任何一条都没有「历史」能力 ——
    历史只能靠本脚本自己的快照，或 backfill（需 token）。
    """
    errs = []
    for src in prefer:
        try:
            if src == "ossinsight_gh":
                body = _http("https://api.ossinsight.io/gh/repos/%s/" % repo)
                v = json.loads(body)["data"]["stargazers_count"]
                return int(v), src
            if src == "github_api":
                body = _http("https://api.github.com/repos/%s" % repo,
                             headers={"Accept": "application/vnd.github+json"})
                v = json.loads(body).get("stargazers_count")
                if v is None:
                    raise ValueError("无 stargazers_count：%s" % body[:120])
                return int(v), src
            if src == "github_html":
                body = _http("https://github.com/%s" % repo)
                m = STARGZ.search(body)
                if not m:
                    raise ValueError("页面里没找到 stargazerCount")
                return int(m.group(1)), src
        except Exception as e:                                    # noqa: BLE001
            errs.append("%s: %s: %s" % (src, type(e).__name__, e))
            if verbose:
                print("    [warn] %s -> %s 失败（%s）" % (repo, src, e), file=sys.stderr)
            time.sleep(0.4)
    raise RuntimeError("；".join(errs) or "全部通路失败")


# ---------------------------------------------------------------- 候选池

def load_universe(path):
    if not path or not os.path.exists(path):
        return []
    out, seen = [], set()
    for line in open(path, encoding="utf-8"):
        n = line.strip()
        if not n or n.startswith("#"):
            continue
        if n.count("/") != 1:
            continue
        if n.split("/")[0] in ("topics", "collections", "marketplace", "orgs",
                               "trending", "sponsors", "features", "enterprise"):
            continue
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


# ---------------------------------------------------------------- 快照

def snap_path(store, boundary):
    return os.path.join(store, "%s.json" % boundary.strftime("%Y-%m-%d"))


def save_snapshot(store, boundary, captured_at, repos, source_note=""):
    os.makedirs(store, exist_ok=True)
    p = snap_path(store, boundary)
    payload = {
        "boundary": iso(boundary),
        "captured_at": iso(captured_at),
        "lag_hours": round((captured_at - boundary).total_seconds() / 3600.0, 2),
        "note": source_note,
        "repos": repos,
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    return p


def load_snapshot(store, boundary):
    p = snap_path(store, boundary)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def cmd_snapshot(args):
    universe = load_universe(args.universe)
    if not universe:
        print("ERR 候选池为空：%s" % args.universe, file=sys.stderr)
        return 2
    boundary = boundary_of(parse_day(args.capture_for) if args.capture_for else now_tz())
    print("快照边界（周一 00:00）：%s" % iso(boundary))
    print("候选池 %d 个仓库，开始抓总数…" % len(universe))

    repos, ok, bad = {}, 0, []
    t_start = time.time()
    for i, name in enumerate(universe, 1):
        try:
            stars, src = fetch_total(name)
            repos[name] = {"stars": stars, "source": src, "at": iso(now_tz())}
            ok += 1
            print("  [%3d/%3d] %-44s %12s  (%s)"
                  % (i, len(universe), name, format(stars, ","), src))
        except Exception as e:                                    # noqa: BLE001
            bad.append({"name": name, "error": str(e)[:200]})
            print("  [%3d/%3d] %-44s FAIL %s" % (i, len(universe), name, e),
                  file=sys.stderr)
    captured = now_tz()
    note = ("逐仓库抓「此刻总星」；三条通路顺序 ossinsight_gh > github_api > github_html。"
            "增量由 compute 子命令做差得出，本文件不含任何第三方增量数字。")
    p = save_snapshot(args.store, boundary, captured, repos, note)
    print()
    print("已写入 %s" % p)
    print("成功 %d / %d，失败 %d，耗时 %.1fs" % (ok, len(universe), len(bad),
                                                time.time() - t_start))
    if bad:
        print("失败清单：")
        for x in bad:
            print("  - %s  %s" % (x["name"], x["error"]))
    return 0 if ok else 1


# ---------------------------------------------------------------- 计算增量

def _baseline_snapshot(path, at):
    """把「归档的某时刻总星」当作窗口起点。

    用途：正常的快照机制需要两周才出数；若历史上某期报告里留下了当时的
    **真实总星数**，可以用它当起点，立刻算出一版全是真的增量。
    ⚠️ 这样算出的窗口**不是**规则的「上周一 00:00 → 本周一 00:00」，
       必须在 window 里如实写出真实起止，并加 caveat。
    支持两种格式：{"repo": 12345} 或 {"repo": {"stars": 12345, "at": "..."}}
    """
    raw = json.load(open(path, encoding="utf-8"))
    repos = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            if "stars" not in v:
                continue
            repos[k] = {"stars": int(v["stars"]),
                        "source": v.get("source", "archived_report"),
                        "at": v.get("at") or at}
        else:
            repos[k] = {"stars": int(v), "source": "archived_report", "at": at}
    return {"boundary": at, "captured_at": at, "lag_hours": None,
            "note": "归档总数（非本机制快照），用于一次性回填",
            "repos": repos}


def cmd_compute(args):
    t0 = parse_day(args.frm) if args.frm else None
    t1 = parse_day(args.to) if args.to else None
    if not (t0 and t1):
        a, b = window_of()
        t0, t1 = (t0 or a), (t1 or b)

    if args.baseline:
        s0 = _baseline_snapshot(args.baseline, args.baseline_at or iso(t0))
        if args.baseline_at:
            t0 = datetime.datetime.fromisoformat(args.baseline_at)
        s1 = load_snapshot(args.store, t1)
    else:
        s0, s1 = load_snapshot(args.store, t0), load_snapshot(args.store, t1)

    universe = load_universe(args.universe)

    missing = [n for n, s in (("%s（窗口起点）" % iso(t0), s0),
                              ("%s（窗口终点）" % iso(t1), s1)) if s is None]
    if missing:
        print("ERR 缺少快照：%s" % "、".join(missing), file=sys.stderr)
        print("    快照目录：%s" % args.store, file=sys.stderr)
        print("    已有：" + (", ".join(sorted(f[:-5] for f in os.listdir(args.store)
                                             if f.endswith(".json")))
                             if os.path.isdir(args.store) else "（目录不存在）"),
              file=sys.stderr)
        print("    → 历史窗口无法用快照回填；需要精确还原请用 backfill 子命令 + GitHub token。",
              file=sys.stderr)
        return 3

    items, excluded = [], []
    names = universe or sorted(set(s0["repos"]) | set(s1["repos"]))
    for name in names:
        a = (s0["repos"].get(name) or {}).get("stars")
        b = (s1["repos"].get(name) or {}).get("stars")
        if a is None or b is None:
            excluded.append({"name": name,
                             "reason": "起点快照缺" if a is None else "终点快照缺"})
            continue
        items.append({"name": name, "stars_from": a, "stars_to": b,
                      "delta": b - a,
                      "source_from": (s0["repos"][name].get("source")),
                      "source_to": (s1["repos"][name].get("source"))})

    # ⚠️ 唯一允许的排序依据：delta 降序
    items.sort(key=lambda x: (-x["delta"], x["name"].lower()))
    for i, x in enumerate(items, 1):
        x["rank"] = i

    nominal = round((t1 - t0).total_seconds() / 86400.0, 2)
    span_h = (datetime.datetime.fromisoformat(s1["captured_at"])
              - datetime.datetime.fromisoformat(s0["captured_at"])).total_seconds() / 3600.0
    rule = args.window_rule or (
        "一次性回填：起点用归档总数，窗口非规则的 7 天，以 window.from/to 为准"
        if args.baseline else
        "上一周周一 00:00 → 本周一 00:00，固定 7 天")
    caveats = [
        "本文件不含任何第三方直接给出的「本周增量」，增量一律为两次总星之差。",
        "若两次的实拍时刻偏离周一 00:00 超过数小时，实际窗口会与名义 7 天有偏差，"
        "以 window 的起止、actual_capture_span_hours 与 lag_hours 为准。",
        "窗口内新建的仓库若无起点数据，会被计入 excluded，不参与排名。",
    ]
    if args.baseline:
        caveats.append(
            "⚠️ 本次起点来自归档总数（不是本机制同一时刻拍的快照），"
            "因此窗口 = 归档时刻 → 本次快照时刻，**不是**「上周一 00:00 → 本周一 00:00」。"
            "这是一次性回填，不能当规则窗口用。")
    out = {
        "window": {
            "from": iso(t0), "to": iso(t1),
            "nominal_days": nominal,
            "tz": "Asia/Shanghai (GMT+8)",
            "window_rule": rule,
        },
        "actual_capture_span_hours": round(span_h, 2),
        "method": ("archived-total-diff (自算：终点快照总星 − 归档总星)"
                   if args.baseline else
                   "snapshot-diff (自算：窗口终点总星 − 窗口起点总星)"),
        "generated_at": iso(now_tz()),
        "snapshots": {
            "from": {"file": (args.baseline if args.baseline
                              else snap_path(args.store, t0)),
                     "captured_at": s0["captured_at"],
                     "lag_hours": s0.get("lag_hours")},
            "to": {"file": snap_path(args.store, t1),
                   "captured_at": s1["captured_at"],
                   "lag_hours": s1.get("lag_hours")},
        },
        "items": items,
        "excluded": excluded,
        "caveats": caveats,
    }

    print("窗口：%s → %s（%.2f 天，实拍间隔 %.1f 小时）"
          % (iso(t0), iso(t1), nominal, span_h))
    print("起点数据：%s" % s0["captured_at"])
    print("终点快照：%s" % s1["captured_at"])
    print("参与排名 %d 条，排除 %d 条" % (len(items), len(excluded)))
    if items:
        print()
        for x in items[:25]:
            print("  #%-3d %-44s +%s"
                  % (x["rank"], x["name"], format(x["delta"], ",")))
    if excluded:
        print()
        print("排除（无起点快照，无法算区间增量）：")
        for x in excluded[:20]:
            print("  - %s（%s）" % (x["name"], x["reason"]))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print()
        print("已写入 %s" % args.out)
    return 0


# ---------------------------------------------------------------- 精度自检

def cmd_verify(args):
    universe = load_universe(args.universe)
    if not universe:
        return 2
    sample = universe[:args.sample]
    print("三条通路互相对数（同一时刻同一仓库，差异应只来自抓取时间差）")
    print("%-44s %12s %12s %12s  %s" % ("repo", "ossinsight", "github_api", "html", "判定"))
    worst = 0
    for name in sample:
        vals = {}
        for src in ("ossinsight_gh", "github_api", "github_html"):
            try:
                v, _ = fetch_total(name, prefer=(src,), verbose=False)
                vals[src] = v
            except Exception as e:                                # noqa: BLE001
                vals[src] = None
                print("    [warn] %s %s: %s" % (name, src, e), file=sys.stderr)
        got = [v for v in vals.values() if v]
        diff = (max(got) - min(got)) if len(got) > 1 else 0
        worst = max(worst, diff)
        verdict = "一致" if diff <= 2 else ("接近(差 %d)" % diff if diff < 50 else "★不一致")
        print("%-44s %12s %12s %12s  %s" % (
            name,
            "{:,}".format(vals["ossinsight_gh"]) if vals["ossinsight_gh"] else "-",
            "{:,}".format(vals["github_api"]) if vals["github_api"] else "-",
            "{:,}".format(vals["github_html"]) if vals["github_html"] else "-",
            verdict))
        time.sleep(0.6)
    print()
    print("最大差异 %d 星；差异在数颗以内属正常（抓取时刻不同 + 页面缓存）。" % worst)
    return 0


# ---------------------------------------------------------------- 精确回填（需 token）

def _stargazers_page(repo, page, token, per_page=100):
    url = ("https://api.github.com/repos/%s/stargazers?per_page=%d&page=%d"
           % (repo, per_page, page))
    body = _http(url, headers={
        "Accept": "application/vnd.github.star+json",
        "Authorization": "Bearer %s" % token,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return json.loads(body)


def _index_at(repo, when, token, per_page=100):
    """返回「starred_at < when」的 star 个数（= 该时刻的总星数）。

    stargazers 按 star 时间升序 → 对页号二分定位边界，再在页内线性数。
    需 token：未授权时该接口返回 401（2026-10-12 实测）。
    """
    first = _stargazers_page(repo, 1, token, per_page)
    if len(first) < per_page:
        return sum(1 for e in first if e["starred_at"] < when)
    # 总页数：先粗探页号，直到取到不足一页为止（同时拿到上界）
    lo, hi = 1, 2
    while True:
        try:
            page = _stargazers_page(repo, hi, token, per_page)
        except urllib.error.HTTPError as e:
            if e.code == 422:          # 超出末页
                break
            raise
        if len(page) < per_page:
            hi = hi
            break
        lo = hi
        hi *= 2
        if hi > 20000:
            break
    # 二分：找第一个「末元素 starred_at >= when」的页
    lo, hi = 1, hi
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            page = _stargazers_page(repo, mid, token, per_page)
        except urllib.error.HTTPError as e:
            if e.code == 422:
                hi = mid
                continue
            raise
        if not page:
            hi = mid
            continue
        if page[-1]["starred_at"] < when:
            lo = mid + 1
        else:
            hi = mid
    page = _stargazers_page(repo, lo, token, per_page)
    base = (lo - 1) * per_page
    return base + sum(1 for e in page if e["starred_at"] < when)


def cmd_backfill(args):
    token = args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("ERR backfill 需要 GitHub token（--token 或环境变量 GITHUB_TOKEN）。", file=sys.stderr)
        print("    原因：/repos/{o}/{r}/stargazers 的 star+json 媒体类型必须认证，"
              "未授权直接 401；它是唯一能给每个 star 带时间戳的接口。", file=sys.stderr)
        print("    未提供 token 时不做任何猜测，直接退出。", file=sys.stderr)
        return 4

    t0 = parse_day(args.frm) if args.frm else window_of()[0]
    t1 = parse_day(args.to) if args.to else window_of()[1]
    universe = load_universe(args.universe)
    if not universe:
        return 2
    print("精确回填窗口 %s → %s（%d 个仓库）" % (iso(t0), iso(t1), len(universe)))

    w0, w1 = t0.isoformat(), t1.isoformat()
    items, excluded = [], []
    for i, name in enumerate(universe, 1):
        try:
            i0 = _index_at(name, w0, token)
            i1 = _index_at(name, w1, token)
            items.append({"name": name, "stars_from": i0, "stars_to": i1,
                          "delta": i1 - i0, "source_from": "stargazers_timeline",
                          "source_to": "stargazers_timeline"})
            print("  [%3d] %-44s %d → %d  (+%d)" % (i, name, i0, i1, i1 - i0))
        except Exception as e:                                    # noqa: BLE001
            excluded.append({"name": name, "reason": str(e)[:200]})
            print("  [%3d] %-44s FAIL %s" % (i, name, e), file=sys.stderr)

    items.sort(key=lambda x: (-x["delta"], x["name"].lower()))
    for i, x in enumerate(items, 1):
        x["rank"] = i
    out = {
        "window": {"from": iso(t0), "to": iso(t1), "nominal_days": (t1 - t0).days,
                   "tz": "Asia/Shanghai (GMT+8)",
                   "window_rule": "上一周周一 00:00 → 本周一 00:00，固定 7 天"},
        "method": "stargazers-timeline (自算：按 starred_at 时间戳逐个数窗口内落入的 star)",
        "generated_at": iso(now_tz()),
        "items": items, "excluded": excluded,
        "caveats": [
            "本文件由 GitHub 官方 /stargazers（star+json）时间线直接计数，是精确值。",
            "时间戳为 UTC，窗口边界按 +08:00 换算后传入；误差不超过 1 秒。",
        ],
    }
    print()
    print("参与 %d 条，排除 %d 条" % (len(items), len(excluded)))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("已写入 %s" % args.out)
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="star 区间增量（自算口径）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--universe", default=DEFAULT_UNIVERSE)

    p = sub.add_parser("snapshot", help="抓「此刻总星」并落盘")
    common(p)
    p.add_argument("--store", default=DEFAULT_STORE)
    p.add_argument("--capture-for", default="",
                   help="把快照挂在哪个周一 00:00 边界下（默认自动取最近一个周一）")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("compute", help="两次快照做差，输出按增量降序的 JSON")
    common(p)
    p.add_argument("--store", default=DEFAULT_STORE)
    p.add_argument("--from", dest="frm", default="")
    p.add_argument("--to", default="")
    p.add_argument("--baseline", default="",
                   help="用归档总数当窗口起点（JSON：{repo: stars} 或 {repo: {stars, at}}）；"
                        "一次性回填用，算出的窗口不是规则 7 天")
    p.add_argument("--baseline-at", default="",
                   help="归档总数的取样时刻（ISO8601，如 2026-10-06T13:30:00+0800）")
    p.add_argument("--window-rule", default="", help="覆盖 window.window_rule 文案")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_compute)

    p = sub.add_parser("verify", help="校验三条总数通路是否一致")
    common(p)
    p.add_argument("--sample", type=int, default=4)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("backfill", help="用 GitHub token 精确回填历史窗口（需 token）")
    common(p)
    p.add_argument("--from", dest="frm", default="")
    p.add_argument("--to", default="")
    p.add_argument("--token", default="")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_backfill)

    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()
