"""Check the setup the tool needs (doctor) and install what is safe to install (setup).

doctor never prints the key or any part of it. It reports only where the key was found,
whether podkst accepts it, the HTTP code, missing scopes and the balance.
setup installs only user-level things: npm packages, Playwright's Chromium, whisper models
and the key file. It prints the commands for system packages and never runs them.
"""
import dataclasses
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from . import studio

PLUGIN = pathlib.Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[1]
LIB = PLUGIN / "tools" / "browser" / "lib.js"
PLAYWRIGHT = "playwright@^1.56.0"
# asr defaults to small.en; probe also transcribes other languages with small.
MODELS = ("small.en", "small")
SCOPES = ("generate:podcast", "read:jobs", "billing:read")
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
REQUIRED, OPTIONAL = "required", "optional"
OSES = ("mac", "debian", "windows", "other")

FIXES = {
    "python": {"mac": ["brew install python@3.12"], "debian": ["sudo apt install python3"],
               "windows": ["winget install Python.Python.3.12"], "other": ["https://www.python.org/downloads/"]},
    "numpy": {"mac": ["brew install numpy"], "debian": ["sudo apt install python3-numpy"],
              "windows": ["py -m pip install numpy"], "other": ["python3 -m pip install --user numpy"]},
    "ffmpeg": {"mac": ["brew install ffmpeg"], "debian": ["sudo apt install ffmpeg"],
               "windows": ["winget install Gyan.FFmpeg", "or: choco install ffmpeg"], "other": ["https://ffmpeg.org/download.html"]},
    "node": {"mac": ["brew install node"], "debian": ["sudo apt install nodejs npm", "if that is older than 18: https://nodejs.org/en/download"],
             "windows": ["winget install OpenJS.NodeJS.LTS"], "other": ["https://nodejs.org/en/download"]},
    "playwright": {"other": ["voiced-deck setup"]},
    "chromium": {"debian": ["voiced-deck setup", "if Chromium still does not launch: sudo npx playwright install-deps chromium"],
                 "other": ["voiced-deck setup"]},
    "uv": {"mac": ["brew install uv"], "debian": ["curl -LsSf https://astral.sh/uv/install.sh | sh"],
           "windows": ["winget install astral-sh.uv"], "other": ["https://docs.astral.sh/uv/getting-started/installation/"]},
    "whisper": {"other": ["voiced-deck setup --asr"]},
}
FIXES["ffprobe"] = FIXES["aac"] = FIXES["ffmpeg"]


def host_os():
    if sys.platform == "darwin":
        return "mac"
    if os.name == "nt":
        return "windows"
    return "debian" if pathlib.Path("/etc/debian_version").exists() else "other"


def tilde(p):
    s, h = str(p), str(pathlib.Path.home())
    return "~" + s[len(h):] if s.startswith(h + os.sep) else s


def key_guide(os_name):
    save = "setx PODKST_API_KEY <your key>" if os_name == "windows" else "export PODKST_API_KEY=<your key>  (in your shell profile)"
    return ["First-time key:",
            "1. Sign in at https://podkst.ai.",
            "2. Open Dashboard, then Settings, then API Keys (https://podkst.ai/dashboard/api-keys).",
            "3. Create a key with the scopes " + ", ".join(SCOPES) + ".",
            "4. Save it in one of two ways. Do not paste it into a chat.",
            "   " + save,
            "   or: voiced-deck safebox  (a local form that writes %s with mode 0600 and never echoes the key)" % tilde(studio.key_file())]


@dataclasses.dataclass
class Result:
    status: str
    detail: str
    fix: list = None
    data: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Item:
    id: str
    name: str
    tier: str
    status: str
    detail: str
    fix: list
    data: dict


def _run(argv, timeout=20):
    exe = shutil.which(argv[0])
    if not exe:
        return None
    try:
        return subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _version(text):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


BROWSER_PROBE = """
const lib = require(process.argv[1]);
try { lib.playwright(); } catch (e) { console.log(JSON.stringify({ pw: false })); process.exit(0); }
lib.launch().then(async b => { const v = b.version(); await b.close(); console.log(JSON.stringify({ pw: true, chromium: v })); })
  .catch(e => console.log(JSON.stringify({ pw: true, chromium: null, error: String(e.message).split('\\n')[0].slice(0, 160) })));
"""


