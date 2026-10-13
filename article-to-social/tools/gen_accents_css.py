# -*- coding: utf-8 -*-
"""
gen_accents_css.py — impeccable 主题「换色皮肤」色板的**生成与写回**工具

用途：模板 templates/cards.html 里那 5 条
        [data-theme="impeccable"][data-accent="<名称>"]{...}
      颜色变量块，全部由本脚本生成 —— 别手改那些块。

用法:
  python gen_accents_css.py            # 只打印 CSS + 对比度体检报告
  python gen_accents_css.py --write    # 就地写回 templates/cards.html（替换同名块）

加一套新皮：在 PALETTES 里加一行（5 个 HSL 基准值）+ 在 cards.html 加一行同名空块占位，
           再 --write。色相命名见下。

⚠️ 本脚本只产出/维护模板 CSS，**不是出图入口** —— 出图一律走 pipeline/make.py。

关于色相取舍（2026-10-12 实测）：
  impeccable 的检测器把「深底上的霓虹紫 / 霓虹青」列为 AI 生成 UI 的典型指纹
  （ai-color-palette，计入 anti-pattern，不是 advisory）。所以紫、青两套的
  bright 色刻意压低明度与饱和度 —— 走「沉稳的酒紫 / 灰青」而不是霓虹感，
  这样六套在 `npx impeccable detect` 下都干净。
"""
import argparse
import os
import re
import colorsys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "templates", "cards.html"))

# brass（黄铜）是默认皮，手写在模板基础块里，本脚本不动它 —— 只负责另外 5 套。
PALETTES = {
    # 名称       地面 ground        纸面 paper        深底强 bright    深底次强 bright2   浅底强 deep
    "terracotta": dict(ground=(20, 16, 6.7),  paper=(30, 45, 96.5),
                       bright=(20, 58, 56),   bright2=(20, 62, 68),   deep=(20, 66, 33)),
    "indigo":     dict(ground=(220, 22, 7.5), paper=(220, 40, 97.0),
                       bright=(219, 52, 67),  bright2=(219, 58, 78),  deep=(219, 50, 36)),
    "moss":       dict(ground=(96, 12, 6.7),  paper=(80, 30, 96.5),
                       bright=(84, 36, 55),   bright2=(84, 40, 68),   deep=(84, 46, 29)),
    # 玫红：替换掉原来的「茄紫」。紫色相（~270-310°）无论怎么降饱和，
    # 都会被 impeccable 检测器判为 ai-color-palette（霓虹紫 = AI 生成 UI 指纹），
    # 实测降饱和后仍报 3 条，故整条色相换掉。
    "rose":       dict(ground=(345, 14, 7.0), paper=(345, 32, 97.0),
                       bright=(345, 46, 58),  bright2=(345, 48, 70),  deep=(345, 52, 34)),
    # 青：同样降温（原本 34/58、40/71 会被判为 cyan-on-dark）
    "teal":       dict(ground=(178, 18, 6.3), paper=(174, 26, 96.6),
                       bright=(174, 22, 50),  bright2=(174, 26, 62),  deep=(174, 44, 27)),
}

KEYS = (
    "cv-bg", "cv-title", "cv-title2", "cv-kicker", "cv-line", "cv-chip-fg",
    "cv-chip-bd", "cv-desc", "cv-src", "cv-idx", "cv-stat-bd", "cv-stat-b",
    "cv-stat-span", "in-bg", "in-title", "in-brand", "in-brand-em", "in-page",
    "in-idx", "in-sub", "in-rule", "item-bd", "item-t", "item-d", "dot", "txt",
    "acc", "hl", "data-bg", "data-sub", "rank-bd", "rank-me-bg", "foot",
    "acc-bright", "acc-bright2", "acc-deep", "on-dark-ink", "on-dark-body",
    "on-dark-mute", "on-dark-faint", "rl-line",
)

CHECKS = [
    ("cv-title",      "cv-bg",   4.5, "封面大标题（白）"),
    ("cv-title2",     "cv-bg",   4.5, "封面第二行（强调色大字）"),
    ("cv-kicker",     "cv-bg",   4.5, "封面 kicker"),
    ("cv-desc",       "cv-bg",   4.5, "封面小字说明"),
    ("cv-src",        "cv-bg",   3.0, "封面角标"),
    ("on-dark-mute",  "cv-bg",   4.5, "榜单 6-10 名文字"),
    ("on-dark-faint", "cv-bg",   3.0, "榜单 6-10 名徽章字"),
    ("acc",           "in-bg",   4.5, "内页强调色（品牌 / 竖线 / 圆点）"),
    ("in-title",      "in-bg",   7.0, "内页大标题"),
    ("item-t",        "in-bg",   7.0, "条目标题"),
    ("item-d",        "in-bg",   4.5, "条目说明"),
    ("txt",           "in-bg",   4.5, "正文"),
    ("in-sub",        "in-bg",   4.5, "页内小字"),
    ("in-page",       "in-bg",   4.5, "页码"),
    ("foot",          "in-bg",   4.5, "页脚来源"),
    ("cv-bg",         "acc-bright", 4.5, "榜单第一名徽章字"),
]


def hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def hex2rgb(x):
    x = x.lstrip("#")
    return tuple(int(x[i:i + 2], 16) for i in (0, 2, 4))


