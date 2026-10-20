---
name: voiced-deck
description: Build a keynote-grade, single-file HTML slide deck that presents itself. A natural pitch voice rendered through the podkst Studio API drives every slide and build in sync, with pause and resume, captions and a presenter view. Use when someone asks for a pitch deck, board deck or talk that should play with a voice, a "voiced deck", "presenter mode with audio", or a deck to post in a chat that only shows images.
---

# Voiced deck

You build three connected things: a deck (`deck.html`), a voiced script (`performance.json`), and the audio with its timing manifest embedded in the deck. Pressing **Presenter** then plays the pitch, and the audio clock advances each build and slide.

`VD` below means `python3 -I ${CLAUDE_PLUGIN_ROOT}/tools/voiced-deck`. Outside Claude Code, the plugin root is two folders above this file. Every step is one subcommand. Run `VD <command> --help` for flags.

Read these when the step calls for them:

- `references/deck-design.md` for the design bar and the slide conventions.
- `references/voice-direction.md` before you write a single line of `performance.json`.
- `references/podkst-studio-api.md` when a Studio call fails or you need an endpoint.
- `references/delivery.md` before you hand the deck over.

The demo in `${CLAUDE_PLUGIN_ROOT}/examples/demo/` is a finished example of every file below.

## Requirements

- Python 3.10+, ffmpeg and numpy. Node 18+ with Playwright for the browser checks.
- Optional: faster-whisper for the ASR check, run through `uv run --with faster-whisper`.
- A podkst API key with the scopes `generate:podcast`, `read:jobs` and `billing:read`. The tools read `$PODKST_API_KEY` or `~/.config/podkst/api.key`. Never print, echo or log the key. Never ask the owner to paste it into the chat.

## Steps

Copy these into your todo list and finish each one before the next.

1. **Brief.** Write down the audience, the one thing they must remember, the slide arc, and where every number comes from. One idea per slide. Invent no numbers.
2. **Deck.** Run `VD new deck.html`, then write the slides per `references/deck-design.md`. Read the `dataviz` skill before any chart if your session has it. Audit with `node ${CLAUDE_PLUGIN_ROOT}/tools/browser/audit.js $PWD/deck.html shots`. Look at the PNGs in `shots/` yourself and fix overflow, clipping, overlaps and slides over about 30 words.
3. **Script.** Write `script.md`: one `## N · Title` section per slide, with a `[click]` wherever a build appears. Run `VD script script.md deck.html`. It writes the deck's `#pitch` JSON and fails if a slide's builds differ from its `[click]` count.
4. **Performance.** Run `VD perf init --deck deck.html --performance performance.json`, then rewrite every line as spoken text plus a direction, per `references/voice-direction.md`. Run `VD perf check --deck deck.html --performance performance.json` until it passes.
5. **Key and credits.** Run `VD credits`. If there is no key, run `VD safebox` in the background and send the owner the printed localhost URL. For an owner away from the machine, see the tunnel note in `references/delivery.md`. Then run `VD estimate --deck deck.html --performance performance.json`. The estimate is free.
6. **Audition.** Run `VD audition --performance performance.json --voices Charon,Orus,Algenib --lines <3 varied line ids> --out audio`. Send the owner the per-voice `.m4a` files in `audio/audition/`. The ear picks the voice. The metrics only break ties.
7. **Render.** Run `VD render --deck deck.html --performance performance.json --voice <winner>`. It creates a Studio project, synthesises every line, sets the pauses, masters to -16 LUFS, writes `audio/deck.m4a` and `audio/deck.png`, and embeds the manifest in the deck. `--max-credits` caps any single step.
8. **Measure.** Run `VD check --performance performance.json --out audio` for pace, pitch range, pauses and phrase-final drop. Run `uv run --with faster-whisper --with numpy python -I ${CLAUDE_PLUGIN_ROOT}/tools/voiced-deck asr --out audio --performance performance.json` to transcribe each line. Listen to every flagged line, or have the owner listen.
9. **Pronunciation.** For a name the voice gets wrong, run `VD probe --performance performance.json --word <Word> --variant "<note 1>" --variant "<note 2>" --out audio --apply`. It renders each wording in a scratch project, scores each take by transcript, and writes the winning note into `performance.json`.
10. **Re-master.** Edit `performance.json` (text, style, `gapAfterMs`, `pronounce`) and run `VD render` again. Only edited lines are re-synthesised. A line whose new direction equals a probe take reuses that audio at no cost. Use `VD regen --deck deck.html --performance performance.json <line id>` for a new take of an unchanged line.
11. **Sync.** Run `VD sync --deck deck.html --script script.md --performance performance.json --browser`. Builds, `[click]` marks, performance segments and manifest must all agree at 1280, 728 and 390 px.
12. **Presenter tests.** Run `VD pack-deck deck.html`, then `VD_DECK=$PWD/deck.html node ${CLAUDE_PLUGIN_ROOT}/tests/presenter/run.js`. All four files must pass.
13. **Deliver.** Follow `references/delivery.md`: the folder with `deck.html` and `audio/`, served or opened locally, or the PNG-packed loader for chat hosts that only inline images.

## Rules

- The ear is the gate. Metrics and ASR find lines to listen to. They do not approve audio.
- All delivery direction goes in `style`. The model reads `text` word for word.
- Keep `audio/studio-state.json` and `audio/master.*` out of git. They hold project and take ids.
- Never commit a key, a project id, or the owner's private numbers. Run the repo's scrub check if it has one.
