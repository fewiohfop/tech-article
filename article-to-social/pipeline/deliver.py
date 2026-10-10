# -*- coding: utf-8 -*-
"""
deliver.py — 把渲染结果与汇总 HTML 落到交付目录

用法: python deliver.py <工作目录> <主题文件夹名> <xhs主文件名> <dy主文件名>
例:   python deliver.py ./xhs_03_dsh 20261005_DeepSeek兼容Claude插件 DeepSeek兼容Claude插件 DeepSeek兼容Claude插件

交付根目录由 XHS_DIR / DY_DIR 环境变量指定（本机惯例位置见 _paths.py）；
两者都未设置时直接报错退出——**不静默丢产物**。
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PY, SCRIPTS, XHS_DIR, DY_DIR  # noqa: E402

# 2026-10-06 起两平台合并为 article-to-social，build_preview.py 只有一份
PREVIEW = os.path.join(SCRIPTS, "build_preview.py")


def main():
    work, folder, xhs_name, dy_name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    if not (XHS_DIR or DY_DIR):
        print("ERR 未设置成品根目录：设 XHS_DIR / DY_DIR 环境变量后重试")
        sys.exit(1)
    xd = os.path.join(XHS_DIR, folder) if XHS_DIR else ""
    yd = os.path.join(DY_DIR, folder) if DY_DIR else ""
    targets = [p for p in (xd, yd) if p]
    for p in targets:
        os.makedirs(p, exist_ok=True)

    for sub, dst in (("out_xhs", xd), ("out_dy", yd)):
        src = os.path.join(work, sub)
        if not os.path.isdir(src):
            continue
        for f in os.listdir(src):
            if f.lower().endswith(".png"):
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f))

    jobs = []
    if xd:
        jobs.append((os.path.join(work, "out_xhs"),
                     os.path.join(xd, "小红书_%s.html" % xhs_name),
                     os.path.join(work, "meta_xhs.json"),
                     "xhs"))
    if yd:
        jobs.append((os.path.join(work, "out_dy"),
                     os.path.join(yd, "抖音_%s.html" % dy_name),
                     os.path.join(work, "meta_dy.json"),
                     "dy"))
    for cards, out, meta, plat in jobs:
        if not os.path.isdir(cards):
            continue
        # ⚠️ 必须传 --platform：2026-10-09 前漏传，模板里「小红书」写死 →
        # 交付的「抖音_xxx.html」打开全是小红书字样（用户实测发现）。
        cmd = [PY, PREVIEW, "--cards", cards, "--out", out, "--platform", plat]
        if os.path.exists(meta):
            cmd += ["--meta", meta]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r.stdout or "").strip() or (r.stderr or "").strip())
        # 2026-10-06：把 meta 一并复制到交付目录。
        # 汇总 HTML 重构后 <title> 变成通用串「小红书图文笔记」，标题只存于 meta；
        # build_index.py 靠 meta 取标题，缺了就只能显示通用串。
        if os.path.exists(meta) and out:
            shutil.copy2(meta, os.path.join(os.path.dirname(out),
                                            os.path.basename(meta)))

    for p in targets:
        print(p, "->", len([f for f in os.listdir(p) if f.lower().endswith(".png")]), "张 PNG",
              "|", len([f for f in os.listdir(p) if f.lower().endswith(".html")]), "个 HTML")


if __name__ == "__main__":
    main()
