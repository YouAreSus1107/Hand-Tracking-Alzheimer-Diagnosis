# Walking test illustrations

These are the pictures for the Walking test page (`#page-gait` in `launcher_web/index.html`). Only the seated part is built so far, so every picture shows it. Each `.art-slot` placeholder names its file in `data-art`, and hovering over it shows the brief below. To drop a picture in, replace the slot's `<div class="slot-ph">…</div>` with `<img src="img/gait/<name>.webp" alt="…">` and add the alt text's Chinese to `launcher_web/i18n.zh.js`.

The art direction is shared across every test. It is written out in `launcher_web/img/tapping/README.md`: flat vector, token colours only, the same older gender-neutral character, a glyph on every ✓/✕, and no words in the art. This test is filmed side-on, so the character is drawn in profile.

| File | Ratio | Shows |
|---|---|---|
| `step-1-set-up.webp` | 4:3 | **Sit side-on to the camera.** Side view of a room: a person seated in profile on a sturdy chair, a phone or webcam on a shelf 2-3 m away at hip height, its view cone covering head to feet. |
| `step-2-right-arm.webp` | 4:3 | **Raise your right arm.** The same seated person raising their right arm straight above the head; a check mark appears. |
| `step-3-stamps.webp` | 4:3 | **Stamp each foot.** Seated, one foot lifted high with motion arcs, about to stamp down; the other foot flat. 10 s ring in the corner. |
| `step-4-sit-to-stand.webp` | 4:3 | **Stand up five times.** Three overlaid poses of the same person, arms crossed on the chest: seated, leaning forward, standing tall. A counter reads 3 of 5. |
| `tip-1-do.webp` | 1:1 | **Head to feet in view.** The whole body in the frame, with room above the head for standing up. |
| `tip-1-dont.webp` | 1:1 | **Feet cut off.** Camera too close: the feet cut off at the bottom edge; amber edge band. |
| `tip-2-do.webp` | 1:1 | **Sturdy chair, helper near.** A heavy chair with armrests against a wall; a helper standing beside it. |
| `tip-2-dont.webp` | 1:1 | **Chair on wheels.** A rolling office chair with castors, nobody nearby. |

## Not an illustration

`example-recording.json` is the real run drawn under "What we measure". None is on record yet, so the page shows a placeholder. To add one, copy a clean session from `results/` with only `test`, `mode`, `metrics` and `raw` (no profile or timestamp), then set `file` for this test in `RECORDINGS` (`launcher_web/app.js`).
