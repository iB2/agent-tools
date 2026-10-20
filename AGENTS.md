# Agent instructions

This repo is a set of tools for coding agents. Each tool lives in `plugins/<tool>/` with a skill (`skills/<tool>/SKILL.md`), its CLIs (`tools/`), tests and a demo.

## Using a tool from any agent

1. Read `plugins/<tool>/skills/<tool>/SKILL.md` in full. It is the playbook.
2. Where the skill says `${CLAUDE_PLUGIN_ROOT}`, use the absolute path of `plugins/<tool>/`.
3. Read a file under `references/` when a step points to it.
4. Copy the skill's steps into your task list and finish each one before the next.

For voiced-deck the CLI is `python3 -I plugins/voiced-deck/tools/voiced-deck`. Run it with `--help` for every command. Run its `doctor` command before the first step. It names each missing requirement and its fix.

## Secrets and private data

- Read the podkst key only through the tools. They take it from `$PODKST_API_KEY` or `~/.config/podkst/api.key` and send it only as the Bearer header to `api.podkst.ai`. Never print it, echo it, log it or ask for it in chat. Use `voiced-deck safebox` to collect it.
- Keep `audio/studio-state.json` and `audio/master.*` out of git. They hold account ids.
- Run `python3 -I scripts/scrub_check.py` before every commit. It must report 0 hits.

## Working on this repo

- Edit the engine only in `plugins/voiced-deck/template/deck.html`, then run `python3 -I plugins/voiced-deck/tools/voiced-deck engine-sync plugins/voiced-deck/examples/demo/deck.html`.
- Run `npm test` before you commit. It runs the unit tests, the presenter tests and the scrub check.
- Write plain English: short sentences, no long dashes, no mid-sentence colons.
