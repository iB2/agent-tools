import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

from . import deckfile, deliver, manifest, perf as P, pngpack, script as S

TOOLS = pathlib.Path(__file__).resolve().parents[1]
CAP = int(os.environ.get("VD_MAX_CREDITS", "50"))


def _out(a):
    return pathlib.Path(a.out) if getattr(a, "out", None) else pathlib.Path(a.deck).resolve().parent / "audio"


def cmd_new(a):
    dest = pathlib.Path(a.deck)
    if dest.exists() and not a.force:
        raise SystemExit(f"{dest} exists; pass --force to overwrite")
    shutil.copyfile(deckfile.TEMPLATE, dest)
    print(f"wrote {dest} from the template")


def cmd_engine_sync(a):
    tpl, bad = deckfile.read(deckfile.TEMPLATE), 0
    for d in a.decks:
        html = deckfile.read(d)
        new = deckfile.sync_engine(html, tpl)
        if new == html:
            print(f"{d}: engine matches the template")
        elif a.check:
            print(f"{d}: engine differs from the template; run `voiced-deck engine-sync {d}`")
            bad += 1
        else:
            deckfile.write(d, new)
            print(f"{d}: engine refreshed from the template")
    sys.exit(1 if bad else 0)


def cmd_script(a):
    entries = S.parse(pathlib.Path(a.script).read_text(encoding="utf-8"))
    html = deckfile.read(a.deck)
    new = deckfile.set_pitch(html, entries)
    if new != html:
        deckfile.write(a.deck, new)
    clicks = sum(len(e["segments"]) - 1 for e in entries)
    print(f"{a.deck}: script has {len(entries)} slides, {clicks} clicks{'' if new != html else ', unchanged'}")
    sys.exit(_static_sync(new))


def _static_sync(html):
    pitch, builds, fails = deckfile.pitch(html), deckfile.static_builds(html), []
    if len(pitch) != len(builds):
        fails.append(f"deck has {len(builds)} slides, script has {len(pitch)}")
    for p, b in zip(pitch, builds):
        want = len(p["segments"]) - 1
        for lay in ("wide", "narrow"):
            if b["charts"] and b[lay] < want:
                continue
            if b[lay] != want:
                fails.append(f"slide {p['slide']}: {lay} layout has {b[lay]} builds, script has {want} [click]")
    for f in fails:
        print("FAIL", f)
    if not fails:
        print("PASS static build counts match the [click] counts (chart builds are checked in the browser)")
    return 1 if fails else 0


def cmd_perf_init(a):
    dest = pathlib.Path(a.performance)
    if dest.exists() and not a.force:
        raise SystemExit(f"{dest} exists; pass --force to overwrite")
    perf = P.init(deckfile.pitch(deckfile.read(a.deck)), voice=P.voice_of({}, a.voice), language=a.language)
    P.save(dest, perf)
    print(f"wrote {dest}: {len(P.flat(perf))} lines. Write a direction into every style, then run perf check.")


def cmd_perf_check(a):
    perf = P.load(a.performance)
    err, warn, stats = P.check(perf, deckfile.pitch(deckfile.read(a.deck)) if a.deck else None)
    for w in warn:
        print("warning:", w)
    for e in err:
        print("FAIL", e)
    print(json.dumps(stats))
    print("FAIL" if err else "PASS")
    sys.exit(1 if err else 0)


def cmd_sync(a):
    html = deckfile.read(a.deck)
    rc = _static_sync(html)
    if a.script:
        if S.parse(pathlib.Path(a.script).read_text(encoding="utf-8")) != deckfile.pitch(html):
            print(f"FAIL the deck's #pitch differs from {a.script}; run `voiced-deck script {a.script} {a.deck}`")
            rc = 1
        else:
            print(f"PASS the deck's #pitch equals {a.script}")
    if a.performance:
        err, _, _ = P.check(P.load(a.performance), deckfile.pitch(html))
        for e in err:
            print("FAIL", e)
        rc |= 1 if err else 0
        if not err:
            print(f"PASS {a.performance} matches the deck segments")
    man = deckfile.manifest(html)
    if man is not None:
        errors = manifest.check(man, deckfile.pitch(html))
        for e in errors:
            print("FAIL manifest:", e)
        rc |= 1 if errors else 0
        if not errors:
            print("PASS embedded manifest matches the deck segments")
    if a.browser:
        sys.stdout.flush()
        r = subprocess.run(["node", str(TOOLS / "browser" / "builds.js"), str(pathlib.Path(a.deck).resolve())])
        rc |= r.returncode
    sys.exit(rc)


def cmd_credits(a):
    from . import studio
    print("balance:", studio.balance())


