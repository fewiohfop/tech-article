# 素材源与抓取路径

实测时间：**2026-09-28**（含用户开启 VPN 后的复测）→ **2026-10-01 追加全科技赛道源体检**（见第七节）。标「实测」= 本机真跑过；标「调研」= 查到的方案未验证。

> **复测记录**：初测时本机无代理，Reddit / X / HN 全部 `fetch failed`。
> 用户随后开启 VPN（系统代理 `127.0.0.1:10808`），以下结论是**开启后**重测得到的。
> 注意：工作区的 WebFetch 工具**不走系统代理**，所以 WebFetch 对这些站点仍然失败；
> 能通的是 **PowerShell 的 `Invoke-WebRequest`**（它读系统代理设置）。

---

## ⓪ 多源并行收集（用户 2026-09-28 明确：今日热榜和 X 都收，其他渠道也可以）

选题阶段**默认四路并发**，不要只跑一个源就交差：

| 顺序 | 源 | 通道 | 是否需 VPN | 拿到什么 |
|---|---|---|---|---|
| 1 | 今日热榜 | WebFetch 直读 | 否 | 国内 AI/科技条目 + 原始链接 + 热度 |
| 2 | X 前沿 | WebSearch + 域名限定 | 否 | 聚合站转载的 X 原帖（带作者时间） |
| 3 | Reddit | PowerShell `.rss` | **是** | 标题 / 时间 / permalink（**无分数**） |
| 4 | HN / GitHub Trending | WebFetch | HN 需、GitHub 否 | 技术社区当日热点 |

**合并规则**：同一条新闻被多个源命中时**合并为一条**并标注命中数——命中越多说明此刻热度越高，
优先做。最终按来源分组呈现给用户挑。

Reddit 批量抓取片段（PowerShell，注意限速）：

```powershell
$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36'
$subs = @('LocalLLaMA','singularity','MachineLearning','OpenAI','ClaudeAI')
$out = @()
foreach ($s in $subs) {
  try {
    $r = Invoke-WebRequest -Uri "https://www.reddit.com/r/$s/top/.rss?t=day" `
         -UserAgent $UA -TimeoutSec 25 -UseBasicParsing
    $titles = [regex]::Matches($r.Content,'<title>(.*?)</title>') | ForEach-Object { $_.Groups[1].Value }
    $out += "### r/$s (" + $titles.Count + ")"
    $out += $titles
  } catch { $out += "### r/$s FAIL $($_.Exception.Message)" }
  Start-Sleep -Seconds 6      # 必须限速，连发即 429
}
$out | Out-File "$env:TEMP\_reddit.txt" -Encoding utf8
```

> 不带 `t` 参数的 `.rss`（如 `/r/x/.rss`）实测**返回 429**，务必带上 `?t=day`。

---

## 一、今日热榜 tophub.today —— 主力源，已跑通

### 实测结论

| 测的东西 | 结果 |
|---|---|
| `https://tophub.today/` 首页 | ✅ 可抓 |
| `https://tophub.today/c/tech` 科技分类 | ✅ 可抓，415 个节点 |
| `https://tophub.today/c/ai` AI 分类 | ✅ 可抓，215 个节点 |
| `https://tophub.today/n/<id>` 单节点页 | ✅ 可抓，拿到条目标题 + **原始链接 + 来源媒体名 + 热度值** |

页面是服务端渲染的静态 HTML，**WebFetch 直读即可，不需要 Playwright**，
也不需要 VPN。

### 节点清单

**AI 分类（共 215 个节点，首页展示 12 个）**

| 节点 | 链接 |
|---|---|
| 掘金 | https://tophub.today/n/rYqoXz8dOD |
| 量子位 | https://tophub.today/n/MZd7azPorO |
| AIbase | https://tophub.today/n/ENeYylkeY4 |
| 产品经理的人工智能学习库 | https://tophub.today/n/DOvnyGpoEB |
| AI工具集 | https://tophub.today/n/8Rv2NjnvLw |
| MIT Technology Review（Top Stories） | https://tophub.today/n/7GdabqLeQy |
| 36氪 AI 频道 | https://tophub.today/n/x9oz2O1oXb |
| AI产品榜 | https://tophub.today/n/proPKWkeq6 |
| Google AI Blog | https://tophub.today/n/1Vd58gW85 |
| MIT Technology Review（All Stories） | https://tophub.today/n/yjvQDK6obg |
| CSDN博客 人工智能热榜 | https://tophub.today/n/47o8bRLdMm |
| ~~超神经~~ | ~~https://tophub.today/n/4MdA863vxD~~ ❌ 2026-09-30 复测返回 1 月旧稿，**弃用** |

