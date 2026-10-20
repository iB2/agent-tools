# Voice direction guide

What makes a synthetic pitch sound like a person fighting for an idea, learned from real owner reviews of Gemini TTS voices rendered through podkst.

## The ear is the gate

Metrics have passed audio that the owner rejected twice. Use `VD check` and `VD asr` to find lines worth listening to, then listen. When you cannot listen, send the owner the audition files and the flagged lines and ask.

## Targets

| Measure | Target | Why |
|---|---|---|
| Speech pace | about 168 to 185 wpm | A clone at 210 to 229 wpm was judged too fast and monotone. 180 wpm was judged much better. |
| Pitch range (F0 p5 to p95) | about 15 semitones or more | The voice judged much better ran 15.5 st. A human can sound fine at 5 st, a synthetic voice cannot. |
| Pauses | fewer than you think | Synthetic voices over-pause. One run measured 22 to 27 pauses a minute against a human's 13.6. |
| Phrase-final drop | small | Synthetic voices drop about 4 st at the end of almost every phrase, which sounds like reading. |

`VD check` reports `wpm_speech`, `f0_range_st`, `pauses_per_min` and `final_drop_st`. Compare a voice only with itself or other voices measured by the same tool. The demo measured 170 wpm, 16.7 st, 26.5 pauses a minute and a 2.9 st final drop.

## Text and style

- `text` is what is said, word for word. The model reads it literally.
- `style` is how it is said. Every direction goes there, never in `text`. A whisper written as an inline tag is spoken aloud.
- Write numbers the way they should sound: "one thousand two hundred and forty", "twenty twenty-seven", "one point two million dollars". `VD perf check` warns on digits.
- Spell a brand the way it should sound and record it under `respell`, for example `{"MyBrand": "my brand"}`. `perf check` fails if the written form slips back in. Test a respelling by ear: a phonetic respelling can make it worse.
- Put a pronunciation note for a hard word under `pronounce`. Render adds it to the direction of every line that contains the word. Find the best wording with `VD probe`.
- `pace` is appended to every direction. Use it for the show-wide energy, for example "a live pitch: brisk, upbeat and natural, controlled nerves, confident never arrogant".
- Avoid a blanket "confident and expressive". It fights soft deliveries.
- Direction is capped at 500 characters per line, style, pace and notes together.

## Inline tags

Only these work inside `text`: `<breath>`, `<short pause>`, `<long pause>`, `<chuckle>`, `<laugh>`, `<sigh>`, `<gasp>`, `<cough>`. Use them rarely. `perf check` rejects any other tag.

## Sounding human

- Write one line per breath group, usually one sentence. Short lines give you control over each beat.
- Give each line its own direction, specific to the moment: "lean in, quieter, a nervous energy held in check", "a jolt of energy, stress on 'roars', bigger". Per-line direction like "warm... smiling" is what owners approved.
- Add hesitations: a filler ("uh", "um"), an ellipsis pause, or a small repeat ("I'll, I'll say so"). Use 1 to 3 per paragraph, never more. `perf check` fails a segment with more than 3.
- End phrases open. Ask for "ending lifted" or "no falling sigh" on lines that lead somewhere.
- Vary the energy across the arc: candid and lower for the problem, bright for the insight, steady for the numbers, big for the ask.
- Persuade, never fabricate. Every fact in a line must be in the deck's sources.

## Gaps

`gapAfterMs` is the silence after a line, from 80 to 1600 ms. Use about 120 to 300 ms between lines of one thought, 400 to 650 ms before a build or a new slide. Tighten gaps first when the pause rate is high. The model already pauses at commas and ellipses.

## Voices

Deep male candidates that suit a pitch: Charon, Orus, Algenib, Alnilam, Rasalgethi. Other built-in male voices include Puck, Fenrir, Enceladus, Iapetus, Umbriel, Algieba, Schedar, Achird, Zubenelgenubi, Sadachbia and Sadaltager. Audition 3 to 5 on the same 3 lines, chosen to cover a question, a list and a big claim.
