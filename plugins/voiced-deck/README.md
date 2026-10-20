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
| `pack-deck` | The deck as a PNG plus a tiny loader, for chat hosts that only inline images. |
| `serve` | Serves a folder on localhost with audio MIME types. |
| `safebox` | One-time localhost form that stores the podkst key with mode 0600. |

Browser tools: `node tools/browser/builds.js <deck>` and `node tools/browser/audit.js <deck> [outDir]`.

## Tests

From the repo root, `npm test`. To run the presenter tests against your own deck, `VD_DECK=/abs/path/deck.html node tests/presenter/run.js`.
