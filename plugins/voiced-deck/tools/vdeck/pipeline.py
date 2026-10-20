"""performance.json -> podkst Studio project -> master -> manifest -> voiced deck.

State lives in <out>/studio-state.json (project id, segment ids, what each line was sent with).
It holds a project id, so keep it out of git. Running render again edits only the lines whose
text, direction or pause changed, synthesises only those, and re-masters.
"""
import json
import os
import pathlib
import re
import subprocess

from . import asr, deckfile, manifest, measure, perf as P, pngpack, studio

AAC_KBPS = int(os.environ.get("VD_AAC_KBPS", "40"))


def _state_path(out):
    return pathlib.Path(out) / "studio-state.json"


def load_state(out):
    p = _state_path(out)
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(out, st):
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    _state_path(out).write_text(json.dumps(st, indent=1))


def script_text(rows, speaker):
    for label, d, t in rows:
        if "\n" in t or "\n" in d or "]" in d:
            raise SystemExit(f"line text or direction has a newline or ']': {t[:60]}")
    return "\n".join(f"{label}: [{d}] {t}" for label, d, t in rows)


def desired(perf):
    return [{"id": l["id"], "text": l["text"], "direction": P.direction(l, perf), "gap": int(l["gapAfterMs"])}
            for _, _, l in P.flat(perf)]


def validate(deck, perf):
    pitch = deckfile.pitch(deckfile.read(deck))
    err, warn, stats = P.check(perf, pitch)
    for w in warn:
        print("warning:", w)
    if err:
        raise SystemExit("performance.json fails its checks:\n - " + "\n - ".join(err))
    return pitch, stats


def render(deck, perf_path, voice, out, max_credits, fresh=False, title=None):
    perf = P.load(perf_path)
    pitch, stats = validate(deck, perf)
    voice = P.voice_of(perf, voice)
    want = desired(perf)
    st = {} if fresh else load_state(out)
    if st and (st.get("voice") != voice or [x["id"] for x in st.get("lines", [])] != [w["id"] for w in want]):
        print("line ids or voice changed since the last render; starting a new project")
        st = {}
    spent = 0
    if not st:
        label = perf.get("speaker", "Narrator")
        body = {"title": title or perf.get("title") or "voiced deck", "language": perf.get("language", "en-US"),
                "quality": perf.get("quality", "pro"), "voices": {label: voice},
                "script": script_text([(label, w["direction"], w["text"]) for w in want], label)}
        print(f"render: {stats['lines']} lines, {stats['words']} words, about {stats['est_minutes']} min")
        proj, job, est = studio.create(body, f"render ({voice})", max_credits)
        segs = proj["segments"]
        if len(segs) != len(want):
            raise SystemExit(f"Studio parsed {len(segs)} lines, the performance has {len(want)}")
        st = {"project_id": proj["id"], "voice": voice, "lines": [{**w, "segment_id": s["id"], "gap": None} for w, s in zip(want, segs)]}
        save_state(out, st)
        studio.wait_job(job, "synthesis")
        spent += est
    ops = []
    for old, new in zip(st["lines"], want):
        sid = old["segment_id"]
        if old["text"] != new["text"]:
            ops.append({"op": "set_text", "segment_id": sid, "text": new["text"]})
        if old["direction"] != new["direction"]:
            ops.append({"op": "set_direction", "segment_id": sid, "direction": new["direction"]})
        if old["gap"] != new["gap"]:
            ops.append({"op": "set_pause", "segment_id": sid, "pause_after_ms": new["gap"]})
    if ops:
        studio.patch(st["project_id"], ops)
        st["lines"] = [{**new, "segment_id": old["segment_id"]} for old, new in zip(st["lines"], want)]
        save_state(out, st)
        edited = sum(1 for o in ops if o["op"] != "set_pause")
        print(f"patched {len(ops)} ops ({edited} text or direction edits)")
        spent += studio.synthesize(st["project_id"], "re-synthesis", max_credits)
    finish(deck, perf, st, out)
    st["credits_estimated"] = st.get("credits_estimated", 0) + spent
    save_state(out, st)
    return st


def regen(deck, perf_path, out, ids, max_credits=3):
    perf, st = P.load(perf_path), load_state(out)
    by_id = {l["id"]: l["segment_id"] for l in st["lines"]}
    for i in ids:
        studio.regenerate(st["project_id"], by_id[i], f"regenerate {i}", max_credits)
    finish(deck, perf, st, out)


