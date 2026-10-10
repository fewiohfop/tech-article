#!/usr/bin/env bash
# run_daily.sh —— 每日选题池一键跑。只做选题发现，不碰图文生成与发布。
#
# 用法：bash C:/srtwb/pool/run_daily.sh [YYYY-MM-DD]
#
# 步骤：抓 tophub 17 节点 → 抓海外/直连源 → 解析 → 合并排序 → 出 HTML
set -u
cd "$(dirname "$0")"
PY="C:/Users/无妄/.workbuddy/binaries/python/versions/3.13.12/python.exe"
DATE="${1:-$(date +%F)}"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

echo "=== [1/5] 抓 tophub 节点 ==="
for n in x9oz2O1oXb MZd7azPorO ENeYylkeY4 8Rv2NjnvLw rYqoXz8dOD 7GdabqLeQy proPKWkeq6; do
  curl -s -m 20 "https://tophub.today/n/$n" -H "User-Agent: $UA" -o "ai_$n.html" &
done
for n in 74Kvx59dkx n4qv90roaK 74KvxK7okx 20MdK2vw1q Y3QeLMPo7k Y2KeDGQdNP \
         5VaobgvAj1 Q1Vd5Ko85R NRrvWYDe5z NaEdZZXdrO; do
  curl -s -m 20 "https://tophub.today/n/$n" -H "User-Agent: $UA" -o "tk_$n.html" &
done
wait
echo "    tophub 节点已落盘"

echo "=== [2/5] 抓海外 + 直连源 ==="
"$PY" fetch_overseas.py
curl -s -m 30 --socks5-hostname 127.0.0.1:10808 \
  "https://hacker-news.firebaseio.com/v0/topstories.json" -o hn_top.json
"$PY" fetch_hn.py 30 > /dev/null 2>&1
echo "    海外源完成"

echo "=== [3/5] 解析 tophub + GitHub ==="
"$PY" parse_tophub.py | tail -3
"$PY" parse_github.py | tail -2

echo "=== [4/5] 生成选题池 ==="
"$PY" make_pool.py "$DATE"
