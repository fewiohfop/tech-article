# -*- coding: utf-8 -*-
"""
make_all.py — 批量渲染多个选题目录

每个目录复用 make.py 的完整流程（构建 → 违禁词预检 → autogap → 测量 → 截图 → 回写），
以多进程并发跑，省掉逐条等待的往返时间。

用法:
  python make_all.py                        # 默认扫当前目录下 xhs_*
  python make_all.py --root D:\\work         # 指定根目录
  python make_all.py --pattern "xhs_0*"     # 指定目录模式
  python make_all.py --workers 4            # 并发数（默认 3）
  python make_all.py --only xhs_07_apple    # 只跑某一个

输出:每个目录一行摘要，异常页单独列出。
"""
import argparse
import concurrent.futures
import glob
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PY  # noqa: E402

MAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "make.py")


def run_one(d):
    t0 = time.time()
    r = subprocess.run([PY, MAKE, d], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    dt = time.time() - t0

    result = next((l.strip() for l in out.splitlines() if l.startswith("RESULT")), "")
    fails = [l.strip() for l in out.splitlines()
             if l.startswith("BUILD FAIL") or l.startswith("ERR")]
    bad = [l.strip() for l in out.splitlines() if re.match(r"^!\s", l)]
    comp = [l.strip() for l in out.splitlines() if "【" in l and "中危" in l]
    # 只有高危/中危才算需要关注；「提示」级多为序数词等误报，不阻断
    hits = [c for c in comp if not re.search(r"高危 0 / 中危 0", c)]
    return {
        "name": os.path.basename(d),
        "sec": dt,
        "result": result,
        "bad": bad,
        "fails": fails,
        "risk": hits,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd(),
                    help="待扫描的根目录，默认当前目录")
    ap.add_argument("--pattern", default="xhs_*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", help="只跑目录名包含该字符串的")
    a = ap.parse_args()

    dirs = [d for d in sorted(glob.glob(os.path.join(a.root, a.pattern)))
            if os.path.isdir(d) and not os.path.basename(d).startswith("_test")
            and os.path.basename(d).startswith("xhs_")]
    if a.only:
        dirs = [d for d in dirs if a.only in os.path.basename(d)]
    if not dirs:
        print("没有匹配的目录")
        sys.exit(1)

    print("批量渲染 %d 个目录，并发 %d" % (len(dirs), a.workers))
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = [f.result() for f in
                   [ex.submit(run_one, d) for d in dirs]]
    total = time.time() - t0

    print("")
    n_bad = 0
    for r in sorted(results, key=lambda x: x["name"]):
        mark = "OK " if not (r["bad"] or r["fails"] or r["risk"]) else "!! "
        n_bad += 1 if mark == "!! " else 0
        print("%s%-22s %6.1fs  %s" % (mark, r["name"], r["sec"], r["result"] or "?"))
        for b in r["bad"]:
            print("       ", b)
        for b in r["fails"]:
            print("       ", b)
        for b in r["risk"]:
            print("       违禁词:", b)
    print("")
    print("总计 %.1fs（%d 个目录，并发 %d，单目录平均 %.1fs）| 需关注目录 %d"
          % (total, len(dirs), a.workers, sum(r["sec"] for r in results) / len(results), n_bad))
    sys.exit(1 if n_bad else 0)


if __name__ == "__main__":
    main()
