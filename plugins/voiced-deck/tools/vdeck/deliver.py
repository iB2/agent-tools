"""Delivery: one self-contained HTML with the audio inside, or PNGs plus a tiny loader for hosts that only inline images.

The loader reads the deck PNG through a canvas, decodes the HTML, swaps the deck's audio PNG
path for the loader's AUDIO value (a data URI once the host has inlined it), and writes the
result into the page. The path to swap is built by string concatenation so the host's path
inliner does not rewrite it inside the loader.
"""
import base64
import functools
import http.server
import json
import mimetypes
import os
import pathlib
import shutil
import subprocess
import tempfile

from . import deckfile, pngpack

LOADER = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head><body>
<script>
var DECK={deck}, AUDIO={audio};
function unpack(src){{return new Promise(function(res,rej){{var i=new Image();i.onload=function(){{var c=document.createElement('canvas');c.width=i.naturalWidth;c.height=i.naturalHeight;var x=c.getContext('2d',{{willReadFrequently:true}});x.drawImage(i,0,0);var d=x.getImageData(0,0,c.width,c.height).data;var rgb=new Uint8Array(c.width*c.height*3);for(var p=0,q=0;p<d.length;p+=4){{rgb[q++]=d[p];rgb[q++]=d[p+1];rgb[q++]=d[p+2];}}var n=((rgb[0]<<24)|(rgb[1]<<16)|(rgb[2]<<8)|rgb[3])>>>0;res(rgb.slice(4,4+n));}};i.onerror=rej;i.src=src;}});}}
unpack(DECK).then(function(b){{var html=new TextDecoder().decode(b);var P={parts}.join('');if(AUDIO&&P)html=html.split(P).join(AUDIO);document.open();document.write(html);document.close();}});
</script></body></html>
"""


def pack_deck(deck, out_dir=None):
    deck = pathlib.Path(deck)
    out = pathlib.Path(out_dir) if out_dir else deck.parent
    out.mkdir(parents=True, exist_ok=True)
    html = deckfile.read(deck)
    deck_png = out / f"{deck.stem}.inline.png"
    deck_png.write_bytes(pngpack.pack(html.encode("utf-8")))
    man = deckfile.manifest(html) or {}
    src = (man.get("audio") or {}).get("png") or ""
    audio = ""
    if src:
        if not (deck.parent / src).exists():
            raise SystemExit(f"the deck's audio PNG {src} does not exist; run render or `voiced-deck pack` first")
        audio = os.path.relpath((deck.parent / src).resolve(), out.resolve())
    half = len(src) // 2
    title = (html.split("<title>", 1)[-1].split("</title>", 1)[0] if "<title>" in html else deck.stem).strip()
    loader = LOADER.format(title=title.replace("<", "&lt;"), deck=json.dumps(os.path.relpath(deck_png.resolve(), out.resolve())),
                           audio=json.dumps(audio), parts=json.dumps([src[:half], src[half:]]))
    page = out / f"{deck.stem}.inline.html"
    page.write_text(loader, encoding="utf-8")
    return page, deck_png, audio


def _audio_bytes(deck, man, audio):
    if audio:
        return pathlib.Path(audio).read_bytes()
    src = man.get("audio") or {}
    m4a, png = src.get("m4a") or "", src.get("png") or ""
    if m4a.startswith("data:"):
        return base64.b64decode(m4a.split(",", 1)[1])
    if m4a and (deck.parent / m4a).is_file():
        return (deck.parent / m4a).read_bytes()
    if png and not png.startswith("data:") and (deck.parent / png).is_file():
        return pngpack.unpack((deck.parent / png).read_bytes())
    raise SystemExit(f"no audio found for {deck.name}; pass --audio or run render first")


def reencode(data, bitrate):
    if not shutil.which("ffmpeg"):
        raise SystemExit("--bitrate needs ffmpeg; run `voiced-deck doctor` for the fix")
    with tempfile.TemporaryDirectory() as d:
        src, dst = pathlib.Path(d) / "in", pathlib.Path(d) / "out.m4a"
        src.write_bytes(data)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map", "0:a:0", "-map_metadata", "-1", "-ac", "1",
                        "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart", str(dst)], check=True)
        return dst.read_bytes()


def pack_single(deck, audio=None, out=None, bitrate=None):
    """Write one HTML that carries its audio as a data: URI in the manifest, so it plays with no files beside it."""
    deck = pathlib.Path(deck)
    html = deckfile.read(deck)
    man = deckfile.manifest(html)
    if not man:
        raise SystemExit(f"{deck.name} has no voice manifest; run render first")
    data = _audio_bytes(deck, man, audio)
    if bitrate:
        data = reencode(data, bitrate)
    elif data[4:8] != b"ftyp":
        raise SystemExit("the audio is not an MP4/AAC file; pass --bitrate (for example 32k) to encode it")
    man = dict(man, audio={"m4a": "data:audio/mp4;base64," + base64.b64encode(data).decode("ascii")})
    dest = pathlib.Path(out) if out else deck.with_name(deck.stem + ".single.html")
    dest.parent.mkdir(parents=True, exist_ok=True)
    deckfile.write(dest, deckfile.set_manifest(html, man))
    return dest, len(data)


def serve(root, port=8765):
    mimetypes.add_type("audio/mp4", ".m4a")
    mimetypes.add_type("text/html", ".html")
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    print(f"serving {root} at http://localhost:{port}/", flush=True)
    srv.serve_forever()
