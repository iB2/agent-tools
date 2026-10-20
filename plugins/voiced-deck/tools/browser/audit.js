'use strict';
// Screenshot every slide fully built and audit it: words, headline, overflow, small text, collisions, console errors.
// usage: node audit.js /abs/deck.html [outDir] [widths=1280,728,390] [schemes=dark,light]
const fs = require('fs');
const path = require('path');
const { launch, serve, watch } = require('./lib');

const deck = path.resolve(process.argv[2]);
const OUT = path.resolve(process.argv[3] || 'shots');
const widths = (process.argv[4] || '1280,728,390').split(',').map(Number);
const schemes = (process.argv[5] || 'dark,light').split(',');
const SKIP = '.sr,.hd,.kick,[data-noword],title,style,script,.tk';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const srv = await serve(path.dirname(deck));
  const b = await launch();
  const report = { errors: [], words: [], overflow: [], small: [], collide: [], bytes: fs.statSync(deck).size };
  for (const w of widths) for (const cs of schemes) {
    const ctx = await b.newContext({ viewport: { width: w, height: Math.round(w * (w < 560 ? 4 / 3 : 9 / 16)) + 80 }, colorScheme: cs, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    const errs = []; watch(page, errs);
    await page.goto(`${srv.url}/${path.basename(deck)}`);
    await page.addStyleTag({ content: 'body{background:' + (cs === 'dark' ? '#121212' : '#ffffff') + '}' });
    await page.waitForTimeout(500);
    await page.evaluate(() => window.__deck.instant(true));
    const n = await page.evaluate(() => window.__deck.count);
    for (let i = 1; i <= n; i++) {
      await page.evaluate(i => window.__deck.go(i - 1, 'all'), i);
      await page.waitForTimeout(400);
      const info = await page.evaluate(SKIP => {
        const s = document.querySelector('.slide.cur'), sr = document.getElementById('stage').getBoundingClientRect();
        const letters = [], numbers = [], small = [], over = [], boxes = [];
        const tw = document.createTreeWalker(s, NodeFilter.SHOW_TEXT); let nd;
        while ((nd = tw.nextNode())) {
          const pe = nd.parentElement; if (!pe) continue;
          const t = nd.textContent.trim(); if (!t) continue;
          let hidden = false; for (let a = pe; a && a !== s.parentElement; a = a.parentElement) { const c = getComputedStyle(a); if (c.display === 'none' || c.visibility === 'hidden' || +c.opacity === 0) { hidden = true; break; } }
          if (hidden) continue;
          const r = document.createRange(); r.selectNodeContents(nd); const rr = r.getBoundingClientRect();
          const svg = pe.closest('svg'), vb = svg && svg.viewBox && svg.viewBox.baseVal;
          const fsz = parseFloat(getComputedStyle(pe).fontSize) * (svg && vb && vb.width ? svg.getBoundingClientRect().width / vb.width : 1);
          if (fsz < 12.9) small.push(t.slice(0, 18) + ':' + fsz.toFixed(1));
          if (rr.width && (rr.left < sr.left - 1 || rr.right > sr.right + 1 || rr.top < sr.top - 1 || rr.bottom > sr.bottom + 1)) over.push(t.slice(0, 24));
          for (const q of r.getClientRects()) if (q.width) boxes.push([t.slice(0, 20), q.left, q.top, q.right, q.bottom]);
          if (pe.closest(SKIP)) continue;
          for (const tok of t.split(/\s+/)) { if (/[A-Za-z0-9]/.test(tok)) (/[A-Za-z]/.test(tok) ? letters : numbers).push(tok); }
        }
        const hit = [];
        for (let a = 0; a < boxes.length; a++) for (let c = a + 1; c < boxes.length; c++) {
          const A = boxes[a], C = boxes[c], ox = Math.min(A[3], C[3]) - Math.max(A[1], C[1]), oy = Math.min(A[4], C[4]) - Math.max(A[2], C[2]);
          if (ox > 2 && oy > 2 && A[0] !== C[0]) hit.push(A[0] + ' | ' + C[0]);
        }
        const hd = s.querySelector('.hd'), head = hd ? hd.textContent.trim() : '';
        return { letters, numbers, small, over, hit, head, headWords: head ? head.split(/\s+/).length : 0, headPx: hd ? parseFloat(getComputedStyle(hd).fontSize).toFixed(1) : 0 };
      }, SKIP);
      if (w === widths[0] && cs === schemes[0]) report.words.push({ slide: i, head: info.head, headWords: info.headWords, headPx: info.headPx, words: info.letters.length, numbers: info.numbers.length });
      if (info.over.length) report.overflow.push({ w, cs, slide: i, over: info.over });
      if (info.small.length) report.small.push({ w, cs, slide: i, small: info.small.slice(0, 6) });
      if (info.hit.length) report.collide.push({ w, cs, slide: i, hit: info.hit.slice(0, 6) });
      await (await page.$('#deck')).screenshot({ path: path.join(OUT, `s${String(i).padStart(2, '0')}-${w}-${cs}.png`) });
    }
    errs.forEach(e => report.errors.push(`${w}/${cs}: ${e}`));
    await ctx.close();
  }
  await b.close(); srv.close();
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
  console.log(JSON.stringify({ bytes: report.bytes, errors: report.errors, overflow: report.overflow, small: report.small, collide: report.collide }));
  for (const x of report.words) console.log(String(x.slide).padStart(2), `head ${x.headWords} words ${x.headPx}px | body words ${x.words}, numbers ${x.numbers} | ${x.head}`);
  const bad = report.errors.length || report.overflow.length || report.small.length || report.words.some(x => x.headWords > 8 || x.words > 30) || report.bytes > 200 * 1024;
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e.message); process.exit(2); });
