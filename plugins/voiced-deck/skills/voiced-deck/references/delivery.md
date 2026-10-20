# Delivery

A voiced deck is `deck.html` plus `audio/deck.m4a` and `audio/deck.png`. The manifest inside the deck points at both with relative paths. Pick the route that matches where the owner will open it.

## Local file or a web server

- Send or publish the folder as is. Any static host works.
- `VD serve <folder>` serves it on `http://localhost:8765/` with the right audio MIME type.
- Opened straight from disk (`file://`), the deck plays the `.m4a` directly. The waveform meter then animates without the Web Audio analyser, because browsers silence analysed `file:` media.
- Load order: a `data:` PNG first, then the `.m4a`, then the packed PNG. Add `?voice=png` to the URL to force the PNG path.

## Chat hosts that only inline images

Some chat hosts render an HTML page but only inline image files it references, so an `.m4a` next to it never loads. Pack everything into PNG pixels:

```
VD pack-deck deck.html
```

It writes `deck.inline.png` (the whole deck HTML in RGB pixels) and `deck.inline.html`, a loader under 2 KB. Give the host the loader. The loader:

1. loads the deck PNG into an image, draws it on a canvas and reads `getImageData`;
2. keeps the RGB bytes, reads a 4-byte big-endian length, and decodes that many bytes with `TextDecoder`;
3. replaces the deck's audio PNG path with its own `AUDIO` value, which the host has turned into a `data:` URI. The path to replace is built by string concatenation, so the host's inliner never rewrites it;
4. writes the result into the page with `document.open`, `document.write` and `document.close`.

The deck then sees a `data:` audio PNG, unpacks it the same way, and plays it from a blob. `tests/presenter/loader.test.js` checks both a served loader and one whose PNGs were inlined as `data:` URIs and opened from disk.

`VD pack <file> <out.png>` and `VD unpack` pack any file this way.

## Key entry when the owner is remote

`VD safebox` serves a one-time form on `127.0.0.1:8766` behind a random token. The owner pastes the key, the tool writes it to `~/.config/podkst/api.key` with mode 0600, checks it against `/credits`, and exits. It prints only the URL and a status line. The key never enters the chat, a log or the shell history.

When the owner is not at the machine, expose the form for the few seconds it is needed with a quick tunnel, for example `cloudflared tunnel --url http://localhost:8766`, send the owner the tunnel URL plus the token path, and stop the tunnel once the tool prints `SAFEBOX_DONE`.

## Before you hand it over

- `VD sync --deck deck.html --script script.md --performance performance.json --browser` passes.
- `VD_DECK=$PWD/deck.html node tests/presenter/run.js` passes.
- `deck.html` is under 200 KB.
- No key, project id or private number is in any file you send.
