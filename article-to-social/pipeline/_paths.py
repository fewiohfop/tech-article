# -*- coding: utf-8 -*-
"""
_paths.py — 出图流水线的路径与解释器解析（跨 Windows / Linux / macOS）

设计原则（2026-10-06）：
  **脚本里不写死任何本机绝对路径。** 所有环境相关的量都从这里解析，
  解析顺序统一为：环境变量 > 本机惯例位置 > 内置默认。

被 make.py / build_cards.py / deliver.py / make_all.py 共用，
改动只需改这一处。

对外接口：
    SKILL_ROOT   skill 根目录（本文件的上上级）
    TEMPLATE     卡片模板 cards.html
    SCRIPTS      skill 的 scripts/ 目录
    PY           用来跑子脚本的 Python 解释器
    NODE         Node 可执行文件
    NODE_PATH    含 playwright-core 的 node_modules 目录（可能为 None）
    XHS_DIR      小红书成品根目录
    DY_DIR       抖音成品根目录
    CARD_JSON    工作目录里的卡片描述文件名
    resolve_dirs(d)  返回该工作目录对应的 (xhs根, 抖音根)
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL_ROOT, "scripts")
PIPELINE = HERE

# 卡片模板：合并后只有一份
TEMPLATE = os.environ.get("CARDS_TEMPLATE") or os.path.join(
    SKILL_ROOT, "templates", "cards.html")

# 单份内容模式（一份 card.json 出两个平台）
CARD_JSON = "card.json"


# --------------------------------------------------------------------------
# 解释器解析
# --------------------------------------------------------------------------
def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception:
        return 1, ""


def find_python():
    """
    跑子脚本用的 Python。
    优先用当前解释器（`sys.executable`）—— 这是最可靠的：它一定能跑标准库。
    云端 /venv、conda、Linux 系统 python 都靠这一条自然适配。
    """
    exe = sys.executable or ""
    if exe and os.path.exists(exe):
        return exe
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            return p
    return exe or "python"


def find_node():
    """
    Node 定位。⚠️ 不要写死版本号（如 versions\\22.22.2-6\\node.exe）——
    WorkBuddy 升级后路径就变了，是本机最易失效的一处硬编码。

    顺序：NODE_BIN 环境变量 → PATH → WorkBuddy 便携版 versions\\current 指针
          → macOS 常见安装位置。
    """
    p = os.environ.get("NODE_BIN", "")
    if p and os.path.exists(p):
        return p
    p = shutil.which("node") or shutil.which("nodejs") or ""
    if p:
        return p

    home = os.path.expanduser("~")
    cands = []
    if os.name == "nt":
        cands += [
            os.path.join(home, ".workbuddy", "binaries", "node", "versions"),
            os.path.join(home, "AppData", "Local", "Programs", "WorkBuddy",
                         "resources", "vendor", "node"),
        ]
    else:
        cands += [
            "/usr/local/bin", "/opt/homebrew/bin",
            os.path.join(home, ".nvm", "current", "bin"),
        ]

    for root in cands:
        if not os.path.isdir(root):
            continue
        exe_name = "node.exe" if os.name == "nt" else "node"
        # 优先读 current 指针（WorkBuddy 的版本目录约定）
        cur = os.path.join(root, "current")
        if os.path.isdir(cur):
            with open(cur, encoding="utf-8", errors="replace") as f:
                ver = f.read().strip()
            cands_v = os.path.join(root, ver, exe_name)
            if os.path.exists(cands_v):
                return cands_v
        if os.path.exists(os.path.join(root, exe_name)):
            return os.path.join(root, exe_name)
        # 扫一层版本目录，取版本号最大的那个
        vers = []
        try:
            for d in os.listdir(root):
                fp = os.path.join(root, d, exe_name)
                if os.path.exists(fp):
                    vers.append((d, fp))
        except OSError:
            continue
        if vers:
            vers.sort(key=lambda x: x[0])
            return vers[-1][1]
    return ""


def find_node_path(node_bin):
    """
    含 playwright-core 的 node_modules 目录。
    找不到返回 None —— render2.cjs 会自己 require 失败并给出安装指引。
    """
    env = os.environ.get("NODE_PATH", "")
    if env and os.path.isdir(env):
        return env

    cands = [os.path.join(os.getcwd(), "node_modules"),
             os.path.join(SKILL_ROOT, "node_modules")]
    if node_bin:
        base = os.path.dirname(node_bin)
        home = os.path.expanduser("~")
        cands += [
            os.path.join(base, "node_modules"),
            os.path.join(base, "..", "workspace", "node_modules"),
            os.path.join(home, ".workbuddy", "binaries", "node",
                         "workspace", "node_modules"),
        ]
        if os.name == "nt":
            cands.append(os.path.join(
                home, "AppData", "Local", "Programs", "WorkBuddy",
                "resources", "vendor", "node", "lib", "node_modules"))
    for c in cands:
        if os.path.isdir(os.path.join(c, "playwright-core")):
            return os.path.normpath(c)
    return None


PY = find_python()
NODE = find_node()


# --------------------------------------------------------------------------
# 成品根目录解析
# --------------------------------------------------------------------------
def _default_roots():
    """
    本机惯例位置。**云端 /别的设备上大概率不存在** —— 那时用环境变量指定。
    Windows 盘根直挂是本机习惯，Linux/macOS 下不存在。
    """
    if os.name != "nt":
        return "", ""
    return "C:\\小红书", "C:\\抖音"


def resolve_roots():
    """
    (小红书成品根, 抖音成品根)

    顺序：环境变量 XHS_DIR / DY_DIR  >  本机惯例位置。
    两者都没有时返回 ("", "")，代表「不做交付、只出图」——云端属这种情况。
    """
    x = os.environ.get("XHS_DIR", "").strip()
    y = os.environ.get("DY_DIR", "").strip()
    if x or y:
        return x, y
    return _default_roots()


XHS_DIR, DY_DIR = resolve_roots()


def node_env():
    """给子进程用的环境变量（含 NODE_PATH）。"""
    env = dict(os.environ)
    np = find_node_path(NODE)
    if np:
        env["NODE_PATH"] = np
    return env


def diagnose():
    """给 --doctor / 出错时打印用。"""
    np = find_node_path(NODE)
    return [
        ("SKILL_ROOT", SKILL_ROOT),
        ("TEMPLATE", TEMPLATE + ("" if os.path.exists(TEMPLATE) else "  [缺失]")),
        ("PY", PY),
        ("NODE", NODE or "  [未找到：装 Node 18+ 或设 NODE_BIN]"),
        ("NODE_PATH", np or "  [未找到 playwright-core：npm i playwright-core]"),
        ("XHS_DIR", XHS_DIR or "  [未设置：不做交付]"),
        ("DY_DIR", DY_DIR or "  [未设置：不做交付]"),
    ]
