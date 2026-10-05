# 发布自动化：用「浏览器本体」跑（2026-09-29 方法更新）

本文件记录「本机半自动发布」这条路的**已验证**实现细节。用户环境：Windows + 夸克浏览器（Chromium 内核）+ 抖音图文。

> ⚠️ **方法已更新（2026-09-29）**
> 早期实现是「关夸克 → 复制 Cookie → 解密 → 注入自建 Chrome」。用户指出这个思路不对：
> **夸克里本来就有登录态，不该把 Cookie 搬到另一个浏览器**。现已改为**直接用夸克本体跑**。
> 旧的跨浏览器搬 Cookie 路径保留在第三节末尾，仅作反面教材。

---

## 一、结论

| 项 | 状态 |
|---|---|
| Playwright 驱动**夸克本体** | ✅ 验证通过（启动 2.6 s，内核 Chromium 144） |
| 复用夸克登录态（免扫码、免搬 Cookie） | ✅ 验证通过（B 站 `isLogin=true`；抖音创作中心直达后台） |
| 消除 `navigator.webdriver` 自动化标志 | ✅ 验证通过（`true → false`） |
| 复用夸克现有抖音登录态（免扫码） | ✅ 验证通过 |
| 自动上传图文卡片（实测 2–9 张；上传框上限 35 张） | ✅ 验证通过 |
| 自动填作品标题 / 作品描述 / 话题 | ✅ 验证通过 |
| 自动设置「自主声明」 | ✅ 验证通过 |
| 自动点「发布」 | ❌ **刻意不做** |

「自动上传 + 填充完整、停在发布页」是收益与风险的拐点：省掉全部重复劳动，保留人工确认。再往下走即把账号交给脚本，平台处罚落在账号上。

---

## 二、核心方法：浏览器本体 + 它自己的 profile（推荐）

### 原则

**登录态在哪个浏览器里，就用哪个浏览器跑。** 绝不跨浏览器搬 Cookie —— 那会引入
域绑定加密、密钥迁移、指纹不一致等一整串问题（见第三节的反面教材）。

用户会**用不同浏览器登录不同账号**做区分；测试时**哪个有登录态就用哪个**。

### 标准写法

```js
const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
  executablePath: 'C:\\Users\\<user>\\AppData\\Local\\Programs\\Quark\\quark.exe',
  headless: false,
  ignoreDefaultArgs: ['--enable-automation'],               // 关键：去掉自动化标志
  args: ['--disable-blink-features=AutomationControlled'],  // 关键：navigator.webdriver → false
});
```

**两个参数必须同时给**，只给一个 `navigator.webdriver` 仍是 `true`。

### profile 目录怎么准备

夸克 User Data 约 **4 GB，不要整体复制**。实测只有三样是登录态必需：

| 文件 | 大小 | 运行时可否读 |
|---|---|---|
| `Local State`（含 DPAPI 加密的 AES 主密钥） | 34 KB | ✅ **可读**（无独占锁） |
| `Default\Network\Cookies` | 622 KB | ❌ **独占锁** |
| `Default\Preferences` | 200 KB | ✅ **可读** |

```js
fs.mkdirSync(path.join(PROFILE, 'Default', 'Network'), { recursive: true });
fs.copyFileSync(path.join(QUARK_UD, 'Local State'),                      path.join(PROFILE, 'Local State'));
fs.copyFileSync(COOKIES_SNAPSHOT,                                        path.join(PROFILE, 'Default', 'Network', 'Cookies'));
fs.copyFileSync(path.join(QUARK_UD, 'Default', 'Preferences'),           path.join(PROFILE, 'Default', 'Preferences'));
```

**为什么这样就能带登录态**（原理，别搞错）：
- AES 主密钥在 `Local State`，用 **Windows DPAPI** 加密（绑定当前 Windows 账户）→ **换目录仍能解密**
- Cookie 值的域绑定前缀是 `SHA256(host_key)`（只与域名相关）→ **与路径无关，复制后依然有效**
- 因此夸克启动这份副本 profile 时，**自己就能解密自己的 Cookie** —— 全程不碰加密逻辑

