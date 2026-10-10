# topic-pool —— 选题池脚本（镜像副本）

① 线「选题发现」的抓取与出池脚本。

> ⚠️ **运行目录在本机 `C:\srtwb\pool\`，本目录是它的镜像副本**，只为随仓库同步、
> 换设备时可用。**不要在副本上直接改** —— 否则两边分叉，下次同步会互相覆盖。

## 文件

| 文件 | 作用 |
|---|---|
| `run_daily.sh` | 一键入口：抓 tophub 17 节点 → 海外/直连源 → 解析 → 出 HTML |
| `fetch_overseas.py` | 直连源抓取（HuggingFace 等） |
| `fetch_hn.py` | Hacker News top，详情须 8 线程并发（串行 30 次会被 SIGTERM） |
| `parse_tophub.py` | tophub 节点页解析（⚠️ 页面结构是 `<table><tr>`，按 div 写会解析 0 条） |
| `parse_github.py` | GitHub Trending 解析（star 总数取不到，只用「今日新增 star」当热度） |
| `make_pool.py` | 去重 / 跨源合并 / 排序 / 出选题池 HTML（主体，2026-10-09 重做版） |

产物：`C:\选题\今日AI科技选题池_<日期>.html` —— **单文件**，AI 与科技同页、章内分节
（`A`=AI / `T`=科技 / `H`=钩子候选 / `M`=推荐补位）。

## 用法

```bash
bash run_daily.sh 2026-10-10             # 抓取 + 出池（完整链路）
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
