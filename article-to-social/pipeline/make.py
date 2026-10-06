# -*- coding: utf-8 -*-
"""
make.py — 一步完成「生成 HTML → 自动收敛 gap + 测量 + 截图 → 回写 spec」

用法:
  python make.py <工作目录> [--no-autogap] [--tag 交付名] [--quiet] [--doctor]

流程:
  1) build_cards.py 生成 xhs_cards.html / dy_cards.html
  2) render2.cjs 一次 Chromium 会话完成：autogap 收敛 → 测量 → 截图
  3) 把收敛后的 gap 回写进 xhs.json / douyin.json（下次构建即用新值）
  4) --tag 给出时，顺带交付到 <小红书根>/<tag>/ 与 <抖音根>/<tag>/
     （根目录由 XHS_DIR / DY_DIR 环境变量指定；未设则只出图不交付）

相比旧 build_one.py:
  - 两平台共用一次浏览器会话（省一次冷启动 + 一次字体等待）
  - 密度不再解图，改 DOM 测量（不受封面光晕 / 贴底脚注干扰）
  - gap 自动收敛，无需为「留白不达标」再写补丁脚本
  - 输出精简，不把整页日志灌进上下文

2026-10-06：随 skill 收进仓库，全部路径改由 _paths.py 解析（跨三平台）。
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (  # noqa: E402
    PY, NODE, SCRIPTS, XHS_DIR, DY_DIR, node_env,
)

BUILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_cards.py")
RENDER2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render2.cjs")
DELIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deliver.py")
BANNED = os.path.join(SCRIPTS, "check_banned_words.py")

# 两个平台的 spec / HTML / 出图目录。根目录为空时代表「不做交付」。
PAIRS = [
    ("xhs.json", "xhs_cards.html", "out_xhs", "xhs", XHS_DIR),
    ("douyin.json", "dy_cards.html", "out_dy", "douyin", DY_DIR),
]


def run(cmd, cwd=None, env=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def writeback_gap(d, spec_name, outdir, rows):
    """把 render2 收敛后的 gap 写回 spec，保证下次构建沿用"""
    if spec_name == "card.json":
        # 单份内容两平台共用：gap 由 autogap 每次收敛，不回写以免两平台互相覆盖
        return 0
    path = os.path.join(d, spec_name)
    if not os.path.exists(path):
        return 0
    spec = json.load(open(path, encoding="utf-8"))
    by_name = {r["name"]: r for r in rows}
    changed = 0
    for p in spec.get("pages", []):
        r = by_name.get(p.get("export"))
        if not r or r.get("gap") is None:
            continue
        if p.get("type") == "cover":
            continue
        new_gap = int(r["gap"])
        if p.get("gap") != new_gap:
            p["gap"] = new_gap
            changed += 1
    if changed:
        json.dump(spec, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", help="工作目录（存放 spec 的目录）")
    ap.add_argument("--no-autogap", action="store_true")
    ap.add_argument("--tag", help="给出则顺带交付到两个平台目录（文件夹名，如 20261005_主题）")
    ap.add_argument("--file-name", help="HTML 主文件名，默认取 --tag 去掉日期前缀")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--doctor", action="store_true",
                    help="只打印路径与解释器解析结果后退出（换设备/云端排查用）")
    args = ap.parse_args()

    if args.doctor:
        from _paths import diagnose
        for k, v in diagnose():
            print("  %-11s %s" % (k, v))
        sys.exit(0)

    if not args.dir:
        ap.error("需要工作目录（或用 --doctor 只看环境）")

    d = os.path.abspath(args.dir)
    env = node_env()

    jobs, specs = [], []
    # 单份内容出两个平台：目录里有 card.json 就用它，否则沿用 xhs.json + douyin.json
    if os.path.exists(os.path.join(d, "card.json")):
        plan = [("card.json", "xhs_cards.html", "out_xhs", "xhs"),
                ("card.json", "dy_cards.html", "out_dy", "douyin")]
        single = True
    else:
        plan = [(s, h, o, p) for s, h, o, p, _r in PAIRS]
        single = False

    for spec, html, outdir, plat in plan:
        if not os.path.exists(os.path.join(d, spec)):
            continue
        cmd = [PY, BUILD, "--spec", spec, "--out", html]
        if single:
            cmd += ["--platform", plat]
        code, out = run(cmd, cwd=d)
        if code != 0:
            print("BUILD FAIL " + spec)
            print(out[-600:])
            sys.exit(1)
        jobs += ["--html", html, "--out", outdir]
        specs.append((spec, outdir))

    if not jobs:
        print("ERR 目录下没有 xhs.json / douyin.json")
        sys.exit(1)

    # ---- 违禁词预检：构建即查，避免「写完才发现命中、再回改一轮」----
    bc = [PY, BANNED]
    for f in ("meta_xhs.json", "meta_dy.json"):
        if os.path.exists(os.path.join(d, f)):
            bc += ["--meta", f]
    for f in ("xhs_cards.html", "dy_cards.html"):
        if os.path.exists(os.path.join(d, f)):
            bc += ["--html", f]
    if len(bc) > 2:
        code, out = run(bc, cwd=d)
        hits = [l.strip() for l in out.splitlines()
                if "【" in l or l.startswith("结论") or "🔴" in l or "🟠" in l or "🟡" in l]
        if hits:
            print("COMPLIANCE")
            for l in hits:
                print("  " + l)

    report = os.path.join(d, "_measure.json")
    cmd = [NODE, RENDER2] + jobs + ["--scale", "2", "--report", report]
    if not args.no_autogap:
        cmd.append("--autogap")
    code, out = run(cmd, cwd=d, env=env)
    if not args.quiet:
        print(out.rstrip())

    if not os.path.exists(report):
        print("ERR 未生成测量报告")
        sys.exit(1)
    data = json.load(open(report, encoding="utf-8"))
    by_out = {os.path.basename(j["out"]): j["rows"] for j in data}

    total_gap_fix = 0
    for spec, outdir in specs:
        n = writeback_gap(d, spec, outdir, by_out.get(outdir, []))
        total_gap_fix += n
        if n and not args.quiet:
            print("  ↳ %s: 回写 %d 页 gap" % (spec, n))

    bad = sum(1 for j in data for r in j["rows"]
              if r["verdict"] in ("LOW", "CROWD", "WRAP", "OVERFLOW"))
    print("RESULT  bad=%d  gap_writeback=%d  shots=%d" %
          (bad, total_gap_fix, sum(len(j["saved"]) for j in data)))

    if args.tag:
        if not (XHS_DIR or DY_DIR):
            print("ERR --tag 需要成品根目录：设 XHS_DIR / DY_DIR 环境变量后重试")
            sys.exit(1)
        # 文件夹名带日期前缀（20261005_主题），HTML 主文件名不带日期
        main_name = args.file_name or re.sub(r"^\d{8}_", "", args.tag)
        code, out = run([PY, DELIVER, d, args.tag, main_name, main_name])
        print(out.rstrip()[-500:])

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
