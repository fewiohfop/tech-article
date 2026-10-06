# pipeline — 出图流水线

把「spec → HTML → 截图 → 交付」整条链路收进skill 仓库，**跨 Windows / Linux / macOS**。

2026-10-06 起从本机 `C:\srtwb\cards\` 迁入。此前只在本机，云端 `import` 后跑不了第 ⑥ 步。

## 文件

| 文件 | 作用 |
|---|---|
| `make.py` | **主入口**：构建 HTML → 违禁词预检 → autogap 收敛 → DOM 密度测量 → 截图 → 回写 gap → 可选交付 |
| `build_cards.py` | spec JSON →套模板 → `cards.html` |
| `render2.cjs` | Playwright 渲染：一次 Chromium 会话跑多个 HTML，自带 DOM 密度测量与 `--autogap` |
| `deliver.py` | 把 PNG 与汇总 HTML 复制到两平台成品目录 |
| `make_all.py` | 批量并发跑多个选题目录 |
| `_paths.py` | **所有路径与解释器解析都在这里**，改环境只改这一处 |

## 用法

```bash
# 换设备 / 云端第一件事：看环境解析对不对
python make.py --doctor

# 常规出图（工作目录里放 xhs.json + douyin.json，或放一份 card.json）
python make.py <工作目录>

# 顺带交付到两平台成品目录
python make.py <工作目录> --tag 20261005_主题

# 批量
python make_all.py --root <根目录> --pattern "xhs_*" --workers 3
```

退出码：`bad=0` 为 0，有LOW / CROWD / WRAP / OVERFLOW 页则非 0。

## 环境变量

全部可选，不设也能跑（会退到本机惯例位置；非 Windows 上就是「只出图不交付」）。

| 变量 | 作用 | 缺省 |
|---|---|---|
| `XHS_DIR` | 小红书成品根目录 | Windows 下 `C:\小红书`，其他平台为空 |
| `DY_DIR` | 抖音成品根目录 | Windows 下 `C:\抖音`，其他平台为空 |
| `NODE_BIN` | Node 可执行文件 | 依次找 `PATH` → WorkBuddy `versions\current` → 常见安装位置 |
| `NODE_PATH` | 含 `playwright-core` 的 `node_modules` | 自动扫描常见位置 |
| `PW_CHROMIUM` | Chromium 可执行文件 | 扫 `ms-playwright` 常见根目录 |
| `PLAYWRIGHT_BROWSERS_PATH` | Chromium 根目录 | 同上 |
| `CARDS_TEMPLATE` | 卡片模板路径 | `templates/cards.html` |

**只有传 `--tag` 时才需要 `XHS_DIR` / `DY_DIR`**，否则 `deliver.py` 报错退出（不静默丢产物）。

## 依赖

- Python 3.8+（标准库，**无需 pip 安装任何东西**；密度测量用 DOM 而非解图）
- Node 18+ 与 `playwright-core`（`npm i playwright-core`）
- Chromium（`npx playwright install chromium`，约 428 MB）

> ⚠️ `check_density.py`（旧像素扫描方案）需要 Pillow，但**本流水线不走那条路**——
> `render2.cjs` 用 DOM 直测，不解图，因此出图链路无第三方 Python 依赖。

## 两平台只写一份内容

工作目录里放 `card.json` 时，`make.py` 自动出两个平台（平台专属的页码 / 滑动提示 /
互动引导由 `build_cards.py` 派生）。放 `xhs.json` + `douyin.json` 则是老的两份模式，
此时 autogap 收敛的 gap 会**回写进各自的 spec**。

## 已知边界

- `card.json` 模式下 gap **不回写**（两平台字号不同，回写会互相覆盖），由 autogap 每次收敛。
- 封面两行标题必须用 `title` + `title2` 两个字段；在 `title` 里塞 `<br>` 会误报 `WRAP`
  （`WRAP` 测的是「单词不换行」）。
- 测量报告路径必须绝对路径 —— `render2.cjs` 在 `cwd=工作目录` 里跑，相对路径会被拼成
  `<目录>\<目录>\`；而 `exists()` 靠的是上一轮的旧文件，**静默用陈旧数据，不报错**。
  `make.py` 已用 `os.path.abspath` 处理。
