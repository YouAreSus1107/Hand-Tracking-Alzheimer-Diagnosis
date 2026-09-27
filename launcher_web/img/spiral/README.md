# Spiral tracing illustrations

These are the pictures for the Spiral tracing page (`#page-spiral` in `launcher_web/index.html`). Each `.art-slot` placeholder names its file in `data-art`, and hovering over it shows the brief below. To drop a picture in, replace the slot's `<div class="slot-ph">…</div>` with `<img src="img/spiral/<name>.webp" alt="…">` and add the alt text's Chinese to `launcher_web/i18n.zh.js`.

The art direction is shared across every test. It is written out in `launcher_web/img/tapping/README.md`: flat vector, token colours only, the same older gender-neutral character, a glyph on every ✓/✕, and no words in the art.

| File | Ratio | Shows |
|---|---|---|
| `step-1-get-set.webp` | 4:3 | **Point your finger.** Laptop screen showing the spiral, sitting high on the screen. The character's hand is raised with the index finger pointed at it; the whole hand fits inside the frame. |
| `step-2-practice.webp` | 4:3 | **Practice spiral.** A smaller spiral with a soft teal pace band along one stretch of it and a speed gauge beside it. Clearly marked as practice: dashed outline, no score. |
| `step-3-trace.webp` | 4:3 | **Trace from the centre.** The fingertip following the spiral outward from the centre, a fading trail behind it. No dot ahead to chase. |
| `step-4-score.webp` | 4:3 | **Your score.** Mini result card: a big smoothness number (72) with a green ✓ chip, beside a small thumbnail of the traced spiral in green. |
| `tip-1-do.webp` | 1:1 | **Hand fits.** Seated back; whole hand and fingertip inside the frame, below the spiral. |
| `tip-1-dont.webp` | 1:1 | **Hand off the bottom.** Seated too close; the palm runs off the bottom edge, red edge band and inward chevron. |
| `tip-2-do.webp` | 1:1 | **Even pace.** Dots along a spiral arc, evenly spaced: a steady speed. |
| `tip-2-dont.webp` | 1:1 | **Stop and start.** Dots bunched then gapped along the arc: rushing and pausing. |
| `tip-3-do.webp` | 1:1 | **Lit from the front.** Lamp in front; hand evenly lit. |
| `tip-3-dont.webp` | 1:1 | **Window behind.** Bright window behind; hand a dark silhouette. |

## Not an illustration

`example-recording.json` is the real run drawn under "What we measure": a de-identified copy of one session (`test`, `mode`, `metrics` and `raw` only, with no profile or timestamp). `renderRecording()` in `launcher_web/app.js` draws it with `report.js`'s own charts.
