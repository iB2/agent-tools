# voiced-deck

A single-file HTML deck that presents itself with a natural voice from the podkst Studio API. The skill in [skills/voiced-deck/SKILL.md](skills/voiced-deck/SKILL.md) is the playbook. The demo in [examples/demo](examples/demo) is the finished result.

## Install

```
/plugin marketplace add iB2/agent-tools
/plugin install voiced-deck@agent-tools
```

On Claude Code 2.1.275 or later, one step works too: `/plugin install voiced-deck --marketplace iB2/agent-tools`.

## Commands

`python3 -I tools/voiced-deck <command>`:

| Command | What it does |
|---|---|
| `doctor` | Checks Python, numpy, ffmpeg, Node, Playwright, Chromium, uv, the whisper models and the podkst key, and prints the fix for each gap. `--json` for machines. Exits 1 when a required item fails. |
| `setup` | Installs what is safe to install: the Playwright package, its Chromium, the whisper models (`--asr`) and the key (through `safebox`). Prints the commands for system packages. `--dry-run` only prints the plan, `--yes` runs it without asking. |
| `new` | Copies the template to a new deck. |
| `engine-sync` | Refreshes the engine blocks of a deck from the template. `--check` fails on drift. |
| `script` | Writes `script.md` into the deck's `#pitch` JSON and checks build counts against `[click]` marks. |
| `perf init`, `perf check` | Scaffolds `performance.json` from the deck script, and lints it against the voice rules. |
| `sync` | Checks deck builds, script, performance and manifest agree. `--browser` counts builds at 1280, 728 and 390 px. |
| `credits`, `estimate` | Credit balance, and the free cost probe for a full render. |
| `audition` | Renders the same lines in several voices, with prosody per voice and an `.m4a` each. |
| `render` | Creates or updates the Studio project, masters, encodes AAC, packs a PNG copy and embeds the manifest. Re-runs edit only changed lines. |
| `regen` | A new take (new seed) for given lines, then re-master. |
| `check` | Per-line duration sanity and whole-show pace, pitch range, pauses and phrase-final drop. |
| `asr` | Per-line faster-whisper transcription with number-normalised WER. |
| `probe` | Tries several pronunciation notes for a hard word in a scratch project, scores each by ASR, keeps the best. |
| `measure` | Prosody of any audio file or slice. |
| `embed` | Embeds or clears a manifest. Idempotent, and refuses a manifest that does not match the deck. |
| `pack`, `unpack` | Any file into PNG pixels and back. |
| `pack-single` | One self-contained HTML with the audio embedded as a `data:` URI, so it plays with no files beside it. `--bitrate 32k` re-encodes to mono AAC with ffmpeg to shrink it, `--max-mb` (default 2) sets the size warning. |
| `pack-deck` | The deck as a PNG plus a tiny loader, for chat hosts that only inline images. |
| `serve` | Serves a folder on localhost with audio MIME types. |
| `safebox` | One-time localhost form that stores the podkst key with mode 0600. |

Browser tools: `node tools/browser/builds.js <deck>` and `node tools/browser/audit.js <deck> [outDir]`.

## One file, plays anywhere

A rendered deck is `deck.html` plus `audio/deck.m4a`. Send the HTML alone and it opens silent. `pack-single` puts the audio inside the HTML:

```
python3 -I tools/voiced-deck pack-single --deck deck.html
python3 -I tools/voiced-deck pack-single --deck deck.html --bitrate 32k
```

It writes `deck.single.html` and prints its size. The file plays from an email attachment, Slack, Drive, Downloads, a web server, or pasted into a chat host's sandboxed preview where the host allows the size and sound. The demo's single file is [examples/demo/deck.single.html](examples/demo/deck.single.html), 0.88 MB.

When to use which route is in [references/delivery.md](skills/voiced-deck/references/delivery.md).

## First run

```
python3 -I tools/voiced-deck doctor
python3 -I tools/voiced-deck setup --dry-run
python3 -I tools/voiced-deck setup
```

`doctor` prints one line per item, PASS, WARN or FAIL, with the fix for your OS. `setup` never runs `sudo`, `brew`, `apt` or `winget`. It prints those commands for you to run.

## Optional: the podkst MCP server

voiced-deck does not need it. The CLI calls the podkst Studio REST API itself. Add the [`@podkst/mcp-server`](https://www.npmjs.com/package/@podkst/mcp-server) (version 1.1.0 when this was written) when you want to edit a Studio project by hand from a chat: change one line, select another take, undo or redo.

Run one of these in your own terminal, not through an agent, so the key stays out of the transcript:

```
claude mcp add podkst -e PODKST_API_KEY=<your key> -- npx -y @podkst/mcp-server
claude mcp add --transport http podkst https://api.podkst.ai/mcp --header "Authorization: Bearer <your key>"
```

The first runs the server locally over stdio and needs Node 20 or later. The second uses the hosted server, the same tools over Streamable HTTP, with nothing to install. The CLI does not see edits made through the MCP server. Copy a text or direction change into `performance.json` before the next `render`.

## Tests

From the repo root, `npm test`. To run the presenter tests against your own deck, `VD_DECK=/abs/path/deck.html node tests/presenter/run.js`.