**科技分类（共 415 个节点，首页展示 8 个）**

| 节点 | 链接 |
|---|---|
| 36氪 24小时热榜 | https://tophub.today/n/Q1Vd5Ko85R |
| 少数派 热门文章 | https://tophub.today/n/Y2KeDGQdNP |
| 虎嗅网 热文 | https://tophub.today/n/5VaobgvAj1 |
| 果壳 科学人 | https://tophub.today/n/20MdK2vw1q |
| IT之家 日榜 | https://tophub.today/n/74Kvx59dkx |
| 爱范儿 每日最新 | https://tophub.today/n/74KvxK7okx |
| 科普中国网 | https://tophub.today/n/DgeyxkwdZq ❌已弃用 |
| **极客公园** | https://tophub.today/n/**NRrvWYDe5z** ✅ |
| 36氪 最新 | https://tophub.today/n/KqndgapoLl ❌已停更 |

> 🔴 **节点 id 纠错（2026-10-08）**：极客公园的正确 id 是 **`NRrvWYDe5z`**。
> 本文件与 `SKILL.md` 曾长期写作 `NaEdZZXdrO` —— **那个 id 实际指向「少数派最新文章」**。
> 因此「极客公园已弃用」是**抓错节点造成的误判**，实际该源一直可用。
> 📌 **引用任何 tophub 节点前，先抓一次核对页面标题与媒体名对得上。**

### 选题适配度

- **量子位、极客公园** —— 信息密度最高，代码/参数/数据多，最适合做卡片。极客公园的「极客早知道」
  一帖聚合多条快讯，**单帖能拆出 3–5 条选题**，是科技线最高效的源。
- **36氪 AI 频道** —— 更新最快（分钟级），但只有它与 36氪 24h 有当日内容
- **IT之家 / 威锋 / 爱范儿** —— 数码快讯为主，适合短平快的单点话题。**威锋 30 条全当日**且带站内热度值，
  是科技线单日产量最高的节点
- **果壳** —— 诺奖/基础科学专题，**单轮可出 10 条**，是「基础科学」赛道唯一主力
- **Readhub** —— 快讯聚合，车企交付/科研/政策覆盖好，无热度值
- **少数派 / 虎嗅** —— 产品体验与商业分析，适合观点型笔记（虎嗅有阅读量数值）

### ⚠️ 时效性坑（2026-09-29 首次总结，2026-10-08 全面复测）

tophub **抓得到 ≠ 抓到的内容是今天的**。有些节点早已停更或指向归档页，
返回的却是几年前的旧文，混进选题池就是事故。实跑中过招的节点：

| 节点 | 实际返回 | 处理 |
|---|---|---|
| **超神经 `4MdA863vxD`** | **2026-09-30 复测返回 2026-01-15 的旧稿（差 8 个多月）** | **弃用**（⚠️ 09-29 曾误标为 ✅，已修正） |
| 科普中国网 `DgeyxkwdZq` | 链接为 `.../202109/t20210929_...` 路径，2021 年内容（**2026-10-08 复测仍如此**） | **弃用** |
| Google AI Blog `1Vd58gW85` | 2024 年 1–3 月文章（09-30 复测仍如此） | **弃用**（该源本身已停更） |
| 产品经理的人工智能学习库 `DOvnyGpoEB` | 页面统一显示 2026-02-27（09-30 复测） | **弃用**，更新极慢 |
| **36氪最新 `KqndgapoLl`** | **页面标注更新停在 2026-08-05**，一个多月未更新（2026-10-08 实测） | **弃用**（⚠️ 它是快讯流，停更后无提示，最容易误采信） |
| AI产品榜 `proPKWkeq6` | 条目内容可读，但**原始链接是 `aicpb.com/news/iframe?world=...` 占位地址，点不开** | ⚠️ 能用但需站内按标题检索 |

**复核方法（每次改节点都跑一遍）**：抓节点页 → 看「时光机」当日快照有没有条目 →
没有就查页面自己标的更新时间 → 时间超过 1 个月直接弃用，并把 id 记进这张表。

