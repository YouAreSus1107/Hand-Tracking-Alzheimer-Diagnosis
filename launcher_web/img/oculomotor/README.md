# Eye movement illustrations

These are the pictures for the Eye movement page (`#page-oculomotor` in `launcher_web/index.html`). Each `.art-slot` placeholder names its file in `data-art`, and hovering over it shows the brief below. To drop a picture in, replace the slot's `<div class="slot-ph">…</div>` with `<img src="img/oculomotor/<name>.webp" alt="…">` and add the alt text's Chinese to `launcher_web/i18n.zh.js`.

The art direction is shared across every test. It is written out in `launcher_web/img/tapping/README.md`: flat vector, token colours only, the same older gender-neutral character, a glyph on every ✓/✕, and no words in the art.

| File | Ratio | Shows |
|---|---|---|
| `step-1-calibrate.webp` | 4:3 | **Three dots.** Screen with three dots (centre, left, right) joined by a faint path. The character's head is level and still, only the eyes turned toward the right dot. |
| `step-2-toward.webp` | 4:3 | **Look toward.** Centre cross, a dot flashes on the right, and a green arrow runs from the eyes to the dot. |
| `step-3-away.webp` | 4:3 | **Look away.** Centre cross, a dot flashes on the left (drawn faint), and a green arrow runs from the eyes to the empty right side. |
| `step-4-hold.webp` | 4:3 | **Hold still.** A centre cross with a tight little cluster of gaze dots on it. |
| `tip-1-do.webp` | 1:1 | **Head still.** Face square to the camera; only the eyes turned to the side. |
| `tip-1-dont.webp` | 1:1 | **Head turning.** The whole head turned toward the dot. |
| `tip-2-do.webp` | 1:1 | **Face lit.** Lamp in front; both eyes clearly visible. |
| `tip-2-dont.webp` | 1:1 | **Face in shadow.** Window behind; face dark, eyes hard to see. |
| `tip-3-do.webp` | 1:1 | **Clear lenses.** Glasses with no reflection; iris visible. |
| `tip-3-dont.webp` | 1:1 | **Glare on glasses.** A bright glare patch covering one lens. |

## Not an illustration

`example-recording.json` is the real run drawn under "What we measure": a de-identified copy of one session (`test`, `mode`, `metrics` and `raw` only, with no profile or timestamp). `renderRecording()` in `launcher_web/app.js` draws it with `report.js`'s own charts.
