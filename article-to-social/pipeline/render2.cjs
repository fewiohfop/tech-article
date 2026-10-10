/**
 * render2.cjs — 增强渲染器（article-to-social 通用（一份模板出两平台））
 *
 * 相比 skill 自带 render.cjs 的改进：
 *   1) 一次 Chromium 会话可渲染多个 HTML（省掉重复冷启动）
 *   2) 密度检测搬到 DOM 层：不解图、不受封面光晕/贴底脚注干扰
 *   3) --autogap：按线性解算出命中目标填充度的 gap，一次收敛，不再反复重渲染
 *   4) 换行 / 溢出检测程序化，只在异常时才需要人看 PNG
 *   5) 输出精简，不把整页日志灌进上下文
 *
 * 用法:
 *   node render2.cjs --html a.html --out dirA [--html b.html --out dirB] \
 *        [--scale 2] [--autogap] [--gap-min 20] [--gap-max 70] \
 *        [--fill-lo 58] [--fill-hi 92] [--report out.json] [--no-shot]
 *
 * 说明:
 *   - 目标填充度默认 78%~90%（内容底部占卡片高度，不含贴底脚注）
 *   - gap 上限默认 70px，超出即认定「内容本身不足，需补内容」（见 SKILL 规则）
 *   - 封面与带 .in-foot 的末页不参与 autogap，仅报读数（设计使然）
 */
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright-core');

const CHROMIUM_BINS = [
  ['chrome-win64', 'chrome.exe'],
  ['chrome-win', 'chrome.exe'],
  ['chrome-win32', 'chrome.exe'],
  ['chrome-linux64', 'chrome'],
  ['chrome-linux', 'chrome'],
  ['chrome-headless-shell-linux64', 'chrome-headless-shell'],
  ['chrome-headless-shell-win64', 'chrome-headless-shell.exe'],
  ['chrome-mac', 'Chromium.app/Contents/MacOS/Chromium'],
  ['chrome-mac-arm64', 'Chromium.app/Contents/MacOS/Chromium'],
];

const CHROMIUM_ROOTS = [
  process.env.PLAYWRIGHT_BROWSERS_PATH,
  process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'ms-playwright'),
  process.env.USERPROFILE && path.join(process.env.USERPROFILE, 'AppData', 'Local', 'ms-playwright'),
  process.env.HOME && path.join(process.env.HOME, '.cache', 'ms-playwright'),
  process.env.HOME && path.join(process.env.HOME, 'Library', 'Caches', 'ms-playwright'),
].filter(Boolean);

function findChromium() {
  if (process.env.PW_CHROMIUM && fs.existsSync(process.env.PW_CHROMIUM)) return process.env.PW_CHROMIUM;
  for (const root of CHROMIUM_ROOTS) {
    if (!fs.existsSync(root)) continue;
    let dirs;
    try { dirs = fs.readdirSync(root); } catch { continue; }
    // 完整版优先，headless shell 兜底（两者渲染特性不完全相同，避免出图不一致）
    dirs = dirs
      .filter((d) => /^chrom(e|ium)/i.test(d))
      .sort((a, b) => {
        const ha = /headless[_-]?shell/i.test(a) ? 1 : 0;
        const hb = /headless[_-]?shell/i.test(b) ? 1 : 0;
        if (ha !== hb) return ha - hb;
        return b.localeCompare(a);
      });
    for (const d of dirs)
      for (const [sub, binname] of CHROMIUM_BINS) {
        const p = path.join(root, d, sub, binname);
        if (fs.existsSync(p)) return p;
      }
  }
  return null;
}

function parseArgs(argv) {
  const jobs = [];
  let cur = null;
  const o = {
    scale: 2, autogap: false, report: null, shot: true,
    // 2026-10-08：fillLo 78 → 58。用户口径「填充占 60% 以上就够，别为补密度加内容」。
    // LOW 只是「偏松」的读数，不再是需要修的问题；真正要修的是 CROWD / OVERFLOW / WRAP。
    gapMin: 20, gapMax: 70, fillLo: 58, fillHi: 92,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--html') { cur = { html: argv[++i], out: null }; jobs.push(cur); }
    else if (a === '--out') { if (cur) cur.out = argv[++i]; else throw new Error('--out 必须跟在 --html 之后'); }
    else if (a === '--scale') o.scale = Number(argv[++i]);
    else if (a === '--autogap') o.autogap = true;
    else if (a === '--no-shot') o.shot = false;
    else if (a === '--report') o.report = argv[++i];
    else if (a === '--gap-min') o.gapMin = Number(argv[++i]);
    else if (a === '--gap-max') o.gapMax = Number(argv[++i]);
    else if (a === '--fill-lo') o.fillLo = Number(argv[++i]);
    else if (a === '--fill-hi') o.fillHi = Number(argv[++i]);
  }
  return { jobs, o };
}