**Cookies 独占锁的绕法**：夸克运行时 `cp` / Python `open()` / `CreateFileW` 共享句柄 /
`esentutl /vss`（报 `0x80070005` 无备份权限）**全部失败**。只有两条路：
1. 用一份**已有快照**（`_quark_cookies_backup.db`）；
2. 关闭夸克后复制 —— 注意**关窗口 ≠ 退进程**，会残留 20+ 后台进程，
   必须 `taskkill /IM quark.exe /F /T` 或 `Stop-Process -Name quark -Force`。

### 实测证据（2026-09-29）

```
启动成功 2371 ms   browser().version() = 144.0.7559.86

B 站：webdriver=false，API isLogin=true，用户名=罗集，mid=32851208
抖音：creator.douyin.com/creator-micro/home（直达后台，非登录页，页面含「罗集 抖音号：40737032447」）
```

**B 站风控对比**（说明"用本体"确实更可信）：
`api.bilibili.com/x/space/arc/search` 在自建 Chromium 下是 `code=-352 风控校验失败` + HTTP 412，
换夸克本体后变为 `code=-799 请求过于频繁` —— **风控已过，只剩限流**。

---

## 三、附：已弃用路径（跨浏览器搬 Cookie，留作反面教材）

### 夸克环境定位（实测）

| 项 | 值 |
|---|---|
| 程序 | `%LOCALAPPDATA%\Programs\Quark\quark.exe` |
| 用户数据 | `%LOCALAPPDATA%\Quark\User Data`（标准 Chromium 结构） |
| Cookie 库 | `User Data\Default\Network\Cookies`（缓存日志模式，非 WAL） |
| 定位方法 | 注册表 `Uninstall` 键的 `DisplayIcon`；**不要**用 WScript.Shell 读 .lnk（本机 COM 实例化被安全策略拦截） |

**夸克运行中对 Cookie 库加独占锁**，以下方式全部实测失败：
`shutil.copy2`（WinError 32）、Python `open()`（PermissionError 13）、`cp`（Device busy）、
`CreateFileW` + `FILE_SHARE_READ|WRITE|DELETE`（错误码 32）。

→ **必须先关闭夸克。** 注意：**关窗口 ≠ 退进程**，夸克会留 20+ 个后台进程继续占着库，必须
`taskkill /IM quark.exe /F /T` 或 `Stop-Process -Name quark -Force` 清干净才算退出。

另外：夸克在 `127.0.0.1:9128` 有监听端口，但**不是 CDP 调试端口**（任意路径返回 `{"code":"NOT_FOUND"}`），无法接管。

---

### Cookie 解密与域绑定前缀（只有跨浏览器搬才会遇到）

Chromium 标准链路：
```
Local State 的 os_crypt.encrypted_key
  → base64 → 去掉前 5 字节 "DPAPI" → CryptUnprotectData（ctypes 即可，不需要 pywin32）
  → 得到 32 字节 AES 主密钥
encrypted_value
  → 前 3 字节是 v10 / v11（v20 是 App-Bound 加密，离线解不开）
  → nonce = [3:15]，ciphertext = [15:-16]，tag = [-16:]
  → AES-256-GCM 解密
```

### ⚠️ 必做最后一步：剥掉 32 字节域绑定前缀

新版 Chromium 在**明文开头**加了一段绑定到域名的哈希：

```
decrypted_plaintext = SHA256(host_key)[0:32]  ||  真正的 cookie 值
```

- 判断方式：`plaintext[:32] == hashlib.sha256(host_key.encode()).digest()` → 剥掉前 32 字节
- **不剥掉的后果**：得到夹杂控制字符和 `U+FFFD` 的乱码；AES-GCM 认证标签是**通过的**，
  所以脚本不会报任何错，只在注入浏览器时被 Chromium 判为
  `Protocol error (Storage.setCookies): Invalid cookie fields`
- 本次实测 93/93 条抖音 Cookie 全部带这个前缀

