# podkst Studio API notes

`tools/vdeck/studio.py` wraps these calls. Read this when a call fails or you need one the CLI does not make.

Base URL `https://api.podkst.ai/v1`. Auth is `Authorization: Bearer <key>`. The key needs the scopes `generate:podcast`, `read:jobs` and `billing:read`.

## Get a key

1. Sign in at https://podkst.ai.
2. Open Dashboard, then Settings, then API Keys (https://podkst.ai/dashboard/api-keys).
3. Create a key with the scopes `generate:podcast`, `read:jobs` and `billing:read`.
4. Save it in one of two ways. Add `export PODKST_API_KEY=<your key>` to the shell profile, or run `voiced-deck safebox` and paste the key into its local form. The form writes `~/.config/podkst/api.key` with mode 0600 and never echoes the key.

`voiced-deck doctor` then calls `GET /credits` once. A 200 means podkst accepts the key and it has `billing:read`. A 401 means podkst rejects the key. A 403 with `permission_error` names a missing scope. Doctor does not test `generate:podcast` or `read:jobs`, because that needs a call that writes. The first render tests them.

## Facts learned the hard way

- **Rate limit.** 10 requests a minute on the base plan. A 429 carries `error.retry_after` in seconds (or a `Retry-After` header). Wait that long and retry. The client also spaces its own calls.
- **User-Agent.** Cloudflare answers the default `Python-urllib/x.y` User-Agent with 403, error 1010. Send a custom User-Agent on every request, signed-URL downloads included.
- **Versioned edits.** PATCH needs `If-Match: "<version>"`, with the quotes. Read the project first to get the version.
- **Edit after jobs.** Send a PATCH only after any synthesis job on the project has finished. The worker writes the project too, and a concurrent edit races it.
- **Free cost probe.** Create, synthesize and master with `max_credits: 0` return 409 with `estimated_credits` when they would spend. Send the call again with `max_credits` set to that estimate. A 2xx at `max_credits: 0` means nothing needed paying.
- **Content-addressed takes.** A take is keyed by voice, model, text, direction, language and seed. Identical settings reuse the audio at no cost, across projects. The demo measured this: the pronunciation probe's winning take came back byte-for-byte in the main project (waveform correlation 0.984, same length) and the re-synthesis was accepted at `max_credits: 0`. Build the direction string with one function everywhere so equal inputs stay equal.
- **Edits clear one take.** `set_text` and `set_direction` clear that line's take only. `set_pause` changes timing only.
- **Script format.** One line per turn, `Speaker: [direction] text`. The bracket becomes the line's direction and is not spoken. A newline or a `]` inside the direction breaks parsing.

## Endpoints the tools use

| Call | Purpose |
|---|---|
| `GET /credits` | `{balance}` |
| `POST /studio/projects` `{title, language, quality, script, voices, max_credits}` | Create and synthesise. `voices` maps speaker label to `builtin:<Voice>`. `language` is `en-US` or `pt-BR`, `quality` is `standard` or `pro`. Returns `{project: {id, version, segments: [{id}]}, job_id}`. |
| `GET /studio/jobs/{job_id}` | `{status: queued, processing, succeeded or failed, result, error}` |
| `GET /studio/projects/{id}` | The project with `version` and `segments`. |
| `PATCH /studio/projects/{id}` `{ops: [...]}` | Ops: `{op: "set_text", segment_id, text}`, `{op: "set_direction", segment_id, direction}`, `{op: "set_pause", segment_id, pause_after_ms}`. |
| `POST /studio/projects/{id}/synthesize` `{max_credits}` | Synthesise lines without a take. |
| `POST /studio/projects/{id}/segments/{segment_id}/regenerate` `{max_credits}` | A new take with a new seed. |
| `POST /studio/projects/{id}/master` `{preset, max_credits}` | Presets `wav-master`, `podcast-mono` (-19 LUFS) and `podcast-stereo` (-16 LUFS, -1 dBTP). The result has a signed `url`, `duration_s`, `integrated_lufs`, `true_peak_dbtp` and `lines: [{segment_id, start_s, end_s}]`. |

Takes are 24 kHz mono, levelled per take before mixing. The voiced deck uses `wav-master` and encodes it to 40 kbps mono AAC (`VD_AAC_KBPS` changes the rate).

## The podkst MCP server is optional

The tools call the REST API themselves and do not need the MCP server. It helps for manual edits to a Studio project from a chat: one line, a different take, undo and redo. See the plugin README for how to add it.

## Ids are private

Project, job, render, segment and take ids identify the owner's account. `studio-state.json` and `master.json` hold them, so keep both out of git. The manifest the deck embeds holds none.
