"""把小红书版 card.json 转成抖音版（一次一主题）—— 旧流程工具，保留兼容。

做两平台共用一份内容时，xhs.json 与 douyin.json 的差异只有 3 处，本脚本自动补齐：
  1) platform 改为 douyin
  2) 每页加 idx 连号页码（"03/06"），封面加 swipe 滑动提示
  3) 内页去掉小红书连号字段 page

⚠️ 2026-10-06 起推荐直接用 `card.json` 一份内容出两平台
（`make.py` 内部走 `build_cards.py`，自动注入 data-platform），**不再需要本脚本**。
本脚本仅为兼容旧调用保留。

⚠️ 2026-10-08：末页互动引导 `.ask` 已按要求全部删除，本脚本不再挂它。

用法：
  python to_douyin.py <xhs.json> <douyin.json>

⚠️ 若手工用旧流程，转完**必须手工调前两张**（见 SKILL.md「结构重组」）：
  - 第 1 张抛钩子但**不要把结论说完**
  - 第 2 张必须是第 1 张没有的新信息，且能独立成立
  - 钩子**不能与小红书版重复**，否则等于同一篇发两遍
  - 抖音字号更大，封面第二行一般不超过 7 个汉字（实测 7 字仍放得下）

另需单独写 meta_dy.json（抖音口吻比小红书直接，话题字段仍叫 tags）。
"""
import io, json, os, sys


def conv(src, dst):
    d = json.load(io.open(src, encoding="utf-8"))
    d["platform"] = "douyin"
    pages = d["pages"]
    n = len(pages)
    for i, p in enumerate(pages, 1):
        p.pop("page", None)
        p.pop("ask", None)   # 2026-10-08：互动引导已停用，清掉源里的残留字段
        p["idx"] = "%02d/%02d" % (i, n)
        if p.get("type") == "cover":
            p["swipe"] = "左滑看完全部 %d 张" % n
    json.dump(d, io.open(dst, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("%-14s -> %-14s %d 页（未挂 ask：互动引导已停用）" % (
        os.path.basename(src), os.path.basename(dst), n))


if __name__ == "__main__":
    conv(sys.argv[1], sys.argv[2])