def cmd_estimate(a):
    from . import pipeline, studio
    perf = P.load(a.performance)
    pipeline.validate(a.deck, perf)
    label = perf.get("speaker", "Narrator")
    body = {"title": "estimate", "language": perf.get("language", "en-US"), "quality": perf.get("quality", "pro"),
            "voices": {label: P.voice_of(perf, a.voice)},
            "script": pipeline.script_text([(label, w["direction"], w["text"]) for w in pipeline.desired(perf)], label)}
    print("estimated credits:", studio.estimate_create(body), "balance:", studio.balance())


def cmd_audition(a):
    from . import pipeline
    pipeline.audition(a.performance, a.voices.split(","), a.lines.split(","), a.out, a.max_credits)


def cmd_render(a):
    from . import pipeline
    st = pipeline.render(a.deck, a.performance, a.voice, _out(a), a.max_credits, fresh=a.fresh)
    print(f"done: {a.deck} is voiced ({st.get('credits_estimated', 0)} credits estimated across runs)")


def cmd_regen(a):
    from . import pipeline
    pipeline.regen(a.deck, a.performance, _out(a), a.ids)


def cmd_check(a):
    from . import pipeline
    rep = pipeline.check(a.performance, a.out)
    print(json.dumps({k: v for k, v in rep.items() if k != "flags"}, indent=1))
    print(f"flags: {len(rep['flags'])}")
    for f in rep["flags"]:
        print(f"  {f['id']} ratio {f['ratio']} ({f['dur']} s vs {f['expect']} s): {f['text'][:70]}")


