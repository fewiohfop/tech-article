/**
 * crop.cjs — 用 Chromium 把一张图裁成指定尺寸（不装 Pillow/sharp 也能裁）
 *
 * 用法:
 *   node crop.cjs <源图> <输出图> <宽> <高> [offsetY=0] [scale=1]
 *
 * 语义:
 *   把源图按 1:1 像素放到画布左上角，从 (0, offsetY) 起截取 宽×高 的区域。
 *   常用于：裁掉 AI 生图右下角的平台水印。
 *
 * 依赖: playwright-core（NODE_PATH）+ 本机 ms-playwright 的 Chromium
 */
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright-core');

const [srcArg, outArg, wArg, hArg, offArg, scaleArg] = process.argv.slice(2);
if (!srcArg || !outArg || !wArg || !hArg) {
  console.log('ERR 用法: node crop.cjs <源图> <输出图> <宽> <高> [offsetY] [scale]');
  process.exit(1);
}

const SRC = path.resolve(srcArg);
const OUT = path.resolve(outArg);
const W = Number(wArg);
const H = Number(hArg);
const OFF = Number(offArg || 0);
const SCALE = Number(scaleArg || 1);

function findChromium() {
  if (process.env.PW_CHROMIUM && fs.existsSync(process.env.PW_CHROMIUM)) return process.env.PW_CHROMIUM;
  const roots = [
    path.join(process.env.LOCALAPPDATA || '', 'ms-playwright'),
    path.join(process.env.USERPROFILE || '', 'AppData', 'Local', 'ms-playwright'),
  ];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const dirs = fs.readdirSync(root).filter((d) => d.toLowerCase().startsWith('chromium')).sort().reverse();
    for (const d of dirs) {
      for (const sub of ['chrome-win64', 'chrome-win', 'chrome-win32']) {
        const p = path.join(root, d, sub, 'chrome.exe');
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return null;
}

(async () => {
  if (!fs.existsSync(SRC)) {
    console.log('ERR 找不到源图: ' + SRC);
    process.exit(1);
  }
  const EXE = findChromium();
  if (!EXE) {
    console.log('ERR 未找到 Chromium');
    process.exit(1);
  }

  const tmpHtml = path.join(os.tmpdir(), 'crop-' + Date.now() + '.html');
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;padding:0;background:#F4F1EA}
    #wrap{position:absolute;top:${-OFF}px;left:0;width:${W}px;overflow:hidden}
    #wrap img{display:block;width:auto;max-width:none;height:auto}
  </style></head><body><div id="wrap"><img src="${pathToFileURL(SRC).href}"></div></body></html>`;
  fs.writeFileSync(tmpHtml, html, 'utf-8');

  const browser = await chromium.launch({ executablePath: EXE });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE });
  await page.goto(pathToFileURL(tmpHtml).href, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(600);

  const box = await page.evaluate(() => {
    const img = document.querySelector('#wrap img');
    return { w: img.naturalWidth, h: img.naturalHeight };
  });

  await page.screenshot({ path: OUT, clip: { x: 0, y: 0, width: W, height: H } });
  console.log(`SRC ${box.w}x${box.h}  ->  OUT ${W}x${H} @offsetY=${OFF} scale=${SCALE}`);
  console.log('SAVED ' + path.basename(OUT));

  await browser.close();
  try { fs.unlinkSync(tmpHtml); } catch (e) {}
})().catch((e) => {
  console.log('ERR ' + e.message);
  process.exit(1);
});
