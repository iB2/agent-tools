"""script.md -> the deck's #pitch JSON.

Format:
  ## 1 · Title of slide one          (also "## 1. Title" or "## 1: Title")
  <!-- target: 20 -->                 optional seconds for the presenter timer
  Spoken text. [click] More text after build 1. (pause) is a beat, **word** is stress.
  ---                                 anything after a --- line inside a slide is not spoken
Any other "## " heading ends the slides (a Q&A section, say).
"""
import re

HEAD = re.compile(r"^## (\d+)\s*[·.:\-]\s*(.+?)\s*$")
WPM = 170


def words(t):
    return len(re.sub(r"\[click\]|\(pause\)|\*\*|<[^>]+>", " ", t).split())


def parse(md):
    slides, cur = [], None
    for line in md.splitlines():
        m = HEAD.match(line)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2), "body": [], "target": None, "cut": False}
            slides.append(cur)
            continue
        if line.startswith("## "):
            cur = None
            continue
        if cur is None:
            continue
        t = re.match(r"^\s*<!--\s*target:\s*(\d+)\s*-->\s*$", line)
        if t:
            cur["target"] = int(t.group(1))
        elif line.strip() == "---":
            cur["cut"] = True
        elif not cur["cut"]:
            cur["body"].append(line)
    out = []
    for s in slides:
        say = re.sub(r"\s+", " ", " ".join(s["body"])).strip()
        segs = [x.strip() for x in say.split("[click]")]
        out.append({"slide": s["n"], "title": s["title"], "say": say, "segments": segs,
                    "target": s["target"] or round(words(say) / WPM * 60 + 2)})
    nums = [e["slide"] for e in out]
    if nums != list(range(1, len(out) + 1)):
        raise SystemExit(f"script slides are numbered {nums}, expected 1..{len(out)}")
    return out
