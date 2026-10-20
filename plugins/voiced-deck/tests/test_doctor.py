import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
CLI = PLUGIN / "tools" / "voiced-deck"
sys.path.insert(0, str(PLUGIN / "tools"))

from vdeck import doctor  # noqa: E402

KEY = "pk_canary" + "Q7w2E9r4T1y8Zx"
LOG = 'echo "${0##*/} $*" >> "$CALLS"\n'
FAKES = {
    "ffmpeg": '#!/bin/sh\ncase "$*" in *-encoders*) echo " A....D aac   AAC (Advanced Audio Coding)";; *) echo "ffmpeg version 7.1 Copyright";; esac\n',
    "ffprobe": '#!/bin/sh\necho "ffprobe version 7.1 Copyright"\n',
    "node": '#!/bin/sh\nif [ "$1" = "--version" ]; then echo v20.11.0; else echo \'{"pw": false}\'; fi\n',
    "npm": "#!/bin/sh\n" + LOG,
    "npx": "#!/bin/sh\n" + LOG,
}


class FakePodkst:
    """Answers GET /v1/credits like podkst, and like Cloudflare for the default Python User-Agent."""

    def __init__(self, mode):
        self.mode, self.seen = mode, []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "ua": self.headers.get("User-Agent")})
                sent = (self.headers.get("Authorization") or "")[7:]
                if (self.headers.get("User-Agent") or "").startswith("Python-urllib"):
                    code, body = 403, b"error code: 1010"
                elif outer.mode == "ok":
                    code, body = 200, json.dumps({"balance": 42}).encode()
                elif outer.mode == "scope":
                    code, body = 403, json.dumps({"error": {"type": "permission_error", "code": "insufficient_scope",
                                                            "message": "key %s lacks billing:read" % sent}}).encode()
                else:
                    code, body = 401, json.dumps({"error": {"type": "authentication_error", "code": "invalid_api_key",
                                                            "message": "Invalid API key %s" % sent}}).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/v1" % self.srv.server_address[1]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def closed_port_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d/v1" % port


