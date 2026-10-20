'use strict';
// The voiced show's controls: count-in, sync at 8x, karaoke, pause and resume, slide jumps, captions, end state, stop.
const { launch, serve, watch, checker, sleep, ROOT, DEMO } = require('./common');

(async () => {
  const ok = checker();
  const srv = await serve(ROOT), b = await launch();
  const W = +(process.argv[2] || 1280);
  const p = await b.newPage({ viewport: { width: W, height: W < 560 ? 900 : 1000 } });
  const errs = []; watch(p, errs);
  await p.goto(srv.url + DEMO);
  const V = () => p.evaluate(() => Object.assign(window.__deck.voice.state(), window.__deck.state()));
  const waitFor = async (fn, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { const s = await V(); if (fn(s)) return s; await sleep(50); } return V(); };
  const N = await p.evaluate(() => window.__deck.count);

  let s = await waitFor(s => s.voice === 'ready' || s.voice === 'failed', 15000);
  ok(s.voice === 'ready', 'voice loads and is ready', s.voice);
  const dv = await p.evaluate(() => document.getElementById('bpv').getAttribute('data-voice'));
  ok(dv === 'ready', 'Presenter button carries the ready state', dv);
  const M = await p.evaluate(() => { const v = window.__deck.voice.manifest(); return { start: v.start, steps: v.steps, dur: v.dur }; });

  await p.evaluate(() => window.__deck.go(0, 0));
  await p.click('#bpv');
  s = await V();
  ok(s.phase === 'count' && s.pv, 'Presenter click starts the count-in and opens the presenter panel', { phase: s.phase, pv: s.pv });
  s = await waitFor(s => s.phase === 'play', 4000);
  ok(s.phase === 'play' && !s.paused, 'audio plays after the count-in', { phase: s.phase, paused: s.paused });
  const t1 = (await V()).t; await sleep(600); const t2 = (await V()).t;
  ok(t2 - t1 > 0.4, 'currentTime advances at rate 1', { t1, t2 });

  await p.evaluate(() => {
    window.__log = []; let last = '';
    (function f() { const st = window.__deck.state(), t = window.__deck.voice.audio.currentTime, key = st.cur + ':' + st.step;
      if (key !== last) { window.__log.push({ cur: st.cur, step: st.step, t }); last = key; } window.__raf = requestAnimationFrame(f); })();
    window.__deck.voice.rate(8);
  });
  await sleep(6000);
  const log = await p.evaluate(() => { cancelAnimationFrame(window.__raf); return window.__log; });
  const bad = [];
  for (const e of log.slice(1)) { const cue = e.step === 0 ? M.start[e.cur] : M.steps[e.cur][e.step]; const lag = e.t - cue; if (lag < -0.05 || lag > 0.6) bad.push({ ...e, cue, lag: +lag.toFixed(3) }); }
  ok(log.length > 4 && bad.length === 0, `builds and slides follow manifest cues at 8x (${log.length - 1} transitions)`, bad.slice(0, 5));

  await p.evaluate(() => window.__deck.voice.rate(1)); await sleep(300);
  const kar = await p.evaluate(() => ({ lc: document.querySelectorAll('#pvsc .ln.lc').length, words: document.querySelectorAll('#pvsc .ln.lc .w').length, prog: document.getElementById('vpi').style.transform }));
  s = await V();
  ok(kar.lc === 1 && kar.words > 0, 'presenter panel highlights exactly one current line', kar);
  ok(s.analyser || s.direct, 'meter has a source (Web Audio analyser or direct element)', { analyser: s.analyser, direct: s.direct });
  ok(/scaleX\(0\.[0-9]*[1-9]/.test(kar.prog), 'stage progress line fills with speech time', kar.prog);

  await p.keyboard.press('k');
  s = await V(); const tp = s.t; await sleep(500); const s2 = await V();
  ok(s.phase === 'pause' && s2.paused && Math.abs(s2.t - tp) < 0.01, 'K pauses and time holds', { phase: s.phase, tp, t: s2.t });
  const before = s2.cur;
  await p.focus('#stage'); await p.keyboard.press(' ');
  s = await V(); await sleep(400); const s3 = await V();
  ok(s.phase === 'play' && s3.t > tp + 0.2 && s3.t - tp < 1.2, 'Space resumes from where it stopped', { tp, t: s3.t });
  ok(s3.cur === before, 'resume keeps the slide', { before, after: s3.cur });

  await p.click('#bplay'); s = await V();
  ok(s.phase === 'pause' && s.paused, 'Pause button pauses', s.phase);
  await p.click('#bplay'); s = await V();
  ok(s.phase === 'play', 'Pause button resumes', s.phase);

  await p.evaluate(() => window.__deck.voice.jump(1)); await sleep(150);
  const c0 = (await V()).cur;
  await p.keyboard.press('ArrowRight'); await sleep(150); s = await V();
  ok(s.cur === c0 + 1 && s.step === 0 && Math.abs(s.t - M.start[c0 + 1]) < 0.4 && s.phase === 'play', 'ArrowRight jumps to the next slide start and keeps playing', { cur: s.cur, step: s.step, t: s.t, want: M.start[c0 + 1] });
  await p.keyboard.press('ArrowLeft'); await sleep(150); s = await V();
  ok(s.cur === c0 && s.step === 0 && Math.abs(s.t - M.start[c0]) < 0.4, 'ArrowLeft jumps back to the previous slide start', { cur: s.cur, t: s.t, want: M.start[c0] });
  const box = await p.locator('#stage').boundingBox();
  await p.mouse.click(box.x + box.width * 0.8, box.y + box.height * 0.4); await sleep(150); s = await V();
  ok(s.cur === c0 + 1 && s.step === 0 && Math.abs(s.t - M.start[c0 + 1]) < 0.4, 'stage click zone jumps a slide with audio', { cur: s.cur, t: s.t });
  await p.click('#bn'); await sleep(150); s = await V();
  ok(s.cur === c0 + 2 && s.step === 0 && Math.abs(s.t - M.start[c0 + 2]) < 0.4, 'bar next jumps a slide with audio', { cur: s.cur, t: s.t });

  const steps = await p.evaluate(N => { const r = []; for (let i = 0; i < 2; i++) { const a = window.__deck.state(); window.__deck.next(); const b = window.__deck.state(); r.push([a.cur, a.step, b.cur, b.step]); } return r; }, N);
  ok(steps.every(([ac, , bc, bs]) => bs === 0 && bc === Math.min(ac + 1, N - 1)), 'next() never steps a build during the show, only slides', steps);
  await p.keyboard.press('Home'); await sleep(150);
  await p.keyboard.press('k'); await sleep(100);
  await p.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5); await sleep(150); s = await V();
  ok(s.phase === 'play' && s.cur === 0, 'tapping the paused slide resumes instead of skipping', { phase: s.phase, cur: s.cur });

  await sleep(1500); await p.keyboard.press('c'); await sleep(300);
  const cap = await p.evaluate(() => { const c = document.getElementById('vcap'); return { shown: getComputedStyle(c).display, text: c.textContent }; });
  ok(cap.shown === 'block' && cap.text.length > 3, 'C toggles captions with the current line', cap);
  await p.keyboard.press('c');

  await p.evaluate(N => window.__deck.voice.jump(N - 1), N); await p.evaluate(() => window.__deck.voice.rate(16));
  s = await waitFor(s => s.phase === 'end', 30000);
  const end = await p.evaluate(() => ({ vend: getComputedStyle(document.querySelector('.vend')).display, txt: document.querySelector('.vend').textContent, want: document.getElementById('deck').getAttribute('data-end') || 'Q&A', label: document.getElementById('bpl').textContent }));
  ok(s.phase === 'end' && s.cur === N - 1 && s.step === s.max, 'show stops on the last slide with all builds', { phase: s.phase, cur: s.cur, step: s.step, max: s.max });
  ok(end.vend === 'flex' && end.txt.includes(end.want) && end.label === 'Replay', 'end state with its label and Replay is shown', end);
  await p.evaluate(() => window.__deck.voice.rate(1));
  await p.click('#vrep'); await sleep(300); s = await V();
  ok(s.phase === 'play' && s.cur === 0 && s.t < 1, 'Replay restarts from slide 1', { phase: s.phase, cur: s.cur, t: s.t });

  await p.keyboard.press('Escape'); await sleep(100); s = await V();
  ok(s.phase === 'off' && s.paused && !s.pv, 'Esc stops the audio and returns to manual mode', { phase: s.phase, paused: s.paused, pv: s.pv });
  const m0 = await V(); await p.keyboard.press('ArrowRight'); const m1 = await V();
  ok((m1.cur === m0.cur && m1.step === m0.step + 1) || m0.max === 0, 'manual mode steps builds again', { m0: [m0.cur, m0.step], m1: [m1.cur, m1.step] });
  await p.keyboard.press('p'); s = await waitFor(s => s.phase === 'play', 4000);
  ok(s.phase === 'play', 'P key starts the show', s.phase);
  await p.keyboard.press('p'); s = await V();
  ok(s.phase === 'off' && s.paused, 'P again stops the show', s.phase);

  const q = await b.newPage({ viewport: { width: 728, height: 900 } });
  await q.goto(srv.url + DEMO + '?voice=png');
  await q.waitForFunction(() => /ready|failed/.test(window.__deck.voice.state().voice), null, { timeout: 15000 });
  const pq = await q.evaluate(() => ({ v: window.__deck.voice.state(), src: window.__deck.voice.audio.src.slice(0, 5) }));
  ok(pq.v.voice === 'ready' && !pq.v.direct && pq.src === 'blob:', 'the packed PNG decodes to playable audio', pq);

  ok(errs.length === 0, 'no console errors or warnings', errs);
  await b.close(); srv.close();
  process.exit(ok.done() ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
