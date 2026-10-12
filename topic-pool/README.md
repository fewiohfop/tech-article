# topic-pool —— 选题池脚本（镜像副本）

① 线「选题发现」的抓取与出池脚本。

> ⚠️ **运行目录在本机 `C:\srtwb\pool\`，本目录是它的镜像副本**，只为随仓库同步、
> 换设备时可用。**不要在副本上直接改** —— 否则两边分叉，下次同步会互相覆盖。

## 文件

| 文件 | 作用 |
|---|---|
| `run_daily.sh` | 一键入口：抓 tophub 17 节点 → 海外/直连源 → 解析 → 抓发布时间 → 出 HTML |
| `fetch_overseas.py` | 直连源抓取（HuggingFace 等） |
| `fetch_hn.py` | Hacker News top，详情须 8 线程并发（串行 30 次会被 SIGTERM）；带 `time` 字段 |
| `parse_tophub.py` | tophub 节点页解析（⚠️ 页面结构是 `<table><tr>`，按 div 写会解析 0 条） |
| `parse_github.py` | GitHub Trending 解析（star 总数取不到，只用「今日新增 star」当热度） |
| `fetch_pubtime.py` | 给池内每条外链取「发布时间」→ `pubtime.json`（2026-10-12 新增，详见下节） |
| `make_pool.py` | 去重 / 跨源合并 / 排序 / 出选题池 HTML（主体，2026-10-09 重做版） |

产物：`C:\选题\今日AI科技选题池_<日期>.html` —— **单文件**，AI 与科技同页、章内分节
（`A`=AI / `T`=科技 / `H`=钩子候选 / `M`=推荐补位）。

## 发布时间与「必抓 7 天窗」（2026-10-12）

起因：用户发现「必抓更新」表里混着发布时间很久的新闻，且页面上看不出每条到底多久了。

- `fetch_pubtime.py` 读 `tophub_items.json` + `hn_items.json`，逐条抓外链的发布时间，
  写 `pubtime.json` ≈ `{url: {day, iso, epoch, src}}`；缓存 `_pubtime_cache.json`，只抓新 URL。
- **站点专用规则优先于通用 meta** —— 36氪是 SPA，通用 `<meta article:published_time>`
  取到的是「页面渲染那一刻」（同一秒抓 4 条值完全相同），必须改用页内 JSON `"publishTime"`（毫秒）。
- **AIbase（`aibase.com`）列入 `NO_TIME_HOSTS` 不取** —— 它是「AI日报」聚合页，
  一页里多条新闻各带自己的时间，而池内标题是从日报标题拆出来的 →「页面第一个日期」
  会给所有条目安上同一个假时间。宁可标「时间未取到」，也不给错误时间。
- 假阳性防护（`parse_val`）：未来 >2 天、早于 2024-01-01、与抓取时刻差 <180 秒（SPA 渲染时间）→ 全部丢弃。
- `make_pool.py` 里 `MUST_WINDOW_DAYS = 7`：必抓只收最近 7 天，**超期的降到
  「必抓但超期未采用」单列，不静默丢弃**；条目时间标签由 `pub_of(urls)` 给出 ——
  取该事件**所有来源里最早**的那个时间（最早的报道时刻才代表它何时开始发生）。

## 用法

```bash
bash run_daily.sh 2026-10-10             # 抓取 + 出池（完整链路）
python fetch_pubtime.py                  # 只补发布时间（缓存命中时很快）
python make_pool.py 2026-10-10           # 只出池：用已落盘数据，不重新抓取
python make_pool.py 2026-10-10 --split   # 回退成「AI / 科技 各一份」旧输出
```

抓取产物（`ai_*.html` / `tk_*.html` / `*_items.json` 等）落在 `C:\srtwb\pool\`，
**不进仓库** —— 每次跑都会覆盖。

## 同步（改完运行目录后）

```bash
cp C:/srtwb/pool/*.py C:/srtwb/pool/run_daily.sh <本仓库>/topic-pool/
```

改动始终以 `C:\srtwb\pool\` 那一份为准，本目录只是副本。