| CSDN 人工智能热榜 `47o8bRLdMm` | 能抓，但条目多为教程/征稿，热度 2–5 万且与新闻无关 | 不用作选题源 |

**自检规则（进选题池前逐条过）**：
1. 看条目 URL 里的年月，与今天差超过 1 个月的**直接丢**；
2. 看榜单页有没有「上榜时间」（36氪 24h 节点会显示 `08:10 [标题]`）——有时间的可信；
3. 同一节点连续两天返回**完全一样的条目**，说明它已停更，从节点清单里划掉；
4. **节点页里所有条目显示同一个日期**（如整齐的 `2026-01-15`）= 该页是归档，直接弃用
   —— 09-30 的超神经就是这样被抓出来的。

可靠度排序（2026-09 实测）：36氪 24h ≈ 36氪 AI > IT之家日榜 > 爱范儿 ≈ 量子位 > 掘金 > 少数派 > 虎嗅 > 果壳。

### 境外源：开 VPN 时的实测表现（2026-09-30 复测）

- 探测方式：读注册表 `HKCU:\...\Internet Settings` 的 `ProxyEnable` / `ProxyServer`，
  本次为 `1` / `127.0.0.1:10808` → **VPN 开启状态**。
- 开启后：**Hacker News 200**（HTML 直读，正则取 `<span class="titleline">` 与 `<span class="score">`
  即可拿到「标题 + 分数」）、**Reddit r/singularity `.rss` 200**。
- ⚠️ **Reddit 连抓两个板块会触发 429**：本轮 r/singularity 成功后，
  r/artificial 与 r/LocalLLaMA 均返回 `429 Too Many Requests`。
  **多个板块要串行且间隔 ≥6 秒**，仍可能被限 → 此时如实记为「限流，非源失效」。
- ⚠️ **Reddit RSS 解析坑**：用 `<entry>.*?<title>(.*?)</title>.*?<link href="(.*?)"` 配 `Singleline`
  会**跨条目贪婪匹配，导致标题与链接错位**（标题是第 N 条、链接给了第 N+1 条）。
  正确做法：先 `-split '</entry>'` 切分，再在每段内单独匹配 title 与 link。
  拿到结果后**抽查 1–2 条链接与标题是否对得上**再写进选题池。

---

## 二、境外站点可达性（2026-09-28 开 VPN 后复测）

| 站点 / 端点 | 无 VPN | 开 VPN 后 | 说明 |
|---|---|---|---|
| github.com | ✅ | ✅ | — |
| news.ycombinator.com | ❌ | ✅ 200 | 域名可达，HTML 直读 |
| x.com（域名） | ❌ | ✅ 200 | **但正文拿不到**，见第三节 |
| reddit.com `/r/x/top.json` | ❌ | ❌ 403 | **Reddit 已在网络层封锁匿名 JSON** |
| reddit.com `/r/x/top/.rss?t=day` | ❌ | ✅ 200，81 KB 有效 Atom feed | **✅ 目前唯一可用的零认证通道** |
| reddit.com `/r/x/.rss`（不带 t） | ❌ | ❌ 429 | 触发限速，**必须限流** |
| old.reddit.com `/r/x/top/.rss` | ❌ | ⚠️ 返回登录墙页，**不是 feed** | 不要用 |
| rsshub.app | ❌ | ❌ 403 | 公共实例已封 |
| r.jina.ai（**含 example.com**） | — | ❌ 403 | **要求 API Key，不再是免费无 Key** |
| Nitter（nitter.net / poast.org / xcancel） | ❌ | ❌ 连接被关 / 451 | 公共实例全线死亡 |

### 一句话结论

- **Reddit 可以抓了** → 走 `.rss`，零认证，**但必须限速**
- **X 仍抓不到正文** → 域名通不等于内容可读
- **Jina Reader 不能再用作免费降级**（这条推翻了本 skill 早期版本的写法）
- **VPN 关掉时境外源直接归零** → 2026-09-29 复测：系统代理 `ProxyEnable=0` 时，
  HN 与 Reddit 的 `Invoke-WebRequest` **全部「操作超时」**，WebFetch 走 HN 也报 `fetch failed`
  （WebFetch 本就不走系统代理）。⚠️ 此时选题池末尾**必须单列「本轮未采到的源 + 原因」**，
  写清是「网络不可达」而非「源失效」——**不允许省略，也不允许用推测补**。

