# -*- coding: utf-8 -*-
"""
内容成品总索引生成器
=====================================================================
扫描小红书 / 抖音两个成品根目录下所有「已完成成品目录」，生成一张单文件 HTML 索引页。
双击即可看到全部成品，并直接点开对应的汇总页（不用再去翻找目录或翻聊天记录）。

目录配置优先级（换机器 / 上云端**无需改代码**）：
  --roots CLI 参数  >  环境变量 XHS_DIR / DY_DIR / INDEX_OUT  >  skill 目录下 config.json  >  内置默认

用法：
  python build_index.py
  python build_index.py --out "C:\\内容成品总索引.html"
  python build_index.py --roots "C:\\小红书" "D:\\抖音"
  XHS_DIR=/root/xhs DY_DIR=/root/dy python build_index.py

约定：
  成品目录名格式 = YYYYMMDD_项目名，例如 20260929_手绘风格技能包
  目录内需含至少 1 个 *.html（汇总页）与若干 *.png（卡片）
"""
import os
import re
import sys
import html
import json
import argparse
from datetime import datetime
from urllib.parse import quote

# ---------------------------------------------------------------- 配置
#
# 跨设备 / 云端：不要改这里的常量，用「环境变量」或「同级的 config.json」覆盖。
# 优先级：CLI 参数 > 环境变量 > config.json > 内置默认。

CONFIG_NAME = "config.json"


def _skill_root():
    """本脚本所在 skill 的根目录（scripts 的上一级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """读 skill 根目录下的 config.json（可选，不进版本库）。"""
    p = os.path.join(_skill_root(), CONFIG_NAME)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        print("WARN %s 解析失败，已忽略：%s" % (CONFIG_NAME, e))
        return {}


CFG = load_config()


def cfg_dir(env_name, cfg_key, default):
    """目录型配置：环境变量 > config.json > 内置默认。"""
    return os.environ.get(env_name) or CFG.get(cfg_key) or default


DEFAULT_XHS = cfg_dir("XHS_DIR", "xhs_dir", r"C:\小红书")
DEFAULT_DY = cfg_dir("DY_DIR", "dy_dir", r"C:\抖音")

DEFAULT_ROOTS = [
    (DEFAULT_XHS, "小红书"),
    (DEFAULT_DY, "抖音"),
]

DEFAULT_OUT = cfg_dir(
    "INDEX_OUT", "index_out", os.path.join(DEFAULT_XHS, "内容成品总索引.html")
)

# 非成品目录（不作为成品列出）
SKIP_DIRS = {"合集封面", "发布助手", "选题", "选题池", ".workbuddy", "_build"}

# 选题类目录（单独一栏列出其中的 HTML）
SELECTION_DIR_NAMES = ["选题", "选题池"]

DATE_RE = re.compile(r"^(\d{8})_(.+)$")


# ---------------------------------------------------------------- 工具


def read_title(path):
    """从汇总 HTML 的 <title> 里取主题名，并去掉尾部平台后缀。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read(30000)
        m = re.search(r"<title>(.*?)</title>", raw, re.S)
        if not m:
            return ""
        t = html.unescape(m.group(1).strip())
        # 去掉「· 小红书图文成品」这类尾巴
        t = re.sub(r"\s*[·|]\s*[^·|]*图文成品\s*$", "", t).strip()
        return t
    except Exception:
        return ""


def file_url(path):
    """把本地路径转成浏览器可点的 file:// URL（中文做百分号编码）。"""
    p = os.path.abspath(path).replace("\\", "/")
    return "file:///" + quote(p, safe="/:")


def mtime_str(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%m-%d %H:%M")
    except Exception:
        return ""


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


# ---------------------------------------------------------------- 扫描


def scan(roots):
    items, picks = [], []

    for root, platform in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if not os.path.isdir(full):
                continue
            if name in SKIP_DIRS:
                # 选题类目录单独收集
                if name in SELECTION_DIR_NAMES:
                    for f in sorted(os.listdir(full)):
                        if f.lower().endswith((".html", ".htm")):
                            fp = os.path.join(full, f)
                            picks.append(
                                {
                                    "platform": platform,
                                    "file": f,
                                    "path": fp,
                                    "size": os.path.getsize(fp),
                                    "mtime": mtime_str(fp),
                                }
                            )
                continue

            m = DATE_RE.match(name)
            if not m:
                continue

            pngs = [
                f
                for f in os.listdir(full)
                if f.lower().endswith(".png") and not f.startswith("~$")
            ]
            htmls = [
                f
                for f in os.listdir(full)
                if f.lower().endswith((".html", ".htm"))
            ]
            if not htmls:
                continue

            htmls.sort(key=lambda f: (0 if "小红书" in f or "抖音" in f else 1, f))
            main = os.path.join(full, htmls[0])

            items.append(
                {
                    "date": m.group(1),
                    "date_fmt": "%s-%s-%s" % (m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:]),
                    "topic": m.group(2),
                    "platform": platform,
                    "dir": full,
                    "html": main,
                    "html_name": htmls[0],
                    "title": read_title(main) or m.group(2),
                    "png": len(pngs),
                    "size": os.path.getsize(main),
                    "mtime": mtime_str(main),
                }
            )

    items.sort(key=lambda x: (x["date"], x["platform"]), reverse=True)
    picks.sort(key=lambda x: x["mtime"], reverse=True)
    return items, picks