def encode(wav, m4a, png):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(wav), "-ac", "1", "-ar", "24000", "-c:a", "aac",
                    "-b:a", f"{AAC_KBPS}k", "-movflags", "+faststart", str(m4a)], check=True)
    png.write_bytes(pngpack.pack(m4a.read_bytes()))


def finish(deck, perf, st, out):
    out = pathlib.Path(out)
    meta = studio.master(st["project_id"], out / "master.wav")
    name = pathlib.Path(deck).stem
    m4a, png = out / f"{name}.m4a", out / f"{name}.png"
    encode(out / "master.wav", m4a, png)
    base = pathlib.Path(deck).resolve().parent
    audio = {"m4a": os.path.relpath(m4a.resolve(), base), "png": os.path.relpath(png.resolve(), base)}
    man = manifest.build(perf, [l["id"] for l in st["lines"]], [l["segment_id"] for l in st["lines"]], meta, st["voice"], audio)
    (out / "manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False))
    embed(deck, man)
    print(f"  audio: {m4a.name} {m4a.stat().st_size // 1024} KB, {png.name} {png.stat().st_size // 1024} KB")


def embed(deck, man):
    html = deckfile.read(deck)
    if man is not None:
        errors = manifest.check(man, deckfile.pitch(html))
        if errors:
            raise SystemExit("manifest does not match the deck script:\n - " + "\n - ".join(errors))
    new = deckfile.set_manifest(html, man)
    if new == html:
        print(f"{pathlib.Path(deck).name}: manifest already {'clear' if man is None else 'embedded'}, unchanged")
        return False
    deckfile.write(deck, new)
    print(f"{pathlib.Path(deck).name}: manifest {'cleared' if man is None else 'embedded'}")
    return True


def check(perf_path, out, wpm=178):
    perf, st = P.load(perf_path), load_state(out)
    out = pathlib.Path(out)
    meta = json.loads((out / "master.json").read_text())
    by_seg = {x["segment_id"]: x for x in meta["lines"]}
    flags, words, speech = [], 0, 0.0
    for (slide, k, l), s in zip(P.flat(perf), st["lines"]):
        t = by_seg[s["segment_id"]]
        d = t["end_s"] - t["start_s"] - 0.08
        w = P.spoken_words(l["text"])
        words += w
        speech += d
        expect = w / (wpm / 60) + 0.25 * l["text"].count("...") + 0.3 * l["text"].count("<")
        ratio = d / max(expect, 0.4)
        if ratio < 0.55 or ratio > 1.7:
            flags.append({"id": l["id"], "dur": round(d, 2), "expect": round(expect, 2), "ratio": round(ratio, 2), "text": l["text"]})
    pros = measure.prosody(measure.decode(out / "master.wav"), 24000)
    rep = {"duration_s": round(meta["duration_s"], 2), "words": words, "wpm_overall": round(words / (meta["duration_s"] / 60), 1),
           "wpm_speech": round(words / (speech / 60), 1), "lufs": meta.get("integrated_lufs"), "prosody": pros, "flags": flags}
    (out / "check.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    return rep


def audition(perf_path, voices, line_ids, out, max_credits):
    perf = P.load(perf_path)
    by_id = {l["id"]: l for _, _, l in P.flat(perf)}
    lines = [by_id[i] for i in line_ids]
    out = pathlib.Path(out) / "audition"
    out.mkdir(parents=True, exist_ok=True)
    saved = out / "state.json"
    rows = [(v, P.direction(l, perf), l["text"]) for v in voices for l in lines]
    if saved.exists() and json.loads(saved.read_text()).get("voices") == voices:
        pid = json.loads(saved.read_text())["project_id"]
        print("audition: resuming the saved project")
    else:
        body = {"title": "voice audition", "language": perf.get("language", "en-US"), "quality": perf.get("quality", "pro"),
                "script": script_text(rows, None), "voices": {v: P.voice_of(perf, v) for v in voices}}
        proj, job, _ = studio.create(body, "audition", max_credits)
        pid = proj["id"]
        saved.write_text(json.dumps({"project_id": pid, "voices": voices}))
        studio.wait_job(job, "audition synthesis")
    segs = studio.get_project(pid)["segments"]
    n = len(lines)
    studio.patch(pid, [{"op": "set_pause", "segment_id": s["id"], "pause_after_ms": lines[i % n]["gapAfterMs"] if (i + 1) % n else 1500}
                       for i, s in enumerate(segs)])
    meta = studio.master(pid, out / "audition.wav")
    timing = {x["segment_id"]: x for x in meta["lines"]}
    words = sum(P.spoken_words(l["text"]) for l in lines)
    report = {}
    for vi, v in enumerate(voices):
        ts = [timing[s["id"]] for s in segs[vi * n:(vi + 1) * n]]
        a, b = ts[0]["start_s"], ts[-1]["end_s"]
        m = measure.prosody(measure.decode(out / "audition.wav", a, b), 24000)
        m["wpm_speech"] = round(words / (sum(x["end_s"] - x["start_s"] for x in ts) / 60), 1)
        report[v] = m
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{max(0, a - 0.1):.3f}", "-to", f"{b + 0.3:.3f}",
                        "-i", str(out / "audition.wav"), "-ac", "1", "-c:a", "aac", "-b:a", "64k", str(out / f"{v}.m4a")], check=True)
        print(f"  {v:12s} F0 median {m['f0_median_hz']} Hz, range {m['f0_range_st']} st, {m['wpm_speech']} wpm, "
              f"{m['pauses_per_min']} pauses/min, final drop {m['final_drop_st']} st")
    (out / "report.json").write_text(json.dumps(report, indent=1))
    return report