### 聚合站命中率（2026-09-29 复测，第二次验证）

4 组关键词做 `allowed_domains` 限定检索，**2 组有返回、2 组返回 0**：

| 检索方向 | 结果 |
|---|---|
| OpenAI / Anthropic 模型发布与评测 | ✅ 命中 officechai.com 2 篇（含完整基准数据） |
| Claude Opus / GPT-6 榜位 | ✅ 命中同一篇（去重后 1 篇） |
| Google Gemini / DeepMind 发布 | ❌ 返回 0 |
| AI hardware / robotics / chip | ❌ 返回 0 |

**结论**：这批站是「AI 模型」专用富矿，**机器人 / 芯片方向两次实测均为 0**（与 skill 正文的判断一致）。
机器人方向改用超神经、量子位、36氪 AI 频道等国内源。

---

## 三、Reddit 抓取路径（✅ 本机实测可用）

### 可用端点

```
https://www.reddit.com/r/<sub>/.rss                    # 新帖
https://www.reddit.com/r/<sub>/top/.rss?t=day          # 日榜（t=hour|day|week|month|year|all）
https://www.reddit.com/r/<sub>/hot/.rss
https://www.reddit.com/search.rss?q=<关键词>            # 全站搜索
https://www.reddit.com/r/<sub>/search.rss?q=<kw>&restrict_sr=1
https://www.reddit.com/r/<sub>/comments/<id>/.rss      # 某帖的评论
```

### 强制注意事项

- **必须带描述性 User-Agent**，格式 `平台:应用:版本 (by /u/用户名)`，
  只写 `Mozilla/5.0` 不够，容易被拦。
- **必须限速**。实测不带 `t` 参数连发即返回 **429**。建议**每次请求间隔 ≥ 5 秒**，
  遇 429 退避 60 秒。
- **RSS 的能力边界**（RSS ≠ API，要提前跟用户说清）：
  - ✅ 有：标题、作者、发帖时间、正文摘要、**permalink**
  - ❌ 没有：**得分（score）、评论数、点赞率**
  - ❌ 评论是**平铺列表**，没有父子层级
  - ❌ 单次上限约 **25 条**
- 想要 score / 嵌套评论，只能上官方 OAuth API（需预审批）或付费托管 API。

### 值得关注的 AI 社区（AI/科技选题富矿）

`r/LocalLLaMA`、`r/singularity`、`r/MachineLearning`、`r/OpenAI`、`r/ClaudeAI`、`r/StableDiffusion`

### 现成轮子（GitHub，2026-09 检索）

| 项目 | 说明 | 与实测是否吻合 |
|---|---|---|
| **ninjackster/reddit-rss-mcp** | 零依赖 MCP server，只走 RSS。支持 search / browse subreddit / 读评论。无需 key、无 OAuth | ✅ **与本次实测完全一致**——该项目的说明文档同样写明「Reddit 已在网络层封掉匿名 JSON，但 RSS 仍返回 200」。**推荐。** |
| ReScienceLab/opc-skills · reddit | 1.8k star，2026-09-05 更新，走公开 JSON API | ⚠️ 它宣称 `.json` 可用，但**本机实测 403**。以实测为准，别照搬 |
| openclaw-skills/reddit-readonly | 走 public JSON，带 `REDDIT_RO_MIN_DELAY_MS` 等退避参数 | ⚠️ 同上，JSON 路径存疑；但它的**退避设计值得借鉴** |
| ChocoData 商业 API | 免费 1000 次；$ 付费扩展 | 托管方案，免维护 |

---

## 四、X（Twitter）抓取路径（❌ 正文仍不可得）

### 实测：域名通，内容不通

| 测的东西 | 结果 |
|---|---|
| `https://x.com/<user>` | ✅ 200，186 KB HTML |
| 该 HTML 里有没有推文？ | ❌ **没有**。`data-testid` 计数 = **0**，React 未服务端渲染 |
| 能拿到什么？ | 仅 `og:title`、`og:description`（**个人简介**），没有任何一条推文正文 |
| `publish.twitter.com/oembed` | ❌ 404 |
| `cdn.syndication.twimg.com/tweet-result` | ⚠️ 端点可达，但需**真实推文 ID + 正确 token**，本次无法构造，**未验证** |
| Nitter 公共实例 | ❌ 全死（nitter.net / nitter.poast.org 连接被关；xcancel 返回 451） |
| Jina Reader 渲染 | ❌ 403（要 API Key） |

