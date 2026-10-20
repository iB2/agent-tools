"""One-time key entry: a localhost form that writes the podkst key to a 0600 file without echoing it.

It prints only the one-time URL. The key never reaches the agent's transcript, a log or the shell.
The validation call sends the client's User-Agent; Cloudflare blocks the default Python-urllib one.
"""
import http.server
import os
import secrets
import threading
import urllib.parse

from . import studio

PAGE = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>podkst key</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#161817;color:#f1ede4;font:16px/1.4 -apple-system,Helvetica,Arial,sans-serif}
.box{width:min(92vw,420px);padding:28px;border-radius:18px;background:#1f2220;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}
h1{margin:0 0 6px;font-size:22px}p{margin:0 0 18px;color:#a9a498;font-size:14px}
input{width:100%;box-sizing:border-box;padding:14px;border-radius:10px;border:1px solid #444;background:#111;color:#f1ede4;font:15px ui-monospace,Menlo,monospace}
button{margin-top:14px;width:100%;padding:14px;border:0;border-radius:10px;background:#2aa192;color:#06120f;font-weight:800;font-size:16px}
.ok{color:#2aa192;font-weight:700}.err{color:#e0644f;font-weight:700}
</style></head><body><div class=box>{{BODY}}</div></body></html>"""

FORM = """<h1>podkst key</h1><p>Paste your podkst API key. It is saved on this machine with owner-only access and is never shown to the agent.</p>
<form method=post autocomplete=off><input name=k type=password placeholder="pk_..." autofocus required><button>Save key</button></form>"""


def check(key):
    st, j = studio.call("GET", "/credits", key=key, tries=2)
    if st == 200:
        return True, "Key works. Balance: %s credits." % (j or {}).get("balance", "?")
    if st in (401, 403):
        return False, "podkst rejected the key (HTTP %d). Check its scopes: generate:podcast, read:jobs, billing:read." % st
    return None, "Saved. Could not check it with podkst right now (HTTP %d)." % st


def run(port=8766, key_file=None):
    path = key_file or studio.key_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(16)

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, code=200):
            b = PAGE.replace("{{BODY}}", body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path != "/" + token:
                return self._send("<p class=err>Not found.</p>", 404)
            self._send(FORM)

        def do_POST(self):
            if self.path != "/" + token:
                return self._send("<p class=err>Not found.</p>", 404)
            n = int(self.headers.get("Content-Length", "0") or 0)
            key = urllib.parse.parse_qs(self.rfile.read(min(n, 4096)).decode()).get("k", [""])[0].strip()
            if not key.startswith("pk_"):
                return self._send(FORM.replace("<form", "<p class=err>That does not look like a podkst key.</p><form"))
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(key)
            os.chmod(path, 0o600)
            ok, msg = check(key)
            key = None
            self._send("<h1>%s</h1><p class=%s>%s</p><p>You can close this tab.</p>" % (
                "Saved" if ok is not False else "Saved, but", "err" if ok is False else "ok", msg))
            print("SAFEBOX_DONE status=%s" % ("ok" if ok else ("rejected" if ok is False else "unchecked")), flush=True)
            if ok is not False:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    print("SAFEBOX_URL http://localhost:%d/%s" % (port, token), flush=True)
    srv.serve_forever()