**排查经验**：`addCookies` 报 `Invalid cookie fields` 时，不要怀疑域名 / path / sameSite / expires
（用最小用例逐个字段试过，全部通过）。真正的原因是**值本身不是合法字符串**——打印值的码位分布，
看有没有 `U+FFFD` 和控制字符。

---

## 四、抖音发布页：两个长得几乎一样的页面

**这是排查时绕的最大一个弯。**

| | 视频发布页 | 图文发布页 |
|---|---|---|
| 入口 | 直接打开 `/creator-micro/content/upload` | 先开 upload 页，**再点「发布图文」标签** |
| 最终 URL | `/creator-micro/content/publish?enter_from=publish_page` | `/creator-micro/content/post/image?enter_from=publish_page&media_type=image&type=new` |
| 图片上传框 | `input[type=file][accept*="image"]`，**`multiple=false`**（其实是**封面图**用的） | `input[type=file][accept*="image"][multiple]`，最多 35 张 |
| 标题框 | placeholder「填写作品标题，为作品获得更多流量」，限 **30 字** | placeholder「**添加作品标题**」，限 **20 字** |
| 自主声明选项 | 只有「无需添加自主声明」 | **6 个**：内容由AI生成 / 内容为个人观点或见解 / 内容为转载信息 / 内容含营销推广信息 / 虚构演绎，仅供娱乐 / 无需添加自主声明 |

走错页面的典型症状：图片被当封面吃掉（截图里右侧还是「点击上传视频」区）、标题框找不到、
自主声明弹层里只有一个选项。**只看 URL 不够**——两者 URL 前缀都是 `content/`，要靠右侧栏文案区分。

---

## 五、填充流程的四个具体坑

1. **传播完图会弹「设置封面」裁剪弹窗**，它拦截后续所有点击（`ReactCrop__crop-selection` intercepts pointer events）。
   必须先关掉：点弹窗内的「保存」/「完成」。只针对裁剪弹窗关，别把「自主声明」弹层一起关了。

2. **多个 `.semi-modal-wrap` 会残留在 DOM 里**（封面弹窗关掉后节点还在）。
   `.last()` 很可能选中隐藏的那个，导致定位失败。要按弹层**标题文案**过滤
   （`hasText: '对作品内容添加声明'`）。

3. **半设计（Semi UI）的弹层对 Playwright actionability 检查不友好**，`locator.click()` 会一直超时。
   改用 `page.evaluate()` 里做原生 DOM 点击。

4. **点单选按钮必须用原生 `input.click()`**，才会触发 React 的 `onChange`。
   用 `inp.checked = true` + `dispatchEvent(new Event('click'))` 伪造事件 React **不认**，
   后果是「确定」按钮永远保持禁用，而脚本查不出原因。

`dismissOverlays` 的正确判据：`.ReactCrop__crop-selection` 是否存在，而不是 `.semi-modal-wrap` 是否存在。

---

## 六、输入配置的形态

单个 JSON 文件即可（`_发布内容.json`），字段：
`图片目录 / 标题 / 正文 / 话题[] / 自主声明 / 合集`。
标题上限 **20 字**（2026-09-29 用户最终更正：「**两边都是标题 20 字，正文 1000 字**」；
本机后台 dump 的图文页计数器 `19/20` 与此一致）。
脚本按页面 placeholder 判定实际上限并**按上限截断**，实填字数与是否被截都写进报告，便于回头对账。

- `自主声明`：本项目**固定「内容由AI生成」，由脚本代选**（2026-10-05 用户更新）。
  路径：点击页面上「自主声明」入口 → 弹层「对作品内容添加声明」→ 单选该项 → 点确定；
  `pub_fill*.cjs` 的默认值已同步，配置里不写该字段也会选它。
  ⚠️ 历史沿革：早期「必须勾选 AIGC」→ 2026-09-29「不代操作、保持默认」→
  **2026-10-05 固定选「内容由AI生成」，以最新一条为准。**