class Ctx:
    def __init__(self, os_name):
        self.os = os_name

    @functools.cached_property
    def node(self):
        r = _run(["node", "--version"])
        return _version(r.stdout) if r and r.returncode == 0 else None

    @functools.cached_property
    def browser(self):
        r = _run(["node", "-e", BROWSER_PROBE, str(LIB)], timeout=90)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (AttributeError, IndexError, ValueError):
            return {"pw": False, "error": "the Playwright probe did not run"}

    @functools.cached_property
    def key(self):
        try:
            return studio.read_key()
        except OSError:
            return studio.key_file(), ""


def check_python(ctx):
    v = sys.version_info
    ok = v >= (3, 10)
    return Result(PASS if ok else FAIL, "%d.%d.%d" % v[:3] + ("" if ok else ", needs 3.10 or later"))


def check_numpy(ctx):
    try:
        import numpy
    except ImportError:
        return Result(FAIL, "not importable by " + sys.executable)
    return Result(PASS, numpy.__version__)


def _tool(name):
    r = _run([name, "-version"])
    if r is None:
        return Result(FAIL, "not on PATH")
    words = (r.stdout or r.stderr).split()
    return Result(PASS, words[2] if len(words) > 2 else "found")


def check_aac(ctx):
    r = _run(["ffmpeg", "-hide_banner", "-encoders"])
    if r is None:
        return Result(FAIL, "needs ffmpeg")
    if re.search(r"^\s*A\S*\s+aac\s", r.stdout, re.M):
        return Result(PASS, "aac encoder found")
    return Result(FAIL, "this ffmpeg has no aac encoder")


def check_node(ctx):
    v = ctx.node
    if v is None:
        return Result(FAIL, "not on PATH")
    s = "%d.%d.%d" % v
    return Result(PASS, s) if v >= (18,) else Result(FAIL, s + ", needs 18 or later")


def check_key(ctx):
    src, k = ctx.key
    if src is None:
        return Result(FAIL, "no key in $PODKST_API_KEY or " + tilde(studio.key_file()), key_guide(ctx.os))
    where = src if isinstance(src, str) else tilde(src)
    if not k:
        return Result(FAIL, where + " is empty or unreadable", key_guide(ctx.os))
    if isinstance(src, pathlib.Path) and studio.loose(src):
        return Result(WARN, "found in %s, but other users can read it" % where, ["chmod 600 " + where])
    return Result(PASS, "found in " + where)