def probe(perf_path, word, variants, out, max_credits, voice=None, alt_lang=None, bad=(), apply=False):
    """Render each wording of a pronunciation note on every line that has `word`, in a scratch project.
    Transcribe each take in English (and alt_lang), score it, and keep the best wording."""
    perf = P.load(perf_path)
    voice = P.voice_of(perf, voice)
    hits = [l for _, _, l in P.flat(perf) if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", l["text"], re.I)]
    if not hits:
        raise SystemExit(f"no line says '{word}'")
    rows = []
    for v, note in enumerate(variants):
        trial = {**perf, "pronounce": {**(perf.get("pronounce") or {}), word: note}}
        for l in hits:
            rows.append({"id": l["id"], "v": v, "note": note, "direction": P.direction(l, trial), "text": l["text"]})
    label = perf.get("speaker", "Narrator")
    body = {"title": f"pronunciation probe: {word}", "language": perf.get("language", "en-US"), "quality": perf.get("quality", "pro"),
            "voices": {label: voice}, "script": script_text([(label, r["direction"], r["text"]) for r in rows], label)}
    out = pathlib.Path(out) / "probe" / re.sub(r"\W+", "-", word.lower())
    out.mkdir(parents=True, exist_ok=True)
    proj, job, est = studio.create(body, f"probe '{word}' ({len(rows)} takes)", max_credits)
    studio.wait_job(job, "probe synthesis")
    pid = proj["id"]
    segs = studio.get_project(pid)["segments"]
    studio.patch(pid, [{"op": "set_pause", "segment_id": s["id"], "pause_after_ms": 800} for s in segs])
    meta = studio.master(pid, out / "probe.wav")
    timing = {x["segment_id"]: x for x in meta["lines"]}
    audio = measure.decode(out / "probe.wav", sr=16000)
    m = asr.model("small")
    target, bads = asr.norm(word), [b.lower() for b in bad]
    for r, s in zip(rows, segs):
        t = timing[s["id"]]
        langs = ["en"] + ([alt_lang] if alt_lang else [])
        r["hyp"] = {lg: asr.transcribe(m, audio, 16000, t["start_s"], t["end_s"], lg) for lg in langs}
        score = 0
        for lg, hyp in r["hyp"].items():
            h = " ".join(asr.norm(hyp))
            score += 2 * (" ".join(target) in h) + (not any(b in hyp.lower() for b in bads))
        r["score"] = score
        print(f"  {r['id']} v{r['v']} score {score}: " + " | ".join(f"{k}: {x}" for k, x in r["hyp"].items()))
    totals = [sum(r["score"] for r in rows if r["v"] == v) for v in range(len(variants))]
    best = max(range(len(variants)), key=lambda v: totals[v])
    res = {"word": word, "credits_estimated": est, "totals": totals, "winner": best, "note": variants[best], "rows": rows}
    (out / "result.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"winner v{best} (scores {totals}): {variants[best]}")
    if apply:
        perf.setdefault("pronounce", {})[word] = variants[best]
        P.save(perf_path, perf)
        print(f"wrote the note into {perf_path} under pronounce['{word}']; run render to apply it")
    return res
