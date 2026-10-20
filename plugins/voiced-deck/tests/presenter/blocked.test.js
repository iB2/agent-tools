'use strict';
// Autoplay blocked lands on tap-to-start, reduced motion skips the count-in, a deck with no manifest keeps the manual presenter view.
const { launch, serve, watch, checker, sleep, ROOT, DEMO, TEMPLATE } = require('./common');

(async () => {
  const ok = checker();
  const srv = await serve(ROOT), b = await launch({ args: ['--autoplay-policy=document-user-activation-required'] });
  const errs = [];
  let p = await b.newPage({ viewport: { width: 390, height: 900 } });
  await p.addInitScript(() => { const orig = HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play = function () { if (!this.muted && window.__block) return Promise.reject(new DOMException('blocked', 'NotAllowedError')); return orig.call(this); }; });
  watch(p, errs);
  await p.goto(srv.url + DEMO);
  await p.waitForFunction(() => window.__deck.voice.state().voice === 'ready', null, { timeout: 15000 });
  await p.evaluate(() => { window.__block = true; window.__deck.voice.start(); }); await sleep(2600);
  let s = await p.evaluate(() => window.__deck.voice.state());
  const vis = await p.evaluate(() => getComputedStyle(document.getElementById('vbig')).display);
  ok(s.phase === 'blocked' && vis === 'flex', 'start without a gesture lands on tap-to-start', { phase: s.phase, vis });
  await p.evaluate(() => { window.__block = false; }); await p.click('#vbig'); await sleep(500); s = await p.evaluate(() => window.__deck.voice.state());
  ok(s.phase === 'play' && !s.paused && s.t > 0.1, 'tap starts playback', { phase: s.phase, t: s.t });
  await p.close();

  p = await b.newPage({ viewport: { width: 728, height: 900 }, reducedMotion: 'reduce' });
  watch(p, errs);
  await p.goto(srv.url + DEMO);
  await p.waitForFunction(() => window.__deck.voice.state().voice === 'ready', null, { timeout: 15000 });
  await p.click('#bpv'); await sleep(200); s = await p.evaluate(() => window.__deck.voice.state());
  ok(s.phase === 'play', 'reduced motion skips the count-in', s.phase);
  await p.close();

  p = await b.newPage({ viewport: { width: 728, height: 900 } });
  watch(p, errs);
  const tpl = await serve(TEMPLATE);
  await p.goto(tpl.url + '/deck.html'); await sleep(800);
  tpl.close();
  await p.click('#bpv'); await sleep(200);
  s = await p.evaluate(() => Object.assign(window.__deck.voice.state(), { pv: window.__deck.state().pv, dv: document.getElementById('bpv').getAttribute('data-voice') }));
  ok(s.phase === 'off' && s.pv && s.dv === 'none', 'a deck without a manifest keeps the manual presenter view', s);
  ok(errs.length === 0, 'no console errors', errs);
  await b.close(); srv.close();
  process.exit(ok.done() ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