def rgba(hexcolor, a):
    r, g, b = hex2rgb(hexcolor)
    return "rgba(%d,%d,%d,%s)" % (r, g, b, ("%.2f" % a).rstrip("0").rstrip("."))


def lum(hexcolor):
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex2rgb(hexcolor)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def cr(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def build(p):
    """由 5 个 HSL 基准值派生出全部颜色变量（规则与 brass 实测值反推一致）。"""
    gh, gs, gl = p["ground"]
    ph, ps, pl = p["paper"]
    bh, bs, bl = p["bright"]
    b2h, b2s, b2l = p["bright2"]
    dh, ds, dl = p["deep"]

    v = {}
    v["cv-bg"] = hsl(gh, gs, gl)
    v["cv-title"] = hsl(ph + 5, 28, 95)
    v["cv-title2"] = hsl(b2h, b2s, b2l)
    v["cv-kicker"] = hsl(bh, bs, bl)
    v["cv-line"] = hsl(bh, bs, bl)
    v["cv-chip-fg"] = hsl(b2h, b2s, b2l)
    v["cv-chip-bd"] = rgba(hsl(bh, bs, bl), 0.5)
    v["cv-desc"] = hsl(ph, 15, 70)
    v["cv-src"] = hsl(ph - 3, 9, 53)
    v["cv-idx"] = hsl(ph - 3, 9, 53)
    v["cv-stat-bd"] = rgba(v["cv-title"], 0.16)
    v["cv-stat-b"] = hsl(bh, bs, bl)
    v["cv-stat-span"] = hsl(ph - 3, 9, 53)

    v["in-bg"] = hsl(ph, ps, pl)
    v["in-title"] = hsl(gh, 7, 11)
    v["in-brand"] = hsl(dh, ds, dl)
    v["in-brand-em"] = hsl(gh, 5, 41)
    v["in-page"] = hsl(gh, 5, 41)
    v["in-idx"] = hsl(gh, 5, 41)
    v["in-sub"] = hsl(gh, 5, 35)
    v["in-rule"] = hsl(dh, ds, dl)
    v["item-bd"] = hsl(dh, ds, dl)
    v["item-t"] = hsl(gh, 7, 11)
    v["item-d"] = hsl(gh, 6, 29)
    v["dot"] = hsl(dh, ds, dl)
    v["txt"] = hsl(gh, 7, 23)
    v["acc"] = hsl(dh, ds, dl)
    v["hl"] = hsl(gh, 7, 11)
    v["data-bg"] = hsl(ph, 33, 91.5)
    v["data-sub"] = hsl(gh, 5, 35)
    v["rank-bd"] = hsl(ph, 28, 86)
    v["rank-me-bg"] = hsl(ph, 32, 92.5)
    v["foot"] = hsl(gh, 5, 41)

    v["acc-bright"] = hsl(bh, bs, bl)
    v["acc-bright2"] = hsl(b2h, b2s, b2l)
    v["acc-deep"] = hsl(dh, ds, dl)
    v["on-dark-ink"] = v["cv-title"]
    v["on-dark-body"] = hsl(ph + 5, 30, 87)
    v["on-dark-mute"] = hsl(ph, 13, 66)
    v["on-dark-faint"] = hsl(ph - 3, 9, 53)
    v["rl-line"] = rgba(v["cv-title"], 0.13)
    return v


def css_for(name, v):
    return '[data-theme="impeccable"][data-accent="%s"]{%s}' % (
        name, "".join("--%s:%s;" % (k, v[k]) for k in KEYS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="就地写回 templates/cards.html（替换同名块）")
    args = ap.parse_args()

    blocks, failed = {}, 0
    for name, p in PALETTES.items():
        v = build(p)
        print("== %s ==" % name)
        for fg, bg, need, label in CHECKS:
            r = cr(v[fg], v[bg])
            if r < need:
                failed += 1
                print("  FAIL %-14s on %-11s = %5.2f (需 %.1f)  %s" % (fg, bg, r, need, label))
        lo = min(cr(v[fg], v[bg]) for fg, bg, _n, _l in CHECKS)
        print("  对比度最低 %.2f，%s" % (lo, "全部通过" if lo >= 4.5 else "有不达标项"))
        blocks[name] = css_for(name, v)

    if failed:
        print("\n有 %d 项不达标，已中止写回。" % failed)
        raise SystemExit(1)

    if not args.write:
        print("\n（未加 --write，仅预览）")
        for name in PALETTES:
            print(blocks[name][:110] + " ...")
        return

    s = open(TEMPLATE, encoding="utf-8").read()
    changed = 0
    for name, css in blocks.items():
        pat = re.compile(r'\[data-theme="impeccable"\]\[data-accent="%s"\]\{[^}]*\}' % name)
        if not pat.search(s):
            print("WARN  模板里没有 data-accent=\"%s\" 的块，跳过（先手工加一行占位）" % name)
            continue
        s, n = pat.subn(lambda m: css, s, count=1)
        changed += n
    open(TEMPLATE, "w", encoding="utf-8").write(s)
    print("\n写回 %s：更新 %d 块" % (TEMPLATE, changed))


if __name__ == "__main__":
    main()