def cmd_asr(a):
    from . import asr
    out = pathlib.Path(a.out)
    man = json.loads((out / "manifest.json").read_text())
    perf = P.load(a.performance) if a.performance else {}
    res = asr.run(out / "master.wav", man, perf.get("respell"), a.model)
    (out / "asr.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    bad = [o for o in res if asr.flagged(o)]
    print(f"lines {len(res)}, flagged {len(bad)}, mean wer {sum(o['wer'] for o in res) / max(1, len(res)):.3f}")
    for o in sorted(bad, key=lambda o: -o["wer"]):
        print(f"{o['id']} wer {o['wer']} extra {o['extra']}\n  REF: {o['ref']}\n  HYP: {o['hyp']}")


def cmd_probe(a):
    from . import pipeline
    variants = list(a.variant or [])
    if a.variants:
        variants += [x.strip() for x in pathlib.Path(a.variants).read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(variants) < 2:
        raise SystemExit("give at least two wordings with --variant or --variants FILE")
    pipeline.probe(a.performance, a.word, variants, a.out, a.max_credits, a.voice, a.alt_lang, a.bad or (), a.apply)


def cmd_measure(a):
    from . import measure
    print(json.dumps(measure.prosody(measure.decode(a.audio, a.start, a.end), 24000)))


def cmd_embed(a):
    from . import pipeline
    man = None if a.clear else json.loads(pathlib.Path(a.manifest).read_text(encoding="utf-8"))
    pipeline.embed(a.deck, man)


def cmd_pack(a):
    data = pathlib.Path(a.src).read_bytes()
    png = pngpack.pack(data)
    pathlib.Path(a.dest).write_bytes(png)
    print(f"{a.dest}: {len(data)} bytes in a {len(png)} byte PNG")


def cmd_unpack(a):
    pathlib.Path(a.dest).write_bytes(pngpack.unpack(pathlib.Path(a.src).read_bytes()))
    print(f"{a.dest}: unpacked")


def cmd_pack_deck(a):
    page, png, audio = deliver.pack_deck(a.deck, a.out)
    print(f"{page}: loader, {png.name} {png.stat().st_size // 1024} KB" + (f", audio {audio}" if audio else ", no audio"))


def cmd_serve(a):
    deliver.serve(pathlib.Path(a.root).resolve(), a.port)


def cmd_safebox(a):
    from . import safebox
    safebox.run(a.port, pathlib.Path(a.key_file).expanduser() if a.key_file else None)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="voiced-deck", description="Build a keynote-grade HTML deck that presents itself with a podkst voice.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_, description=help_)
        p.set_defaults(fn=fn)
        return p

    p = add("new", cmd_new, "copy the deck template to a new file")
    p.add_argument("deck")
    p.add_argument("--force", action="store_true")
    p = add("engine-sync", cmd_engine_sync, "refresh (or --check) the engine blocks of decks from the template")
    p.add_argument("decks", nargs="+")
    p.add_argument("--check", action="store_true")
    p = add("script", cmd_script, "write script.md into the deck as #pitch JSON and check build counts")
    p.add_argument("script")
    p.add_argument("deck")
    p = add("perf", lambda a: a.perf_fn(a), "performance.json: init a skeleton or check it")
    ps = p.add_subparsers(dest="perf_cmd", required=True)
    q = ps.add_parser("init", help="one line per sentence of the deck script, styles left empty")
    q.set_defaults(perf_fn=cmd_perf_init)
    q.add_argument("--deck", required=True)
    q.add_argument("--performance", required=True)
    q.add_argument("--voice", default="Charon")
    q.add_argument("--language", default="en-US")
    q.add_argument("--force", action="store_true")
    q = ps.add_parser("check", help="lint the voiced script against the voice rules and the deck")
    q.set_defaults(perf_fn=cmd_perf_check)
    q.add_argument("--performance", required=True)
    q.add_argument("--deck")
    p = add("sync", cmd_sync, "check builds, [click] counts, script, performance and manifest agree")
    p.add_argument("--deck", required=True)
    p.add_argument("--script")
    p.add_argument("--performance")
    p.add_argument("--browser", action="store_true", help="also count builds in a headless browser at 1280, 728 and 390 px")
    add("credits", cmd_credits, "show the podkst credit balance")
    p = add("estimate", cmd_estimate, "free cost probe for a full render")
    p.add_argument("--deck", required=True)
    p.add_argument("--performance", required=True)
    p.add_argument("--voice")
    p = add("audition", cmd_audition, "render the same lines in several voices and measure each")
    p.add_argument("--performance", required=True)
    p.add_argument("--voices", required=True, help="comma list, e.g. Charon,Orus,Algenib")
    p.add_argument("--lines", required=True, help="comma list of line ids")
    p.add_argument("--out", required=True)
    p.add_argument("--max-credits", type=int, default=CAP)
    p = add("render", cmd_render, "render or update the voice, master it, and embed it in the deck")
    p.add_argument("--deck", required=True)
    p.add_argument("--performance", required=True)
    p.add_argument("--voice", help="builtin voice name; default is voiceDefault in performance.json")
    p.add_argument("--out", help="audio folder, default <deck dir>/audio")
    p.add_argument("--max-credits", type=int, default=CAP, help=f"refuse a step that costs more (default {CAP}, env VD_MAX_CREDITS)")
    p.add_argument("--fresh", action="store_true", help="start a new Studio project")
    p = add("regen", cmd_regen, "new takes (new seeds) for the given line ids, then re-master and embed")
    p.add_argument("--deck", required=True)
    p.add_argument("--performance", required=True)
    p.add_argument("--out")
    p.add_argument("ids", nargs="+")
    p = add("check", cmd_check, "per-line duration sanity and whole-show prosody of the master")
    p.add_argument("--performance", required=True)
    p.add_argument("--out", required=True)
    p = add("asr", cmd_asr, "transcribe each line with faster-whisper and flag mismatches")
    p.add_argument("--out", required=True)
    p.add_argument("--performance")
    p.add_argument("--model", default="small.en")
    p = add("probe", cmd_probe, "try N pronunciation notes for a hard word in a scratch project and keep the best")
    p.add_argument("--performance", required=True)
    p.add_argument("--word", required=True)
    p.add_argument("--variant", action="append")
    p.add_argument("--variants", help="file with one wording per line")
    p.add_argument("--out", required=True)
    p.add_argument("--voice")
    p.add_argument("--alt-lang", help="also transcribe in this language, e.g. pt")
    p.add_argument("--bad", action="append", help="a word that must not be heard, e.g. a translation")
    p.add_argument("--apply", action="store_true", help="write the winning note into performance.json")
    p.add_argument("--max-credits", type=int, default=CAP)
    p = add("measure", cmd_measure, "prosody of an audio file or a slice of it")
    p.add_argument("audio")
    p.add_argument("--start", type=float)
    p.add_argument("--end", type=float)
    p = add("embed", cmd_embed, "embed a manifest into the deck (idempotent), or --clear it")
    p.add_argument("deck")
    p.add_argument("manifest", nargs="?")
    p.add_argument("--clear", action="store_true")
    p = add("pack", cmd_pack, "pack any file into PNG pixels")
    p.add_argument("src")
    p.add_argument("dest")
    p = add("unpack", cmd_unpack, "unpack a packed PNG")
    p.add_argument("src")
    p.add_argument("dest")
    p = add("pack-deck", cmd_pack_deck, "pack the deck into a PNG plus an inline loader page")
    p.add_argument("deck")
    p.add_argument("--out")
    p = add("serve", cmd_serve, "serve a folder on localhost with audio MIME types")
    p.add_argument("root")
    p.add_argument("--port", type=int, default=8765)
    p = add("safebox", cmd_safebox, "one-time localhost form that stores the podkst key with 0600 permissions")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--key-file")

    a = ap.parse_args(argv)
    if a.cmd == "embed" and not a.clear and not a.manifest:
        ap.error("embed needs a manifest path or --clear")
    a.fn(a)
