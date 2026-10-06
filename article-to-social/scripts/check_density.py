# -*- coding: utf-8 -*-
"""
check_density.py — 卡片底部留白（填充度）自动检测

用法:
  python check_density.py --cards <PNG 目录> [--low 25] [--high 10]

原理:
  从每张图的最底部一行取背景色，然后自下而上扫描，找到第一个"有内容"的行
  （该行存在明显偏离背景色的像素）。据此算出底部留白比例。

判定:
  bottom_blank > --low   → LOW    内容偏少，需补内容（不是继续拉大 gap）
  bottom_blank < --high  → CROWD  可能过挤，需肉眼复核是否溢出
  其余                    → OK

注意:
  1. 深色封面（整屏都是底色+内容）通常判为 CROWD，属正常，忽略它。
  2. 带底部脚注的末页会贴底显示，测出的留白偏小，也属正常。
  3. 本工具只做量化参考，仍必须肉眼复核最容易溢出的那几页。

实测参考值（2026-09-28，抖音模板 3:4）:
  item 型 4 条 + gap 44px  → 底部留白约 15%
  point 型 5 条 + gap 60~70px → 底部留白约 15~21%
  混合型（2 point + 榜单表） + gap 40px → 约 24%
"""
import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("ERR 需要 Pillow：请使用本机 Python 环境运行")
    sys.exit(1)

TOL = 14
IMG_EXT = (".png", ".jpg", ".jpeg")


def has_content(px, y, w, bg, step=6):
    for x in range(0, w, step):
        r, g, b = px[x, y]
        if abs(r - bg[0]) > TOL or abs(g - bg[1]) > TOL or abs(b - bg[2]) > TOL:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True, help="卡片 PNG 所在目录")
    ap.add_argument("--low", type=float, default=25.0, help="留白超过该值判 LOW（默认 25）")
    ap.add_argument("--high", type=float, default=10.0, help="留白低于该值判 CROWD（默认 10）")
    args = ap.parse_args()

    if not os.path.isdir(args.cards):
        print("ERR 找不到目录: " + args.cards)
        sys.exit(1)

    rows = []
    low_n = 0
    for f in sorted(os.listdir(args.cards)):
        if not f.lower().endswith(IMG_EXT):
            continue
        p = os.path.join(args.cards, f)
        im = Image.open(p).convert("RGB")
        w, h = im.size
        px = im.load()
        bg = px[4, h - 4]
        bottom = h - 1
        for y in range(h - 1, -1, -1):
            if has_content(px, y, w, bg):
                bottom = y
                break
        blank = (h - 1 - bottom) / h * 100
        if blank > args.low:
            flag = "LOW  "
            low_n += 1
        elif blank < args.high:
            flag = "CROWD"
        else:
            flag = "OK   "
        rows.append("%s %-20s bottom_blank=%5.1f%%  filled=%5.1f%%"
                    % (flag, f, blank, 100 - blank))

    print("\n".join(rows))
    print("\nLOW_COUNT = %d  （需补内容或调大 gap 的页数）" % low_n)


if __name__ == "__main__":
    main()