- `合集`：填合集名，本项目固定 **「AI前沿」**（⚠️ 创作者中心里的实际名字**不带空格**；
  脚本比对时忽略空格差异，所以写「AI 前沿」也能选中）。留空则不动该选项。
  页面形态（2026-09-30 实测修正）：合集是「添加合集」那一行里的一个 **semi 下拉选择器**
  （`.semi-select.semi-select-single`，当前值显示「不选择合集」，位置在「自主声明」上方），
  **不是点开后弹浮层的入口** —— 这一点早期写错过，见第八节。
  ⚠️ **该合集必须先在创作者中心创建过**，否则下拉里没有这一项，脚本会记 WARN 交给人工。
- 已废弃字段：`填完保持打开分钟` —— 旧版靠它 `sleep` 等人工，现已改为「填完即退出」，见第七节。
- ⚠️ `话题` 数组**最多 5 个**（用户 2026-09-30 硬规则，两平台一致；超了会被 `check_copy.py` 判超限）。
  脚本按数组顺序逐个输入、**不做数量兜底**，所以超量必须在出稿阶段删掉。

### 一次填多条：多开 tab（2026-09-30 实测可行）

用户问过「是不是只能同时打开一个发布界面」。实测结论：**可以多开** —— 新建 tab 打开
`/content/upload` 再点「发布图文」，图片上传框正常出现，页面没有任何「只能开一个」的限制提示
（正则查过 `只能|仅能|请先|已有未发布|草稿|冲突|上限|同时`，全部 false）。

所以批量场景用 **`pub_fill_multi.cjs` + `_batch.json`**：

- `_batch.json` 写任务数组：`{"任务":[{"名称":"...","配置":"_发布内容_X.json"}, ...]}`；
- 脚本连 9222 → 先找**「处于图文态且标题框还空着」的 tab 复用**，不够再 `newPage()`；
- 每条占一个 tab，逐条填完；报告落 `_out/batch_report.json`，截图落 `_out/batch-N.png`；
- **绝不点发布**：填完所有 tab 都留在编辑态，由用户逐个点。

单条场景仍用 `pub_fill.cjs`，两者填充逻辑一致（同一套选择器经验）。

> ⚠️ **发布页 tab 跳到 `content/manage?enter_from=publish` ≠ 内容丢了。**
> 实测该 URL 对应的是**定时发布已提交**（作品列表里显示「定时: 2026年09月30日 18:34」）。
> 要判断状态，**重新加载管理页读作品列表**，别凭 URL 猜。

---

## 七、脚本跑完后：浏览器怎么留、结果怎么核

**机制（2026-09-29 改造，取代旧的 sleep 方案）**：脚本不再用 `launchPersistentContext`
—— 它会绑住进程，脚本一退就把浏览器带走，于是只能 `sleep N 分钟` 等人工，AI 侧就得一直挂着。
现在改为：

```
spawn(detached) Chrome  --remote-debugging-port=9222 --user-data-dir=<_profile>
   → chromium.connectOverCDP('http://127.0.0.1:9222')
   → 填完（含合集）写报告 → process.exit(0)      ← 绝不调 browser.close()
```

结果：**脚本填完立即退出，Chrome 作为独立进程继续留在发布页**给人工点发布；
后台不再有任何等待中的任务。CDP 端口默认 9222，被占则顺延 9223 / 9224。

**三个连带好处 / 注意**：

1. 重跑时会**先试连已有端口**，复用上次留的那个窗口（不会再开一个新的），
   报告里 `reused_browser: true` 会标出来。
2. 核验不必再靠 History 猜 —— 直接 `connectOverCDP` 连回端口就能读当前页面，
   后续还能连回去读作品列表核对发布结果。
3. ⚠️ 若三个端口都连不上、而 profile 又被占用（上次窗口没关），脚本会 **FATAL 退出**并提示
   「关掉那个 Chrome 窗口再重跑」，不会硬闯 —— 同一 `user-data-dir` 的第二个 Chrome 实例
   只会把参数转给已有实例，端口根本起不来。

