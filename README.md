# agent-tools

Tools for coding agents. Each tool is a Claude Code plugin with a skill that tells the agent what to do, the CLIs that do it, tests, and a working demo. Agents that are not Claude Code can follow [AGENTS.md](AGENTS.md).

| Tool | What it does |
|---|---|
| [voiced-deck](plugins/voiced-deck) | Builds a keynote-grade, single-file HTML deck that presents itself. A natural pitch voice rendered through the [podkst](https://podkst.ai) Studio API drives every slide and build in sync. |

## Install

In Claude Code:

```
/plugin marketplace add iB2/agent-tools
/plugin install voiced-deck@agent-tools
```

Then ask for what you want, for example "make a voiced pitch deck for this plan". The skill takes it from there.

## voiced-deck

You get one HTML file under 200 KB. It has slides with builds, a notes drawer, a presenter view, captions, fullscreen, keyboard and touch navigation, and light and dark themes. Press **Presenter** and the pitch plays. The audio clock advances every build and slide. Pause and resume pick up where they stopped, and jumping to a slide restarts that slide's audio.

The pipeline:

```
brief -> deck.html -> script.md with [click] marks -> performance.json (text + direction per line)
      -> audition voices -> render in podkst Studio -> measure + ASR -> pronunciation probe
      -> re-master only what changed -> manifest embedded in the deck -> presenter tests -> deliver
```

Every step is one command of `plugins/voiced-deck/tools/voiced-deck`. `voiced-deck render --deck deck.html --performance performance.json --voice Charon` does the voice end to end.

### 60-second demo

**[Watch it in your browser](https://ib2.github.io/agent-tools/plugins/voiced-deck/examples/demo/deck.html)** and press **Presenter**.

The demo is a fictional seed pitch, Hivewise, with 7 slides and a 1 minute 55 second voice rendered with podkst.

```
git clone https://github.com/iB2/agent-tools && cd agent-tools
python3 plugins/voiced-deck/tools/voiced-deck serve plugins/voiced-deck/examples/demo
```

Open `http://localhost:8765/deck.html` and press **Presenter** (or `P`). `K` pauses, `C` shows captions, the arrows jump slides, `Esc` stops.

To see the PNG delivery for chat hosts that only inline images, open `http://localhost:8765/deck.inline.html`.

### Requirements

- A podkst API key with the scopes `generate:podcast`, `read:jobs` and `billing:read`. Set `PODKST_API_KEY`, or run `voiced-deck safebox` once to store it in `~/.config/podkst/api.key` with mode 0600. The demo needs no key.
- Python 3.10+, ffmpeg and numpy.
- Optional: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for the per-line ASR check (`uv run --with faster-whisper ...`), and Node 18+ with Playwright for the browser checks and presenter tests.

### Layout

```
plugins/voiced-deck/
  skills/voiced-deck/SKILL.md        the playbook the agent follows
  skills/voiced-deck/references/     deck design bar, voice direction, Studio API notes, delivery
  tools/voiced-deck                  the CLI (python3, stdlib + numpy)
  tools/vdeck/                       its modules: studio client, script, performance, manifest,
                                     prosody, ASR, PNG packing, delivery, safebox
  tools/browser/                     build counts and slide audit in a headless browser
  template/deck.html                 the engine plus a 3-slide skeleton
  examples/demo/                     the voiced Hivewise demo
  tests/                             unit tests and presenter tests
```

## Tests

```
npm install && npx playwright install chromium
npm test
```

`npm test` runs the unit tests, the presenter tests against the demo, and `scripts/scrub_check.py`, which fails on home paths, keys, Studio ids, emails and private phrases in files, packed PNGs and commit messages.

## License

MIT. See [LICENSE](LICENSE).
