"""performance.json: the voiced script, one line per TTS call.

{
  "title": "...", "language": "en-US", "quality": "pro",
  "voiceDefault": "builtin:Charon", "speaker": "Narrator",
  "pace": "appended to every line's direction",
  "pronounce": {"Word": "a direction note added to every line that contains Word"},
  "respell": {"BrandName": "spoken form"},    text must use the spoken form
  "slides": [{"slide": 1, "segments": [{"k": 0, "lines": [
      {"id": "s01k0l01", "text": "what is spoken", "style": "how it is spoken", "gapAfterMs": 300}]}]}]
}
segments[k] belongs to build k of the slide, so it mirrors the deck's #pitch segments.
"""
import json
import pathlib
import re

MAX_DIRECTION = 500
GAP_RANGE = (80, 1600)
ALLOWED_TAGS = {"<breath>", "<short pause>", "<long pause>", "<chuckle>", "<laugh>", "<sigh>", "<gasp>", "<cough>"}
DISFLUENCY = re.compile(r"\b(uh|um|er|I mean)\b|\b([\w']+(?: [\w']+)?)(?:,|\.\.\.) \2(?![\w'])", re.I)
WPM_MID = 178


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def save(path, perf):
    pathlib.Path(path).write_text(json.dumps(perf, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def flat(perf):
    return [(s["slide"], g["k"], l) for s in perf["slides"] for g in s["segments"] for l in g["lines"]]


def voice_of(perf, voice=None):
    v = voice or perf.get("voiceDefault") or "builtin:Charon"
    return v if ":" in v else "builtin:" + v


def notes_for(text, perf):
    low = text.lower()
    return [n for w, n in (perf.get("pronounce") or {}).items() if re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", low)]


def direction(line, perf):
    """The exact direction string sent to Studio. Render and probe both use it, so equal inputs give
    equal takes (Studio content-addresses takes by voice, model, text, direction, language and seed)."""
    parts = [line["style"].strip()]
    if perf.get("pace"):
        parts.append(perf["pace"])
    parts += notes_for(line["text"], perf)
    return "; ".join(p for p in parts if p)


def spoken_words(text):
    return len(re.sub(r"<[^>]+>", " ", text).replace("...", " ").split())


def _sentences(seg):
    t = re.sub(r"\*\*", "", seg)
    out = []
    for part in re.split(r"(?<=[.!?])\s+", t):
        part = part.strip()
        if not part:
            continue
        gap = 300
        if "(pause)" in part:
            part = re.sub(r"\s*\(pause\)\s*", " ", part).strip()
            gap = 600
        if part:
            out.append((part, gap))
    return out


def init(pitch, title="", voice="builtin:Charon", language="en-US"):
    slides = []
    for e in pitch:
        segs = []
        for k, seg in enumerate(e["segments"]):
            lines = [{"id": f"s{e['slide']:02d}k{k}l{n:02d}", "text": t, "style": "", "gapAfterMs": g}
                     for n, (t, g) in enumerate(_sentences(seg), 1)]
            segs.append({"k": k, "lines": lines})
        slides.append({"slide": e["slide"], "segments": segs})
    return {"title": title or (pitch[0]["title"] if pitch else ""), "language": language, "quality": "pro",
            "voiceDefault": voice, "speaker": "Narrator", "pace": "", "pronounce": {}, "respell": {}, "slides": slides}


def check(perf, pitch=None):
    """Return (errors, warnings, stats)."""
    err, warn = [], []
    ids = set()
    words = gaps = 0
    if pitch is not None and len(perf["slides"]) != len(pitch):
        err.append(f"performance has {len(perf['slides'])} slides, deck script has {len(pitch)}")
    for si, s in enumerate(perf["slides"]):
        if s["slide"] != si + 1:
            err.append(f"slide {s['slide']} is at position {si + 1}")
        p = pitch[si] if pitch is not None and si < len(pitch) else None
        if p is not None and len(s["segments"]) != len(p["segments"]):
            err.append(f"slide {s['slide']}: {len(s['segments'])} segments, deck has {len(p['segments'])} (builds + 1)")
        for k, g in enumerate(s["segments"]):
            if g["k"] != k:
                err.append(f"slide {s['slide']}: segment k {g['k']} at position {k}")
            if p is not None and k < len(p["segments"]) and bool(p["segments"][k].strip()) != bool(g["lines"]):
                err.append(f"slide {s['slide']} k{k}: deck segment is {'empty' if not p['segments'][k].strip() else 'spoken'}, performance has {len(g['lines'])} lines")
            dis = 0
            for l in g["lines"]:
                lid, t, st = l.get("id", "?"), l.get("text", ""), l.get("style", "")
                if lid in ids:
                    err.append(f"{lid}: duplicate id")
                ids.add(lid)
                if not re.fullmatch(rf"s{s['slide']:02d}k{k}l\d+", lid):
                    err.append(f"{lid}: id should start s{s['slide']:02d}k{k}l")
                if not st.strip() or st.strip().upper() == "TODO":
                    err.append(f"{lid}: no direction in style")
                if not GAP_RANGE[0] <= l.get("gapAfterMs", -1) <= GAP_RANGE[1]:
                    err.append(f"{lid}: gapAfterMs {l.get('gapAfterMs')} outside {GAP_RANGE}")
                if "\u2014" in t + st or "\u2013" in t + st:
                    err.append(f"{lid}: long dash in text or style")
                if re.search(r"[\[\]()*]", t):
                    err.append(f"{lid}: direction marks in text; the model reads text word for word, put direction in style")
                bad = set(re.findall(r"<[^>]+>", t)) - ALLOWED_TAGS
                if bad:
                    err.append(f"{lid}: unsupported tags {sorted(bad)}")
                for w in (perf.get("respell") or {}):
                    if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t, re.I):
                        err.append(f"{lid}: write '{w}' as '{perf['respell'][w]}' in text")
                if "confident and expressive" in st.lower():
                    warn.append(f"{lid}: 'confident and expressive' flattens soft deliveries")
                if len(direction(l, perf)) > MAX_DIRECTION:
                    err.append(f"{lid}: direction is {len(direction(l, perf))} chars, Studio allows {MAX_DIRECTION}")
                if re.search(r"\d", t):
                    warn.append(f"{lid}: digits in text; spell numbers the way they should be said")
                dis += len(DISFLUENCY.findall(re.sub(r"<[^>]+>", " ", t)))
                words += spoken_words(t)
                gaps += l.get("gapAfterMs", 0)
            if dis > 3:
                err.append(f"slide {s['slide']} k{k}: {dis} disfluencies, keep 1 to 3 per paragraph")
    stats = {"lines": len(ids), "words": words, "gaps_s": round(gaps / 1000, 1),
             "est_minutes": round(words / WPM_MID + gaps / 60000, 2)}
    return err, warn, stats