**AI 侧收工姿势**（用户 2026-09-29 明确要求：「填好之后完成任务就好了，不用一直等着」）：
脚本后台启动 → 读一次 `_out/fill_report.json` 确认 `ok` → **立即结束这一轮回答**。
不 `sleep`、不轮询、不留常驻任务。等用户回来说「发完了」，再按第八节收尾
（新机制下只需关掉那个 Chrome 窗口）。

下面的 History 反推法保留，作为端口不可用时的**兜底**手段：

```python
# 与夸克 Cookie 库不同，Chrome 的 History 允许共享读句柄
GENERIC_READ=0x80000000; SHARE=0x1|0x2|0x4; OPEN_EXISTING=3
h = kernel32.CreateFileW(r"...\_profile\Default\History", GENERIC_READ, SHARE, None, OPEN_EXISTING, 0x80, None)
# 读出全部字节 → 写临时文件 → sqlite3 查 urls 表
# last_visit_time 是 WebKit 微秒：unix = vt/1e6 - 11644473600
```

**判断发布成功的线索**（按可靠度排序）：

| 线索 | 含义 |
|---|---|
| `creator-micro/content/manage?enter_from=publish` | 发布成功后的**标准跳转**，最可靠 |
| `content/publish/poster/...` | 用户点过「设置封面」 |
| 停留在 `content/post/image?...&type=new` | 填好了但**没点发布** |
| `www.douyin.com/user/self` | 用户去看自己的主页了 |

⚠️ 这些是**间接证据**，不是平台回执。对外表述必须写「据浏览历史推断发布成功」，
不能写「已确认发布成功」。

---

## 八、遗留与待验证

- 夸克重启后标签页**是否自动恢复**：未验证（夸克 Preferences 里 `restore_on_startup` 未设置）。
- 封面的具体选择：脚本不动，交人工。
- 「高清发布」开关：脚本不动，交人工。
- 抖音前端改版频繁，选择器需要定期用一次结构 dump 校准。
- **不要并发跑 `pub_fill.cjs`**：它们共用同一个 profile 目录与同一个 `_填充日志.txt`，
  日志会被互相覆盖（实测收尾时读到的日志来自早前失败的那次）。**核对结果只认 `_out/fill_report.json`**。
- **收尾（2026-09-29 新机制下）**：脚本自己已经退出，正常情况**没有 node 进程要收**。
  要收的只有那个独立 Chrome：
  1. 先确认 `Get-CimInstance Win32_Process -Filter "Name='node.exe'"` 里**没有**
     CommandLine 含 `pub_fill.cjs` 的项（有则该次脚本没跑完，先看 `_out/fill_report.json`）；
  2. 关浏览器：CommandLine 含 `发布助手` 的 `chrome.exe` 逐个 `Stop-Process -Force`，
     或者直接让用户点窗口右上角关闭（更干净）。
     ⚠️ **只按 CommandLine 过滤，绝不按进程名批量杀 chrome** ——
     用户自己的 Chrome 也在跑，误杀会关掉他正在用的窗口；
  3. 复查剩余数量应为 0。
- **合集选择器（2026-09-30 已实测打通）**：控件是 semi 下拉，不是浮层。
  **首跑踩坑**：按 `text=添加合集` 去点，点到的是**区域标题文字**，下拉根本没展开，
  于是日志报「展开后没找到名为 X 的合集」——列表里其实有，只是没打开。
  现做法：点 `.semi-select.semi-select-single`（当前含「不选择合集」的那个）→ dump
  `.semi-select-option` → **去空格归一化匹配** → 点中 → 读回
  `.semi-select-selection-text` 自证。
  实测候选为 `["不选择合集", "AI前沿\n共3个作品"]`，选中后回读为「AI前沿」。
  若仍没选中会记 WARN 交给人工，不阻塞发布；补选的独立脚本见 `_fix_collection.cjs`。
- **「发布 / 排期是否成功」脚本无法核验**：填完即退出，拿不到平台回执。
  要看结果，用 CDP 连回 9222 再读一次作品管理页（比上面的 History 法可靠）。

