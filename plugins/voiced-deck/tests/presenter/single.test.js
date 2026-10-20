'use strict';
// The single-file delivery: one HTML with the audio inside, alone in a folder, plays with sound
// from disk, over http, and inside an opaque-origin iframe sandbox (srcdoc and blob), as chat hosts render it.
// Chrome's normal autoplay policy holds, so every show starts from a real click or key press.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { launch, serve, watch, checker, sleep, PLUGIN, DECK } = require('./common');

(async () => {
  const ok = checker();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vd-single-'));
  const file = path.join(dir, 'deck.single.html');
  const r = spawnSync('python3', ['-I', path.join(PLUGIN, 'tools/voiced-deck'), 'pack-single', '--deck', DECK, '--out', file], { encoding: 'utf8' });
  ok(r.status === 0 && fs.existsSync(file), 'pack-single writes the file', (r.stdout + r.stderr).trim());
  ok(fs.readdirSync(dir).length === 1, 'the single file is alone in its folder, with no audio beside it', fs.readdirSync(dir));
  const html = fs.readFileSync(file, 'utf8');
  const srv = await serve(dir), b = await launch({ args: ['--autoplay-policy=document-user-activation-required'] });
  const errs = [];

  const run = async (label, open, gesture) => {
    const p = await b.newPage({ viewport: { width: 1100, height: 800 } });
    watch(p, errs, false);
    const fetched = [];
    p.on('request', q => { if (/\.(m4a|png|wav)(\?|$)/.test(q.url())) fetched.push(q.url()); });
    const f = await open(p);
    await f.waitForFunction(() => window.__deck && /ready|failed/.test(window.__deck.voice.state().voice), null, { timeout: 15000 });
    const V = () => f.evaluate(() => Object.assign(window.__deck.voice.state(), window.__deck.state(),
      { src: window.__deck.voice.audio.src.slice(0, 22), muted: window.__deck.voice.audio.muted, volume: window.__deck.voice.audio.volume }));
    let s = await V();
    ok(s.voice === 'ready' && s.src === 'data:audio/mp4;base64,', `${label}: voice ready from the embedded data URI`, { voice: s.voice, src: s.src });
    await f.evaluate(() => window.__deck.go(0, 0));
    await gesture(p, f);
    await f.waitForFunction(() => window.__deck.voice.state().phase === 'play', null, { timeout: 6000 }).catch(() => {});
    const t1 = (await V()).t; await sleep(700); s = await V();
    ok(s.phase === 'play' && s.pv && !s.paused && s.t - t1 > 0.4, `${label}: Presenter starts and currentTime advances`, { phase: s.phase, pv: s.pv, t1, t: s.t });
    ok(!s.muted && s.volume > 0, `${label}: the element is not muted and has volume`, { muted: s.muted, volume: s.volume });
    ok(s.direct && !s.analyser && (s.ctx === null || s.ctx === 'running'), `${label}: audio is not routed into a Web Audio context`, { direct: s.direct, analyser: s.analyser, ctx: s.ctx });
    await p.keyboard.press('c'); await sleep(300);
    const cap = await f.evaluate(() => { const c = document.getElementById('vcap'); return { shown: getComputedStyle(c).display, text: c.textContent }; });
    ok(cap.shown === 'block' && cap.text.length > 3, `${label}: captions show the current line`, cap);
    await p.keyboard.press('c');
    await f.evaluate(() => { window.__seen = new Set(); (function g() { const st = window.__deck.state(); window.__seen.add(st.cur + ':' + st.step); window.__raf = requestAnimationFrame(g); })(); window.__deck.voice.rate(8); });
    await sleep(4000);
    const seen = await f.evaluate(() => { cancelAnimationFrame(window.__raf); window.__deck.voice.rate(1); return [...window.__seen]; });
    ok(seen.length > 4, `${label}: builds and slides advance with the audio`, seen);
    ok(!fetched.length, `${label}: no external audio is requested`, fetched);
    await p.close();
  };

  const pressP = async p => { await p.keyboard.press('p'); };
  const clickPresenter = async (p, f) => { await f.locator('#bpv').click(); };
  const sandboxed = how => async p => {
    await p.setContent('<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="width:1000px;height:700px;border:0"></iframe></body>');
    await p.evaluate(([h, how]) => { const f = document.getElementById('f'); if (how === 'srcdoc') f.srcdoc = h; else f.src = URL.createObjectURL(new Blob([h], { type: 'text/html' })); }, [html, how]);
    const t0 = Date.now();
    while (Date.now() - t0 < 10000) { const f = p.frames().find(x => x !== p.mainFrame() && x.url() !== 'about:blank'); if (f) { await f.waitForLoadState(); return f; } await sleep(50); }
    throw new Error('iframe did not load');
  };

  await run('file://', async p => { await p.goto('file://' + file); return p.mainFrame(); }, pressP);
  await run('http', async p => { await p.goto(srv.url + '/deck.single.html'); return p.mainFrame(); }, pressP);
  await run('sandboxed srcdoc iframe', sandboxed('srcdoc'), clickPresenter);
  await run('sandboxed blob iframe', sandboxed('blob'), clickPresenter);

  ok(!errs.length, 'no console errors', errs);
  await b.close(); srv.close();
  fs.rmSync(dir, { recursive: true, force: true });
  process.exit(ok.done() ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
