# -*- coding: utf-8 -*-
"""
build_preview.py — 把导出的卡片 PNG 与文案汇总成一个单文件 HTML（图片 base64 内嵌，离线可开）

用法:
  python build_preview.py --cards <output目录> --out <汇总HTML> [--meta meta.json]

meta.json（全部字段可选，缺省则对应模块不渲染）:
{
  "topic":      "Gemini 4 Pro 曝光",
  "source":     "36氪 转载 新智元",
  "source_url": "https://...",
  "date":       "2026-09-27",
  "titles":     [{"style":"事实型","text":"..."}, ...],
  "body":       "正文，保留换行",
  "tags":       ["#Gemini4Pro", "#谷歌"],
  "verify":     [{"point":"...","sources":5,"level":"L1","note":"..."}],
  "sources":    [{"name":"Dataconomy","url":"https://..."}],
  "steps":      ["打开创作服务平台", "..."]
}
"""
import argparse
import base64
import datetime
import json
import os
import sys

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")

LEVEL_CLASS = {"L1": "lv1", "L2": "lv2", "L3": "lv3"}
LEVEL_TEXT = {"L1": "L1 共识", "L2": "L2 据报道", "L3": "L3 爆料"}


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_cards(cards_dir):
    files = sorted(
        f for f in os.listdir(cards_dir) if f.lower().endswith(IMG_EXT)
    )
    out = []
    for f in files:
        p = os.path.join(cards_dir, f)
        with open(p, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        ext = "png" if f.lower().endswith(".png") else "jpeg"
        out.append(
            {
                "name": f,
                "size_kb": round(os.path.getsize(p) / 1024, 1),
                "data": "data:image/%s;base64,%s" % (ext, b64),
            }
        )
    return out


def render_titles(titles):
    if not titles:
        return ""
    rows = []
    for i, t in enumerate(titles, 1):
        rid = "title%d" % i
        rows.append(
            '<div class="copy-row">'
            '<div class="copy-main">'
            '<span class="copy-tag">%s</span>'
            '<span class="copy-text" id="%s">%s</span>'
            "</div>"
            '<button class="btn" onclick="cp(this,\'%s\')">复制</button>'
            "</div>"
            % (esc(t.get("style", "")), rid, esc(t.get("text", "")), rid)
        )
    return "".join(rows)


def render_tags(tags):
    if not tags:
        return ""
    return (
        '<div class="copy-row">'
        '<div class="copy-main"><span class="copy-text mono" id="tagbox">%s</span></div>'
        '<button class="btn" onclick="cp(this,\'tagbox\')">复制</button>'
        "</div>" % esc(" ".join(tags))
    )


def render_wordcheck(meta):
    """发布前违禁词自检结果块（离线词库，检测标题/正文/标签）"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import check_banned_words as cbw
        lex = cbw.load_lexicon()
        parts = []
        for t in meta.get("titles") or []:
            parts.append(str(t.get("text", "")) if isinstance(t, dict) else str(t))
        parts.append(str(meta.get("body", "")))
        parts.append(" ".join(meta.get("tags") or []))
        hits = cbw.scan("\n".join(p for p in parts if p), lex)
    except Exception:
        return ""

    n = {"high": 0, "mid": 0, "low": 0}
    for h in hits:
        n[h["level"]] = n.get(h["level"], 0) + 1

    ver = esc(lex["meta"]["version"])
    if not hits:
        return (
            '<div class="wc wc-ok">✅ <b>发布前违禁词自检：未发现高危 / 中危词条</b>'
            '<span class="wc-sub">离线词库 v%s · 基于《广告法》与小红书、抖音通行规则；'
            '词库为通用规则库，不能替代平台实际审核</span></div>' % ver
        )

    if n["high"]:
        cls, icon, head = "wc-high", "🔴", "检出高危违禁词 %d 个 —— 发布前必须处理" % n["high"]
    elif n["mid"]:
        cls, icon, head = "wc-mid", "🟠", "检出中危词 %d 个 —— 建议替换后再发" % n["mid"]
    else:
        cls, icon, head = "wc-low", "🟡", "有 %d 个需人工判断的词（不必然违规）" % n["low"]

    lv_txt = {"high": "高危", "mid": "中危", "low": "提示"}
    rows = []
    for h in hits:
        sug = ('<span class="wc-sug">建议 → %s</span>' % esc(h["suggest"])) if h["suggest"] else ""
        rows.append(
            '<tr><td><span class="wc-lv %s">%s</span> <b>%s</b>%s</td>'
            '<td class="wc-g">%s</td><td class="wc-ctx">%s</td></tr>'
            % (h["level"], lv_txt[h["level"]], esc(h["word"]), sug,
               esc(h["group_name"]), esc(h["context"]))
        )
    return (
        '<div class="wc %s">%s <b>%s</b>'
        '<span class="wc-sub">离线词库 v%s · 命中≠必然违规，需结合语境判断</span>'
        '<table class="wc-t"><thead><tr>'
        '<th style="width:20%%">词</th><th style="width:20%%">类型</th><th>上下文</th>'
        '</tr></thead><tbody>%s</tbody></table></div>'
        % (cls, icon, esc(head), ver, "".join(rows))
    )


def render_verify(rows):
    if not rows:
        return ""
    tr = []
    for r in rows:
        lv = str(r.get("level", "")).upper()
        cls = LEVEL_CLASS.get(lv, "lv2")
        txt = LEVEL_TEXT.get(lv, esc(r.get("level", "")))
        tr.append(
            "<tr><td>%s</td><td class='c'>%s</td>"
            "<td class='c'><span class='lv %s'>%s</span></td><td>%s</td></tr>"
            % (
                esc(r.get("point", "")),
                esc(r.get("sources", "-")),
                cls,
                txt,
                esc(r.get("note", "")),
            )
        )
    return "".join(tr)


def render_sources(items):
    if not items:
        return ""
    li = []
    for s in items:
        name = esc(s.get("name", ""))
        url = s.get("url", "")
        if url:
            li.append('<li><a href="%s" target="_blank">%s</a></li>' % (esc(url), name))
        else:
            li.append("<li>%s</li>" % name)
    return "".join(li)


def render_steps(steps):
    if not steps:
        steps = [
            "打开小红书创作服务平台（电脑端）或 App 创作页",
            "按 01 → 最后一张 的顺序上传全部图片",
            "粘贴标题与正文，补齐标签",
            "用官方「定时发布」设定时间",
            "确认发布",
        ]
    return "".join("<li>%s</li>" % esc(s) for s in steps)


def build(cards, meta):
    topic = meta.get("topic", "小红书图文笔记")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cards_html = "".join(
        '<figure class="shot"><img src="%s" alt="%s" loading="lazy">'
        '<figcaption><b>%s</b><span>%s · %s KB</span></figcaption></figure>'
        % (c["data"], esc(c["name"]), esc(c["name"]), "2160×2880", c["size_kb"])
        for c in cards
    )
    src_line = esc(meta.get("source", ""))
    if meta.get("source_url"):
        src_line = '<a href="%s" target="_blank">%s</a>' % (
            esc(meta["source_url"]),
            src_line,
        )
    has_meta = bool(meta.get("source") or meta.get("date"))
    meta_bar = (
        '<div class="metabar">'
        + ("<span><b>来源</b>%s</span>" % src_line if meta.get("source") else "")
        + ("<span><b>日期</b>%s</span>" % esc(meta["date"]) if meta.get("date") else "")
        + "<span><b>图片</b>%d 张</span>" % len(cards)
        + "<span><b>生成</b>%s</span>" % now
        + "</div>"
        if has_meta
        else ""
    )

    tpl = TEMPLATE
    repl = {
        "%%TOPIC%%": esc(topic),
        "%%METABAR%%": meta_bar,
        "%%TITLES%%": render_titles(meta.get("titles")),
        "%%WORDCHECK%%": render_wordcheck(meta),
        "%%BODY%%": esc(meta.get("body", "")),
        "%%TAGS%%": render_tags(meta.get("tags")),
        "%%CARDS%%": cards_html,
        "%%VERIFY%%": render_verify(meta.get("verify")),
        "%%SOURCES%%": render_sources(meta.get("sources")),
        "%%STEPS%%": render_steps(meta.get("steps")),
        "%%NOW%%": now,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%%TOPIC%% · 小红书图文成品</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{
    background:#F5F6F8;color:#1F2937;
    font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
    line-height:1.7;-webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1080px;margin:0 auto;padding:48px 32px 96px}
  header.top{margin-bottom:36px}
  .eyebrow{font-size:13px;font-weight:700;letter-spacing:3px;color:#185FA5;margin-bottom:14px}
  h1{font-size:40px;line-height:1.28;font-weight:700;color:#0F172A;letter-spacing:-.5px}
  .metabar{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:22px;font-size:14px;color:#6B7280}
  .metabar b{color:#9CA3AF;font-weight:600;margin-right:6px}
  .metabar a{color:#185FA5;text-decoration:none;border-bottom:1px solid #C7DBF0}

  section{margin-top:52px}
  h2{font-size:22px;font-weight:700;color:#0F172A;padding-bottom:12px;
     border-bottom:2px solid #E5E7EB;margin-bottom:24px;display:flex;align-items:baseline;gap:12px}
  h2 em{font-style:normal;font-size:14px;font-weight:500;color:#9CA3AF}

  .card-box{background:#fff;border:1px solid #E5E7EB;border-radius:14px;padding:22px 26px;
            margin-bottom:14px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
  .copy-row{display:flex;align-items:flex-start;gap:16px}
  .copy-row+.copy-row{margin-top:14px;padding-top:14px;border-top:1px dashed #EDF0F3}
  .copy-main{flex:1;min-width:0}
  .copy-tag{display:inline-block;font-size:12px;font-weight:700;color:#185FA5;
            background:#EAF3FC;border-radius:5px;padding:3px 10px;margin-bottom:8px}
  .copy-text{display:block;font-size:16px;color:#111827;word-break:break-word}
  .copy-text.mono{font-family:"Consolas","Courier New",monospace;font-size:14px;color:#185FA5}
  .btn{flex:none;background:#185FA5;color:#fff;border:0;border-radius:8px;
       padding:8px 18px;font-size:14px;font-weight:600;cursor:pointer;
       font-family:inherit;transition:.15s;margin-top:2px}
  .btn:hover{background:#124B85}
  .btn:active{transform:scale(.97)}
  #bodybox{white-space:pre-wrap;font-size:15.5px;line-height:1.9;color:#374151}
  .cb-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
  .cb-tip{margin-top:12px;font-size:12.5px;line-height:1.7;color:#9CA3AF}
  .btn-strong{background:#185FA5;color:#fff;font-weight:700;padding:9px 16px;border-radius:8px;white-space:nowrap}
  .btn-strong:hover{background:#134B82}
  .wc{border-radius:10px;padding:14px 18px;font-size:14px;line-height:1.7;margin-bottom:16px;border:1px solid}
  .wc-ok{background:#ECFDF5;border-color:#A7F3D0;color:#065F46}
  .wc-high{background:#FEF2F2;border-color:#FCA5A5;color:#991B1B}
  .wc-mid{background:#FFFBEB;border-color:#FCD34D;color:#92400E}
  .wc-low{background:#F9FAFB;border-color:#E5E7EB;color:#4B5563}
  .wc-sub{display:block;margin-top:6px;font-size:12.5px;font-weight:400;opacity:.85}
  .wc-t{width:100%;margin-top:10px;border-collapse:collapse;font-size:13px}
  .wc-t th,.wc-t td{border:0;padding:6px 8px;text-align:left;vertical-align:top}
  .wc-t th{font-weight:700;opacity:.8;border-bottom:1px solid rgba(0,0,0,.1)}
  .wc-t td{border-bottom:1px solid rgba(0,0,0,.06)}
  .wc-ctx{font-family:"Consolas","Courier New",monospace;font-size:12.5px}
  .wc-g{font-size:12.5px}
  .wc-lv{display:inline-block;padding:1px 7px;border-radius:5px;font-size:11.5px;font-weight:700;color:#fff}
  .wc-lv.high{background:#DC2626}
  .wc-lv.mid{background:#F59E0B}
  .wc-lv.low{background:#9CA3AF}
  .wc-sug{display:block;font-size:12px;opacity:.9;font-weight:400}

  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:22px}
  .shot{background:#fff;border:1px solid #E5E7EB;border-radius:14px;overflow:hidden;
        box-shadow:0 1px 3px rgba(16,24,40,.06)}
  .shot img{display:block;width:100%;height:auto}
  .shot figcaption{display:flex;justify-content:space-between;align-items:center;
                   padding:11px 14px;font-size:12.5px;border-top:1px solid #F0F2F5}
  .shot figcaption b{color:#185FA5;font-weight:700}
  .shot figcaption span{color:#9CA3AF}

  table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;
        border:1px solid #E5E7EB;font-size:14.5px}
  th{background:#F8FAFC;text-align:left;font-size:13px;font-weight:700;color:#64748B;
     padding:13px 16px;border-bottom:1px solid #E5E7EB;letter-spacing:.3px}
  td{padding:13px 16px;border-bottom:1px solid #F1F3F6;color:#374151;vertical-align:top}
  tr:last-child td{border-bottom:0}
  td.c{text-align:center;white-space:nowrap}
  .lv{display:inline-block;font-size:12px;font-weight:700;border-radius:5px;padding:2px 9px}
  .lv1{background:#E7F6EC;color:#1A7F45}
  .lv2{background:#FFF6E5;color:#9A6100}
  .lv3{background:#FEECEC;color:#B4232A}

  ol,ul{padding-left:22px;font-size:15px;color:#374151}
  li{margin-bottom:8px}
  ol.steps{counter-reset:s;list-style:none;padding-left:0}
  ol.steps li{position:relative;padding-left:44px;margin-bottom:14px}
  ol.steps li::before{counter-increment:s;content:counter(s);position:absolute;left:0;top:0;
    width:28px;height:28px;border-radius:50%;background:#EAF3FC;color:#185FA5;
    font-size:14px;font-weight:700;display:flex;align-items:center;justify-content:center}
  a{color:#185FA5}
  .note{background:#F8FAFC;border-left:4px solid #CBD5E1;border-radius:0 8px 8px 0;
        padding:14px 18px;font-size:14px;color:#64748B;margin-top:16px}
  footer{margin-top:56px;text-align:center;font-size:13px;color:#B0B7C3}
  @media(max-width:680px){
    .wrap{padding:28px 16px 64px}
    h1{font-size:28px}
    .copy-row{flex-direction:column;gap:10px}
    .btn{width:100%}
  }
</style>
</head>
<body>
<div class="wrap">

  <header class="top">
    <div class="eyebrow">小红书图文成品</div>
    <h1>%%TOPIC%%</h1>
    %%METABAR%%
  </header>

  <section>
    <h2>发布文案 <em>点右侧按钮直接复制</em></h2>
    %%WORDCHECK%%
    <div class="card-box">
      <div style="font-size:13px;font-weight:700;color:#9CA3AF;letter-spacing:.5px;margin-bottom:14px">标题候选（选一条）</div>
      %%TITLES%%
    </div>
    <div class="card-box">
      <div class="cb-head">
        <span style="font-size:13px;font-weight:700;color:#9CA3AF;letter-spacing:.5px">正文</span>
        <button class="btn btn-strong" onclick="cpBody(this,'bodybox')">一键复制正文（已按平台换行优化）</button>
      </div>
      <div id="bodybox">%%BODY%%</div>
      <div class="cb-tip">ⓘ 小红书 / 抖音编辑器会吞掉单个换行。本按钮复制时自动把每行改成「空行分隔」，粘贴后即正常分行；直接选中复制也建议用本按钮。</div>
    </div>
    <div class="card-box">
      <div style="font-size:13px;font-weight:700;color:#9CA3AF;letter-spacing:.5px;margin-bottom:12px">标签</div>
      %%TAGS%%
    </div>
  </section>

  <section>
    <h2>图文卡片 <em>按文件名顺序上传</em></h2>
    <div class="grid">%%CARDS%%</div>
  </section>

  <section>
    <h2>事实核验表 <em>L1 共识 / L2 据报道 / L3 爆料</em></h2>
    <table>
      <thead><tr><th style="width:44%">信息点</th><th class="c" style="width:12%">来源数</th><th class="c" style="width:16%">级别</th><th>备注</th></tr></thead>
      <tbody>%%VERIFY%%</tbody>
    </table>
    <div class="note">L1 为多源一致或官方发布，正文可直接写；L3 为爆料与传闻，图文内必须标注「未经官方确认」，且不得写入标题。</div>
  </section>

  <section>
    <h2>来源清单</h2>
    <ul>%%SOURCES%%</ul>
  </section>

  <section>
    <h2>发布步骤 <em>官方入口，人工点确认</em></h2>
    <ol class="steps">%%STEPS%%</ol>
  </section>

  <footer>生成于 %%NOW%% · 本页为单文件离线汇总，图片以内嵌方式存储</footer>
</div>

<script>
function fb(t, cb){
  var ta = document.createElement('textarea');
  ta.value = t; ta.style.position='fixed'; ta.style.opacity='0';
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand('copy'); cb(); }catch(e){ alert('请手动选中复制'); }
  document.body.removeChild(ta);
}
function copyText(t, btn){
  var done = function(){
    var o = btn.textContent;
    btn.textContent = '已复制 ✓';
    setTimeout(function(){ btn.textContent = o; }, 1600);
  };
  if(navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(t).then(done).catch(function(){ fb(t, done); });
  } else {
    fb(t, done);
  }
}
function cp(btn, id){
  var el = document.getElementById(id);
  if(!el) return;
  copyText(el.innerText, btn);
}
function hardenLines(t){
  /* 小红书/抖音编辑器吞单换行 → 统一加固为「空行分隔」 */
  return String(t).replace(/\r\n/g,'\n').replace(/[ \t\u3000]+\n/g,'\n').replace(/\n+/g,'\n\n').trim();
}
function cpBody(btn, id){
  var el = document.getElementById(id);
  if(!el) return;
  copyText(hardenLines(el.innerText), btn);
}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True, help="卡片 PNG 所在目录")
    ap.add_argument("--out", required=True, help="输出的单文件 HTML 路径")
    ap.add_argument("--meta", help="meta.json 路径")
    args = ap.parse_args()

    if not os.path.isdir(args.cards):
        print("ERR 找不到卡片目录: " + args.cards)
        sys.exit(1)

    meta = {}
    if args.meta:
        if not os.path.isfile(args.meta):
            print("ERR 找不到 meta: " + args.meta)
            sys.exit(1)
        with open(args.meta, "r", encoding="utf-8") as f:
            meta = json.load(f)

    cards = load_cards(args.cards)
    if not cards:
        print("ERR 目录里没有图片: " + args.cards)
        sys.exit(1)

    html = build(cards, meta)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print("OK %s  图片 %d 张  大小 %.1f MB"
          % (args.out, len(cards), os.path.getsize(args.out) / 1024 / 1024))


if __name__ == "__main__":
    main()