**结论：X 在「无需登录」的前提下，目前拿不到推文正文。**

### 已经死掉的方案（2026 年不要再试）

| 工具 | 状态 |
|---|---|
| snscrape | 最后可靠提交停在 2023 年，X 端点变动后失效 |
| Twint | 仓库已归档 |
| Nitter | 公共实例被 X 封锁，仓库已归档 |

根因：**X 在 2023 年关闭了匿名访客访问**，所有还能用的方案都必须登录。

### 仍可用但代价高的（都需要真实账号）

| 方案 | 类型 | 成本 | 备注 |
|---|---|---|---|
| twscrape | 开源 Python | 免费 + 账号 + 住宅代理 | 走内部 GraphQL，可轮换多账号 |
| Scweet | 开源 Python | 免费 + 账号 | 最简单的 cookie 方案 |
| Rettiwt-API | 开源 TypeScript | 免费 + 账号 | Node 项目 |
| 官方 API（tweepy） | 官方 | 按量付费 | **免费额度已于 2026-02-06 取消** |
| Apify Tweet Scraper V2 | 托管 | $0.40 / 1000 条 | 免维护 |
| Sorsa API | 只读数据 API | 从 $0.02 / 1000 条 | 最便宜的托管选项 |

**风险**：账号驱动型爬虫违反 X 服务条款，可能封号；X 每 2–4 周轮换 token，工具周期性失效。

**法律红线**：X 条款禁止未经书面许可的爬取；美国条款（2026-04-10 生效）规定
单日访问超 100 万条推文需付 $15,000 / 百万条违约金；EU / EFTA / UK 条款（2026-01-15 生效）为 EUR 15,000。

### ✅ 实际推荐的替代路径（2026-09-28 实测有效）

1. **第三方聚合站转载 —— 本轮实测最有效的一条，已定型为固定做法。**
   这些站会**逐字转载 X 原帖**（带作者、时间戳），用 WebSearch 的 `allowed_domains`
   限定域名检索，一次就能拿到一批：

   ```
   allowed_domains: ["officechai.com", "nokiapoweruser.com", "kocpc.com.tw",
                     "tldrocket.com", "promptblueprints.tech", "dataconomy.com"]
   ```

   | 域名 | 侧重 |
   |---|---|
   | officechai.com | **产量最大、信息最密**，含官方基准逐项拆解 |
   | nokiapoweruser.com | 谷歌 / Android 生态，Arena 与泄露跟踪 |
   | kocpc.com.tw | 繁中，含原帖截图与开发者引述 |
   | tldrocket.com | 短摘要 + 行业解读 |
   | promptblueprints.tech | 单条爆料的结构化拆解（会标注哪些未证实） |

   **实测战果**：Gemini / OpenAI / Anthropic 三个方向各检索一次，**各拿到 5 篇**，
   全部带 X 原帖引用（@thtbee_、@LuminaBench、@HarshithLucky3、@hakmgpt、@MaaSonder 等）。
   结果已整理为 `C:\小红书\选题\海外AI前沿选题池_2026-09-28.html`（20 条）。

   **边界**：这批站以「AI 模型」新闻为主，**机器人 / 芯片 / 具身智能类命中率低**
   （实测两次均返回 0 结果）——那类需求改用通用检索或国内媒体。

   ⚠️ 聚合站仍是**二手转载**。进事实核验时必须回到一手源（官方博客 / 原论文 / 原帖）
   复核具体数字，**不可直接当 L1 使用**。

2. **借道国内媒体** —— 新智元、量子位、机器之心、雷科技大量翻译引用 X 原帖，
   通过 tophub 的「36氪 AI 频道」就能拿到（实测已抓到多条 `x.com` 来源的报道）。

3. **WebSearch 摘要** —— 搜索工具能返回 X 内容的摘要，不需要直连。

4. **兜底：让用户手动粘贴或截图。**

---

## 五、小红书 / 抖音站内热点

未实测。可用方向：

- tophub 的「实时榜中榜」`https://tophub.today/hot` 含部分社交平台热榜
- 小红书站内热点需登录态，**不建议自动化**（账号风险，理由同 `why-no-autopublish.md`）
- 变通做法：把外部热点（AI 新闻）转成小红书语境，而不是追站内热榜