/* ---------- 页面内执行的测量 ---------- */
function measureCard(card) {
  const cr = card.getBoundingClientRect();
  const isCover = card.classList.contains('cover');
  let contentBottom = cr.top;
  let footTop = null;

  for (const child of card.children) {
    if (child.classList.contains('cv-grid') || child.classList.contains('cv-glow')) continue;
    const r = child.getBoundingClientRect();
    if (r.height === 0) continue;
    if (child.classList.contains('in-foot')) { footTop = r.top; continue; }
    if (child.classList.contains('in-items')) {
      for (const gc of child.children) {
        const gr = gc.getBoundingClientRect();
        if (gr.height > 0) contentBottom = Math.max(contentBottom, gr.bottom);
      }
    } else {
      contentBottom = Math.max(contentBottom, r.bottom);
    }
  }

  const lines = {};
  for (const sel of ['.cv-title', '.cv-title2', '.cv-title3', '.in-title']) {
    const el = card.querySelector(sel);
    if (!el) continue;
    const lh = parseFloat(getComputedStyle(el).lineHeight);
    const h = el.getBoundingClientRect().height;
    lines[sel] = lh > 0 ? Math.round(h / lh) : 1;
  }

  const items = card.querySelector('.in-items');
  return {
    name: card.getAttribute('data-export'),
    cover: isCover,
    fill: +(((contentBottom - cr.top) / cr.height) * 100).toFixed(1),
    foot: footTop !== null,
    lines,
    overflowPx: Math.max(0, card.scrollHeight - card.clientHeight),
    gap: items ? Math.round(parseFloat(items.style.gap || getComputedStyle(items).gap) || 0) : null,
    blockCount: items ? Array.from(items.children).filter((k) => k.getBoundingClientRect().height > 0).length : 0,
  };
}

/* ---------- 页面内执行：封面大字自适应字号（2026-10-10）----------
   背景：封面 2~3 行大字的字号原来靠人手写 title_fs/title2_fs 逐条试，
   长行（含英文）经常放不下 → 折行（WRAP）。这里按行数取基准字号，
   再用 Range 实测每行真实文本宽，收缩到「刚好放得下」。
   模式：uniform（默认，全卡大字同号，取最紧那行）/ line（每行各自取最大）。
   ⚠️ 只处理带 .linesN 的封面；行内已写死 font-size 的行视为人工指定，跳过。 */
function autofitCovers() {
  const out = [];
  for (const card of document.querySelectorAll('.card.cover')) {
    if (!/(^|\s)lines[123](\s|$)/.test(card.className)) continue;
    const bigs = Array.from(card.querySelectorAll('.cv-title,.cv-title2,.cv-title3'))
      .filter((el) => !el.style.fontSize);
    if (!bigs.length) continue;

    const cs = getComputedStyle(card);
    const avail = card.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const base = parseFloat(cs.getPropertyValue('--fs-cv-title')) || 118;
    const mode = card.getAttribute('data-fit') || 'uniform';

    // 归位到基准字号 + 不换行，实测每行真实文本宽
    const widths = bigs.map((el) => {
      el.style.fontSize = base + 'px';
      el.style.whiteSpace = 'nowrap';
      const r = document.createRange();
      r.selectNodeContents(el);
      return r.getBoundingClientRect().width;
    });

    const fitOf = (w) => Math.floor(base * (avail - 4) / w);
    const sizes = mode === 'line'
      ? widths.map((w) => Math.min(base, fitOf(w)))
      : bigs.map(() => Math.min(base, fitOf(Math.max(...widths))));

    // 收敛校验：字号的取整可能仍差 1px，最多补两轮
    for (let k = 0; k < 3; k++) {
      bigs.forEach((el, i) => { el.style.fontSize = sizes[i] + 'px'; el.style.whiteSpace = 'nowrap'; });
      let again = false;
      bigs.forEach((el, i) => {
        const r = document.createRange();
        r.selectNodeContents(el);
        if (r.getBoundingClientRect().width > avail - 1) { sizes[i] -= 1; again = true; }
      });
      if (!again) break;
    }
    bigs.forEach((el, i) => { el.style.fontSize = sizes[i] + 'px'; el.style.whiteSpace = ''; });
    // 行距随字号等比：字小一点、行距也收一点，密度才均匀
    if (mode !== 'line') card.style.setProperty('--cv-tgap', Math.round(sizes[0] * 0.22) + 'px');
    out.push({ name: card.getAttribute('data-export'), mode, base, avail: Math.round(avail), sizes });
  }
  return out;
}

