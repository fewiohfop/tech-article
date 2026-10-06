# -*- coding: utf-8 -*-
"""
build_cards.py — 用 JSON 描述页面 → 套用 article-to-social 模板 CSS → 输出 cards.html

2026-10-06 起 article-to-xhs 与 article-to-douyin 已合并为 article-to-social，
模板合并为一份，由 <html data-platform="..."> 控制平台差异（页码格式 / 封面滑动提示 /
字号档位 / 末页互动引导）。**配色两平台完全一致，不再需要注入。**

用法:
  python build_cards.py --spec spec.json --out cards.html [--template 模板路径]

spec.json 结构:
{
  "platform": "xhs" | "douyin",
  "theme": "midnight|ember|violet|jade|vermilion",   # 5 套统一主题（可整篇，也可逐页覆盖）
           "neon|flare|aurora|acid|crimson",          # 抖音旧主题名，保留为别名，已自动映射
  "html_theme": "midnight",
  "pages": [
    { "type":"cover", "export":"01-封面.png", "theme":"ember",
      "chip":"AI 前沿", "corner":"行业事件",          # xhs 右上角栏目词
      "idx":"01/08",                                  # douyin 右上角连号页码
      "kicker":"...", "title":"...", "title2":"...", "desc":"...<br>...",
      "stats":[["5","处命中"],["2","个角度"]],
      "swipe":"左滑看完全部 8 张"
    },
    { "type":"inner", "export":"02-xxx.png", "theme":"...",
      "brand":"栏目", "mark":"子栏目",                # brand em 位置
      "idx":"02/08",                                  # douyin
      "page":"01",                                    # xhs
      "title":"第一行<br>第二行", "rule":true,
      "gap":46,
      "blocks":[
         {"k":"warn","v":"..."},
         {"k":"items","v":[{"t":"...","d":"..."}]},
         {"k":"points","v":["..."]},
         {"k":"data","v":[["88%","标签"],["95.3%","标签"]]},
         {"k":"sub","v":"..."}
      ],
      "foot":"来源：36氪 · 量子位", "ask":"你觉得这波能信几成？"
    }
  ]
}
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import TEMPLATE  # noqa: E402

# 2026-10-06：两平台合并为一份模板，platform 走 <html data-platform="...">
# 模板路径由 _paths.py 解析（可用环境变量 CARDS_TEMPLATE 覆盖）
TPL = {"_default": TEMPLATE}


def autofill_platform(spec, platform):
    """
    一份内容出两个平台：平台专属的版式字段自动派生，已显式写明的值不覆盖。
      抖音 —— 连号页码 idx、封面滑动提示 swipe、末页互动引导 ask
      小红书 —— 内页页码 page
    """
    pages = spec.get("pages", [])
    n = len(pages)
    inner = 0
    for i, p in enumerate(pages):
        if p.get("type") == "cover":
            if platform == "douyin":
                p.setdefault("idx", "01/%02d" % n)
                p.setdefault("swipe", "左滑看完全部 %d 张" % n)
        else:
            inner += 1
            if platform == "douyin":
                p.setdefault("idx", "%02d/%02d" % (i + 1, n))
            if platform == "xhs":
                p.setdefault("page", "%02d" % inner)
    if platform == "douyin" and pages:
        last = pages[-1]
        if not last.get("ask") and spec.get("ask"):
            last["ask"] = spec["ask"]


def esc(s):
    return str(s)


def theme_attr(page, html_theme):
    t = page.get("theme")
    return ' data-theme="%s"' % t if t else ""


def render_cover(p, platform, html_theme):
    parts = []
    parts.append('<div class="card cover"%s data-export="%s">' % (theme_attr(p, html_theme), p["export"]))
    parts.append('  <div class="cv-grid"></div>')
    parts.append('  <div class="cv-glow"></div>')
    parts.append('')
    if platform == "xhs":
        parts.append('  <div class="cv-head">')
        parts.append('    <span class="cv-chip">%s</span>' % p.get("chip", "AI 前沿"))
        parts.append('    <span class="cv-src">%s</span>' % p.get("corner", ""))
        parts.append('  </div>')
    else:
        parts.append('  <div class="cv-head">')
        parts.append('    <span class="cv-chip">%s</span>' % p.get("chip", "AI 前沿"))
        parts.append('    <span class="cv-idx">%s</span>' % p.get("idx", ""))
        parts.append('  </div>')
    parts.append('')
    parts.append('  <div class="cv-body">')
    if p.get("kicker"):
        parts.append('    <div class="cv-kicker">%s</div>' % p["kicker"])
    if p.get("title"):
        fs = p.get("title_fs")
        style = ' style="font-size:%dpx;letter-spacing:-1px"' % fs if fs else ""
        parts.append('    <div class="cv-title"%s>%s</div>' % (style, p["title"]))
    if p.get("title2"):
        fs2 = p.get("title2_fs")
        style2 = ' style="font-size:%dpx;letter-spacing:-1px"' % fs2 if fs2 else ""
        parts.append('    <div class="cv-title2"%s>%s</div>' % (style2, p["title2"]))
    parts.append('    <div class="cv-line"></div>')
    if p.get("desc"):
        parts.append('    <div class="cv-desc">%s</div>' % p["desc"])
    parts.append('  </div>')
    parts.append('')
    stats = p.get("stats") or []
    stat_html = []
    for v, lab in stats:
        stat_html.append('      <div class="cv-stat"><b>%s</b><span>%s</span></div>' % (v, lab))
    if platform == "xhs":
        parts.append('  <div class="cv-stats">')
        parts.extend(stat_html)
        parts.append('  </div>')
    else:
        parts.append('  <div class="cv-foot">')
        parts.append('    <div class="cv-stats">')
        parts.extend(stat_html)
        parts.append('    </div>')
        if p.get("swipe"):
            parts.append('    <div class="cv-swipe"><i>👉</i>%s</div>' % p["swipe"])
        parts.append('  </div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_blocks(blocks, gap):
    out = []
    gap_attr = ' style="gap:%dpx"' % gap if gap else ""
    out.append('  <div class="in-items"%s>' % gap_attr)
    for b in blocks:
        k = b["k"]
        if k == "warn":
            out.append('    <div class="warn">%s</div>' % b["v"])
        elif k == "items":
            for it in b["v"]:
                out.append('    <div class="item">')
                out.append('      <div class="item-t">%s</div>' % it["t"])
                out.append('      <div class="item-d">%s</div>' % it["d"])
                out.append('    </div>')
        elif k == "points":
            for tx in b["v"]:
                out.append('    <div class="point"><span class="dot"></span><span class="txt">%s</span></div>' % tx)
        elif k == "data":
            out.append('    <div class="data-row">')
            for v, lab in b["v"]:
                out.append('      <div class="data-box"><b>%s</b><span>%s</span></div>' % (v, lab))
            out.append('    </div>')
        elif k == "rank":
            out.append('    <div class="rank">')
            for row in b["v"]:
                cls = "rank-row me" if row.get("me") else "rank-row"
                out.append('      <div class="%s"><span class="nm">%s</span><span class="sc">%s</span></div>'
                           % (cls, row["nm"], row["sc"]))
            out.append('    </div>')
        elif k == "raw":
            out.append(b["v"])
        else:
            raise ValueError("未知 block 类型: %s" % k)
    out.append('  </div>')
    return "\n".join(out)


def render_inner(p, platform, html_theme):
    out = []
    out.append('<div class="card inner"%s data-export="%s">' % (theme_attr(p, html_theme), p["export"]))
    out.append('  <div class="in-head">')
    brand = p.get("brand", "")
    if p.get("mark"):
        brand = '%s <em>%s</em>' % (brand, p["mark"])
    out.append('    <span class="in-brand">%s</span>' % brand)
    if platform == "xhs":
        out.append('    <span class="in-page">%s</span>' % p.get("page", ""))
    else:
        out.append('    <span class="in-idx">%s</span>' % p.get("idx", ""))
    out.append('  </div>')
    if p.get("title"):
        out.append('  <div class="in-title">%s</div>' % p["title"])
    if p.get("rule", True):
        out.append('  <div class="in-rule"></div>')
    else:
        out.append('  <div style="height:30px"></div>')
    if p.get("sub"):
        out.append('  <div class="in-sub">%s</div>' % p["sub"])
    out.append(render_blocks(p.get("blocks") or [], p.get("gap")))
    if p.get("foot") or p.get("ask"):
        if platform == "xhs":
            if p.get("foot"):
                out.append('  <div class="in-foot">%s</div>' % p["foot"])
        else:
            out.append('  <div class="in-foot">')
            out.append('    <span class="src">%s</span>' % p.get("foot", ""))
            # ask 为空时不输出空 span（抖音末页互动引导是可选字段）
            if p.get("ask"):
                out.append('    <span class="ask">%s</span>' % p["ask"])
            out.append('  </div>')
    out.append('</div>')
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--template")
    ap.add_argument("--platform", choices=["xhs", "douyin"],
                    help="覆盖 spec 里的 platform。用同一份内容出两个平台时指定此项")
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    platform = args.platform or spec.get("platform", "xhs")
    tpl_path = args.template or TPL["_default"]
    html = open(tpl_path, encoding="utf-8").read()

    head = html.split("<body>")[0]
    # 平台差异：改 <html data-platform="...">，由模板内的属性选择器接管
    # （页码格式 / 封面滑动提示 / 字号档位 / 末页互动引导）
    head = re.sub(r'(<html[^>]*data-platform=")[^"]*(")', r"\g<1>%s\g<2>" % platform,
                  head, count=1)
    # 整篇主题
    ht = spec.get("html_theme")
    if ht:
        head = re.sub(r'(<html[^>]*data-theme=")[^"]*(")', r"\g<1>%s\g<2>" % ht, head, count=1)

    # 平台专属版式字段自动派生（已写明的值不覆盖）
    autofill_platform(spec, platform)

    chunks = []
    for p in spec["pages"]:
        if p["type"] == "cover":
            chunks.append(render_cover(p, platform, ht))
        else:
            chunks.append(render_inner(p, platform, ht))

    out_html = head + "<body>\n\n" + "\n\n".join(chunks) + "\n\n</body>\n</html>\n"
    open(args.out, "w", encoding="utf-8").write(out_html)
    n = len(spec["pages"])
    exp = [p["export"] for p in spec["pages"]]
    print("OK 写入 %s（%s / %d 页）" % (args.out, platform, n))
    for e in exp:
        print("   ", e)


if __name__ == "__main__":
    main()
