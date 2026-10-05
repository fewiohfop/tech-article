#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发布前违禁词自检（离线，纯本地，不联网、不外传文案）

用法：
  python check_banned_words.py --meta meta_handraw_xhs.json
  python check_banned_words.py --text "这段文案帮我看看"
  python check_banned_words.py --html cards.html
  python check_banned_words.py --meta a.json --meta b.json --json

退出码：2=有高危命中  1=只有中危  0=仅提示或无命中
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEXICON = os.path.join(HERE, "banned_words.json")

LEVEL_ORDER = {"high": 3, "mid": 2, "low": 1}
LEVEL_LABEL = {"high": "🔴 高危", "mid": "🟠 中危", "low": "🟡 提示"}

# 常见词的替换建议（不在表里就留空，由人判断）
SUGGEST = {
    "最佳": "较好 / 表现出色", "最好": "很好 / 推荐", "最优": "更优",
    "最强": "很强 / 实力突出", "最先进": "较新的 / 新一代",
    "最便宜": "价格较低", "最低价": "较低价格", "最高级": "高品质",
    "顶级": "高端", "极致": "出色", "极品": "优质",
    "唯一": "少见 / 为数不多", "独家": "自有", "首个": "早期",
    "首创": "较早推出", "首家": "较早一批", "第一品牌": "知名品牌",
    "国家级": "国内（需有资质才可写）", "世界级": "国际水准（需有依据）",
    "100%": "（写具体数值或删除）", "百分百": "（写具体数值或删除）",
    "绝对": "（删除或改具体描述）", "彻底": "较为充分",
    "永久": "长期", "永不": "不会轻易", "终身": "长期",
    "根治": "改善", "治愈": "缓解 / 帮助改善", "痊愈": "好转",
    "治疗": "护理 / 改善", "特效": "效果明显（需依据）", "速效": "较快见效（需依据）",
    "无副作用": "（删除，不得宣称）", "不复发": "（删除，不得宣称）",
    "稳赚": "有收益预期（需风险提示）", "保本": "（删除，不得承诺）",
    "无风险": "（删除，需风险提示）", "高回报": "（删除，需风险提示）",
    "暴富": "（删除）", "躺赚": "（删除）",
    "转运": "（删除）", "开光": "（删除）", "风水": "（删除）",
    "纯天然": "天然来源（需有依据）", "无添加": "未额外添加（需有依据）",
    "三天见效": "（改为可验证的描述）", "立竿见影": "效果较快（需依据）",
    "秒杀": "限时优惠", "疯抢": "热销", "史上最低": "近期低价",
    "私信我": "评论区聊", "加微信": "（删除，站外导流）",
    "微信号": "（删除，站外导流）", "二维码": "（删除，站外导流）",
    "第一": "前列 / 领先（若为客观报道可保留，需自行判断）",
    "登顶": "升至首位（客观报道可保留）",
}


def load_lexicon(path=LEXICON):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_html_text(html):
    """粗略提取 HTML 可见文本（够用于违禁词扫描）"""
    t = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.DOTALL | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.DOTALL)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"[ \t\u3000]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def load_meta_text(path):
    """从 meta.json 抽 title / body / tags"""
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    parts = []
    for t in d.get("titles", []) or []:
        if isinstance(t, dict):
            parts.append(str(t.get("text", "")))
        else:
            parts.append(str(t))
    parts.append(str(d.get("body", "")))
    parts.append(" ".join(d.get("tags", []) or []))
    return "\n".join(p for p in parts if p)


def scan(text, lex):
    """命中列表。长词优先，被更长命中词完全包含的短词不再重复报。"""
    cands = []
    seen = set()
    for g in lex["groups"]:
        for w in g["words"]:
            if w in seen:
                continue
            seen.add(w)
            idxs = [m.start() for m in re.finditer(re.escape(w), text)]
            if not idxs:
                continue
            cands.append({
                "word": w, "group": g["id"], "group_name": g["name"],
                "level": g["level"], "count": len(idxs), "first": idxs[0],
            })

    cands.sort(key=lambda c: -len(c["word"]))
    covered = []
    kept = []
    for c in cands:
        s, e = c["first"], c["first"] + len(c["word"])
        if any(s >= a and e <= b for a, b in covered):
            continue
        covered.append((s, e))
        kept.append(c)

    for h in kept:
        i = h["first"]
        left = max(0, i - 16)
        right = min(len(text), i + len(h["word"]) + 16)
        ctx = text[left:right].replace("\n", " ⏎ ")
        if left > 0:
            ctx = "…" + ctx
        if right < len(text):
            ctx = ctx + "…"
        h["context"] = ctx
        h["suggest"] = SUGGEST.get(h["word"], "")

    kept.sort(key=lambda h: (-LEVEL_ORDER[h["level"]], -h["count"], h["word"]))
    return kept


def report(name, hits):
    lines = []
    if not hits:
        lines.append("  ✅ 未命中任何词条")
        return "\n".join(lines)
    by = {}
    for h in hits:
        by.setdefault(h["level"], []).append(h)
    for lv in ("high", "mid", "low"):
        if lv not in by:
            continue
        lines.append("  %s（%d 个）" % (LEVEL_LABEL[lv], len(by[lv])))
        for h in by[lv]:
            s = "　→ 建议：%s" % h["suggest"] if h["suggest"] else ""
            lines.append("    · %-14s [%s] ×%d%s" % (h["word"], h["group_name"], h["count"], s))
            lines.append("      上下文：%s" % h["context"])
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="发布前违禁词自检（离线）")
    ap.add_argument("--meta", action="append", default=[], help="meta.json 路径，可多次")
    ap.add_argument("--html", action="append", default=[], help="HTML 路径，可多次")
    ap.add_argument("--text", action="append", default=[], help="直接传文本，可多次")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if not (args.meta or args.html or args.text):
        ap.error("至少给一个 --meta / --html / --text")

    lex = load_lexicon()
    tasks = []
    for p in args.meta:
        tasks.append((os.path.basename(p), load_meta_text(p)))
    for p in args.html:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            tasks.append((os.path.basename(p), extract_html_text(f.read())))
    for t in args.text:
        tasks.append(("(直接输入)", t))

    all_out = {}
    worst = 0
    for name, text in tasks:
        hits = scan(text, lex)
        all_out[name] = hits
        for h in hits:
            worst = max(worst, {"high": 2, "mid": 1, "low": 0}[h["level"]])

    if args.json:
        print(json.dumps(all_out, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("发布前违禁词自检（离线词库 v%s · %s）" % (lex["meta"]["version"], lex["meta"]["updated"]))
        print("=" * 72)
        for name, hits in all_out.items():
            n_high = sum(1 for h in hits if h["level"] == "high")
            n_mid = sum(1 for h in hits if h["level"] == "mid")
            n_low = sum(1 for h in hits if h["level"] == "low")
            print("\n【%s】  高危 %d / 中危 %d / 提示 %d" % (name, n_high, n_mid, n_low))
            print(report(name, hits))
        print("\n" + "-" * 72)
        if worst == 2:
            print("结论：🔴 存在高危命中，发布前必须处理")
        elif worst == 1:
            print("结论：🟠 存在中危命中，建议处理后发布")
        else:
            print("结论：✅ 未发现高危/中危词条")
        print("说明：词库为通用规则库，不能替代平台实际审核；命中≠必然违规，需结合语境判断。")
    return worst


if __name__ == "__main__":
    sys.exit(main())
