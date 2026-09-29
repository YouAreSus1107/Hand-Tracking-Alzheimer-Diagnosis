# Hand tremor illustrations

These are the pictures for the Hand tremor page (`#page-tremor` in `launcher_web/index.html`). Each `.art-slot` placeholder names its file in `data-art`, and hovering over it shows the brief below. To drop a picture in, replace the slot's `<div class="slot-ph">…</div>` with `<img src="img/tremor/<name>.webp" alt="…">` and add the alt text's Chinese to `launcher_web/i18n.zh.js`.

The rest holds moved from the table to the lap on 2026-09-27 (a neurologist's advice), so `step-2-rest` and `step-3-count` were replaced by `step-2-palms-up` and `step-3-palms-down`.

The art direction is shared across every test. It is written out in `launcher_web/img/tapping/README.md`: flat vector, token colours only, the same older gender-neutral character, a glyph on every ✓/✕, and no words in the art.

| File | Ratio | Shows |
|---|---|---|
| `step-1-set-up.webp` | 4:3 | **Aim the camera at your lap.** Side view: seated, a webcam on a stand aimed down at the lap, its view cone covering both hands resting on the thighs. |
| `step-2-palms-up.webp` | 4:3 | **Palms up in your lap.** Top-down view of the lap: both hands resting on the thighs, palms up, fingers loosely curled. 20 s ring in the corner. |
| `step-3-palms-down.webp` | 4:3 | **Turn them over.** The same top-down view: both hands turned over, palms down on the thighs, fingers loose. 20 s ring in the corner. |
| `step-4-arms-out.webp` | 4:3 | **Arms held out.** Front view: both arms straight out, palms down. 20 s ring in the corner. |
| `tip-1-do.webp` | 1:1 | **Both hands in view.** Both hands inside the frame, room around them. |
| `tip-1-dont.webp` | 1:1 | **One hand cut off.** One hand past the edge; red edge band and inward chevron. |
| `tip-2-do.webp` | 1:1 | **Loose hands.** Fingers soft and slightly curled, resting. |
| `tip-2-dont.webp` | 1:1 | **Tense hands.** Fists, or fingers pressed down into the legs. |
| `tip-3-do.webp` | 1:1 | **Body still.** Sitting back, shoulders relaxed, nothing moving. |
| `tip-3-dont.webp` | 1:1 | **Shifting around.** Leaning and shifting, motion lines around the shoulders. |

## Not an illustration

`example-recording.json` is the real run drawn under "What we measure". None is on record yet, so the page shows a placeholder. To add one, copy a clean session from `results/` with only `test`, `mode`, `metrics` and `raw` (no profile or timestamp), then set `file` for this test in `RECORDINGS` (`launcher_web/app.js`).
