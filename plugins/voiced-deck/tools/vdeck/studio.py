"""podkst Studio API client.

The key comes from $PODKST_API_KEY or a key file ($PODKST_API_KEY_FILE, default
~/.config/podkst/api.key). It is read inside this process and sent only as the Bearer
header to the API host. It is never printed, logged or written anywhere.

API facts this client encodes:
- 10 requests a minute on the base plan. The client spaces calls and honors 429 retry_after.
- Cloudflare answers 403 (error 1010) to the default Python-urllib User-Agent. Every request,
  downloads included, sends USER_AGENT.
- PATCH needs If-Match with the current version, and must not run while a synthesis job runs.
- Create, synthesize and master with max_credits 0 return 409 with estimated_credits: a free cost probe.
"""
import collections
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("PODKST_API", "https://api.podkst.ai/v1")
USER_AGENT = "voiced-deck/0.1 (+https://github.com/iB2/agent-tools)"
RATE_PER_MIN = int(os.environ.get("PODKST_RATE_PER_MIN", "10"))
_sent = collections.deque()


class StudioError(SystemExit):
    pass


def key_file():
    return pathlib.Path(os.environ.get("PODKST_API_KEY_FILE", "~/.config/podkst/api.key")).expanduser()


def read_key():
    """Return (source, key): the env var wins over the key file. source is None when neither exists."""
    k = os.environ.get("PODKST_API_KEY", "").strip()
    if k:
        return "$PODKST_API_KEY", k
    f = key_file()
    if not f.is_file():
        return None, ""
    return f, f.read_text(encoding="utf-8").strip()


def loose(path):
    return os.name != "nt" and bool(path.stat().st_mode & 0o077)


def _key():
    src, k = read_key()
    if src is None:
        raise StudioError(f"no podkst API key: set PODKST_API_KEY or run `voiced-deck safebox` to write {key_file()}")
    if isinstance(src, pathlib.Path) and loose(src):
        print(f"warning: {src} is readable by other users; run chmod 600 on it", file=sys.stderr)
    if not k:
        raise StudioError(f"{src} is empty")
    return k


def _throttle():
    now = time.monotonic()
    while _sent and now - _sent[0] > 60:
        _sent.popleft()
    if len(_sent) >= RATE_PER_MIN:
        time.sleep(60 - (now - _sent[0]) + 0.5)
    _sent.append(time.monotonic())


def call(method, path, body=None, headers=None, tries=8, key=None):
    """Return (status, json). Retries 429 and transient errors; other HTTP errors are returned."""
    data = None if body is None else json.dumps(body).encode()
    h = {"Authorization": "Bearer " + (key or _key()), "Content-Type": "application/json",
         "Accept": "application/json", "User-Agent": USER_AGENT}
    h.update(headers or {})
    for i in range(tries):
        _throttle()
        req = urllib.request.Request(API + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                j = json.loads(raw)
            except ValueError:
                j = {"raw": raw[:300].decode("utf-8", "replace")}
            if e.code == 429:
                err = j.get("error") if isinstance(j.get("error"), dict) else {}
                wait = int(err.get("retry_after") or e.headers.get("retry-after") or 30)
                print(f"  rate limited, waiting {wait + 2} s", file=sys.stderr, flush=True)
                time.sleep(wait + 2)
                continue
            if e.code < 500 or i == tries - 1:
                return e.code, j
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))
    return 599, {"error": "retries exhausted"}


def must(status, j, what):
    if status not in (200, 201, 202, 204):
        raise StudioError(f"{what}: HTTP {status} {json.dumps(j)[:600]}")
    return j


def balance():
    return must(*call("GET", "/credits"), "credits").get("balance")


def wait_job(job_id, what, every=12):
    t0, last = time.time(), None
    while True:
        j = must(*call("GET", f"/studio/jobs/{job_id}"), f"job {job_id}")
        if j["status"] != last:
            print(f"  {what}: {j['status']} ({int(time.time() - t0)} s)", flush=True)
            last = j["status"]
        if j["status"] == "succeeded":
            return j.get("result") or {}
        if j["status"] in ("failed", "canceled", "cancelled"):
            raise StudioError(f"{what} {j['status']}: {j.get('error')}")
        time.sleep(every)


def guard(est, what, max_credits):
    bal = balance()
    print(f"{what}: estimated {est} credits, balance {bal}, cap {max_credits}", flush=True)
    if max_credits is not None and est > max_credits:
        raise StudioError(f"{what}: {est} credits is over the cap of {max_credits}; raise --max-credits to proceed")
    if bal is not None and est > bal:
        raise StudioError(f"{what}: needs {est} credits, balance is {bal}")


def estimate_create(body):
    st, j = call("POST", "/studio/projects", {**body, "max_credits": 0})
    if st == 409 and "estimated_credits" in (j or {}):
        return j["estimated_credits"]
    raise StudioError(f"cost probe: HTTP {st} {json.dumps(j)[:400]}")


def create(body, what, max_credits):
    est = estimate_create(body)
    guard(est, what, max_credits)
    j = must(*call("POST", "/studio/projects", {**body, "max_credits": est}), "create project")
    return j["project"], j["job_id"], est


def get_project(pid):
    return must(*call("GET", f"/studio/projects/{pid}"), "get project")


def patch(pid, ops, chunk=200):
    for i in range(0, len(ops), chunk):
        p = get_project(pid)
        must(*call("PATCH", f"/studio/projects/{pid}", {"ops": ops[i:i + chunk]},
                   headers={"If-Match": f'"{p["version"]}"'}), "patch")


def synthesize(pid, what, max_credits):
    """Synthesize lines without a take. Returns credits estimated (0 when nothing to do)."""
    st, j = call("POST", f"/studio/projects/{pid}/synthesize", {"max_credits": 0})
    if st in (200, 201, 202) and (j or {}).get("job_id"):
        wait_job(j["job_id"], what)
        return 0
    if st != 409 or "estimated_credits" not in (j or {}):
        if st in (200, 201, 202, 204):
            return 0
        raise StudioError(f"{what}: HTTP {st} {json.dumps(j)[:400]}")
    est = j["estimated_credits"]
    if not est:
        return 0
    guard(est, what, max_credits)
    j = must(*call("POST", f"/studio/projects/{pid}/synthesize", {"max_credits": est}), what)
    wait_job(j["job_id"], what)
    return est


def regenerate(pid, segment_id, what, max_credits=3):
    j = must(*call("POST", f"/studio/projects/{pid}/segments/{segment_id}/regenerate", {"max_credits": max_credits}), what)
    wait_job(j["job_id"], what)


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)


def master(pid, dest, preset="wav-master"):
    """Mix and master. Writes dest (WAV) and dest.json (timings without the signed URL)."""
    st, j = call("POST", f"/studio/projects/{pid}/master", {"preset": preset, "max_credits": 0})
    if st == 409:
        raise StudioError(f"master would synthesise lines that have no take: {json.dumps(j)[:300]}")
    res = wait_job(must(st, j, "master")["job_id"], "master")
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    download(res["url"], dest)
    meta = {k: v for k, v in res.items() if k != "url"}
    dest.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(f"  master: {dest.name} {meta['duration_s']:.1f} s, {meta.get('integrated_lufs')} LUFS, "
          f"peak {meta.get('true_peak_dbtp')} dBTP", flush=True)
    return meta