---

## 六、选题不考虑用户背景（用户 2026-10-01 明确）

**做选题发现时，不把用户的个人背景、职业经历、以往内容方向当作筛选或加权因素。**
不做「这个跟他以前的经历有关，优先给他」这类推断，也不做「这不在他的舒适区，略过」这类过滤。

选题只按内容本身判：**此刻热度 + 可做度 + 与账号 AI/科技定位是否匹配**。

> 注意与「发布前查重」区分：查重（`C:\小红书\` / `C:\抖音\` 已有目录里是否做过同一事件）
> 是用户单独提出的硬规则，**继续执行**，不属于本条要取消的「历史考量」。
> 本条取消的是**选题阶段的个人化加权**，不是成稿前的去重。

---

## 七、科技赛道扩展：本轮实测新增源（2026-10-01，GMT+8 18:30–19:15）

前述各节以 **AI** 源为主。要覆盖**全科技赛道**（消费电子 / 汽车 / 机器人 / 航天 / 半导体 / 生命科学），
需要补两类源：**tophub 新节点** 与 **垂直原站**。以下是本轮真跑的结果。

### 7.1 tophub 新增可用节点（科技分类）

| 节点 | 节点 id | 状态 | 特征 |
|---|---|---|---|
| **威锋网** | `n4qv90roaK` | ✅ 本轮新发现 | 苹果生态垂直，30 条**全是当日**，**热度值可读**（站内数值，口径页面未说明） |
| **Readhub** | `Y3QeLMPo7k` | ✅ 本轮新发现 | 快讯聚合，**车企交付 / 科研 / 政策**覆盖好，适合非 AI 赛道补位 |

> 威锋网是本轮最实用的一条：既有垂直度（苹果/消费电子），又是唯一「30 条全当日 + 热度可读」的节点。

### 7.2 热度口径（⚠️ 关键限制：不可横向比较）

**tophub 绝大多数节点页面根本不提供热度字段。** 实测只有 3 个节点能读到数字，且**含义各不相同**：

| 节点 | 数字是什么 | 能否比较 |
|---|---|---|
| 虎嗅网 热文 `5VaobgvAj1` | 阅读量（单位「万」） | 仅节点内纵向 |
| IT之家 日榜 `74Kvx59dkx` | **「N 评」＝评论数，不是热度** | ❌ |
| 威锋网 `n4qv90roaK` | 站内数值，**单位与口径页面未说明** | ❌ 未核实 |

**规则**：跨源汇总时**不要拿这几个数字做统一排序**，只能作为「该源内部谁更热」的参考，
并在选题池里显式标注口径。没有热度值的源，用「命中源数量」代替热度信号（见 ⓪ 节的合并规则）。

### 7.3 垂直原站探测结果（curl `--noproxy '*'` 直连）

**国内 ✅ 200**

| 站点 | 地址 | 覆盖车道 |
|---|---|---|
| 快科技 | `https://m.mydrivers.com/newsclass.aspx` | 消费电子 / 数码 |
| cnBeta | `https://www.cnbeta.com.tw/` | 科技综合快讯 |
| 中关村在线 | `https://www.zol.com.cn/` | 消费电子 |
| IT之家（电脑版） | `https://www.ithome.com/` | 数码快讯 |
| 爱范儿 | `https://www.ifanr.com/` | 产品 / 汽车 |
| 智东西 | `https://zhidx.com/` | 智能硬件 / 机器人 |
| 盖世汽车 | `https://auto.gasgoo.com/` | **汽车产业链** |
| 汽车之家 新闻 | `https://www.autohome.com.cn/news/` | 汽车 |
| 科学网 | `https://news.sciencenet.cn/` | **基础科学 / 生命科学** |
| 生物谷 | `https://www.bioon.com/` | 生物医药 |

**国内 ❌ 不可达**：集微网 `jiweinet.com`（000）、航天爱好者网 `spaceflightfans.cn`（000）。

**境外 ✅ 可达**（走系统代理；`curl` 直连需先 `env -u HTTP_PROXY ...`）
The Verge 200 · TechCrunch 200 · Wired 200 · IEEE Spectrum 200 · Tom's Hardware 200 ·
Engadget 202 · **SemiEngineering 200（半导体垂直）** · Nature News 200 · New Scientist 200

