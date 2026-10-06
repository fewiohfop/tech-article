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
│   ├── scripts/
│   │   ├── env_check.py                # 环境自检（换设备第一条命令）
│   │   ├── render.cjs                  # HTML → PNG（Chromium 定位跨三平台）
│   │   ├── build_index.py              # 内容成品总索引（扫两平台）
│   │   ├── build_preview.py            # 单文件汇总 HTML
│   │   ├── check_copy.py               # 文案校验（字数 / emoji / 话题数）
│   │   ├── check_density.py            # 卡片填充度（需 Pillow）
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
| Python | 3.9+ | **唯一第三方依赖是 Pillow**（`check_density.py` 读 PNG 算留白），其余全标准库 |
| Node.js | 18+ | 用于 `render.cjs` 出图 |
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

### 📌 出图工具链不在本仓库（只影响云端，本机一切正常）

`build_cards.py` / `make.py` / `render2.cjs` / `deliver.py` / `make_all.py` 只在本机
`C:\srtwb\cards\`，**没有提交进本仓库**。已核实仓库首版（`85e828d`，44 个文件）里也没有它们
—— **不是某次改动造成的回归**。

| 环境 | 状态 |
|---|---|
| **本机** | ✅ 出图流程完整可用，`make.py` 照常跑 |
| **云端** | ⓪–⑤、⑦–⑧ 可跑；**⑥ 出图跑不了**（`make.py` 找不到） |

**云端绕开方式**：⓪–⑤ 与汇总页在云端做，PNG 回本机补渲染；
或直接调仓库内的 `scripts/render.cjs`，只是没有 autogap 收敛、DOM 密度测量、违禁词预检。

**要云端出图得一次做完三件**（别只做第一件，那样只是把「缺工具」变成「工具在但跑不起来」）：

1. 把 5 个核心脚本去硬编码后收进仓库
   （`C:\srtwb\cards\` 里另外 14 个 `patch*.py` / `fix*.py` 是历史一次性补丁，不收）；
2. 云端装 Chromium（约 428 MB）；
3. 验云端中文字体 + `pip install Pillow`。

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
  （相对路径会让密度报告读到上一轮的旧文件）。
