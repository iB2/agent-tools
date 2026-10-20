"""Delivery: pack a voiced deck into PNGs plus a tiny loader, for hosts that only inline images.

The loader reads the deck PNG through a canvas, decodes the HTML, swaps the deck's audio PNG
path for the loader's AUDIO value (a data URI once the host has inlined it), and writes the
result into the page. The path to swap is built by string concatenation so the host's path
inliner does not rewrite it inside the loader.
"""
import functools
import http.server
import json
import mimetypes
import os
import pathlib

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


def serve(root, port=8765):
    mimetypes.add_type("audio/mp4", ".m4a")
    mimetypes.add_type("text/html", ".html")
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    print(f"serving {root} at http://localhost:{port}/", flush=True)
    srv.serve_forever()