@unittest.skipIf(os.name == "nt", "the fake tools are POSIX shell scripts")
class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.key_file = self.tmp / "home" / ".config" / "podkst" / "api.key"
        self.key_file.parent.mkdir(parents=True)
        self.calls = self.tmp / "calls"
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.close()

    def tools(self, *names):
        for n in names or FAKES:
            p = self.bin / n
            p.write_text(FAKES[n])
            p.chmod(0o755)

    def save_key(self, mode=0o600):
        self.key_file.write_text(KEY)
        self.key_file.chmod(mode)

    def api(self, mode):
        self.server = self.server or FakePodkst(mode)
        self.server.mode = mode
        return self.server

    def cli(self, *args, api=None, env_key=None):
        env = {"PATH": str(self.bin), "HOME": str(self.tmp / "home"), "PODKST_API_KEY_FILE": str(self.key_file),
               "PODKST_API": api or closed_port_url(), "HF_HUB_CACHE": str(self.tmp / "hf"), "CALLS": str(self.calls)}
        if env_key:
            env["PODKST_API_KEY"] = env_key
        r = subprocess.run([sys.executable, "-I", str(CLI), *args, "--os", "mac"], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotIn(KEY, r.stdout + r.stderr)
        self.assertNotIn(KEY[-8:], r.stdout + r.stderr)
        return r

    def items(self, *args, **kw):
        r = self.cli("doctor", "--json", *args, **kw)
        return r, {i["id"]: i for i in json.loads(r.stdout)["items"]}

    def test_missing_ffmpeg_fails_with_the_brew_fix(self):
        self.tools("node")
        self.save_key()
        r, it = self.items(api=self.api("ok").url)
        self.assertEqual(r.returncode, 1)
        self.assertEqual((it["ffmpeg"]["status"], it["ffprobe"]["status"], it["aac"]["status"]), ("FAIL", "FAIL", "FAIL"))
        self.assertEqual(it["ffmpeg"]["fix"], ["brew install ffmpeg"])
        self.assertIn("FAIL ffmpeg", self.cli("doctor", api=self.api("ok").url).stdout)

    def test_missing_key_fails_and_prints_the_first_time_guide(self):
        self.tools()
        r = self.cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL podkst key", r.stdout)
        self.assertIn("Dashboard, then Settings, then API Keys", r.stdout)
        self.assertIn("generate:podcast, read:jobs, billing:read", r.stdout)
        self.assertIn("voiced-deck safebox", r.stdout)
        self.assertIn("WARN podkst accepts the key", r.stdout)

    def test_world_readable_key_file_warns_and_good_key_passes(self):
        self.tools()
        self.save_key(0o644)
        api = self.api("ok")
        r, it = self.items(api=api.url)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(it["key"]["status"], "WARN")
        self.assertEqual(it["key"]["fix"], ["chmod 600 ~/.config/podkst/api.key"])
        self.assertEqual(it["access"]["status"], "PASS")
        self.assertEqual(it["access"]["data"], {"http": 200, "balance": 42, "missing_scopes": []})
        self.assertEqual(api.seen[0]["path"], "/v1/credits")
        self.assertEqual(api.seen[0]["auth"], "Bearer " + KEY)
        self.assertFalse(api.seen[0]["ua"].startswith("Python-urllib"))

    def test_rejected_key_fails(self):
        self.tools()
        self.save_key()
        r = self.cli("doctor", api=self.api("reject").url)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL podkst accepts the key  rejected (HTTP 401)", r.stdout)

    def test_missing_scope_is_named(self):
        self.tools()
        self.save_key()
        r, it = self.items(api=self.api("scope").url)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(it["access"]["data"]["missing_scopes"], ["billing:read"])

    def test_network_down_is_a_warning(self):
        self.tools()
        self.save_key()
        r, it = self.items()
        self.assertEqual(it["access"]["status"], "WARN")
        self.assertIsNone(it["access"]["data"]["http"])
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_json_shape(self):
        self.tools()
        r = self.cli("doctor", "--json")
        out = json.loads(r.stdout)
        self.assertEqual((out["ok"], out["os"]), (False, "mac"))
        self.assertEqual([i["id"] for i in out["items"]],
                         ["python", "numpy", "ffmpeg", "ffprobe", "aac", "node", "key", "access", "playwright", "chromium", "uv", "whisper"])
        for i in out["items"]:
            self.assertEqual(set(i), {"id", "name", "tier", "status", "detail", "fix", "data"})
            self.assertIn(i["status"], ("PASS", "WARN", "FAIL"))
            if i["tier"] == "optional":
                self.assertNotEqual(i["status"], "FAIL")
        self.assertEqual({i["tier"] for i in out["items"][:8]}, {"required"})

    def test_key_value_never_appears(self):
        self.tools()
        self.save_key()
        for mode in ("ok", "reject", "scope"):
            for args in (("doctor",), ("doctor", "--json"), ("setup", "--dry-run")):
                self.cli(*args, api=self.api(mode).url)
                self.cli(*args, api=self.api(mode).url, env_key=KEY)

    def test_setup_dry_run_prints_the_plan_and_changes_nothing(self):
        self.tools()
        r = self.cli("setup", "--dry-run", "--asr")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("npm install --no-audit --no-fund", r.stdout)
        self.assertIn("npx playwright install chromium", r.stdout)
        self.assertIn("$ voiced-deck safebox", r.stdout)
        self.assertIn("Dashboard, then Settings, then API Keys", r.stdout)
        self.assertIn("whisper models: install uv first", r.stdout)
        self.assertIn("uv (optional): brew install uv", r.stdout)
        self.assertIn("dry run: nothing was changed", r.stdout)
        self.assertFalse(self.calls.exists(), "dry run called npm or npx")
        self.assertFalse(self.key_file.exists())

    def test_setup_yes_runs_each_step(self):
        self.tools()
        self.save_key(0o644)
        self.cli("setup", "--yes", "--dry-run", api=self.api("ok").url)
        self.assertFalse(self.calls.exists(), "dry run called npm or npx")
        self.assertEqual(self.key_file.stat().st_mode & 0o777, 0o644)
        r = self.cli("setup", "--yes", api=self.api("ok").url)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(calls, ["npm install --no-audit --no-fund", "npx playwright install chromium"])
        self.assertEqual(self.key_file.stat().st_mode & 0o777, 0o600)
        self.assertIn("PASS podkst key", r.stdout.rsplit("voiced-deck doctor", 1)[1])


class SetupFacts(unittest.TestCase):
    def test_playwright_pin_matches_package_json(self):
        pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(doctor.PLAYWRIGHT, "playwright@" + pkg["devDependencies"]["playwright"])

    def test_every_os_has_a_fix_for_every_system_item(self):
        for id_ in ("python", "numpy", "ffmpeg", "ffprobe", "aac", "node", "uv"):
            for os_name in doctor.OSES:
                self.assertTrue(doctor.fixes(id_, os_name), (id_, os_name))


if __name__ == "__main__":
    unittest.main()
