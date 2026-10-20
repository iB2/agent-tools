'use strict';
const fs = require('fs');
const http = require('http');
const path = require('path');

function playwright() {
  const tries = [process.env.PLAYWRIGHT_PATH, 'playwright', 'playwright-core'].filter(Boolean);
  for (const n of tries) { try { return require(n); } catch (e) { /* next */ } }
  throw new Error('Playwright not found. Run `npm install` at the repo root and `npx playwright install chromium`, or set PLAYWRIGHT_PATH.');
}

async function launch(opts = {}) {
  const o = { headless: true, ...opts };
  if (process.env.CHROME_PATH) o.executablePath = process.env.CHROME_PATH;
  else if (!o.channel) o.channel = 'chromium';
  return playwright().chromium.launch(o);
}

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.m4a': 'audio/mp4', '.wav': 'audio/wav' };

function serve(root) {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      const p = path.join(root, decodeURIComponent(req.url.split('?')[0]));
      if (!p.startsWith(root) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
      const buf = fs.readFileSync(p), range = req.headers.range;
      const type = TYPES[path.extname(p)] || 'application/octet-stream';
      if (range) {
        const [a, b] = range.replace('bytes=', '').split('-');
        const s = +a, e = b ? +b : buf.length - 1;
        res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${s}-${e}/${buf.length}`, 'Accept-Ranges': 'bytes', 'Content-Length': e - s + 1 });
        return res.end(buf.subarray(s, e + 1));
      }
      res.writeHead(200, { 'Content-Type': type, 'Content-Length': buf.length, 'Accept-Ranges': 'bytes' });
      res.end(buf);
    });
    srv.listen(0, '127.0.0.1', () => resolve({ url: `http://127.0.0.1:${srv.address().port}`, close: () => srv.close() }));
  });
}

function watch(page, errs, warnings = true) {
  page.on('console', m => { if (m.type() === 'error' || (warnings && m.type() === 'warning')) errs.push(m.type() + ' ' + m.text()); });
  page.on('pageerror', e => errs.push('pageerror ' + e.message));
}

function checker() {
  let fails = 0;
  const ok = (c, msg, extra) => { console.log((c ? 'PASS ' : 'FAIL ') + msg + (extra !== undefined ? ' ' + JSON.stringify(extra) : '')); if (!c) fails++; };
  ok.done = () => { console.log(fails ? `${fails} FAILED` : 'ALL PASS'); return fails; };
  return ok;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

module.exports = { playwright, launch, serve, watch, checker, sleep };
