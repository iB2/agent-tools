'use strict';
// Plays the whole demo at 8x and checks every slide and build state is reached on its manifest cue, in order.
const { launch, serve, watch, checker, ROOT, DEMO } = require('./common');

(async () => {
  const ok = checker();
  const srv = await serve(ROOT), b = await launch();
  for (const w of [1280, 390]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    const errs = []; watch(p, errs, false);
    await p.goto(srv.url + DEMO); await p.waitForTimeout(800);
    await p.waitForFunction(() => window.__deck.voice.state().voice === 'ready', null, { timeout: 15000 });
    await p.evaluate(() => window.__deck.go(0, 0)); await p.click('#bpv');
    await p.waitForFunction(() => window.__deck.voice.state().phase === 'play', null, { timeout: 8000 });
    await p.evaluate(() => { window.__log = []; let last = ''; (function f() { const st = window.__deck.state(), t = window.__deck.voice.audio.currentTime, key = st.cur + ':' + st.step; if (key !== last) { window.__log.push({ cur: st.cur, step: st.step, t }); last = key; } requestAnimationFrame(f); })(); window.__deck.voice.rate(8); });
    await p.waitForFunction(() => window.__deck.voice.state().phase === 'end', null, { timeout: 90000 });
    const { log, M, builds } = await p.evaluate(() => { const v = window.__deck.voice.manifest(); return { log: window.__log, M: { start: v.start, steps: v.steps }, builds: window.__deck.builds() }; });
    const want = []; builds.forEach((n, i) => { for (let k = 0; k <= n; k++) want.push(i + ':' + k); });
    const seen = new Set(log.map(e => e.cur + ':' + e.step));
    const missed = want.filter(k => !seen.has(k));
    const late = log.slice(1).filter(e => { const c = e.step ? M.steps[e.cur][e.step] : M.start[e.cur]; return e.t - c < -0.05 || e.t - c > 0.8; });
    const order = log.every((e, i) => !i || e.cur > log[i - 1].cur || (e.cur === log[i - 1].cur && e.step > log[i - 1].step));
    ok(!missed.length, `${w}px: all ${want.length} slide and build states reached`, missed);
    ok(!late.length, `${w}px: every transition within 0.8 s of its cue at 8x`, late.slice(0, 5).map(e => ({ ...e, cue: e.step ? M.steps[e.cur][e.step] : M.start[e.cur] })));
    ok(order, `${w}px: transitions are monotonic`);
    ok(!errs.length, `${w}px: no console errors`, errs);
    await p.close();
  }
  await b.close(); srv.close();
  process.exit(ok.done() ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
