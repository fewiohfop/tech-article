"""把小红书版 card.json 转成抖音版（一次一主题）。

做两平台共用一份内容时，xhs.json 与 douyin.json 的差异只有 4 处，本脚本自动补齐：
  1) platform 改为 douyin
  2) 每页加 idx 连号页码（"03/06"），封面加 swipe 滑动提示
  3) 内页去掉小红书连号字段 page
  4) 带来源脚注的末页挂 ask 互动引导

用法：
  python to_douyin.py <xhs.json> <douyin.json> "末页互动提问"

⚠️ 转完**必须手工调前两张**（抖音特有要求，见 SKILL.md「结构重组」）：
  - 第 1 张抛钩子但**不要把结论说完**
  - 第 2 张必须是第 1 张没有的新信息，且能独立成立
  - 钩子**不能与小红书版重复**，否则等于同一篇发两遍
  - 抖音字号更大，封面第二行控制在 6 个汉字内避免 WRAP

另需单独写 meta_dy.json（抖音口吻比小红书直接，话题字段仍叫 tags）。
"""
import io, json, os, sys


def conv(src, dst, ask):
    d = json.load(io.open(src, encoding="utf-8"))
    d["platform"] = "douyin"
    pages = d["pages"]
    n = len(pages)
    for i, p in enumerate(pages, 1):
        p.pop("page", None)
        p["idx"] = "%02d/%02d" % (i, n)
        if p.get("type") == "cover":
            p["swipe"] = "左滑看完全部 %d 张" % n
        if p.get("type") == "inner" and p.get("foot"):
            p["ask"] = ask
    json.dump(d, io.open(dst, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("%-14s -> %-14s %d 页  ask 已挂末页" % (
        os.path.basename(src), os.path.basename(dst), n))


if __name__ == "__main__":
    conv(sys.argv[1], sys.argv[2], sys.argv[3])