---

## 九、数据面板：创作者中心内部数据接口（两平台实测可用）

**统一走第二节的「夸克本体 + profile 副本」**，在页面上下文里 `fetch`，**全部 GET、全部 HTTP 200**。
不要说"B 站拿不到数据"——那是自建 Chromium 无登录态时的结论，用夸克本体后以下接口全通。

### 抖音（2026-09-28 实测）

| 接口 | 内容 |
|---|---|
| `/aweme/janus/creator/data/overview/all/` | 数据总览：11 项指标 × 7 天序列 |
| `/web/api/creator/item/list?cursor=0&count=10&scene=1` | 作品列表 |
| `/aweme/v1/creator/user/info/` | 账号信息（follower_count、权限位） |
| `/aweme/v1/creator/income/category/summary/` | 收入（今日/7 日/30 日/累计/余额） |
| `/web/api/media/aweme/draft` | 草稿箱 |

### B 站（2026-09-29 在夸克本体下实测，全部 `code=0`）

| 接口 | 内容 |
|---|---|
| `member.bilibili.com/x/web/data/index/stat` | **数据总览**：`total_click`(总播放) / `total_dm` / `total_reply` / `total_fans` / `total_fav` / `total_like` / `total_share` / `total_coin` / `total_elec` + 全套 `incr_*` 增量 |
| `member.bilibili.com/x/web/data/fan` | 粉丝数据：`summary` / `rank_list` / `rank_medal` / `source` |
| `member.bilibili.com/x/web/data/survey?type=1` | **按日期的单作品增量**：`{"20260927":{"arc_inc":[{bvid,title,incr,daytime,...}]}}` |
| `member.bilibili.com/x/web/data/archive/stat/query/latest` | 稿件最新统计 |
| `api.bilibili.com/x/space/arc/search` | UP 主投稿列表 —— **创作中心自己调用时 HTTP 200**；手动裸调会因缺 WBI 签名/频率过高被 `-799` 限流 |

创作中心页面共发出 **50 个数据接口**，完整清单见 `_bili_creator.json`（工作区）。
`member.bilibili.com/x/web/archives/list` 与 `.../data/asset` 是我**猜的路径**，返回 404，不存在。

11 项指标：`play`1 / `profile`2 / `digg`3 / `comment`4 / `share`5 / `fans`6 /
`new_fans`9 / `cancel_fans`24 / `music_create`26 / `account_search`29 / `post_search`30。
每点字段 `date` / `count` / `last_day_incr_rate`。

**判据补充**：`item/list` 里有作品 + `draft` 返回 `not found`（空） ⇒ 可推断**发布成功**
（比只看浏览历史的跳转更硬）。注意 `item/list` 里**没有** play/like，单条作品统计需另找接口。

**数据按天产出**，页面原话「若为首次进入，数据次日起计算产出」——别按分钟级设计刷新。

---

## 十、本机环境坑（跑这套脚本必须先知道）

1. **`Add-Type` 被安全策略拦**，`New-Object -ComObject` 同样被拦
   → PowerShell **没有**可用的"删到回收站"手段。可行解法是 **Python ctypes 调 `SHFileOperationW`**：
   `wFunc=3`，`fFlags=FOF_ALLOWUNDO(0x40)|NOCONFIRMATION(0x10)|SILENT(0x4)|NOERRORUI(0x400)`，
   `pFrom = "\0".join(paths) + "\0\0"`。
2. **MSYS 不转换 `NODE_PATH`**：`NODE_PATH="/c/Users/..."` 会让 Node 报 `MODULE_NOT_FOUND`，
   必须写 **`C:/Users/...`**（带盘符）。`pub_fill.cjs` 没暴露这个坑，是因为它自己硬编码了绝对 require 路径。
3. **`SHFileOperationW` 删 Chromium profile 目录会留空目录骨架**（文件已进回收站、壳还在）：
   再调一次同一 API 即可清掉；兜底是逐层 `os.rmdir`。
