# 图文内容生产 Skill 集（小红书 / 抖音）

两支 WorkBuddy skill 的组合仓库，用于把一篇文章或一个选题做成**小红书 / 抖音图文卡片**。

## 为什么是两支（2026-10-06 合并说明）

原先是 `article-to-xhs` + `article-to-douyin` + `github-trending-official` 三支。
合并的实测依据：

| 层 | 合并前实际情况 |
|---|---|
| 脚本 | 两边的 `render.cjs`、`check_banned_words.py` **逐字节相同**；8 个脚本实际只有 5 个不同的东西 |
| 代码依赖 | **跨 skill 硬编码路径 0 处** —— 「必须成对安装」只是文档里的一句约束，不是技术事实 |
| 卡片模板 | 已合并为一份，`data-platform="xhs\|douyin"` 控制 4 处平台差异 |
| SKILL.md | 两份各 494 非空行，但相似度仅 35.6%（平台差异写进了每一句话） |

**合并后行为不变**：出图与两支旧 skill **MD5 16/16 逐字节一致**。

| skill | 职责 |
|---|---|
| `article-to-social` | 文章/选题 → 小红书 + 抖音图文（卡片 PNG + 文案 + 汇总 HTML） |
| `github-trending-official` | 选题发现第 ② 线：GitHub 榜单 / 项目推荐成图文 |

两者关系：`github-trending-official` 产出选题 → 交 `article-to-social` 做图文与发布。

## 目录结构

```
.
├── article-to-social/                 # 文章/选题 → 双平台图文（入口）
│   ├── SKILL.md                        # 工作流定义 ⓪→⑧
│   ├── config.sample.json              # 路径配置模板（复制为 config.json）
│   ├── pipeline/                       # ★ 出图流水线（跨三平台）
│   │   ├── make.py                     # ★ 主入口：构建→预检→autogap→测量→截图→回写→交付
│   │   ├── build_cards.py              # spec JSON → cards.html（注入 data-platform）
│   │   ├── render2.cjs                 # 一次会话多 HTML；DOM 直测密度 + autogap
│   │   ├── deliver.py                  # 复制到两平台成品目录
│   │   ├── make_all.py                 # 批量并发
│   │   ├── _paths.py                   # ★ 所有路径与解释器解析
│   │   └── README.md                   # 命令 / 环境变量 / 依赖 / 已知边界
│   ├── scripts/
│   │   ├── env_check.py                # 环境自检（换设备第一条命令）
│   │   ├── render.cjs                  # HTML → PNG（Chromium 定位跨三平台）
│   │   ├── build_index.py              # 内容成品总索引（扫两平台）
│   │   ├── build_preview.py            # 单文件汇总 HTML
│   │   ├── check_copy.py               # 文案校验（字数 / emoji / 话题数）
│   │   ├── check_density.py            # 卡片填充度（旧像素方案，需 Pillow；出图链路不走它）
│   │   ├── check_banned_words.py       # 违禁词
│   │   └── banned_words.json
│   ├── templates/
│   │   └── cards.html                  # ★ 一份模板出两平台
│   └── references/
│       ├── platform-diff.md            # ★ 开工前必读：两平台全部差异
│       ├── fact-check.md               # 事实核验 / 来源署名 / AIGC 标注
│       ├── rewrite-structure.md        # 结构重组 / 抖音前两张约束
│       ├── sources.md                  # 选题源 / 可达性 / 话题玩法
│       ├── bgm.md                      # 抖音配乐
│       ├── why-no-autopublish.md       # 为什么不自动发布
│       └── publish-automation-quark.md # 抖音半自动填充（停在发布页）
└── github-trending-official/           # 选题发现（GitHub 榜单 / 项目推荐）
    ├── SKILL.md
    ├── scripts/  （trending 抓取 / 榜单拼版）
    └── references/
```

## 环境要求

| 组件 | 要求 | 备注 |
|---|---|---|
| Python | 3.9+ | **出图链路零第三方依赖**（`render2.cjs` 用 DOM 直测密度，不解图）。Pillow 只有手动跑旧像素方案 `check_density.py` 时才需要 |
| Node.js | 18+ | 用于 `pipeline/render2.cjs` 出图 |
| playwright-core | 任意近期版本 | `npm i playwright-core` |
| Chromium | 约 428 MB | `npx playwright install chromium` |
| 中文字体 | 必需 | 缺了中文会渲染成方块；Debian 系 `apt install fonts-noto-cjk` |
| Git | 出图**不需要** | 只在 `git clone` / 推送时用。Windows 上若未装 Git，可复用 WorkBuddy 自带的便携版：`%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\<版本>\cmd\git.exe`（版本号见同目录的 `current` 文件） |

一条命令查全：

```bash
python article-to-social/scripts/env_check.py --net
```

它会报出 Python / Node / playwright-core / Chromium / Pillow / 中文字体 / 成品目录 / 网络的实际状态与缺失项，并给出补装命令。加 `--json` 输出机器可读结果。

## 安装

**方式一（推荐）**：在 WorkBuddy 里执行 `/skills import <本仓库地址>`。

**方式二**：把仓库里两个目录整体复制到本机 skills 目录（Windows 为 `%USERPROFILE%\.workbuddy\skills\`）。

> 合并后**不再有「必须成对安装」的限制** —— 只有一支图文 skill。

## 配置输出目录

脚本默认写到 `C:\小红书` / `C:\抖音`（Windows）。换设备时**不用改代码**，三种方式任选：

```bash
# 1) 环境变量
export XHS_DIR=/path/to/xhs
export DY_DIR=/path/to/douyin

# 2) skill 目录下建 config.json（照 config.sample.json 改）
#    位置：article-to-social/config.json