# ---------------------------------------------------------------- 渲染


def badge(platform):
    cls = "xhs" if platform == "小红书" else "dy"
    return '<span class="pf %s">%s</span>' % (cls, platform)


def render(items, picks, roots):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_xhs = sum(1 for i in items if i["platform"] == "小红书")
    n_dy = sum(1 for i in items if i["platform"] == "抖音")

    rows = []
    for it in items:
        rows.append(
            """      <tr>
        <td class="d">{date}</td>
        <td class="p">{pf}</td>
        <td class="t">
          <div class="nm">{title}</div>
          <div class="meta">{topic} · {png} 张图 · {size} · 更新 {mtime}</div>
        </td>
        <td class="a"><a href="{url}" target="_blank">打开汇总页</a></td>
      </tr>""".format(
                date=it["date_fmt"],
                pf=badge(it["platform"]),
                title=html.escape(it["title"]),
                topic=html.escape(it["topic"]),
                png=it["png"],
                size=human_size(it["size"]),
                mtime=it["mtime"],
                url=file_url(it["html"]),
            )
        )

    pick_rows = []
    for p in picks:
        pick_rows.append(
            """      <tr>
        <td class="p">{pf}</td>
        <td class="t"><div class="nm">{f}</div><div class="meta">{size} · 更新 {mtime}</div></td>
        <td class="a"><a href="{url}" target="_blank">打开</a></td>
      </tr>""".format(
                pf=badge(p["platform"]),
                f=html.escape(p["file"]),
                size=human_size(p["size"]),
                mtime=p["mtime"],
                url=file_url(p["path"]),
            )
        )

    roots_txt = " · ".join(
        "%s（%s）" % (r, p) for r, p in roots if os.path.isdir(r)
    )

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>内容成品总索引</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#F5F6F8;color:#1F2937;
    font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
    line-height:1.7;-webkit-font-smoothing:antialiased}}
  .wrap{{max-width:1040px;margin:0 auto;padding:52px 32px 96px}}
  .eyebrow{{font-size:13px;font-weight:700;letter-spacing:3px;color:#185FA5;margin-bottom:14px}}
  h1{{font-size:40px;font-weight:700;color:#0F172A;letter-spacing:-.5px;line-height:1.25}}
  .lead{{margin-top:16px;font-size:15px;color:#6B7280}}
  .lead b{{color:#0F172A}}
  .stat{{display:flex;gap:14px;margin-top:26px;flex-wrap:wrap}}
  .stat div{{background:#fff;border:1px solid #E5E7EB;border-radius:12px;
    padding:16px 26px;box-shadow:0 1px 2px rgba(16,24,40,.04)}}
  .stat b{{display:block;font-size:28px;font-weight:700;color:#185FA5;line-height:1.2}}
  .stat span{{display:block;font-size:13px;color:#9CA3AF;margin-top:4px}}
  section{{margin-top:48px}}
  h2{{font-size:20px;font-weight:700;color:#0F172A;padding-bottom:12px;
    border-bottom:2px solid #E5E7EB;margin-bottom:20px;display:flex;align-items:baseline;gap:12px}}
  h2 em{{font-style:normal;font-size:13px;font-weight:500;color:#9CA3AF}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;
    border:1px solid #E5E7EB;box-shadow:0 1px 2px rgba(16,24,40,.04)}}
  th{{background:#F8FAFC;text-align:left;font-size:12.5px;font-weight:700;color:#64748B;
    padding:13px 16px;border-bottom:1px solid #E5E7EB;letter-spacing:.3px}}
  td{{padding:15px 16px;border-bottom:1px solid #F1F3F6;vertical-align:middle}}
  tr:last-child td{{border-bottom:0}}
  tr:hover td{{background:#FCFDFE}}
  td.d{{white-space:nowrap;font-family:Consolas,"Courier New",monospace;
    font-size:13.5px;color:#64748B;width:104px}}
  td.p{{width:78px}}
  .pf{{display:inline-block;font-size:12px;font-weight:700;border-radius:6px;
    padding:3px 10px;white-space:nowrap}}
  .pf.xhs{{background:#FFEDEF;color:#D92B3E}}
  .pf.dy{{background:#E9F1FE;color:#185FA5}}
  td.t .nm{{font-size:16px;font-weight:600;color:#111827;line-height:1.5}}
  td.t .meta{{font-size:12.5px;color:#9CA3AF;margin-top:4px}}
  td.a{{width:132px;text-align:right}}
  td.a a{{display:inline-block;background:#185FA5;color:#fff;text-decoration:none;
    font-size:13.5px;font-weight:600;border-radius:8px;padding:8px 16px;white-space:nowrap}}
  td.a a:hover{{background:#124B85}}
  code{{background:#F1F5F9;border-radius:5px;padding:2px 7px;font-size:13px;color:#334155}}
  footer{{margin-top:56px;text-align:center;font-size:13px;color:#B0B7C3;line-height:1.9}}
  @media(max-width:720px){{
    .wrap{{padding:28px 16px 64px}}
    h1{{font-size:28px}}
    td.d,td.p{{display:none}}
  }}
</style>
</head>
<body>
<div class="wrap">

  <div class="eyebrow">内容成品索引</div>
  <h1>做完的图文，都在这里</h1>
  <div class="lead">扫描目录：{roots}<br>
    每次有新成品，重跑一次生成脚本即可刷新本页。</div>

  <div class="stat">
    <div><b>{total}</b><span>成品总数</span></div>
    <div><b>{nx}</b><span>小红书</span></div>
    <div><b>{nd}</b><span>抖音</span></div>
    <div><b>{np}</b><span>选题池</span></div>
  </div>

  <section>
    <h2>成品图文 <em>点右侧按钮直达汇总页（标题 / 正文 / 核验表 / 发布步骤）</em></h2>
    <table>
      <thead><tr><th>日期</th><th>平台</th><th>项目</th><th></th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </section>

  <section>
    <h2>选题池 <em>每期的候选清单</em></h2>
    <table>
      <thead><tr><th>平台</th><th>文件</th><th></th></tr></thead>
      <tbody>
{picks}
      </tbody>
    </table>
  </section>

  <footer>生成于 {now} · 单文件离线索引，无外部依赖<br>
    成品目录约定：<code>YYYYMMDD_项目名</code>，内含 1 个汇总 HTML + N 张卡片 PNG</footer>
</div>
</body>
</html>
""".format(
        roots=html.escape(roots_txt),
        total=len(items),
        nx=n_xhs,
        nd=n_dy,
        np=len(picks),
        rows="\n".join(rows) if rows else '<tr><td colspan="4" style="color:#9CA3AF">暂无成品</td></tr>',
        picks="\n".join(pick_rows) if pick_rows else '<tr><td colspan="3" style="color:#9CA3AF">暂无选题池</td></tr>',
        now=now,
    )


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="生成内容成品总索引 HTML")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="输出文件路径（默认 <小红书目录>/内容成品总索引.html；可用 INDEX_OUT 覆盖）")
    ap.add_argument("--roots", nargs="*",
                    help="自定义扫描根目录（默认取 XHS_DIR / DY_DIR，或 skill 目录下 config.json）")
    args = ap.parse_args()

    if args.roots:
        roots = [(p, os.path.basename(p.rstrip("\\/")) or p) for p in args.roots]
    else:
        roots = DEFAULT_ROOTS
        missing = [r for r, _ in roots if not os.path.isdir(r)]
        if missing and len(missing) == len(roots):
            print("HINT 成品根目录一个都不存在：%s" % " / ".join(missing))
            print("     换机器 / 云端请覆盖目录配置（三选一，都不需要改代码）：")
            print('       --roots "«小红书目录»" "«抖音目录»"')
            print("       环境变量 XHS_DIR / DY_DIR / INDEX_OUT")
            print('       skill 目录下 config.json：{"xhs_dir":"…","dy_dir":"…"}')

    items, picks = scan(roots)
    out = render(items, picks, roots)

    out_parent = os.path.dirname(os.path.abspath(args.out))
    if not os.path.isdir(out_parent):
        print("ERR 输出目录不存在：%s" % out_parent)
        print("     用 --out 指到已存在的目录，或先创建该目录。")
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)

    print("OK  成品 %d 条（小红书 %d / 抖音 %d）· 选题池 %d 份"
          % (len(items),
             sum(1 for i in items if i["platform"] == "小红书"),
             sum(1 for i in items if i["platform"] == "抖音"),
             len(picks)))
    print("OUT " + os.path.abspath(args.out))
    for it in items:
        print("    %s  %-4s  %-34s %2d 图  %s"
              % (it["date_fmt"], it["platform"], it["topic"], it["png"], it["mtime"]))


if __name__ == "__main__":
    main()
