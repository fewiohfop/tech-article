# 图文内容生产 Skill 集（小红书 / 抖音）

三支 WorkBuddy skill 的组合仓库，用于把一篇文章或一个选题做成**小红书 / 抖音图文卡片**。

## 为什么三支放同一个仓库

`article-to-xhs` 与 `article-to-douyin` **互相调用对方的脚本**：

| 调用方 | 被调脚本 | 用途 |
|---|---|---|
| `article-to-xhs` | `article-to-douyin/scripts/check_density.py` | 校验卡片底部留白 |
| `article-to-douyin` | `article-to-xhs/scripts/build_index.py` | 刷新内容成品总索引 |

**所以两者必须成对安装，不能拆开。** `github-trending-official` 是选题发现线（GitHub 榜单/项目推荐成图文），与本仓库其余部分无脚本级依赖，但共用同一套出图链路，一并放在这里。

## 目录结构

```
.
├── article-to-xhs/                 # 小红书图文
│   ├── SKILL.md                    # 工作流定义（入口）
│   ├── scripts/
│   │   ├── build_index.py          # 内容成品总索引（扫两平台）
│   │   ├── env_check.py            # 环境自检（跨平台）
│   │   ├── render.cjs              # HTML → PNG（Playwright）
│   │   ├── build_preview.py        # 预览页
│   │   ├── check_copy.py           # 文案校验（字数 / 话题数）
│   │   ├── check_banned_words.py   # 违禁词
│   │   └── banned_words.json
│   ├── templates/cards.html        # 卡片模板
│   ├── references/                 # 事实核验 / 结构重组 / 来源 等规范
│   └── config.sample.json          # 路径配置模板（复制为 config.json）
├── article-to-douyin/              # 抖音图文
│   ├── SKILL.md
│   ├── scripts/  （含 check_density.py）
│   └── templates/cards.html
└── github-trending-official/       # 选题发现（GitHub 榜单 / 项目推荐）
    ├── SKILL.md
    ├── scripts/  （trending 抓取 / 榜单拼版）
    └── references/
```

## 环境要求

| 组件 | 要求 | 备注 |
|---|---|---|
| Python | 3.9+ | 唯一第三方依赖是 **Pillow**（读 PNG 算留白） |
| Node.js | 18+ | 用于 `render.cjs` 出图 |
| playwright-core | 任意近期版本 | `npm i playwright-core` |
| Chromium | 约 428 MB | `npx playwright install chromium` |
| 中文字体 | 必需 | 缺了中文会渲染成方块；Debian 系 `apt install fonts-noto-cjk` |
| Git | 出图**不需要** | 只在 `git clone` / 推送时用。Windows 上若未安装 Git，可复用 WorkBuddy 自带的便携版：`%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\<版本>\cmd\git.exe`（`<版本>` 见同目录下的 `current` 文件） |

一条命令查全：

```bash
python article-to-xhs/scripts/env_check.py --net
```

它会报出 Python / Node / playwright-core / Chromium / Pillow / 中文字体 / 成品目录 / 网络的实际状态与缺失项，并给出补装命令。加 `--json` 可输出机器可读结果。

## 安装

**方式一（推荐）**：在 WorkBuddy 里执行 `/skills import <本仓库地址>`。

**方式二**：把仓库里三个目录整体复制到本机 skills 目录（Windows 为 `%USERPROFILE%\.workbuddy\skills\`）。

## 配置输出目录

三支脚本默认写到 `C:\小红书` / `C:\抖音`。换设备时**不用改代码**，三种方式任选：

```bash
# 1) 环境变量
export XHS_DIR=/path/to/xhs
export DY_DIR=/path/to/douyin

# 2) skill 目录下建 config.json（照 config.sample.json 改）
#    注意：只有 article-to-xhs 目录下的 config.json 会被读取
#    （扫描与索引逻辑都在 xhs 侧，两 skill 共用这一份配置）

# 3) 命令行参数（仅 build_index.py）
python article-to-xhs/scripts/build_index.py --out /path/to/index.html
```

优先级：**命令行参数 > 环境变量 > `config.json` > 内置默认**。

`config.json` 已被 `.gitignore` 排除，**本机绝对路径不会进仓库**。

## 出图

```bash
NODE_PATH=<含 playwright-core 的 node_modules> \
  node article-to-xhs/scripts/render.cjs <cards.html> <输出目录> <张数>
```

Chromium 会自动扫描 Windows / macOS / Linux 的常见安装位置；也可用 `PLAYWRIGHT_BROWSERS_PATH` 显式指定根目录。找不到时会列出所有扫描过的路径。

## ⚠️ 本仓库工作树就是本机 skills 目录

如果你在本机直接使用本仓库（而非 clone 到别处）：

- **不要执行 `git clean -xdf`** —— 其余未跟踪的 skill 会被一并清掉；
- `.gitignore` 用的是白名单写法（先排除顶层一切，再放行上面三个目录），
  在本机新增的其他 skill **不会被误提交**；
- 新增/切换设备时，改用 `git clone` 到独立目录更省心。

## 出处与时点

本仓库由 2026-10-05 的一次跨设备改造产生：清掉了脚本里写死的本机绝对路径，
补齐了跨平台 Chromium 定位与中文字体 fallback，并加入环境自检。
改造前后在同一份输入上的出图结果 **逐字节相同**。
