# Speech rhythm illustrations

These are the pictures for the Speech rhythm page (`#page-ddk` in `launcher_web/index.html`). Each `.art-slot` placeholder names its file in `data-art`, and hovering over it shows the brief below. To drop a picture in, replace the slot's `<div class="slot-ph">…</div>` with `<img src="img/ddk/<name>.webp" alt="…">` and add the alt text's Chinese to `launcher_web/i18n.zh.js`.

The art direction is shared across every test. It is written out in `launcher_web/img/tapping/README.md`: flat vector, token colours only, the same older gender-neutral character, a glyph on every ✓/✕, and no words in the art.

| File | Ratio | Shows |
|---|---|---|
| `step-1-quiet.webp` | 4:3 | **Room check.** A microphone beside a level meter sitting low in its green zone; the character holds a finger to their lips. |
| `step-2-once.webp` | 4:3 | **Say it once.** A speech bubble with three different shapes in a row (for pa, ta, ka) and the level meter now high in its green zone. |
| `step-3-repeat.webp` | 4:3 | **Keep going.** A row of evenly spaced sound bumps running across, with an 8 s ring in the corner. |
| `step-4-score.webp` | 4:3 | **Your score.** Mini result card: a big rhythm number with a green ✓ chip and a small row of evenly spaced peaks. |
| `tip-1-do.webp` | 1:1 | **Quiet room.** Door closed, nothing else making sound. |
| `tip-1-dont.webp` | 1:1 | **Noisy room.** TV and fan in the background, sound waves around them. |
| `tip-2-do.webp` | 1:1 | **Normal distance.** Sitting at arm's length from the laptop, speaking normally; meter in the green. |
| `tip-2-dont.webp` | 1:1 | **Too close.** Mouth right at the laptop; meter pinned in the red. |
| `tip-3-do.webp` | 1:1 | **Even pace.** A row of evenly spaced bumps. |
| `tip-3-dont.webp` | 1:1 | **Rush and stop.** Bumps crowded together, then a long gap. |

## Not an illustration

`example-recording.json` is the real run drawn under "What we measure". None is on record yet, so the page shows a placeholder. To add one, copy a clean session from `results/` with only `test`, `mode`, `metrics` and `raw` (no profile or timestamp), then set `file` for this test in `RECORDINGS` (`launcher_web/app.js`).
