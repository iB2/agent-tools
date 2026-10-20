'use strict';
// The PNG-packed delivery: the loader unpacks the deck, swaps in the audio, and the show plays.
// Case 1 serves the loader as is. Case 2 inlines both PNGs as data URIs, as an image-only chat host does, and opens it from disk.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { launch, serve, watch, checker, sleep, ROOT, DECK, manifest } = require('./common');

(async () => {
  const ok = checker();
  const stem = path.basename(DECK, '.html'), audioPng = (manifest().audio || {}).png;
  const loader = fs.readFileSync(path.join(ROOT, stem + '.inline.html'), 'utf8');
  const srv = await serve(ROOT), b = await launch();
  const errs = [];
  const run = async (url, label) => {
    const p = await b.newPage({ viewport: { width: 728, height: 700 } });
    watch(p, errs, false);
    await p.goto(url);
    await p.waitForFunction(() => window.__deck && /ready|failed/.test(window.__deck.voice.state().voice), null, { timeout: 15000 });
    const s = await p.evaluate(() => ({ voice: window.__deck.voice.state().voice, src: window.__deck.voice.audio.src.slice(0, 5), slides: window.__deck.count }));
    ok(s.voice === 'ready' && s.slides > 0, `${label}: deck unpacked and voice ready`, s);
    await p.click('#bpv');
    await p.waitForFunction(() => window.__deck.voice.state().phase === 'play', null, { timeout: 6000 }).catch(() => {});
    await sleep(700);
    const t = await p.evaluate(() => window.__deck.voice.state());
    ok(t.phase === 'play' && t.t > 0.2, `${label}: the show plays`, { phase: t.phase, t: t.t });
    await p.close();
  };
  await run(`${srv.url}/${stem}.inline.html`, 'served loader');
  const inline = f => 'data:image/png;base64,' + fs.readFileSync(path.join(ROOT, f)).toString('base64');
  const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'vd-')), 'inlined.html');
  fs.writeFileSync(tmp, loader.replace(`"${stem}.inline.png"`, JSON.stringify(inline(stem + '.inline.png'))).replace(JSON.stringify(audioPng), JSON.stringify(inline(audioPng))));
  await run('file://' + tmp, 'host-inlined loader from disk');
  ok(!errs.length, 'no console errors', errs);
  await b.close(); srv.close();
  process.exit(ok.done() ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