# 3) 命令行参数（仅 build_index.py）
python article-to-social/scripts/build_index.py --out /path/to/index.html
```

优先级：**命令行参数 > 环境变量 > `config.json` > 内置默认**。

`config.json` 已被 `.gitignore` 排除，**本机绝对路径不会进仓库**。

## 出图

一份模板出两个平台，`build_cards.py` 按 `--platform` 注入 `<html data-platform="...">`，
平台差异（页码格式 / 封面滑动提示 / 字号间距档位 / 末页互动引导）由 CSS 自动处理。

```bash
NODE_PATH=<含 playwright-core 的 node_modules> \
  node article-to-social/scripts/render.cjs <cards.html> <输出目录> <张数>
```

Chromium 会自动扫描 Windows / macOS / Linux 的常见安装位置；也可用 `PLAYWRIGHT_BROWSERS_PATH` 显式指定根目录。找不到时会列出所有扫描过的路径。

### ✅ 出图流水线已收进仓库（`article-to-social/pipeline/`）

`make.py` / `build_cards.py` / `render2.cjs` / `deliver.py` / `make_all.py` / `_paths.py`
**全部在本仓库里**，跨 Windows / Linux / macOS。（2026-10-06 从本机 `C:\srtwb\cards\`
迁入并完成去硬编码改造——此前它们从未进过仓库，仓库首版 `85e828d` 的 44 个文件里也没有。）

| 项 | 结果 |
|---|---|
| 本机硬编码 | 21 处 → **2 处**（1 处是「Windows 惯例根目录」的有意默认值，非 Windows 不生效；1 处在文档字符串里） |
| 出图一致性 | 与改造前**MD5 16/16 逐字节一致**（xhs 8 + dy 8） |
| 交付链路 | `--tag` 实测落盘正常（PNG + 汇总 HTML 两平台各一份） |
| Python 第三方依赖 | **零** —— 密度用 DOM 直测，不解图，所以不需要 Pillow |

```bash
python pipeline/make.py --doctor     # ★ 换设备/云端第一条命令：看路径与解释器解析
python pipeline/make.py <工作目录>                # 出图
python pipeline/make.py <工作目录> --tag 20261005_主题   # 出图 + 交付到两平台
```

路径解析全集中在 `pipeline/_paths.py`，优先级 **环境变量 > 本机惯例位置**。
交付根目录由 `XHS_DIR` / `DY_DIR` 指定，**不设则只出图不交付**（非 Windows 上默认如此）。
详见 `pipeline/README.md`。

## 日常推送：双击 `push-to-github.bat`

改完本机 skill 后双击仓库根目录的 `push-to-github.bat` 即可（自动定位 git → 设置身份
→ 提交 → 推送）。

> 🔧 **「Select a credential helper」弹窗已解决（2026-10-06）**
> 便携版 Git 的 system 配置里写着 `credential.helper = helper-selector`，
> 这个程序**每次都会弹选择框**（勾了「Always use this from now on」也不管用，
> 因为它仍排在优先级第一位）。修法是在仓库级用**空值重置上层继承**，只留 `manager`：
> ```bash
> git config --local --replace-all credential.helper ""
> git config --local --add credential.helper "manager"
> ```
> 脚本已内置这两行。凭据已存在时推送**完全静默**，不会开浏览器。

> 🌐 **`CONNECT tunnel failed, response 502` 已自动处理（2026-10-06）**
> 症状：浏览器能正常打开 GitHub，但命令行推送报502，看起来像网络断了。
> 真因：**切换 VPN 节点会换本地代理端口**，而 shell / 双击脚本继承的
> `http_proxy` 还是**旧端口**。浏览器正常是因为它读的是系统当前代理设置，不受影响。
> ⚠️ **「端口在监听」≠「那个端口是 HTTP 代理」** —— 实测本机`2840` 端口活着但根本不是
> HTTP 代理，Git 只能对它报 502；真正可用的是 `10808`。
> 脚本现在会用 curl 逐个探测常用端口（10808 / 7890 / 8888 / 8080 / 33210 / 4780 等），
> 取第一个真正能通的，**换节点后不用再手动干预**。探测不到就退回直连并在失败时提示。
>
> 手工排查用这条（`reg.exe` 被安全策略拉黑，**判断 VPN 只能 curl 实测**）：
> ```bash
> env -u http_proxy -u https_proxy curl -s -o /dev/null -w "%{http_code}\n" \
>   --max-time 8 -x http://127.0.0.1:<端口> https://github.com/
> ```
> 返回 `200` 的才是可用代理。

## ⚠️ 本仓库工作树就是本机 skills 目录

如果你在本机直接使用本仓库（而非 clone 到别处）：

- **不要执行 `git clean -xdf`** —— 其余未跟踪的 skill 会被一并清掉（**这是本仓库唯一危险的命令**）；
- `.gitignore` 用的是白名单写法（先排除顶层一切，再放行上面两个目录），
  在本机新增的其他 skill **不会被误提交**；
- 新增/切换设备时，改用 `git clone` 到独立目录更省心。

## 出处与时点

- **2026-10-05**：跨设备改造 —— 清掉脚本里写死的本机绝对路径，补齐跨平台 Chromium 定位
  与中文字体 fallback，加入环境自检。改造前后出图**逐字节相同**。
- **2026-10-06**：`article-to-xhs` + `article-to-douyin` 合并为 `article-to-social` ——
  脚本去重（8 → 5 个）、卡片模板合为一份（`data-platform` 控制差异）、
  平台差异集中到 `references/platform-diff.md`。合并后出图与两支旧 skill
  **MD5 16/16 逐字节一致**。同日补上 `make.py` 报告路径的静默失败修复
  （相对路径会让密度报告读到上一轮的旧文件），并修掉推送时反复弹出的
  credential helper 选择框。
