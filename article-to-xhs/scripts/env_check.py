#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境自检 —— 换设备 / 上云端后先跑这个，一条命令看清缺什么。
=====================================================================
用法：
  python env_check.py
  python env_check.py --json          # 机器可读输出

检查项：Python / Node / playwright-core / Chromium / 中文字体 / 成品目录 / 网络连通
只读，不改任何文件。

为什么要它：这套流程原本只在本机跑通，换到 Linux 沙箱或另一台电脑时，
缺哪一样都表现为「跑到一半报错」。先跑一次自检，比逐个试错省事。
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
CONFIG_NAME = "config.json"

PASS, FAIL, INFO = "OK", "!!", "--"


def run(cmd, timeout=25):
    """跑一条命令，返回 stdout（失败返回空串，不抛异常）。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return (p.stdout or "").strip()
    except Exception:
        return ""


def which(name):
    return shutil.which(name)


def dwidth(s):
    """按显示宽度算（中文算 2 格），用于对齐。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def pad_to(s, n):
    return s + " " * max(0, n - dwidth(s))


def playwright_candidates(node):
    """可能的 node_modules 位置（用于找 playwright-core）。"""
    c = [p for p in (os.environ.get("NODE_PATH") or "").split(os.pathsep) if p]
    g = run([node, "-e",
             "try{console.log(require('child_process').execSync('npm root -g',"
             "{stdio:['ignore','pipe','ignore']}).toString().trim())}catch(e){console.log('')}"])
    if g and os.path.isdir(g):
        c.append(g)
    nd = os.path.dirname(node)
    for up in ("..", os.path.join("..", ".."), os.path.join("..", "..", "..")):
        base = os.path.normpath(os.path.join(nd, up))
        c.append(os.path.join(base, "node_modules"))
        c.append(os.path.join(base, "workspace", "node_modules"))
    c += [os.path.join(os.getcwd(), "node_modules"),
          os.path.join(SKILL_ROOT, "node_modules")]
    seen, out = set(), []
    for p in c:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ---------------------------------------------------------------- 单项检查

def find_chromium():
    """与 render.cjs 的候选保持一致（Windows / Linux / macOS）。完整版优先于 headless shell。"""
    env = os.environ.get("PW_CHROMIUM")
    if env and os.path.exists(env):
        return env, ["PW_CHROMIUM 已指定"]

    roots = []
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        roots.append(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    if os.environ.get("LOCALAPPDATA"):
        roots.append(os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright"))
    if os.environ.get("USERPROFILE"):
        roots.append(os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "ms-playwright"))
    home = os.path.expanduser("~")
    roots += [os.path.join(home, ".cache", "ms-playwright"),                      # Linux
              os.path.join(home, "Library", "Caches", "ms-playwright")]           # macOS

    bins = [("chrome-win64", "chrome.exe"), ("chrome-win", "chrome.exe"),
            ("chrome-win32", "chrome.exe"), ("chrome-linux64", "chrome"),
            ("chrome-linux", "chrome"),
            ("chrome-headless-shell-linux64", "chrome-headless-shell"),
            ("chrome-headless-shell-win64", "chrome-headless-shell.exe"),
            ("chrome-mac", "Chromium.app/Contents/MacOS/Chromium"),
            ("chrome-mac-arm64", "Chromium.app/Contents/MacOS/Chromium")]

    seen = []
    for root in roots:
        if not root:
            continue
        if not os.path.isdir(root):
            seen.append("%s（不存在）" % root)
            continue
        seen.append("%s（有）" % root)
        try:
            dirs = [d for d in os.listdir(root) if re.match(r"^chrom", d, re.I)]
        except Exception:
            continue
        vkey = lambda d: int(m.group(1)) if (m := re.search(r"(\d+)$", d)) else 0
        full = sorted([d for d in dirs if "headless" not in d.lower()], key=vkey, reverse=True)
        head = sorted([d for d in dirs if "headless" in d.lower()], key=vkey, reverse=True)
        for d in full + head:
            for sub, binname in bins:
                p = os.path.join(root, d, sub, binname)
                if os.path.exists(p):
                    return p, seen
    return None, seen


def find_cjk_fonts():
    s = platform.system()
    if s == "Windows":
        d = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        cand = ["msyh.ttc", "msyhbd.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc",
                "Deng.ttf", "msjh.ttc"]
        return [f for f in cand if os.path.exists(os.path.join(d, f))], "Windows 字体目录"
    if s == "Darwin":
        cand = ["/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/Library/Fonts/Arial Unicode.ttf"]
        return [f for f in cand if os.path.exists(f)], "macOS 系统字体"

    # Linux
    if which("fc-list"):
        out = run(["fc-list", ":lang=zh", "family"])
        fams = sorted({x.split(",")[0].strip() for x in out.splitlines() if x.strip()})
        return fams, "fc-list :lang=zh"
    got = []
    for root in ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]:
        if not os.path.isdir(root):
            continue
        for dp, _dn, fns in os.walk(root):
            for f in fns:
                if f.lower().endswith((".ttf", ".ttc", ".otf")) and any(
                        k in f.lower() for k in ("noto", "cjk", "han", "wqy", "micro")):
                    got.append(os.path.join(dp, f))
    return got[:10], "字体文件扫描（未装 fc-list）"


