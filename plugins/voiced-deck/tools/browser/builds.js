'use strict';
// Count builds per slide in a real browser at 1280, 728 and 390 px and compare with the script.
// usage: node builds.js /abs/path/deck.html
const path = require('path');
const { launch, serve, watch } = require('./lib');

(async () => {
  const deck = path.resolve(process.argv[2]);
  const srv = await serve(path.dirname(deck));
  const b = await launch();
  let fail = 0;
  for (const w of [1280, 728, 390]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    const errs = []; watch(p, errs, false);
    await p.goto(`${srv.url}/${path.basename(deck)}`); await p.waitForTimeout(300);
    const r = await p.evaluate(() => ({ builds: window.__deck.builds(), want: window.__deck.script().map(s => s.segments.length - 1), bad: window.__deck.checkSync() }));
    const same = JSON.stringify(r.builds) === JSON.stringify(r.want);
    console.log(`${same && !errs.length ? 'PASS' : 'FAIL'} ${w}px builds ${JSON.stringify(r.builds)} script ${JSON.stringify(r.want)}${errs.length ? ' errors ' + JSON.stringify(errs) : ''}`);
    if (!same || errs.length) fail++;
    await p.close();
  }
  await b.close(); srv.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e.message); process.exit(2); });
