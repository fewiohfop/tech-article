# -*- coding: utf-8 -*-
"""
check_copy.py — 发布文案自检（小红书 / 抖音）：标题、正文、话题

平台口径（2026-09-30 用户明确，**两个平台完全一致**）：

  标题 ≤ 20 字
  正文 ≤ 1000 字
  话题 ≤ 5 个
  三条都是硬规则，超一个字 / 一个话题就发不出去。

沿革（留档防回退）：
  - 字数：中途曾按「抖音标题 ≤35 字、正文建议 1000、底线 2000」放宽过一轮，
    用户随后更正 ——「字数限制是我错了，两边都是标题 20 字，正文 1000 字，你就按照这个规则执行吧」。
    因此分平台差异已取消，`--platform` 参数**保留仅为兼容既有调用**。
  - 话题：用户 2026-09-30 明确「话题最多带 5 个，小红书和抖音都是一样的，超过 5 个的你删掉」。
    不要再写回 7 个或更多。
  - 抖音的 meta 用 first_lines 存首行候选、小红书用 titles，**两个字段都要认**
    （2026-09-30 修：此前只有小红书那份脚本认了，抖音侧标题字数等于没检）。
  - 本机对创作者中心后台的实测 dump 显示，抖音图文发布页「添加作品标题」计数器为 `19/20`，
    上限就是 20 字，与上一条更正互相印证。

用法:
  python check_copy.py meta_xhs.json                      # 默认按小红书口径
  python check_copy.py --platform dy meta_dy.json
  python check_copy.py --dir "C:\\Users\\xxx\\_build"

读取 meta json 里的 titles / first_lines / body / tags，输出：
  每条标题的字数（超上限标 超!）
  正文字数（总字符 / 去空白）与 emoji 个数（为 0 时提示「缺少 emoji 分段」）
  话题个数（超 5 个标 超!）

退出码：有任一超限 → 1，否则 0。
"""
import argparse
import glob
import json
import os
import re
import sys

TITLE_MAX = 20       # 硬限，两平台相同
BODY_MAX = 1000      # 硬限，两平台相同
BODY_TARGET = 900    # 交付目标：留余量，复制粘贴时会多带空格与换行
TOPIC_MAX = 5        # 话题上限，两平台相同（用户 2026-09-30）

PLATFORMS = {
    "xhs": {"label": "小红书"},
    "dy":  {"label": "抖音"},
}
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")

# 全角标点也算 1 字，与平台口径一致（平台按字符数算）


def check_one(path, plat):
    label = PLATFORMS[plat]["label"]
    name = os.path.basename(path)
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("  ERR  读取失败 %s: %s" % (name, e))
        return 1

    bad = 0
    print("### %s   [%s]" % (name, label))

    # 抖音的 meta 用 first_lines 存首行候选，小红书用 titles —— 两个字段都要认
    titles = d.get("titles") or d.get("first_lines") or []
    if not titles:
        print("  标题    （meta 里既没有 titles 也没有 first_lines 字段）")
    for i, t in enumerate(titles, 1):
        s = t.get("text", "") if isinstance(t, dict) else str(t)
        style = t.get("style", "") if isinstance(t, dict) else ""
        n = len(s)
        flag = "OK " if n <= TITLE_MAX else "超!"
        if n > TITLE_MAX:
            bad += 1
        print("  标题%d [%s %2d/%d 字] %s%s"
              % (i, flag, n, TITLE_MAX, ("[%s] " % style) if style else "", s))

    body = d.get("body", "")
    nb = len(body)
    nbs = len(re.sub(r"\s", "", body))
    emo = len(EMOJI_RE.findall(body))
    paras = len([x for x in body.split("\n") if x.strip()])
    over = nb > BODY_MAX
    flag = "超!" if over else "OK "
    if over:
        bad += 1
    print("  正文   [%s %d 字 · 上限 %d · 目标 %d · 去空白 %d · 段落 %d · emoji %d 个]"
          % (flag, nb, BODY_MAX, BODY_TARGET, nbs, paras, emo))
    if emo == 0:
        print("         ! 正文里没有 emoji —— 小红书/抖音的正文都要求用 emoji 做小标题分段")
    if over:
        print("         提示：超上限 %d 字，必须压到 %d 字以内再交付" % (nb - BODY_MAX, BODY_MAX))
    elif nb > BODY_TARGET:
        print("         提示：已超目标值 %d 字，但在 %d 字硬限内（未超限）" % (BODY_TARGET, BODY_MAX))

    # 话题上限 5 个（用户 2026-09-30：「话题最多带 5 个，小红书和抖音都是一样的」）
    tags = d.get("tags") or []
    if not tags:
        print("  话题   （meta 里没有 tags 字段）")
    else:
        n_t = len(tags)
        tover = n_t > TOPIC_MAX
        if tover:
            bad += 1
        print("  话题   [%s %d/%d 个] %s"
              % ("超!" if tover else "OK ", n_t, TOPIC_MAX, " ".join(str(x) for x in tags)))
        if tover:
            print("         提示：话题最多 %d 个，请删掉多余的 %d 个" % (TOPIC_MAX, n_t - TOPIC_MAX))
    print()
    return bad


def main():
    ap = argparse.ArgumentParser(description="发布文案自检（标题 / 正文 / 话题）")
    ap.add_argument("files", nargs="*", help="meta json 路径")
    ap.add_argument("--platform", choices=["xhs", "dy"], default="xhs",
                    help="仅用于标注平台名；两平台口径一致（标题 20 / 正文 1000 / 话题 5，均为硬限）")
    ap.add_argument("--dir", help="扫描该目录下所有 meta_*.json")
    args = ap.parse_args()

    targets = list(args.files)
    if args.dir:
        targets += sorted(glob.glob(os.path.join(args.dir, "meta_*.json")))
    if not targets:
        ap.print_help()
        sys.exit(2)

    total_bad = 0
    for pth in targets:
        total_bad += check_one(pth, args.platform)

    label = PLATFORMS[args.platform]["label"]
    if total_bad:
        print("!! 有 %d 处超限，必须改完再交付" % total_bad)
        sys.exit(1)
    print("全部通过：%s —— 标题 ≤%d 字、正文 ≤%d 字、话题 ≤%d 个（均为硬限）"
          % (label, TITLE_MAX, BODY_MAX, TOPIC_MAX))


if __name__ == "__main__":
    main()