def credits(key, timeout=10):
    """GET /credits once. Returns (http code or None, parsed body or None, error class name)."""
    req = urllib.request.Request(studio.API + "/credits", headers={
        "Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": studio.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null"), None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), None
        except ValueError:
            return e.code, {"cloudflare_1010": b"1010" in raw}, None
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, None, type(getattr(e, "reason", e)).__name__


def check_access(ctx):
    src, k = ctx.key
    if not k:
        return Result(WARN, "not checked, no key")
    code, body, err = credits(k)
    body = body if isinstance(body, dict) else {}
    data = {"http": code}
    if code is None:
        return Result(WARN, "could not reach %s (%s); check again when online" % (studio.API, err), [], data)
    if code == 200:
        data.update(balance=body.get("balance"), missing_scopes=[])
        return Result(PASS, "accepted (HTTP 200), balance %s credits, billing:read ok, other scopes are checked on first use"
                      % body.get("balance"), data=data)
    e = body.get("error") if isinstance(body.get("error"), dict) else {}
    if code == 403 and body.get("cloudflare_1010"):
        return Result(WARN, "blocked by Cloudflare (HTTP 403, error 1010), not a key problem", [], data)
    if code == 403 and e.get("type") == "permission_error":
        missing = [s for s in SCOPES if s in str(e.get("message", ""))] or ["billing:read"]
        data["missing_scopes"] = missing
        return Result(FAIL, "accepted, but the key lacks %s (HTTP 403)" % ", ".join(missing),
                      ["create a key with the scopes " + ", ".join(SCOPES)] + key_guide(ctx.os)[1:], data)
    if code in (401, 403):
        return Result(FAIL, "rejected (HTTP %d)" % code, ["create a new key"] + key_guide(ctx.os)[1:], data)
    return Result(WARN, "podkst answered HTTP %d; check again later" % code, [], data)


def check_playwright(ctx):
    if ctx.node is None or ctx.node < (18,):
        return Result(WARN, "needs Node 18 or later first", [])
    return Result(PASS, "found") if ctx.browser.get("pw") else Result(WARN, "not installed; the browser checks and presenter tests need it")


def check_chromium(ctx):
    if not ctx.browser.get("pw"):
        return Result(WARN, "needs Playwright first", [])
    if ctx.browser.get("chromium"):
        return Result(PASS, "launches, version " + ctx.browser["chromium"])
    return Result(WARN, "does not launch: " + ctx.browser.get("error", "unknown error"))


def check_uv(ctx):
    r = _run(["uv", "--version"])
    if r is None or r.returncode:
        return Result(WARN, "not on PATH; the ASR check and the pronunciation probe need it")
    return Result(PASS, (r.stdout.split() + ["", "found"])[1])


def hf_hub():
    e = os.environ
    if e.get("HF_HUB_CACHE"):
        return pathlib.Path(e["HF_HUB_CACHE"])
    if e.get("HF_HOME"):
        return pathlib.Path(e["HF_HOME"]) / "hub"
    return pathlib.Path(e.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache") / "huggingface" / "hub"


def check_whisper(ctx):
    have = [m for m in MODELS if (hf_hub() / f"models--Systran--faster-whisper-{m}").is_dir()]
    missing = [m for m in MODELS if m not in have]
    if not missing:
        return Result(PASS, "cached: " + ", ".join(have))
    return Result(WARN, "not cached: %s; the ASR check downloads models on first use" % ", ".join(missing))


CHECKS = [
    ("python", "Python 3.10+", REQUIRED, check_python),
    ("numpy", "numpy", REQUIRED, check_numpy),
    ("ffmpeg", "ffmpeg", REQUIRED, lambda ctx: _tool("ffmpeg")),
    ("ffprobe", "ffprobe", REQUIRED, lambda ctx: _tool("ffprobe")),
    ("aac", "AAC encoder", REQUIRED, check_aac),
    ("node", "Node 18+", REQUIRED, check_node),
    ("key", "podkst key", REQUIRED, check_key),
    ("access", "podkst accepts the key", REQUIRED, check_access),
    ("playwright", "Playwright", OPTIONAL, check_playwright),
    ("chromium", "Chromium", OPTIONAL, check_chromium),
    ("uv", "uv", OPTIONAL, check_uv),
    ("whisper", "whisper models", OPTIONAL, check_whisper),
]


def fixes(id_, os_name):
    t = FIXES.get(id_, {})
    return t.get(os_name) or t.get("other") or []


def run(ctx):
    items = []
    for id_, name, tier, fn in CHECKS:
        r = fn(ctx)
        status = WARN if tier == OPTIONAL and r.status == FAIL else r.status
        fix = [] if status == PASS else (fixes(id_, ctx.os) if r.fix is None else r.fix)
        items.append(Item(id_, name, tier, status, r.detail, fix, r.data))
    return items


def failed(items):
    return [i for i in items if i.status == FAIL]


def render(items, os_name):
    out = [f"voiced-deck doctor ({os_name})"]
    for tier in (REQUIRED, OPTIONAL):
        out.append(tier)
        for i in (i for i in items if i.tier == tier):
            out.append(f"  {i.status} {i.name:<23} {i.detail}")
            out += [f"       fix: {f}" if n == 0 else f"            {f}" for n, f in enumerate(i.fix)]
    bad = failed(items)
    out.append("result: every required item passes" if not bad else
               f"result: {len(bad)} required item{'s' * (len(bad) > 1)} failed. Apply the fix lines, or run `voiced-deck setup`.")
    return "\n".join(out)


def _redact(text, ctx):
    k = ctx.key[1]
    return text.replace(k, "[key]") if k else text


def doctor(as_json=False, os_name=None):
    ctx = Ctx(os_name or host_os())
    items = run(ctx)
    if as_json:
        text = json.dumps({"ok": not failed(items), "os": ctx.os, "items": [dataclasses.asdict(i) for i in items]}, indent=1)
    else:
        text = render(items, ctx.os)
    print(_redact(text, ctx))
    return 1 if failed(items) else 0


@dataclasses.dataclass
class Step:
    title: str
    shown: str
    run: object


def node_dir():
    """The repo root in a checkout of agent-tools, else the plugin root. Node finds Playwright from both."""
    pkg = REPO / "package.json"
    return REPO if pkg.is_file() and '"playwright"' in pkg.read_text(encoding="utf-8") else PLUGIN


def command(title, argv, cwd):
    def go():
        exe = shutil.which(argv[0])
        if not exe:
            print(f"  {argv[0]} is not on PATH")
            return 127
        return subprocess.run([exe, *argv[1:]], cwd=cwd).returncode
    return Step(title, f"$ cd {tilde(cwd)} && {' '.join(argv)}", go)


def _chmod(path):
    def go():
        os.chmod(path, 0o600)
        return 0
    return go


def _safebox():
    from . import safebox
    safebox.run()
    return 0


def plan(items, ctx, asr=False):
    by = {i.id: i for i in items}
    steps, notes = [], []
    for id_ in ("python", "numpy", "ffmpeg", "ffprobe", "aac", "node", "uv"):
        i = by[id_]
        if i.status != PASS and i.fix:
            notes.append(f"{i.name} ({i.tier}): " + "; ".join(i.fix))
    nd = node_dir()
    if by["node"].status == PASS:
        if by["playwright"].status != PASS:
            argv = ["npm", "install", "--no-audit", "--no-fund"] + ([] if nd == REPO else [PLAYWRIGHT])
            steps.append(command("install the Playwright package", argv, nd))
        if by["chromium"].status != PASS:
            steps.append(command("download Playwright's Chromium", ["npx", "playwright", "install", "chromium"], nd))
            if ctx.os == "debian":
                notes.append("Chromium on Linux may need system libraries: sudo npx playwright install-deps chromium")
    if by["whisper"].status != PASS:
        if not asr:
            notes.append("whisper models: pass --asr to download them now (about 1 GB)")
        elif by["uv"].status != PASS:
            notes.append("whisper models: install uv first")
        else:
            code = "from faster_whisper import WhisperModel as W\nfor m in %r: W(m, device='cpu', compute_type='int8')" % (MODELS,)
            steps.append(command("download the whisper models " + ", ".join(MODELS),
                                 ["uv", "run", "--with", "faster-whisper", "python", "-c", code], pathlib.Path.home()))
    src, _ = ctx.key
    if by["key"].status == WARN and isinstance(src, pathlib.Path):
        steps.append(Step("make the key file owner-only", "$ chmod 600 " + tilde(src), _chmod(src)))
    need_key = by["key"].status == FAIL or by["access"].status == FAIL
    if need_key and src == "$PODKST_API_KEY":
        notes.append("podkst key: $PODKST_API_KEY holds a key podkst does not accept. Put a new key in your shell profile.")
        notes += key_guide(ctx.os)
    elif need_key:
        notes += key_guide(ctx.os)
        steps.append(Step("save the podkst key with the local form", "$ voiced-deck safebox", _safebox))
    return steps, notes


def _ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        print("(no terminal; pass --yes to run the steps)")
        return "n"


def setup(yes=False, dry_run=False, asr=False, os_name=None):
    ctx = Ctx(os_name or host_os())
    items = run(ctx)
    print(_redact(render(items, ctx.os), ctx))
    steps, notes = plan(items, ctx, asr)
    if notes:
        print("\nsetup does not install system packages or keys. Do these yourself:")
        print("\n".join("  " + n for n in notes))
    print(f"\nsetup plan: {len(steps)} step{'s' * (len(steps) != 1)}" + (" (dry run)" if dry_run else ""))
    for n, s in enumerate(steps, 1):
        print(f"\nstep {n}/{len(steps)}: {s.title}\n  {s.shown}", flush=True)
        if dry_run:
            continue
        if not yes and _ask("  run it? [Y/n] ") in ("n", "no"):
            print("  skipped")
            continue
        try:
            rc = s.run()
        except KeyboardInterrupt:
            rc = 130
        print("  done" if rc == 0 else f"  failed (exit {rc})", flush=True)
    if dry_run:
        print("\ndry run: nothing was changed")
        return 0
    print()
    return doctor(os_name=ctx.os)
