"""Read and rewrite the named blocks of a deck HTML file."""
import html.parser
import json
import pathlib
import re

TEMPLATE = pathlib.Path(__file__).resolve().parents[2] / "template" / "deck.html"
BEGIN, END = "<!-- voice-manifest:begin -->", "<!-- voice-manifest:end -->"
PITCH_RE = re.compile(r'(<script type="application/json" id="pitch">)(.*?)(</script>)', re.S)
MANIFEST_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
ENGINE_RES = {
    "css": re.compile(r'<style id="vd-engine-css">.*?</style>', re.S),
    "js": re.compile(r'<script id="vd-engine-js">.*?</script>', re.S),
}


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


def write(path, text):
    pathlib.Path(path).write_text(text, encoding="utf-8")


def pitch(html):
    m = PITCH_RE.search(html)
    if not m:
        raise SystemExit('deck has no <script type="application/json" id="pitch"> block')
    return json.loads(m.group(2))


def pitch_json(entries):
    rows = ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in entries)
    return "[\n" + rows + "\n]"


def set_pitch(html, entries):
    body = pitch_json(entries).replace("</", "<\\/")
    if not PITCH_RE.search(html):
        raise SystemExit("deck has no pitch block to replace")
    return PITCH_RE.sub(lambda m: m.group(1) + body + m.group(3), html, count=1)


def manifest(html):
    m = MANIFEST_RE.search(html)
    if not m:
        return None
    j = re.search(r'id="voice">(.*?)</script>', m.group(0), re.S)
    return json.loads(j.group(1).replace("<\\/", "</")) if j else None


def manifest_block(payload):
    body = payload.replace("</", "<\\/")
    return BEGIN + '\n<script type="application/json" id="voice">' + body + "</script>\n" + END


def set_manifest(html, man):
    if len(MANIFEST_RE.findall(html)) != 1:
        raise SystemExit(f"expected exactly one {BEGIN} ... {END} block")
    payload = "null" if man is None else json.dumps(man, ensure_ascii=False, separators=(",", ":"))
    return MANIFEST_RE.sub(lambda _: manifest_block(payload), html)


def engine_blocks(html):
    out = {}
    for name, rx in ENGINE_RES.items():
        found = rx.findall(html)
        if len(found) != 1:
            raise SystemExit(f"expected exactly one engine {name} block, found {len(found)}")
        out[name] = found[0]
    return out


def sync_engine(html, template_html):
    src = engine_blocks(template_html)
    engine_blocks(html)
    for name, rx in ENGINE_RES.items():
        html = rx.sub(lambda _: src[name], html, count=1)
    return html


class _Builds(html.parser.HTMLParser):
    """Static build count per slide section, split by layout. Builds a chart draws in JS are not seen."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
            "use", "path", "circle", "rect", "line", "stop", "ellipse", "polygon", "polyline"}

    def __init__(self):
        super().__init__()
        self.stack, self.slides = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and "slide" in (a.get("class") or "").split():
            self.slides.append({"id": a.get("id"), "wide": 0, "narrow": 0, "charts": 0})
        only = a.get("data-only")
        if tag not in self.VOID:
            self.stack.append(only)
        if self.slides and a.get("data-chart"):
            self.slides[-1]["charts"] += 1
        if self.slides and a.get("data-b", "").isdigit():
            k = int(a["data-b"])
            ctx = [o for o in self.stack + [only] if o]
            s = self.slides[-1]
            if "narrow" not in ctx:
                s["wide"] = max(s["wide"], k)
            if "wide" not in ctx:
                s["narrow"] = max(s["narrow"], k)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID and self.stack:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack:
            self.stack.pop()


def static_builds(html):
    p = _Builds()
    p.feed(html)
    return p.slides