/* ---------- 页面内执行的 autogap：线性解算 ---------- */
function autogapOne(cfg) {
  const { name, gapMin, gapMax, target, lo, hi } = cfg;
  const sel = '[data-export="' + String(name).replace(/"/g, '\\"') + '"]';
  const card = document.querySelector(sel);
  if (!card) return { err: 'card not found: ' + name };
  if (card.classList.contains('cover')) return { skip: 'cover' };
  if (card.querySelector('.in-foot')) return { skip: 'has-foot' };

  const items = card.querySelector('.in-items');
  if (!items) return { skip: 'no-items' };
  const kids = Array.from(items.children).filter((k) => k.getBoundingClientRect().height > 0);
  if (kids.length < 2) return { skip: 'single-block' };

  const cr = card.getBoundingClientRect();
  const cardTop = cr.top, cardH = cr.height;
  const origGap = Math.round(parseFloat(items.style.gap) || 46);

  const fillAt = (g) => {
    items.style.gap = g + 'px';
    void items.offsetHeight; // 强制 reflow
    let b = cardTop;
    for (const k of kids) {
      const r = k.getBoundingClientRect();
      if (r.height > 0) b = Math.max(b, r.bottom);
    }
    return (b - cardTop) / cardH;
  };

  const fMin = fillAt(gapMin);
  const fMax = fillAt(gapMax);
  const slope = (fMax - fMin) / (gapMax - gapMin);

  // 最小干预：原 gap 已在容差区间内、且间距不低于下限时保持不动，不为了「拉平」而无谓改动
  const fOrig = fillAt(origGap);
  if (fOrig * 100 >= lo - 2 && fOrig * 100 <= hi && origGap >= gapMin) {
    items.style.gap = origGap + 'px';
    void items.offsetHeight;
    return {
      gap: origGap, origGap, verdict: 'KEEP',
      fillAtMin: +(fMin * 100).toFixed(1),
      fillAtMax: +(fMax * 100).toFixed(1),
      finalFill: +(fOrig * 100).toFixed(1),
    };
  }

  let gap, verdict;
  if (Math.abs(slope) < 1e-6) {
    gap = origGap;
    verdict = fMin * 100 > hi ? 'CROWD_FIXED' : 'LOW_FIXED';
  } else {
    let g = gapMin + (target / 100 - fMin) / slope;
    g = Math.max(gapMin, Math.min(gapMax, Math.round(g)));
    const f = fillAt(g);
    gap = g;
    verdict = f * 100 < lo ? 'STILL_LOW' : f * 100 > hi ? 'STILL_CROWD' : 'OK';
  }
  const finalFill = fillAt(gap);
  items.style.gap = gap + 'px';
  void items.offsetHeight;
  return {
    gap, origGap, verdict,
    fillAtMin: +(fMin * 100).toFixed(1),
    fillAtMax: +(fMax * 100).toFixed(1),
    finalFill: +(finalFill * 100).toFixed(1),
  };
}

(async () => {
  const { jobs, o } = parseArgs(process.argv.slice(2));
  if (!jobs.length) { console.log('ERR 至少需要一个 --html'); process.exit(1); }
  const EXE = findChromium();
  if (!EXE) {
    console.log('ERR 未找到 Chromium。任选其一：');
    console.log('  1) npx playwright install chromium');
    console.log('  2) 设 PW_CHROMIUM=/path/to/chrome');
    console.log('  3) 设 PLAYWRIGHT_BROWSERS_PATH=/path/to/ms-playwright');
    for (const r of CHROMIUM_ROOTS) console.log('  ' + (fs.existsSync(r) ? '[有]' : '[无]') + ' ' + r);
    process.exit(1);
  }

  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({
    viewport: { width: 1200, height: 1600 },
    deviceScaleFactor: o.scale,
  });
  const page = await ctx.newPage();

  const all = [];
  let totalFail = 0;

  for (const job of jobs) {
    const HTML = path.resolve(job.html);
    const OUT = path.resolve(job.out || path.join(path.dirname(HTML), 'output'));
    const tag = path.basename(OUT);
    if (!fs.existsSync(HTML)) { console.log('ERR 找不到 ' + HTML); totalFail++; continue; }
    if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

    const failedReqs = [];
    const onFail = (r) => failedReqs.push(r.url().slice(0, 100));
    page.on('requestfailed', onFail);

    await page.goto(pathToFileURL(HTML).href, { waitUntil: 'load', timeout: 60000 });
    await page.evaluate(() => document.fonts.ready); // 代替死等 2.5s

    // ---- 封面大字自适应（必须在测量/截图之前，否则拿到的是旧字号）----
    const fitted = await page.evaluate(autofitCovers);

    // ---- 先测量原始状态 ----
    let rows = await page.evaluate((fn) => {
      const f = new Function('return (' + fn + ')')();
      return Array.from(document.querySelectorAll('[data-export]')).map(f);
    }, measureCard.toString());

    // ---- autogap ----
    if (o.autogap) {
      const tunes = [];
      for (const r of rows) {
        const res = await page.evaluate(autogapOne, {
          name: r.name, gapMin: o.gapMin, gapMax: o.gapMax,
          target: (o.fillLo + o.fillHi) / 2, lo: o.fillLo, hi: o.fillHi,
        });
        tunes.push({ name: r.name, tune: res });
      }
      // 应用后重新整体测量，拿到最终真值（含脚注/封面）
      rows = await page.evaluate((fn) => {
        const f = new Function('return (' + fn + ')')();
        return Array.from(document.querySelectorAll('[data-export]')).map(f);
      }, measureCard.toString());
      for (const r of rows) {
        const t = tunes.find((x) => x.name === r.name);
        if (t) r.tune = t.tune;
      }
    }

    // ---- 截图 ----
    const saved = [];
    if (o.shot) {
      for (const h of await page.$$('[data-export]')) {
        const name = (await h.getAttribute('data-export')) || `card-${saved.length + 1}.png`;
        await h.screenshot({ path: path.join(OUT, name) });
        saved.push(name);
      }
    }
    page.off('requestfailed', onFail);

    // ---- 判定 ----
    const judge = (r) => {
      if (r.overflowPx > 2) return 'OVERFLOW';
      if (r.cover) {
        const bad = Object.entries(r.lines || {}).filter(([k, v]) => k.startsWith('.cv-') && v > 1);
        if (bad.length) return 'WRAP';
        return 'cover';
      }
      if (r.foot) return 'foot';
      if (r.fill < o.fillLo - 2) return 'LOW';
      if (r.fill > o.fillHi) return 'CROWD';
      return 'OK';
    };
    for (const r of rows) r.verdict = judge(r);

    all.push({ out: OUT, html: HTML, rows, saved, failedReqs: failedReqs.length });

    // ---- 精简输出 ----
    console.log('JOB ' + tag + '  <' + path.basename(HTML) + '>');
    for (const r of rows) {
      const v = r.verdict;
      const mark = v === 'OK' || v === 'cover' || v === 'foot' ? '  ' : '! ';
      let extra = '';
      if (r.tune && !r.tune.skip && !r.tune.err) extra = `  gap ${r.tune.origGap}->${r.tune.gap}`;
      console.log(
        mark + (r.name + '                          ').slice(0, 26) +
        ' fill=' + String(r.fill).padStart(5) + '%' +
        '  ' + v.padEnd(9) + extra +
        (r.overflowPx > 2 ? '  overflow=' + r.overflowPx + 'px' : '')
      );
    }
    for (const f of fitted) {
      const changed = f.sizes.some((s) => s !== f.base);
      console.log((changed ? '  fit ' : '  fit ') + f.name +
        '  ' + f.mode + '  base=' + f.base + ' -> [' + f.sizes.join(', ') + ']px');
    }
    const cnt = (k) => rows.filter((r) => r.verdict === k).length;
    console.log('  SUMMARY  LOW=' + cnt('LOW') + ' CROWD=' + cnt('CROWD') +
      ' WRAP=' + cnt('WRAP') + ' OVERFLOW=' + cnt('OVERFLOW') +
      ' FAILED_REQ=' + failedReqs.length + '   shots=' + saved.length);
    console.log('');
  }

  await browser.close();

  if (o.report) fs.writeFileSync(o.report, JSON.stringify(all, null, 1), 'utf-8');
  process.exit(totalFail ? 1 : 0);
})().catch((e) => { console.log('ERR ' + e.message); process.exit(1); });
