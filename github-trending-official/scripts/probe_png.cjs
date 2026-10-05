/**
 * probe_png.cjs — 用 Chromium 的 canvas 读像素，定位「右下角水印」的精确范围
 *
 * 用法:
 *   node probe_png.cjs <图片> [右侧占比=0.55] [底部起扫比例=0.5]
 *
 * 输出:
 *   图片真实尺寸、左上角背景色、右下角每一行「非背景像素」的个数（自底向上）
 *   —— 用来判断水印占了哪几行，从而决定裁掉多少。
 *
 * 为了绕开 file:// 的 canvas 污染限制，Chromium 以 --allow-file-access-from-files 启动。
 */
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright-core');

const [srcArg, rightArg, bottomArg, threshArg] = process.argv.slice(2);
if (!srcArg) {
  console.log('ERR 用法: node probe_png.cjs <图片> [右侧占比] [底部起扫比例] [阈值=45]');
  process.exit(1);
}
const SRC = path.resolve(srcArg);
const RIGHT = Number(rightArg || 0.55);
const BOTTOM = Number(bottomArg || 0.5);
const THRESH = Number(threshArg || 45);

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
  const EXE = findChromium();
  if (!EXE) { console.log('ERR 未找到 Chromium'); process.exit(1); }

  const tmpHtml = path.join(os.tmpdir(), 'probe-' + Date.now() + '.html');
  fs.writeFileSync(tmpHtml, `<!DOCTYPE html><html><body style="margin:0">
    <img id="im" src="${pathToFileURL(SRC).href}">
    <script>window.__ready = false;
      document.getElementById('im').onload = () => window.__ready = true;</script>
  </body></html>`, 'utf-8');

  const browser = await chromium.launch({
    executablePath: EXE,
    args: ['--allow-file-access-from-files', '--disable-web-security'],
  });
  const page = await browser.newPage();
  await page.goto(pathToFileURL(tmpHtml).href, { waitUntil: 'load', timeout: 60000 });
  await page.waitForFunction('window.__ready === true', { timeout: 30000 });

  const res = await page.evaluate(({ right, bottom, thresh }) => {
    const im = document.getElementById('im');
    const w = im.naturalWidth, h = im.naturalHeight;
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(im, 0, 0);
    const d = ctx.getImageData(0, 0, w, h).data;

    const bg = [d[0], d[1], d[2]];
    const x0 = Math.floor(w * right);

    const rows = [];
    for (let y = h - 1; y >= Math.floor(h * bottom); y--) {
      let cnt = 0, minX = w, maxX = -1;
      for (let x = x0; x < w; x++) {
        const i = (y * w + x) * 4;
        const diff = Math.abs(d[i] - bg[0]) + Math.abs(d[i + 1] - bg[1]) + Math.abs(d[i + 2] - bg[2]);
        if (diff > thresh) { cnt++; if (x < minX) minX = x; if (x > maxX) maxX = x; }
      }
      rows.push({ y, cnt, minX: maxX < 0 ? null : minX, maxX: maxX < 0 ? null : maxX });
    }
    return { w, h, bg, x0, rows };
  }, { right: RIGHT, bottom: BOTTOM, thresh: THRESH });

  console.log(`SIZE ${res.w}x${res.h}  BG rgb(${res.bg.join(',')})  scanX>=${res.x0}  thresh>${THRESH}`);
  const first = res.rows.find((r) => r.cnt > 3);
  console.log('==> LOWEST_CONTENT_ROW(y, count) = ' + (first ? `${first.y}, ${first.cnt}` : 'none'));
  console.log('y   count   xRange   (自底向上，只列 count>0 的行)');
  let printed = 0;
  for (const r of res.rows) {
    if (r.cnt > 0) {
      console.log(`${String(r.y).padStart(5)}  ${String(r.cnt).padStart(5)}   ${r.minX}..${r.maxX}`);
      if (++printed >= 45) { console.log('... (截断)'); break; }
    }
  }
  if (!printed) console.log('(扫描区内没有任何非背景像素)');

  await browser.close();
  try { fs.unlinkSync(tmpHtml); } catch (e) {}
})().catch((e) => { console.log('ERR ' + e.message); process.exit(1); });
