"""Transcribe each line of the master with faster-whisper and score it against its text.

The score is a word error rate after normalisation: lower case, tags and punctuation removed,
digits spelled out, fillers dropped. A line is flagged when WER > 0.12 or the transcript has
2 or more words too many or too few; a dropped two-word phrase in a short line scores about 0.14.
The ear is still the gate. ASR finds the lines worth listening to.

faster-whisper is optional. Without it installed, run through uv:
  uv run --with faster-whisper python <tools>/voiced-deck asr ...
"""
import difflib
import re

from . import measure

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
SCALE = {"m": "million", "k": "thousand", "bn": "billion"}
FILLERS = {"uh", "um", "er", "a", "an", "the", "and", "of"}


def say(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    for div, word in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= div:
            rest = n % div
            return say(n // div) + " " + word + ("" if not rest else " " + say(rest))
    return str(n)


def year(n):
    if 2000 <= n < 2010:
        return say(n)
    return say(n // 100) + " " + ("hundred" if n % 100 == 0 else ("oh " + say(n % 100) if n % 100 < 10 else say(n % 100)))


def ordinal(n):
    w = say(n).split()
    last = w[-1]
    w[-1] = ORD.get(last) or (last[:-1] + "ieth" if last.endswith("y") else last + "th")
    return " ".join(w)


def _num(m):
    raw = m.group(0).rstrip(",")
    s = raw.replace(",", "")
    suf = re.search(r"(st|nd|rd|th)$", s)
    if suf:
        return ordinal(int(s[:-2]))
    if "." in s:
        a, b = s.split(".", 1)
        return say(int(a or 0)) + " point " + " ".join(ONES[int(c)] for c in b)
    n = int(s)
    return year(n) if 1100 <= n <= 2099 and "," not in raw else say(n)


def norm(t, respell=None):
    t = t.lower()
    for w, spoken in (respell or {}).items():
        t = re.sub(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", spoken.lower(), t)
    t = re.sub(r"<[^>]+>", " ", t).replace("%", " percent")
    t = re.sub(r"\$(\d[\d,]*(?:\.\d+)?)\s*(million|billion|thousand|m\b|k\b|bn\b)?",
               lambda m: f"{m.group(1)} {SCALE.get(m.group(2) or '', m.group(2) or '')} dollars ", t)
    t = re.sub(r"\d[\d,]*(\.\d+)?(st|nd|rd|th)?", _num, t)
    t = re.sub(r"[^a-z' ]", " ", t.replace("-", " "))
    words, buf = [], ""
    for w in t.split():
        if len(w) == 1 and w not in ("a", "i"):
            buf += w
            continue
        if buf:
            words.append(buf)
            buf = ""
        words.append(w)
    if buf:
        words.append(buf)
    return [w for w in words if w not in FILLERS]


def wer(ref, hyp, respell=None):
    r, h = norm(ref, respell), norm(hyp, respell)
    return round(1 - difflib.SequenceMatcher(a=r, b=h).ratio(), 3), len(h) - len(r)


def flagged(o):
    return o["wer"] > 0.12 or abs(o["extra"]) >= 2


def model(name="small.en"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("faster-whisper is not installed; run with: uv run --with faster-whisper python3 <tools>/voiced-deck asr ...")
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(m, audio, sr, a, b, language="en"):
    seg = audio[int(max(0, a - 0.05) * sr):int((b + 0.05) * sr)]
    segs, _ = m.transcribe(seg, language=language, beam_size=5, condition_on_previous_text=False, vad_filter=False)
    return " ".join(s.text for s in segs).strip()


def run(wav, man, respell=None, model_name="small.en", language="en"):
    audio = measure.decode(wav, sr=16000)
    m = model(model_name)
    out = []
    for s in man["slides"]:
        for g in s["segments"]:
            for l in g["lines"]:
                hyp = transcribe(m, audio, 16000, l["start"], l["end"], language)
                w, extra = wer(l["text"], hyp, respell)
                out.append({"id": l["id"], "wer": w, "extra": extra, "ref": l["text"], "hyp": hyp})
    return out
