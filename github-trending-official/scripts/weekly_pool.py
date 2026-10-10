# -*- coding: utf-8 -*-
"""
周报自动化 —— 每周一期，抓 GitHub 官方周榜并生成选题池
=====================================================================
**为什么是每周一而不是固定「周报日」**
2026-10-07 实测：GitHub 官方周榜是**滚动 7 天窗口**，不是自然周（周一→周日）。
证据：10-06 与 10-07 两次抓取，20 条 → 12 条，15 个掉榜、7 个新进榜；
且同名项目的「周增量」一天内就变了（openrig 3776 → 3327，说明旧项目正退出窗口）。
→ 所以不存在「官方每周四更新」这种时刻。**任意时刻抓都是有效的滚动 7 天快照。**
→ 选周一早上的唯一理由是**读者预期**（"周报"这个词的自然节奏），不是数据原因。

用法：
  python weekly_pool.py                 # 抓取 + 生成选题池（默认今天日期）
  python weekly_pool.py --date 2026-10-07
  python weekly_pool.py --limit 12      # 只取前N条（默认 12，约等于官方页实际条数）

产物（**只出一份，不分平台**，2026-10-08 起）：
  C:\选题\选题池_GitHub周榜与推荐_<YYYY-MM-DD>.html
  （可用环境变量 TOPIC_DIR 覆盖目录；平台目录 C:\小红书 / C:\抖音 只放成品）
中间数据留在 <workdir>，便于复查：
  _gh_weekly.json / _gh_daily.json / _gh_fields.json / _pool_desc.json
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)          # github-trending-official skill 根
SCRIPTS = os.path.join(SKILL, "scripts")

DEFAULT_PY = sys.executable
TREND = os.path.join(SCRIPTS, "github_trending_official.py")
FIELDS = os.path.join(SCRIPTS, "fetch_repo_fields.py")
BUILD = os.path.join(SCRIPTS, "build_pool.py")

# 选题池输出目录：环境变量优先，其次本机惯例
# 2026-10-08 起选题只出一份，统一放 C:\选题（不再分平台；平台目录只放成品）
def _topic_dir():
    return os.environ.get("TOPIC_DIR") or r"C:\选题"


def run(cmd, timeout=600):
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    dt = time.time() - t0
    tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    print("  [%5.1fs] %s" % (dt, tail[-1] if tail else "(no output)"))
    if r.returncode != 0:
        print("  !! 退出码 %s" % r.returncode)
        for line in tail[-5:]:
            print("     " + line)
    return r


def main():
    ap = argparse.ArgumentParser(description="GitHub 周榜选题池（每周一期）")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--work", default="")
    args = ap.parse_args()

    work = args.work or os.path.join(
        os.environ.get("TEMP", "."), "_gh_weekly_%s" % args.date.replace("-", ""))
    os.makedirs(work, exist_ok=True)
    w = lambda n: os.path.join(work, n)
    d = args.date.replace("-", "")

    print("== GitHub 周榜选题池 %s ==" % args.date)
    print("工作目录: %s" % work)
    print()

    print("[1/4] 抓周榜（官方 trending?since=weekly，star 增量口径）")
    run([DEFAULT_PY, TREND, "--period", "weekly", "--limit", str(args.limit),
         "--json", "--out", w("_gh_weekly.json")])

    print("[2/4] 抓日榜（用于标注重合）")
    run([DEFAULT_PY, TREND, "--period", "daily", "--limit", str(args.limit),
         "--json", "--out", w("_gh_daily.json")])

    # 汇总仓库清单
    def load(p):
        if not os.path.exists(p):
            return []
        d = json.load(open(p, encoding="utf-8"))
        return d if isinstance(d, list) else d.get("items", [])

    weekly = load(w("_gh_weekly.json"))
    daily = load(w("_gh_daily.json"))
    if not weekly:
        print("ERR 周榜没抓到数据，终止（不生成空文件）")
        sys.exit(1)

    names, seen = [], set()
    for x in weekly + daily:
        n = x.get("name")
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    with open(w("repos.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names))

    print("[3/4] 抓仓库字段（星标 / 最后更新 pushed_at / 许可证）")
    print("      共 %d 个仓库" % len(names))
    run([DEFAULT_PY, FIELDS, "--repos-file", w("repos.txt"),
         "--out", w("_gh_fields.json")])

    # 拼版需要人工文案文件。脚本只出数据，所以给一份带正确键名的骨架，
    # 让 build_pool.py 能跑通。
    # ⚠️ 键名必须与 build_pool.py 读取的完全一致，否则 KeyError。
    #    实测必需键共 6 个：D["a_desc"] D["b1"] D["b2"] D["b3"] D["picks"]
    #    （另有可选 D.get("extra_notes"/"pull_a"/"pull_f")）。
    #    —— 2026-10-07 因漏键连续报 KeyError: 'b1' → 'a_desc'，逐个补才试出来。
    desc_path = w("_pool_desc.json")
    if not os.path.exists(desc_path):
        names = [x["name"] for x in weekly]
        skeleton = {
            # a_desc: {仓库名: 自定义描述}，缺则回落到 trending 页的 description
            "a_desc": {n: "" for n in names},
            # b1/b2/b3: 三个推荐位，每项是 [repo, 昵称, 语言, 描述] 四元组
            "b1": [], "b2": [], "b3": [],
            # picks: 挑选建议（字符串列表）
            "picks": [],
            "extra_notes": (
                "⚠️ 本文件由 weekly_pool.py **自动生成，只有数据、没有人工文案**。"
                "a_desc / b1 / b2 / b3 / picks 全为空，**必须补写后才可交付**。"
                "参考结构：a_desc 是 {仓库名: 描述}；"
                "b1/b2/b3 每项是 `[repo, 昵称, 语言, 描述]`；picks 是字符串列表。"
            ),
        }
        json.dump(skeleton, open(desc_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("      已生成 _pool_desc.json 骨架（**需补写文案**）")

    print("[4/4] 生成选题池 HTML")
    sel = _topic_dir()
    os.makedirs(sel, exist_ok=True)
    r = run([DEFAULT_PY, BUILD, "--work", work, "--out", sel, "--date", args.date])
    print("  → %s" % sel)

    print()
    print("完成。周榜 %d 条，日榜 %d 条。" % (len(weekly), len(daily)))
    print("⚠️ 官方周榜=滚动 7 天窗口，本文件只反映 %s 抓取时刻的快照。" % args.date)


if __name__ == "__main__":
    main()