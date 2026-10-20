"""The voice manifest: when each slide segment and line starts in the mastered audio.

{"duration": s, "voice": "Charon", "engine": "podkst Studio", "audio": {"m4a": "...", "png": "..."},
 "slides": [{"slide": 1, "segments": [{"k": 0, "start": s, "end": s, "lines": [{"id", "start", "end", "text"}]}]}]}
A segment with no lines (a silent build) starts just after the previous segment ends.
"""


def build(perf, line_ids, segment_ids, master_meta, voice, audio=None):
    by_seg = {x["segment_id"]: x for x in master_meta["lines"]}
    line_seg = dict(zip(line_ids, segment_ids))
    slides, prev_end, prev_gap = [], 0.0, 0.0
    for s in perf["slides"]:
        out = []
        for g in s["segments"]:
            ls = []
            for l in g["lines"]:
                t = by_seg[line_seg[l["id"]]]
                ls.append({"id": l["id"], "start": round(t["start_s"], 3), "end": round(t["end_s"], 3), "text": l["text"]})
            if ls:
                start, end = ls[0]["start"], ls[-1]["end"]
                prev_gap = g["lines"][-1]["gapAfterMs"] / 1000
            else:
                start = end = round(prev_end + min(0.3, prev_gap / 2), 3)
            out.append({"k": g["k"], "start": start, "end": end, "lines": ls})
            prev_end = end
        slides.append({"slide": s["slide"], "segments": out})
    man = {"duration": round(master_meta["duration_s"], 3), "voice": voice.split(":")[-1], "engine": "podkst Studio"}
    if audio:
        man["audio"] = audio
    man["slides"] = slides
    return man


def check(man, pitch):
    """Errors that would desync the show: missing slides, wrong segment count, times out of order."""
    errors, last = [], -1.0
    slides = {s.get("slide"): s for s in man.get("slides", [])}
    for note in pitch:
        n = note["slide"]
        s = slides.get(n)
        if not s:
            errors.append(f"slide {n}: missing from manifest")
            continue
        segs = sorted(s["segments"], key=lambda g: g["k"])
        if [g["k"] for g in segs] != list(range(len(note["segments"]))):
            errors.append(f"slide {n}: manifest k = {[g['k'] for g in segs]}, deck has {len(note['segments'])} segments")
        for g in segs:
            if g["start"] + 1e-6 < last:
                errors.append(f"slide {n} k {g['k']}: start {g['start']} is before the previous segment start {last}")
            last = g["start"]
            for line in g.get("lines", []):
                if not (g["start"] - 1e-3 <= line["start"] <= line["end"]):
                    errors.append(f"slide {n} k {g['k']} line {line.get('id')}: times {line['start']}..{line['end']} outside segment")
    if not man.get("duration") or man["duration"] < last:
        errors.append(f"duration {man.get('duration')} is shorter than the last segment start {last}")
    return errors