**境外 ⚠️ / ❌**
- Hacker News：`curl` 走代理 **000**，但 **PowerShell `Invoke-WebRequest` 200**（以 PowerShell 为准）
- Ars Technica：**405**（服务端拒绝非浏览器请求）
- SpaceNews：**403**

### 7.4 赛道覆盖矩阵（实测结论，用于判断「这个赛道该去哪个源」）

| 赛道 | 有源 | 缺口 |
|---|---|---|
| AI 模型与产品 | ✅ 强（tophub AI 节点 / HN / X 聚合站 / aihot） | — |
| 开发者工具与开源 | ✅ 强（GitHub / HN） | — |
| 消费电子与芯片 | ✅ 可用（威锋网 / IT之家 / SemiEngineering） | 国内半导体垂直源不可达（集微网） |
| 智能汽车与出行 | ✅ 可用（Readhub / 盖世汽车 / 汽车之家） | — |
| 机器人与具身智能 | ⚠️ 仅通用源（量子位 / 智东西 / 36氪 AI） | **无垂直源**；X 聚合站两次实测命中 0 |
| 生命科学与健康 | ✅ 可用（科学网 / 生物谷） | — |
| 基础科学与科普 | ✅ 可用（果壳 / Nature News / New Scientist） | — |
| **航天与前沿工程** | ❌ | **无源**：航天爱好者网不可达、SpaceNews 403 |
| 互联网产品与商业科技 | ✅ 强（36氪 / 虎嗅 / 少数派） | — |
| 财经与资本市场 | ✅ 可用（36氪 最新 / Readhub） | — |

**结论**：全科技赛道里**航天是唯一完全无源的赛道**，机器人只有通用源。
遇到这两类需求要**如实告知用户覆盖有限**，不要用 AI 源硬凑。

### 7.5 另一条可选通道：aihot API

`aihot.virxact.com` —— **匿名只读，无需 Key**，中文 AI 资讯策展。

```
/api/v1/items?mode=selected&window=24h        # 今天 / 过去 24 小时
/api/v1/items?mode=selected&window=7d&limit=10 # 最近一周
```

状态：**接口存在，本轮未实跑**（未验证返回结构）。要用先跑一次确认，别当已通。

### 7.6 明确排除，不要再试

- **常规社会热榜**：抖音/微博/百度/B站/快手热搜、音乐榜、猫眼票房、App Store 榜、人民日报
  —— 与账号 AI/科技定位冲突（用户 2026-09-29 明确分离）
- **已死方案**：Nitter 公共实例、rsshub.app 公共实例、Jina Reader（要 Key）、snscrape、Twint

---

## 八、总表

| 源 | 可达 | 自动化 | 建议 |
|---|---|---|---|
| tophub.today | ✅ | ✅ 全自动 | **主力源** |
| tophub · 威锋网 `n4qv90roaK` | ✅ | ✅ | **新增**，苹果生态垂直，全当日 + 热度可读 |
| tophub · Readhub `Y3QeLMPo7k` | ✅ | ✅ | **新增**，车企交付 / 科研 / 政策补位 |
| 36氪 / 量子位 / 少数派等原站 | ✅ | ✅ | WebFetch 直读正文 |
| 垂直原站（盖世汽车 / 汽车之家 / 科学网 / 生物谷 / 智东西） | ✅ | ✅ | **新增**，非 AI 赛道一手报道 |
| 境外媒体（The Verge / TechCrunch / Wired / IEEE Spectrum / Tom's Hardware / SemiEngineering / Nature / New Scientist） | ✅ | ✅ | **新增**，走系统代理 |
| GitHub | ✅ | ✅ | 技术选题补充 |
| **Reddit** | ✅（VPN + `.rss`） | ✅ 可自动化（**需限速**） | 抓标题/时间/链接够用；分数与嵌套评论拿不到 |
| **X** | ⚠️ 域名通、正文不通 | ❌ | **走第三方聚合站转载或 WebSearch** |
| Hacker News | ✅（VPN，用 PowerShell） | ✅ | HTML 直读；`curl` 走代理会 000 |
| aihot API | ⚠️ 接口在，未实跑 | ✅ | 中文 AI 策展，无需 Key |
| 微信公众号 | ⚠️ 需特殊通道 | ❌ | 让用户粘贴正文 |
| Jina Reader | ❌ 403 | ❌ | **要 API Key，不再免费直接用** |
| 集微网 / 航天爱好者网 / SpaceNews | ❌ | ❌ | 不可达或 403，**航天赛道无源** |

