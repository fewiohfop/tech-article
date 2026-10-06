#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量取 GitHub 仓库字段（官方 API）——给推荐类选题池与方向 B 成篇用。
=====================================================================
取：星标 / forks / open issues / 许可证 / **pushed_at（=最后更新）** / 建仓时间 / topics / homepage。
**不要从第三方页面抄星标**：2026-09-29 实测 HelloGitHub 页面的数字与 GitHub 实际差一个数量级。

用法：
  python fetch_repo_fields.py --repos owner/a owner/b ... --out fields.json
  python fetch_repo_fields.py --repos-file repos.txt --out fields.json
  python fetch_repo_fields.py --repos owner/a --sleep 0.6

注意：
  - 未授权配额 **60 次/小时**；实测 33 个仓库顺序抓（0.6s 间隔）不超限。
  - 遇 403 会**立即停止**并把已拿到的写盘，不会静默跳过。
  - 只写标准库，无第三方依赖。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _clear_stale_proxy():
    """清掉换VPN 节点后残留的失效代理端口，避免 502。需保留时设 PROXY_PASSTHROUGH=1。"""
    if os.environ.get("PROXY_PASSTHROUGH") == "1":
        return
    hit = []
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if os.environ.get(k):
            hit.append("%s=%s" % (k, os.environ[k]))
            os.environ.pop(k, None)
    if hit:
        print("[INFO] 已清空失效代理环境变量：%s" % ", ".join(hit), file=sys.stderr)


_clear_stale_proxy()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def fetch_one(repo, timeout=25):
    url = "https://api.github.com/repos/" + repo
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                              "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    lic = (d.get("license") or {}).get("spdx_id") or ""
    return {
        "stars": d.get("stargazers_count"),
        "forks": d.get("forks_count"),
        "issues": d.get("open_issues_count"),
        "license": "" if lic in ("NOASSERTION", None) else lic,
        "pushed_at": (d.get("pushed_at") or "")[:10],   # = 最后更新，不是 updated_at
        "created_at": (d.get("created_at") or "")[:10],
        "desc": (d.get("description") or "").strip(),
        "topics": d.get("topics") or [],
        "homepage": d.get("homepage") or "",
        "archived": d.get("archived", False),
    }


def main():
    ap = argparse.ArgumentParser(description="批量取 GitHub 仓库字段")
    ap.add_argument("--repos", nargs="*", default=[], help="owner/repo 列表")
    ap.add_argument("--repos-file", help="每行一个 owner/repo 的文件")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    ap.add_argument("--sleep", type=float, default=0.6, help="请求间隔秒（默认 0.6）")
    args = ap.parse_args()

    repos = list(args.repos)
    if args.repos_file:
        with open(args.repos_file, encoding="utf-8") as f:
            repos += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    seen, uniq = set(), []
    for r in repos:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    out = {}
    for i, r in enumerate(uniq, 1):
        try:
            out[r] = fetch_one(r)
            print("[%2d/%d] OK  %-46s stars=%-8s pushed=%s" % (i, len(uniq), r, out[r]["stars"], out[r]["pushed_at"]))
        except urllib.error.HTTPError as e:
            out[r] = {"error": "HTTP %s" % e.code}
            print("[%2d/%d] HTTP %s  %s" % (i, len(uniq), e.code, r))
            if e.code == 403:
                print("!! 403 配额用尽（未授权 60 次/小时），停止后续请求")
                break
        except Exception as e:
            out[r] = {"error": str(e)[:80]}
            print("[%2d/%d] ERR  %s  %s" % (i, len(uniq), r, e))
        time.sleep(args.sleep)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    ok = sum(1 for v in out.values() if "error" not in v)
    print("SAVED %d/%d repos -> %s" % (ok, len(uniq), args.out))


if __name__ == "__main__":
    main()