def check_net(url, timeout=6):
    t = time.time()
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "env-check/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, round(time.time() - t, 2), ""
    except Exception as e:  # noqa: BLE001
        return None, round(time.time() - t, 2), str(e)[:70]


def load_dirs():
    """目录配置：环境变量 > config.json > 内置默认（与 build_index.py 同规则）。"""
    cfg = {}
    p = os.path.join(SKILL_ROOT, CONFIG_NAME)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    xhs = os.environ.get("XHS_DIR") or cfg.get("xhs_dir") or r"C:\小红书"
    dy = os.environ.get("DY_DIR") or cfg.get("dy_dir") or r"C:\抖音"
    return xhs, dy


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="选题发布流程的环境自检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--net", action="store_true", help="附带网络连通检查（较慢）")
    args = ap.parse_args()

    R = {"platform": "%s %s" % (platform.system(), platform.release())}

    # Python
    R["python"] = {"ver": platform.python_version(), "bin": sys.executable,
                   "ok": sys.version_info >= (3, 8)}

    # Node
    node = which("node") or os.environ.get("NODE_BIN", "")
    ver = run([node, "-v"]) if node else ""
    R["node"] = {"bin": node, "ver": ver, "ok": bool(ver)}

    # playwright-core：先按当前 NODE_PATH 试，找不到再扫常见位置
    pw, pw_src, pw_found = "", "", []
    if node:
        js = ("try{console.log(require('playwright-core/package.json').version)}"
              "catch(e){console.log('')}")
        pw = run([node, "-e", js])
        pw_src = "当前 NODE_PATH"
        if not pw:
            for d in playwright_candidates(node):
                if os.path.isdir(os.path.join(d, "playwright-core")):
                    pw_found.append(d)
            if pw_found:
                os.environ["NODE_PATH"] = pw_found[0]
                pw = run([node, "-e", js])
                pw_src = "自动发现于 %s" % pw_found[0]
    R["playwright"] = {"ver": pw, "src": pw_src, "found": pw_found, "ok": bool(pw)}

    # Chromium
    exe, seen = find_chromium()
    R["chromium"] = {"path": exe, "searched": seen, "ok": bool(exe)}

    # Pillow —— 三支 skill 里唯一的第三方依赖（check_density.py 读 PNG 用）
    try:
        from PIL import Image  # noqa: F401
        import PIL
        R["pillow"] = {"ver": getattr(PIL, "__version__", "?"), "ok": True}
    except Exception as e:  # noqa: BLE001
        R["pillow"] = {"ver": str(e)[:60], "ok": False}

    # 中文字体
    fonts, how = find_cjk_fonts()
    R["cjk_font"] = {"fonts": fonts[:6], "how": how, "ok": bool(fonts)}

    # 成品目录
    xhs, dy = load_dirs()
    def dir_info(p):
        if not os.path.isdir(p):
            return {"path": p, "exists": False, "n": 0, "ok": False}
        n = len([d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))])
        return {"path": p, "exists": True, "n": n, "ok": True}
    R["xhs_dir"] = dir_info(xhs)
    R["dy_dir"] = dir_info(dy)

    # 网络（可选）
    if args.net:
        R["net"] = {}
        for u in ["https://api.github.com", "https://github.com",
                  "https://raw.githubusercontent.com"]:
            code, sec, err = check_net(u)
            R["net"][u] = {"code": code, "sec": sec, "err": err, "ok": bool(code)}
        R["proxy"] = {k: os.environ[k] for k in
                      ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
                      if os.environ.get(k)}

    if args.json:
        print(json.dumps(R, ensure_ascii=False, indent=2))
        return

    # ---- 人类可读输出
    W = 66
    print("=" * W)
    print(" 环境自检 · %s" % R["platform"])
    print(" skill 根目录：%s" % SKILL_ROOT)
    print("=" * W)

    def line(flag, label, value, sub=None):
        print(" [%s] %s %s" % (flag, pad_to(label, 18), value))
        if sub:
            print("      └ %s" % sub)

    line(PASS if R["python"]["ok"] else FAIL, "Python", R["python"]["ver"],
         R["python"]["bin"])
    line(PASS if R["node"]["ok"] else FAIL, "Node",
         R["node"]["ver"] or "未找到",
         R["node"]["bin"] or "装 Node 18+，或设 NODE_BIN 指向可执行文件")
    pw_ok = R["playwright"]["ok"]
    pw_sub = None
    if not pw_ok:
        if R["playwright"]["found"]:
            pw_sub = "已发现于 %s，但 require 失败 → 设 NODE_PATH 指向它" % R["playwright"]["found"][0]
        else:
            pw_sub = "设 NODE_PATH 指向含 playwright-core 的 node_modules 目录，或 npm i playwright-core"
    line(PASS if pw_ok else FAIL, "playwright-core",
         ("%s · %s" % (R["playwright"]["ver"], R["playwright"]["src"])) if pw_ok else "未安装",
         pw_sub)

    if R["chromium"]["ok"]:
        line(PASS, "Chromium", R["chromium"]["path"])
    else:
        line(FAIL, "Chromium", "未找到",
             "解决：npx playwright install chromium（或设 PW_CHROMIUM）")
        for s in R["chromium"]["searched"]:
            print("      · 已查 %s" % s)

    line(PASS if R["pillow"]["ok"] else FAIL, "Pillow",
         R["pillow"]["ver"] if R["pillow"]["ok"] else "未安装",
         None if R["pillow"]["ok"] else
         "check_density.py 读 PNG 算留白需要它：pip install Pillow")

    if R["cjk_font"]["ok"]:
        line(PASS, "中文字体", "%d 个候选（%s）" % (len(R["cjk_font"]["fonts"]), R["cjk_font"]["how"]),
             " / ".join(R["cjk_font"]["fonts"][:3]))
    else:
        line(FAIL, "中文字体", "未发现（%s）" % R["cjk_font"]["how"],
             "卡片里的中文会渲染成方块。Linux 装：apt install fonts-noto-cjk")

    for key, label in (("xhs_dir", "成品目录·小红书"), ("dy_dir", "成品目录·抖音")):
        d = R[key]
        if d["ok"]:
            line(PASS, label, "%s（%d 个子目录）" % (d["path"], d["n"]))
        else:
            line(FAIL, label, "%s（不存在）" % d["path"],
                 "设环境变量 %s，或建 skill 目录下 config.json" %
                 ("XHS_DIR" if key == "xhs_dir" else "DY_DIR"))

    if args.net:
        for u, v in R["net"].items():
            line(PASS if v["ok"] else FAIL, u.replace("https://", ""),
                 ("HTTP %s · %ss" % (v["code"], v["sec"])) if v["ok"] else v["err"])
        if R.get("proxy"):
            print("      └ 注意：检测结果受代理影响，当前 %s" %
                  "、".join("%s=%s" % kv for kv in R["proxy"].items()))

    bad = [k for k in ("python", "node", "playwright", "chromium", "pillow", "cjk_font")
           if not R[k]["ok"]]
    bad += [k for k in ("xhs_dir", "dy_dir") if not R[k]["ok"]]
    print("-" * W)
    if not bad:
        print(" 结论：环境完整，可跑全流程（含出图）")
    else:
        names = {"python": "Python", "node": "Node", "playwright": "playwright-core",
                 "chromium": "Chromium", "pillow": "Pillow", "cjk_font": "中文字体",
                 "xhs_dir": "小红书目录", "dy_dir": "抖音目录"}
        print(" 结论：缺 %d 项 → %s" % (len(bad), "、".join(names[b] for b in bad)))
        if "chromium" in bad or "cjk_font" in bad:
            print("       ⚠️ 出图（⑥）环节在当前环境不可用；选题/文案/汇总不受影响")
    if args.net:
        netbad = [u for u, v in R["net"].items() if not v["ok"]]
        if netbad:
            print("       ⚠️ %d 个域名不可达（%s）→ 选题发现（⓪）会缺源，出图不受影响"
                  % (len(netbad), "、".join(u.replace("https://", "") for u in netbad)))
    print("=" * W)


if __name__ == "__main__":
    main()
