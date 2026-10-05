/**
 * render.cjs — 把 cards.html 里的每个卡片元素导出为 PNG
 *
 * 用法:
 *   node render.cjs <cards.html> <输出目录> [scale=2]
 *
 * 约定:
 *   HTML 中每个需要导出的卡片元素，必须带 data-export="文件名.png"
 *   导出的文件名即属性值，顺序 = DOM 中出现顺序（即上传顺序）
 *
 * 依赖:
 *   playwright-core（通过 NODE_PATH 引入）
 *   Chromium 自动扫描 Windows / Linux / macOS 三平台常见位置；
 *   也可用 PW_CHROMIUM 显式指定可执行文件，或用 PLAYWRIGHT_BROWSERS_PATH 指定根目录。
 */
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright-core');

const [htmlArg, outArg, scaleArg] = process.argv.slice(2);
if (!htmlArg) {
  console.log('ERR 用法: node render.cjs <cards.html> <输出目录> [scale]');
  process.exit(1);
}

const HTML = path.resolve(htmlArg);
const OUT = path.resolve(outArg || path.join(path.dirname(HTML), 'output'));
const SCALE = Number(scaleArg || 2);

/** Chromium 的候选根目录（跨 Windows / Linux / macOS） */
const CHROMIUM_ROOTS = [
  process.env.PLAYWRIGHT_BROWSERS_PATH,
  process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'ms-playwright'),
  process.env.USERPROFILE &&
    path.join(process.env.USERPROFILE, 'AppData', 'Local', 'ms-playwright'),
  process.env.HOME && path.join(process.env.HOME, '.cache', 'ms-playwright'), // Linux
  process.env.HOME &&
    path.join(process.env.HOME, 'Library', 'Caches', 'ms-playwright'), // macOS
].filter(Boolean);

/** 各平台下 子目录 → 可执行文件名 的候选组合 */
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

/** 扫描可用的 Chromium；跨平台，找不到返回 null（由调用方给安装指引） */
function findChromium() {
  // 1) 显式指定优先
  if (process.env.PW_CHROMIUM && fs.existsSync(process.env.PW_CHROMIUM)) {
    return process.env.PW_CHROMIUM;
  }
  // 2) 在候选根目录下扫 chromium-* / chrome-*
  for (const root of CHROMIUM_ROOTS) {
    if (!fs.existsSync(root)) continue;
    let dirs;
    try {
      dirs = fs.readdirSync(root);
    } catch {
      continue;
    }
    dirs = dirs
      .filter((d) => /^chrom(e|ium)/i.test(d))
      .sort((a, b) => {
        // 完整版优先，headless shell 只作兜底：两者渲染特性不完全相同，
        // 让完整版排前可保证同一份内容在任何机器上出图一致。
        const ha = /headless[_-]?shell/i.test(a) ? 1 : 0;
        const hb = /headless[_-]?shell/i.test(b) ? 1 : 0;
        if (ha !== hb) return ha - hb;
        return b.localeCompare(a); // 同组内版本号较大的优先
      });
    for (const d of dirs) {
      for (const [sub, bin] of CHROMIUM_BINS) {
        const p = path.join(root, d, sub, bin);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  // 3) 退一步：PATH 里若有系统装的 chromium / google-chrome 也能用
  const { execSync } = require('node:child_process');
  for (const name of ['chromium', 'chromium-browser', 'google-chrome', 'chrome']) {
    try {
      const p = execSync(`command -v ${name}`, { stdio: ['ignore', 'pipe', 'ignore'] })
        .toString()
        .trim();
      if (p && fs.existsSync(p)) return p;
    } catch {
      /* 没装就继续试下一个 */
    }
  }
  return null;
}

(async () => {
  if (!fs.existsSync(HTML)) {
    console.log('ERR 找不到 HTML: ' + HTML);
    process.exit(1);
  }
  const EXE = findChromium();
  if (!EXE) {
    console.log('ERR 未找到 Chromium。三种解决方式（任选其一）：');
    console.log('  1) 安装浏览器：  npx playwright install chromium');
    console.log('  2) 指定可执行文件：PW_CHROMIUM=/path/to/chrome');
    console.log('  3) 指定浏览器根目录：PLAYWRIGHT_BROWSERS_PATH=/path/to/ms-playwright');
    console.log('已扫描的位置：');
    for (const r of CHROMIUM_ROOTS) {
      console.log('  ' + (fs.existsSync(r) ? '[有]' : '[无]') + ' ' + r);
    }
    if (!CHROMIUM_ROOTS.length) console.log('  （无候选根目录：环境变量 HOME/USERPROFILE 都未设置）');
    process.exit(1);
  }
  console.log('CHROMIUM ' + EXE);

  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({ executablePath: EXE });
  const page = await browser.newPage({
    viewport: { width: 1200, height: 1600 },
    deviceScaleFactor: SCALE,
  });

  const failed = [];
  page.on('requestfailed', (r) => failed.push(r.url().slice(0, 120)));

  await page.goto(pathToFileURL(HTML).href, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(2500); // 等字体与布局稳定

  const handles = await page.$$('[data-export]');
  if (!handles.length) {
    console.log('ERR 页面里没有找到带 data-export 的元素');
    await browser.close();
    process.exit(1);
  }

  let i = 0;
  for (const h of handles) {
    const name = (await h.getAttribute('data-export')) || `card-${++i}.png`;
    await h.screenshot({ path: path.join(OUT, name) });
    console.log('SAVED ' + name);
  }

  console.log('FAILED_REQ ' + failed.length + (failed.length ? ' ' + failed.join(' | ') : ''));
  await browser.close();
})().catch((e) => {
  console.log('ERR ' + e.message);
  process.exit(1);
});
