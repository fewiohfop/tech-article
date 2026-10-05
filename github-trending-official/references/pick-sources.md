# 方向 B「好用的项目 / 工具」的多源采集

用户 2026-09-29 明确：判断依据**可以来自周榜，也可以来自其他渠道**——
GitHub 自身推荐、第三方站、甚至我们要发布的平台（抖音 / 小红书 / X）上的推荐。
只要是好项目就可以分享。

本文件记录**实测过的渠道**与抓取路径。标「实测」= 2026-09-29 本机真跑过。

---

## 一、渠道清单

| 优先级 | 渠道 | 通道 | 状态 | 拿到什么 |
|---|---|---|---|---|
| ① | `https://hellogithub.com/` | WebFetch 直读 | ✅ 实测 | **中文一句话说明 + 星标数 + 日更**，最省事 |
| ② | `https://github.com/explore` | WebFetch 直读 | ✅ 实测 | 官方 Trending / Popular topic / **Collections 精选** / **官方 staff 推荐的 Marketplace 工具** |
| ③ | 本 skill 脚本的**周榜** | 本地脚本 | ✅ 实测 | star 增量排序 + `is_tool` 标记，筛候选最快 |
| ④ | `https://www.producthunt.com/` | WebFetch 直读 | ✅ 实测 | 今日/昨日/上周/上月 Top，**带 upvote 数**，偏商业产品 |
| ⑤ | 今日热榜 `tophub.today` | WebFetch | ✅ 实测 | 国内媒体推荐、榜单文章 |
| ⑥ | 抖音总榜 `tophub.today/n/DpQvNABoNE` | WebFetch | ✅ 实测 | 站内热点，判断「这个题材有没有人看」 |
| ⑦ | X 前沿（聚合站转载） | WebSearch + `allowed_domains` | ✅ 实测 | 海外开发者口碑 |
| ⑧ | Reddit（`r/LocalLLaMA` 等） | PowerShell `.rss`，**需 VPN，限速 ≥5 秒** | ✅ 实测 | 技术社区真实讨论 |
| ⑨ | `github-check`（市场 skill） | — | ⚪ 未安装 | 判断是否刷 star / 可否安全采用 |

**默认并发跑 ①②③，再按题材补 ④–⑧。** 不要只跑一个源就交差。

---

## 二、各渠道抓取要点

### ① HelloGitHub —— 最省事的入口

- WebFetch 直读 `https://hellogithub.com/`，**无需 VPN**
- 每条自带：项目名 / **中文一句话说明** / 作者 / 语言 / 星标数 / 相对时间 / 项目页链接
- 页面结构是「卡片流」，当期 20 条左右，**大量条目是 AI 技能包**
  （实测当期就有 `handraw-style` 手绘风格 AI 生图技能包、
  `threejs-architecture-effects`、`srt-whiteboard-animation`、`skills-manager`）
- 站内项目页形如 `https://hellogithub.com/repository/<owner>/<repo>`，
  可作为中文说明的**二手来源**；具体数字仍需回 GitHub 一手核对

> ⚠️ 它的中文说明是**编辑撰写的二手描述**，不是官方原文。
> 进内容前必须回 GitHub 仓库 README 复核，**不可当 L1**。

### ② GitHub Explore —— 官方推荐口径

- WebFetch 直读，**服务端渲染，无需 JS**
- 四个可用版块：
  1. **Trending repository**（官方展示的当日热门）
  2. **Popular topic**（热门话题）
  3. **Collection recommended by GitHub**（官方精选合集，如
     `github.com/collections/<slug>`，合集本身有条目数）
  4. **This recommendation was created by GitHub staff**（官方员工推荐的工具）
- 适合用来回答「**官方**推荐了什么」，比社区榜单更有权威性

### ③ 本 skill 的周榜 + `is_tool`

```powershell
$py = '<python.exe 路径>'
$s  = '<本 skill 目录>\scripts\github_trending_official.py'
& $py $s --period weekly --json --out "$env:TEMP\gh_weekly.json"
```

读 `period_stars` 排序，先看 `is_tool: true` 的。
**`is_tool` 是关键词启发式，会误判也要漏判**，它只是排序辅助，
不能当分类结论写进成品。

### ④ Product Hunt —— 商业产品与工具发布

- WebFetch 直读，**可读**（实测拿到今日 Top 22 + 昨日 + 上周 + 上月）
- 每条：产品名 / **一句话 tagline** / 分类标签 / upvote 数
- 偏「产品」不偏「开源」，**适合与 GitHub 项目做互补**：
  GitHub 找开源实现，Product Hunt 找同名商业产品做对比
- 注意：它是**发布当天**的榜，产品热度衰减快，隔几天再推要重新核实时效

### ⑤–⑧ 复用既有文档

- tophub 节点清单、X 聚合站域名、Reddit `.rss` 用法：
  直接看 `article-to-xhs/references/sources.md`，**不要重复调研**
- 抖音站内榜：`article-to-douyin/references/sources.md`

---

## 三、选取标准（5 条，缺一不可）

1. **有明确使用场景** —— 能一句话说清「谁在什么情况下会用它」
2. **上手成本可描述** —— 装什么、什么系统、要不要账号、要不要花钱
3. **有实证** —— Demo / 截图 / 真实数据 / 用户反馈，至少占一样（对应 §B 的 P4）
4. **还活着** —— 近期有提交或发版；看仓库的 last commit 与 issue 响应
5. **不与已发内容重复** —— 发文前查 `C:\小红书\` 与 `C:\抖音\` 已有目录

> 「火」不等于「好用」。榜单排名只用来**发现候选**，
> 最终入选靠上面 5 条。

---

## 四、去重与合并

同一项目被多个渠道命中时**合并为一条**并记录命中渠道数——
命中越多说明此刻共识越强，优先做。

跨渠道匹配用 `owner/repo` 作主键（GitHub 项目）；
Product Hunt 类非开源产品用产品名做近似匹配，**匹配不确定就分列，不要硬并**。

---

## 五、核实（进 §B 的 P4 之前）

- 项目名 / 作者 / 语言 / 星数 / 许可证 → **回仓库首页看**
- 「能做什么」→ **回 README 看**，不要用第三方一句话说明当能力清单
- 「实例认证」→ 优先用仓库里的 Demo / 截图 / benchmark；用第三方案例要标来源
- 星数是否虚高 → 送 `github-check`
- 涉及具体数字（性能、准确率）→ 按 `article-to-xhs/references/fact-check.md`
  的三级标注处理

**找不到实证的项目，宁可不做，也不要靠推测把它写「好用」。**