---

## 抖音独有：话题玩法、配乐、发布时间

> 2026-10-06 合并 `article-to-douyin` 时并入。**这三节仅抖音适用，小红书那套不适用。**

### 抖音总榜（做抖音优先看这个）

```
https://tophub.today/n/DpQvNABoNE
```

已实测可抓，WebFetch 直读。这是抖音站内热点的聚合视图，比抓抖音 App 更省事。

2026-09-29 实测补充：条目自带**作者名 + 播放量 + 作品链接**，页面顶部显示「最新总榜 N 分钟前更新」，
所以可以标注数据时点，不用猜。

> ⚠️ **实测结论：总榜对 AI / 科技选题帮助有限。** 2026-09-29 的 20 条里只有 1 条带 AI 标签，
> 且那是「AI 创作大赛」的参赛作品，不是 AI 新闻；其余是央媒正能量、搞笑、游戏、情感、音乐。
> 推论：**做 AI / 科技内容不要指望总榜带量，要靠搜索流量**（与 SKILL 里「推荐约 70% + 搜索约 30%」吻合）。
> 总榜的正确用法是：① 看平台在推什么官方活动（本次看到 #抖音ai创作大赛 #即梦AI创作者成长计划）；
> ② 看哪些非科技题材（出片、旅拍）被验证过有流量，作为跨题材参考。

### 🚧 选题不看用户背景（用户 2026-10-01 明确要求）

**做选题发现时，不要把用户的个人背景、职业经历、以往内容方向当作筛选或加权因素。**

- ❌ 不做「这个跟他以前的经历有关，优先给他」
- ❌ 不做「这不在他的舒适区 / 他没做过这个方向，略过」
- ✅ 只按内容本身判：**此刻热度 + 可做度 + 与账号 AI/科技定位是否匹配**

> 与「发布前查重」不冲突：查 `C:\小红书\` / `C:\抖音\` 已有目录、同一事件做过就 pass，
> 是用户单独提出的硬规则，**继续执行**。本条取消的是**选题阶段的个人化加权**，不是成稿前的去重。

## 三、话题玩法（抖音特有，小红书那套不适用）

### 核心原则：话题不是流量开关，是内容分类信号

它不负责给你流量，它负责告诉系统「这条该给谁看」。
**选话题的标准不是它多热，是它多准。**
一个 50 万播放的精准话题，比一个 5 亿播放的泛话题有用得多——后者的池子里
全是跟你不相干的内容，你根本排不上号。

### 三级结构（3–5 个，最精准的放最前面）

| 类型 | 加几个 | 作用 | 示例（AI 科技号） |
|---|---|---|---|
| **精准内容标签** | 2–3 个 | 告诉系统这条讲什么，找对人群 | `#大模型评测` `#AI工具` |
| **场景人群标签** | 1 个 | 把人群再切细，吃长尾搜索 | `#程序员日常` `#AI学习` |
| **热点 / 活动标签** | 0–1 个 | 有匹配的官方活动才加，没有就空着 | 当期官方话题 |

**顺序：精准在前、泛在后。** 话题栏里的词同时也是搜索词，前面的权重更高。

### 四种白加的加法（避免）

1. **堆流量词**：`#热门` `#上热门` `#涨粉` —— 没有内容含义，系统无法提取分类信息
2. **加满十个**：等于告诉系统「我什么都是」，结果什么都不精准
3. **蹭不相干热点**：播放可能高一次，但账号标签被搅乱，要养很久才回来
4. **每条都用同一套话题**：不同内容该进不同池子

> 以上为社区运营方的通行经验，多方口径一致，但**均非抖音官方公示规则**，
> 按 L2 / 经验规则使用，不要当硬性机制陈述。

---

## 四、配乐原则（图文也能配，影响完播）

- 节奏偏快、**无人声或纯音乐**为主 —— 有人声会干扰阅读
- 热度高的 BGM 有额外曝光加权
- 情绪要和选题匹配：争议类用紧张感，盘点类用轻快
- 在发布页选，不要提前写进文案

---

## 五、发布时间参考（社区经验，非官方）

- 优先：工作日 **07:30–08:30**、**18:00–19:30**
- 避开：午间 12:00–13:30、22:00 之后
