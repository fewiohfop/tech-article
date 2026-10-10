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
      "foot":"来源：36氪 · 量子位"
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
      抖音 —— 连号页码 idx、封面滑动提示 swipe
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
        pass  # 2026-10-08：末页互动引导 ask 已停用，不再自动注入


def esc(s):
    return str(s)


def theme_attr(page, html_theme):
    t = page.get("theme")
    return ' data-theme="%s"' % t if t else ""


def _hl(text, word):
    """把封面某一行里的**一个关键词**包成 .cv-hl 换色（2026-10-09 新增）。

    用户口径：小红书/抖音爆款封面都会在标题里挑 1 个词换色做视觉焦点，
    整行同色会让「重点不突出」。只换**第一个**匹配处，避免一行多个焦点。
    词不在行里（写错/被改）→ 原样返回，不报错；调用方另有告警。"""
    if not word or not text or word not in text:
        return text
    return text.replace(word, '<span class="cv-hl">%s</span>' % word, 1)


def render_cover(p, platform, html_theme):
    parts = []
    # compact：榜单类封面用。标题缩小、留白收紧，把版面让给 blocks。
    # 2026-10-07 新增 —— 原来封面既不渲染 blocks 也没有紧凑模式，
    # 榜单放不进去，且标题被挤到 WRAP。
    compact = ' compact' if p.get("compact") else ''
    # 按大字行数打 linesN 标记（2026-10-10）：模板据此给基准字号与行距，
    # render2.cjs 据此做「实测字宽 → 收缩」，保证每行都放得下、不折行。
    # ⚠️ 榜单类封面（compact）不加，仍走 .cover.compact 自己的小字号档。
    nbig = sum(1 for k in ("title", "title2", "title3") if p.get(k))
    lines_cls = '' if (compact or not nbig) else ' lines%d' % nbig
    fit_attr = (' data-fit="%s"' % p["cover_fit"]) if (lines_cls and p.get("cover_fit")) else ''
    parts.append('<div class="card cover%s%s"%s data-export="%s"%s>'
                 % (compact, lines_cls, theme_attr(p, html_theme), p["export"], fit_attr))
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
        # kicker 默认 38/40px + 8/9px 字距（.cv-kicker）。用户要求某条封面把这一行
        # 「字小一点」时，用它自己的 kicker_fs / kicker_ls 覆盖（2026-10-09 新增）。
        # ⚠️ 只在本页生效，不动 --fs-kicker 全局变量（避免影响别条封面）。
        # ⚠️ 只给 kicker_ls 时不写 font-size，让两平台各自沿用档位字号；
        #    写死字号会让抖音退回 38px，与平台档位脱钩。（2026-10-09 修正）
        kfs, kls = p.get("kicker_fs"), p.get("kicker_ls")
        if kfs or kls:
            _st = []
            if kfs:
                _st.append("font-size:%dpx" % kfs)
            _st.append("letter-spacing:%dpx"
                       % (kls if kls is not None else max(2, round((kfs or 38) * 0.2))))
            parts.append('    <div class="cv-kicker" style="%s">%s</div>'
                         % (";".join(_st), p["kicker"]))
        else:
            parts.append('    <div class="cv-kicker">%s</div>' % p["kicker"])
    if p.get("title"):
        fs = p.get("title_fs")
        style = ' style="font-size:%dpx;letter-spacing:-1px"' % fs if fs else ""
        parts.append('    <div class="cv-title"%s>%s</div>'
                     % (style, _hl(p["title"], p.get("title_hl"))))
    if p.get("title2"):
        fs2 = p.get("title2_fs")
        st2 = []
        if fs2:
            st2.append("font-size:%dpx" % fs2)
            st2.append("letter-spacing:-1px")
        if p.get("title2_plain"):
            # 第二行大字不要强调色（2026-10-10 新增）。用户口径「GPT6 这个字不用紫色
            # 就可以了」——整行改用主题白（--cv-title），不做视觉焦点。
            # ⚠️ 此时行内 _hl 的高亮也会是同一个白，整行同色属于预期。
            st2.append("color:var(--cv-title)")
        style2 = ' style="%s"' % ";".join(st2) if st2 else ""
        parts.append('    <div class="cv-title2"%s>%s</div>'
                     % (style2, _hl(p["title2"], p.get("title2_hl"))))
    if p.get("title3"):
        # 第三行大字（2026-10-09 新增）：白/紫/白 交替。仅个别封面用到。
        fs3 = p.get("title3_fs")
        style3 = ' style="font-size:%dpx;letter-spacing:-1px"' % fs3 if fs3 else ""
        parts.append('    <div class="cv-title3"%s>%s</div>'
                     % (style3, _hl(p["title3"], p.get("title3_hl"))))
    parts.append('    <div class="cv-line"></div>')
    if p.get("desc"):
        parts.append('    <div class="cv-desc">%s</div>' % p["desc"])
    parts.append('  </div>')
    parts.append('')
    # 封面 blocks（2026-10-07 新增）。榜单类封面靠它放整份榜单。
    if p.get("blocks"):
        parts.append('  <div class="cv-blocks">')
        parts.extend(render_blocks(p["blocks"], p.get("gap")).split("\n"))
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
        elif k == "ranklist":
            # 封面榜单专用（2026-10-07 新增）。rank 只有 nm/sc 两列、me 是「同行高亮」，
            # 装不下「一次放 10 条 + 前 5 强 / 后 5 弱」→ 单独一种。
            #   r  名次 | n  项目名 | d  一句话（仅 top 档渲染）| inc  增量数字
            #   top: 1-5 实心徽章高亮；6-10 空心徽章弱化（CSS 里 .dim 隐去 d）
            # 2026-10-07 用户反馈「6-10 与 1-5 区分太大」→ dim 档按名次逐级降透明度，
            # 做渐变过渡而不是一刀切下去。名称只写仓库名（不含 owner），owner 放末页/正文。
            out.append('    <div class="ranklist">')
            dim_rows = [r for r in b["v"] if not r.get("top")]
            for row in b["v"]:
                cls = "rl-row top" if row.get("top") else "rl-row dim"
                dt = ('<span class="rl-dt">%s</span>' % row["d"]) if row.get("d") else ""
                style = ""
                if not row.get("top") and dim_rows:
                    # 渐变过渡：第 6 名 0.85 → 每往后一名降 0.05，最末不低于 0.6。
                    # 下限不能低于 0.6 —— dim 档是空心徽章，边框本身很淡，
                    # 透明度再低徽章轮廓就整个消失（第 10 名实测只剩一条竖线）。
                    idx = dim_rows.index(row)
                    op = max(0.6, round(0.85 - idx * 0.05, 3))
                    style = ' style="opacity:%s"' % op
                out.append('      <div class="%s"%s>'
                           '<span class="rl-no">%s</span>'
                           '<span class="rl-nm">%s%s</span>'
                           '<span class="rl-inc">%s<i>stars</i></span>'
                           '</div>'
                           % (cls, style, row["r"], row["n"], dt, row.get("inc", "")))
            out.append('    </div>')
        elif k == "raw":
            out.append(b["v"])
        elif k == "sub":
            # 页内小字补充说明。模板有 .in-sub 样式，SKILL.md 也写了，
            # 但2026-10-07 实测前build_cards 漏了这个分支 → ValueError 直接失败。
            out.append('    <div class="in-sub">%s</div>' % b["v"])
        else:
            raise ValueError("未知 block 类型: %s（支持: warn/items/points/data/rank/ranklist/raw/sub）" % k)
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
    if p.get("foot"):
        if platform == "xhs":
            out.append('  <div class="in-foot">%s</div>' % p["foot"])
        else:
            # 2026-10-08：抖音末页也只出「来源」一行。原 .ask 互动引导
            # （「你觉得这波能信几成？」这类）已按用户要求全部删除 ——
            # 属于引导评论的话术，正常陈述内容即可。
            out.append('  <div class="in-foot">')
            out.append('    <span class="src">%s</span>' % p["foot"])
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

    # 封面行内高亮词自检：词不在对应行文本里 = 写了等于没写（静默失效，最难查）
    for p in spec["pages"]:
        if p.get("type") != "cover":
            continue
        for base in ("title", "title2", "title3", "kicker"):
            w = p.get(base + "_hl")
            if w and w not in (p.get(base) or ""):
                print("WARN  封面 %s 的 %s_hl=「%s」不在该行文本里，高亮不会生效"
                      % (p.get("export", "?"), base, w))

    out_html = head + "<body>\n\n" + "\n\n".join(chunks) + "\n\n</body>\n</html>\n"
    open(args.out, "w", encoding="utf-8").write(out_html)
    n = len(spec["pages"])
    exp = [p["export"] for p in spec["pages"]]
    print("OK 写入 %s（%s / %d 页）" % (args.out, platform, n))
    for e in exp:
        print("   ", e)


if __name__ == "__main__":
    main()
