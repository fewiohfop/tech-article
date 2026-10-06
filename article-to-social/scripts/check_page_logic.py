"""标题—内容一致性自查（2026-10-06用户确立的第一原则）。

核心：每页标题都是一个承诺，内容必须兑现它。
本脚本把「这页在回答什么」抽成关键词匹配，给出可疑页。

用法：
    python check_page_logic.py <工作目录>          # 检查 xhs.json + douyin.json
    python check_page_logic.py <工作目录> --strict  # 可疑页返回非零退出码

判定方式：把标题转成「在问什么」，再看该页条目里有没有对应类别的内容词。
不是靠字面匹配，是按语义类别映射：
"""
import io
import json
import os
import re
import sys

# 标题问的东西 -> 该页应该出现的证据（任一类命中即算兑现）
CATEGORY = [
    #问「是什么 / 是谁」
    ("定义归属", [
        "发布", "推出", "上线", "开源", "权重", "模型名字", "谁做的", "公司",
        "实验室", "机构", "创始人", "创立", "首次", "版本", "协议", "架构",
        "参数", "激活", "专家", "语言", "技术", "型号", "项目名",
    ]),
    # 问「为什么」
    ("原因动机", [
        "因为", "原因", "为了", "背景", "法案", "监管", "要求", "动机", "驱动",
        "所以", "由于", "政策", "合规", "推动",
    ]),
    # 问「怎么做 / 怎么训」
    ("方法步骤", [
        "预训练", "训练", "强化学习", "rollout", "数据", "算力", "GPU", "张",
        "步骤", "阶段", "流程", "方法", "怎么", "过程", "月", "周", "天",
    ]),
    # 问「有多强 / 凭什么」
    ("数字对比", [
        "跑分", "基准", "评测", "分数", "对比", "对照", "领先", "落后", "第一",
        "高于", "低于", "超过", "SOTA", "榜单", "%", "分",
    ]),
    # 问「值不值得用 / 门槛」
    ("门槛成本", [
        "部署", "显存", "内存", "单卡", "成本", "价格", "免费", "硬件", "要求",
        "门槛", "安装", "运行", "占用", "GB", "卡",
    ]),
    # 问「有什么坑」
    ("局限风险", [
        "但", "局限", "短板", "缺点", "风险", "问题", "限制", "不建议", "注意",
        "坑", "误", "不能", "没", "截止", "争议",
    ]),
]

# 标题里的疑问指向（顺序敏感：越具体的越靠前）
INTENT = [
    (r"谁更强|承认谁|谁赢|多强|有多强|凭什么是", 3),
    (r"值不值|值得|门槛|怎么用|上手|部署|多少成本|贵不|能不能", 4),
    (r"坑|风险|局限|短板|问题|争议|不准|别|站不住", 5),
    (r"怎么|如何|做法|流程|训的|训练", 2),
    (r"为什么|为何|原因|凭什么|靠什么|为了什么|是为了", 0),
    (r"撞出|同一个数|对照|对比", 3),
    (r"看点|本质|真正|不是跑分", 5),
    (r"叫什么|是什么|是啥|哪家|什么模型|模型名字|谁做的|是谁|多少|多大|多重|激活率|这模型|这套技术|模型叫|技术叫", 0),
    (r"证明不了|做到|用了", 5),
]

INTENT_NAMES = ["定义归属", "原因动机", "方法步骤", "数字对比", "门槛成本", "局限风险"]


def page_text(page):
    out = []
    out.append(str(page.get("title", "")))
    out.append(str(page.get("title2", "") or ""))
    for b in page.get("blocks", []):
        for v in b.get("v", []) or []:
            if isinstance(v, dict):
                out.append(str(v.get("t", "")))
                out.append(str(v.get("d", "")))
            else:
                out.append(str(v))
    return "\n".join(out)


def guess_intent(title):
    for pat, idx in INTENT:
        if re.search(pat, title):
            return idx
    return None


def check(path):
    d = json.load(io.open(path, encoding="utf-8"))
    pages = d.get("pages", [])
    problems = []
    print("=" * 62)
    print(os.path.basename(path), " 共", len(pages), "页")
    print("=" * 62)
    for i, pg in enumerate(pages):
        title = re.sub(r"<[^>]+>", "", str(pg.get("title", "")))
        full = page_text(pg)
        if i == 0:
            print("  p1 [封面] %s" % title.replace("\n", ""))
            continue
        if i == len(pages) - 1:
            print("  p%d [末页] %s" % (i + 1, title.replace("\n", "")))
            continue
        intent = guess_intent(title)
        if intent is None:
            print("  p%-2d ????   %s   （标题未匹配到疑问指向，需人工判断）"
                  % (i + 1, title.replace("\n", "")))
            problems.append((i + 1, title, "标题没有明确疑问指向"))
            continue
        cats = CATEGORY[intent][1]
        hit = [w for w in cats if w in full]
        name = INTENT_NAMES[intent]
        status = "OK  " if len(hit) >= 2 else "WARN"
        print("  p%-2d %s [%s] %s   命中 %d 项"
              % (i + 1, status, name, title.replace("\n", ""), len(hit)))
        if len(hit) < 2:
            problems.append((i + 1, title,
                             "标题在问「%s」，但内容命中证据仅 %d 项：%s"
                             % (name, len(hit), hit)))
    return problems


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    root = sys.argv[1]
    strict = "--strict" in sys.argv
    allp = []
    for fn in ("xhs.json", "douyin.json"):
        p = os.path.join(root, fn)
        if os.path.exists(p):
            allp += [(p, x) for x in check(p)]
    print()
    print("-" * 62)
    if not allp:
        print("✅ 全部页面的标题与内容方向一致")
        return 0
    print("⚠️ 需人工确认 %d 处：" % len(allp))
    for p, (idx, title, why) in allp:
        print("  %s 第%d页 「%s」" % (os.path.basename(p), idx, title.replace("\n", "")))
        print("     %s" % why)
    print()
    print("处理原则：先看标题问的是什么。若内容没答上，")
    print("  · 标题问的是别的事 → 改标题")
    print("  · 该页确实是这段内容 → 改标题去匹配内容")
    print("不要靠加一条硬规则补（模型名、产品名都只是结果）。")
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
