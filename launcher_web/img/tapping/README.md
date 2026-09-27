# Finger tapping illustrations

These are the pictures for the Finger Tapping page (`#page-iiv` in `launcher_web/index.html`). Every slot on the page is an `.art-slot` placeholder whose `data-art` matches a file below. To drop a picture in, replace the slot's `<div class="slot-ph">…</div>` with `<img src="img/tapping/<name>.webp" alt="…">`. Its alt text needs a Chinese translation in `launcher_web/i18n.zh.js`, the same as every other visible string. The frame, radius and aspect ratio stay as they are.

## Art direction (applies to every image, on every test page)

- **Style:** flat vector illustration on a transparent background, or on `#0E1520`.
- **Palette:** tokens only: brand `#12A594`, interactive `#2D7FF9`, success `#22C55E`, danger `#EF4444` (✕ only), and nothing else.
- **One recurring character:** an older adult in their 60s-70s, gender-neutral, with a stylised skin tone. Hands show knuckles, not young smooth ones. The same character appears in every frame.
- **Never colour alone:** every ✓/✕ carries its glyph (UI guide §2.4).
- **No words in the art.** The page is also shown in 繁體中文. Numbers are allowed.
- **Export:** WebP, ≤ 60 kB each. The 4:3 frames are 960×720, the do/don't tiles 1:1 at 600×600.

## Files

**Delivered (2026-09-25):** everything except `step-3-paced` and `step-4-score-paced`. These are real screenshots of the tool rather than illustrations. The sources are in `assets/screenshots/finger-tapping/`, converted to WebP (960 px steps, 600 px square tiles). `step-2` is padded to 4:3 with a blurred copy of itself. Two tiles reuse step images, as asked: `tip-2-do` (lit from the front) is `get-set` and `tip-3-do` (wide taps) is `open-wide`, each cropped square.

| File | Ratio | Shows |
|---|---|---|
| `step-1-get-set.webp` | 4:3 | The laptop screen seen from the patient's side, showing a mirrored camera view with a dashed frame. The whole hand, palm to camera, sits inside it with room at every edge, and a small green ✓ chip sits in the corner. This teaches the framing gate (`core/framing.py`). Used by both modes. |
| `step-2-open-close.webp` | 4:3 | A ghosted "open" pose (thumb and index spread wide) over a solid "closed" pose (tips touching), with a curved two-headed teal arrow across the gap. This is the calibration warm-up. Used by both modes. |
| `step-3-fast.webp` | 4:3 | The hand mid-tap with three motion arcs on the index finger, showing big and fast movement. A 20 s countdown ring, three-quarters full, sits in the corner. |
| `step-3-paced.webp` | 4:3 | The hand mid-tap beside the rhythm ring (UI guide §6.3): expanding teal rings with a speaker glyph in the centre. Below them, evenly spaced beat ticks with a tap dot on each. A 30 s ring sits in the corner. |
| `step-4-score-fast.webp` | 4:3 | A mini result card like the tool's own results screen: a big "12%", a green ✓ chip, and a small sparkline of evenly spaced taps. |
| `step-4-score-paced.webp` | 4:3 | The same card reading "9%", plus a small strip of tap dots clustered tightly on the beat lines. |
| `tip-1-do.webp` / `tip-1-dont.webp` | 1:1 | ✓ The hand is centred with room at every edge. ✕ The fingers run past the frame edge, with a red edge band and an inward chevron (the tool's real `edge_alert` look). |
| `tip-2-do.webp` / `tip-2-dont.webp` | 1:1 | ✓ A lamp in front, so the hand is evenly lit. ✕ A bright window behind, so the hand is a dark silhouette. |
| `tip-3-do.webp` / `tip-3-dont.webp` | 1:1 | ✓ A wide thumb-to-index gap with a long arrow. ✕ A twitch-sized gap with a tiny arrow. This is the shallow tapping the adaptive detector has to chase. |

## Not an illustration

`example-recordings.json` holds the real run shown under "What we measure", one per mode: a de-identified copy of two sessions (the trace, taps, thresholds, beats and headline numbers, with no profile or timestamp). Big & Fast is `20260830_181304` (CV 5.1%, 26 taps) and Paced is `20260826_225134` (CV 7.4%, 28 taps). `renderRecording()` in `app.js` draws them with `report.js`'s own tapping charts (`window.tapCharts`).
