# UI Style Guide — Hand-Tracking Cognitive Screening Suite

_Last updated: 2026-07-23. **This is the single source of truth for all UI in
this project.** Every screen — the OpenCV test overlays (`finger_tapping.py`,
`spiral_test.py`, `oculomotor_test.py`, and future speech tests) and the
`launcher.py` web hub — must conform to the tokens, components, motion, and
accessibility rules here. Reference this file in every future UI design and PR._

The suite is a **clinical-grade cognitive-screening application** used by older
adults (target 50–89) and clinicians. The design language is therefore
**calm, trustworthy, uncluttered, and highly legible** — closer to a medical
device than a consumer game. When in doubt, choose clarity over decoration.

---

## 1. Design Principles

1. **Calm & clinical.** Muted, professional palette; generous whitespace; no
   visual noise competing with the camera feed or the task.
2. **Legible first.** Large type, high contrast, one primary action per screen.
   Assume presbyopia, cataracts, and low-end laptop screens in bright rooms.
3. **Guided, never guessing.** The user always knows what to do next, whether
   they're doing it right, and what happens after. Real-time, specific feedback.
4. **Trust through honesty.** Clear "not a diagnosis" framing, visible data
   handling, no dark patterns, no fake precision.
5. **Accessible by default.** WCAG 2.1 AA minimum. Never encode meaning in color
   alone. Respect reduced-motion. Offer audio and visual cues together.
6. **One system.** Every test looks and behaves like part of the same product.
   Shared tokens + components, not per-file ad-hoc styling.

---

## 2. Color System

Colors are defined as **semantic tokens**. Never hardcode a raw hex/BGR in a
screen — reference a token. Values are given as hex (web/PIL) **and** OpenCV
**BGR** tuples (note: OpenCV is B,G,R, not R,G,B).

### 2.1 Brand & interactive
| Token | Hex | BGR | Use |
|---|---|---|---|
| `brand` | `#12A594` | `(148,165,18)` | Primary brand teal — calm, medical. Logo, primary accents. |
| `brand-strong` | `#0E8577` | `(119,133,14)` | Pressed/active brand. |
| `interactive` | `#2D7FF9` | `(249,127,45)` | Primary buttons, links, focus. |
| `interactive-hover` | `#5197FB` | `(251,151,81)` | Hover state. |

### 2.2 Status (clinical semantics) — always pair with icon + label
| Token | Hex | BGR | Meaning |
|---|---|---|---|
| `success` | `#22C55E` | `(94,197,34)` | Within typical range / good signal. |
| `warning` | `#F5A524` | `(36,165,245)` | Mild / monitor / adjust. |
| `danger` | `#EF4444` | `(68,68,239)` | Elevated / follow-up / error. |
| `info` | `#38BDF8` | `(248,189,56)` | Neutral guidance. |

### 2.3 Neutrals (dark "clinical" theme — default over video)
| Token | Hex | BGR | Use |
|---|---|---|---|
| `bg` | `#0E1520` | `(32,21,14)` | App background (non-video areas). |
| `surface` | `#111827` | `(39,24,17)` | Panels/cards (draw at 72–90% alpha over video). |
| `surface-2` | `#1C2430` | `(48,36,28)` | Raised/secondary panels. |
| `border` | `#2A3442` | `(66,52,42)` | Hairline separators, panel outlines. |
| `text` | `#F8FAFC` | `(252,250,248)` | Primary text on dark. |
| `text-muted` | `#94A3B8` | `(184,163,148)` | Secondary text, captions. |
| `text-disabled`| `#64748B` | `(139,116,100)` | Disabled/hint. |

A **light theme** (for the web hub / printed reports) mirrors these: `bg #F8FAFC`,
`surface #FFFFFF`, `text #0F172A`, `text-muted #475569`, same status colors.

### 2.4 Rules
- Text over video **always** sits on a `surface` panel or has a 1–2 px dark
  shadow/outline — never bare text on the raw camera image.
- Status color is **never** the only signal: pair with an icon and a word
  (✓ "Typical", ! "Monitor", ✕ "Follow-up").
- Maintain **≥ 4.5:1** contrast for body text, **≥ 3:1** for large text/UI.

---

## 3. Typography

- **Primary typeface:** Inter (or Source Sans 3) — bundle the `.ttf`, load via
  Pillow for OpenCV rendering. **Fallback:** `cv2.FONT_HERSHEY_SIMPLEX` only if
  PIL is unavailable.
- **Numerals:** use tabular/monospaced figures for live metrics so digits don't
  jitter (Inter has tabular figures; or JetBrains Mono for big readouts).

### Type scale (px @ ~720p canvas; scale proportionally to frame height)
| Role | Size | Weight | Notes |
|---|---|---|---|
| Display (result headline, countdown) | 48–64 | Bold | Tabular figures. |
| H1 (screen title) | 32 | Semibold | |
| H2 (section) | 24 | Semibold | |
| Body-L (instructions) | 20 | Regular | **Minimum for primary instructions.** |
| Body | 18 | Regular | Never smaller for content older adults must read. |
| Caption / disclaimer | 14 | Regular | `text-muted`; secondary info only. |

- **Line length** ≤ ~50 characters for instruction blocks.
- **Line height** ~1.4× for body. Left-align paragraphs; center only short
  single lines (titles, CTAs).

---

## 4. Layout & Spacing

- **8-pt spacing scale:** 4, 8, 12, 16, 24, 32, 48. Use multiples; no arbitrary
  gaps.
- **Safe margins:** ≥ 24 px from frame edges for content; the progress bar and
  status bar own the top/bottom 48 px.
- **Panels:** rounded corners **radius 16 px**, `surface` fill at 72–90% alpha,
  1 px `border`, soft shadow (offset 0/4, blur 16, 40% black) for separation
  from video.
- **Grid:** single centered content column (max ~560 px) for instructions/results;
  full-width only for the live camera view and progress.
- **One primary action per screen**, bottom-right or centered; secondary actions
  are lower-emphasis (ghost/outline).

---

## 5. Component Library

Each component is a spec; implement once in `core/ui/components.py` and reuse.

- **Button** — height 48 px, radius 12, 16 px horizontal padding, Body weight
  Semibold. Variants: `primary` (interactive fill), `success`, `ghost`
  (transparent + border). States: default / hover (`*-hover`) / pressed
  (`*-strong`, 1 px inset) / disabled (`text-disabled`, 50% fill) / focus (2 px
  `interactive` ring). Min touch target 44×44.
- **Card / Panel** — §4 panel spec. Header (H2) + body + optional action row.
- **Status Bar (persistent top)** — hand-detected chip, signal-quality chip
  (lighting/FPS), current mode label, brand mark. Chips: pill, 28 px tall, icon
  + label.
- **Chip / Badge** — pill; status variants use status color at 18% fill + full-
  strength text + icon.
- **Progress Bar** — 8 px track (`surface-2`), rounded, fill in phase color
  (`warning` for warm-up, `success`/`brand` for scored). Show remaining time
  label above.
- **Metric Readout** — big tabular number (Display) + unit + label + status
  badge. Used in the live HUD and results.
- **Beat / Rhythm Indicator** — see §6.3.
- **Sparkline** — live line of the tap distance signal (last ~4 s), `brand`
  stroke on `surface`, 1.5 px, `LINE_AA`; a dot marks each detected tap.
- **Toast / Coach Message** — transient bottom-center pill with icon + short
  message; info/warning/success variants; auto-fade (§6). Used for real-time
  guidance instead of raw colored text.
- **Disclaimer Ribbon** — always-available "Screening tool, not a diagnosis —
  consult a healthcare professional." in Caption on `surface`.

---

## 6. Motion & Animation

Motion must feel **smooth, purposeful, and calm** — it guides attention and
confirms actions; it never merely decorates. Because OpenCV renders frame-by-
frame, "animation" = **interpolating a value by elapsed time each frame**.
Implement easing helpers in `core/ui/anim.py`.

### 6.1 Durations & easing
| Token | Duration | Easing | Use |
|---|---|---|---|
| `fast` | 120 ms | ease-out | Hover, small state flips. |
| `base` | 200 ms | ease-in-out | Panel/screen cross-fades, toasts. |
| `slow` | 320 ms | ease-in-out | Screen transitions, value count-ups. |
| `pulse` | per-beat | custom | Beat indicator (§6.3). |

Standard easing: cubic. `easeOutCubic(t) = 1-(1-t)³`;
`easeInOutCubic(t) = t<0.5 ? 4t³ : 1-((-2t+2)³)/2`. Provide `lerp(a,b,t)`.

### 6.2 Core transitions
- **Screen change:** 200 ms cross-fade of the overlay panel (alpha 0→1), content
  slides up 8 px (`base`).
- **Countdown:** each number scales `1.3→1.0` with `easeOutCubic` over 300 ms and
  fades; a ring sweeps 360°→0° across the second.
- **Value count-up (results):** animate the metric from 0 to final over `slow`
  with tabular figures so width is stable.
- **Toast:** fade+rise in over `base`, hold, fade out over `base`.

### 6.3 Beat / tap feedback (replaces the current harsh white flash)
- **Rhythm ring:** a ring at the top-center. On each beat it **expands**
  (radius ×1.0→1.25) and brightens, then relaxes back over the beat interval
  with `easeOutCubic` — a gentle "breathing" pulse the user can follow.
- **Tap confirmation:** on a detected tap, a soft `success` ring ripples outward
  from the fingertip (radius grows, alpha fades over 250 ms) and the hand
  skeleton briefly brightens — **no** full-screen white flash.
- **Border pulse:** at most a 2 px `brand` border glow at 40%→0% over 200 ms;
  disabled entirely under reduced-motion.

### 6.4 Reduced motion
Provide a `reduced_motion` setting. When on: no pulsing/rippling/parallax;
replace with instant, non-flashing state changes and static indicators. **Never
flash faster than 3 Hz** (photosensitivity safety) under any setting.

---

## 7. Indicators & Real-Time Feedback

Feedback is a first-class feature of a screening app. Always show:
- **Hand-detection state:** persistent chip — `success` ✓ "Hand detected" vs
  `warning` ! "Show your hand". If lost mid-test, a calm toast, not alarm.
- **Signal quality:** lighting/exposure + FPS chip. Warn (`warning`) if FPS < 24
  or the frame is too dark/bright to track reliably.
- **Positioning guidance:** specific, kind coaching via toasts — "Move a little
  closer", "Center your hand", "A bit more light" — driven by measured distance/
  brightness, shown *before* scoring starts.
- **Task progress:** phase label (Warm-up / Recording), time remaining, progress
  bar in phase color.
- **Performance encouragement:** brief positive reinforcement ("Nice steady
  rhythm") to keep older users at ease — sparing, never patronizing.

---

## 8. Iconography

- Simple, 2 px stroke, rounded joins, single-color (inherits token). Sizes 20/24.
- Core set: hand, check, alert-triangle, info-circle, cross, camera, sound-on/off,
  play, retry, save, export, chart/trend.
- Draw as vectors (PIL paths) or bundle a minimal SVG→raster step; avoid emoji in
  the clinical UI.

---

## 9. Accessibility Checklist (must pass)

- [ ] Body text ≥ 18 px; primary instructions ≥ 20 px.
- [ ] Contrast ≥ 4.5:1 (text), ≥ 3:1 (large text / UI components).
- [ ] Status never conveyed by color alone (icon + label always present).
- [ ] Color-blind-safe: success/warning/danger distinguishable by icon+text
      (verify in deuteranopia/protanopia simulation).
- [ ] Focus states visible for all interactive elements (2 px `interactive` ring).
- [ ] Reduced-motion mode available; no flashing > 3 Hz.
- [ ] Audio cues have a visual equivalent and vice-versa; volume/mute control.
- [ ] Touch/click targets ≥ 44×44 px.
- [ ] Every screen states the next action in plain language.

---

## 10. Voice & Copy

- **Plain language**, short sentences, second person ("Tap your finger…").
  Avoid jargon; if a clinical term is needed, gloss it once.
- **Reassuring, non-alarming.** Results use "within typical range / monitor /
  recommend follow-up", never "abnormal/failed".
- **Always include** the disclaimer: *"This is a screening tool, not a medical
  diagnosis. Please consult a healthcare professional."*
- **Neutral pronouns** for any third party; never assume the user's gender.
- Numbers carry units and, where clinical, a reference band and a one-line
  plain explanation.

---

## 11. Implementation Notes

### OpenCV overlay screens (near-term)
- Add `core/ui/theme.py` (tokens as named BGR constants + hex), `components.py`
  (the §5 widgets), `anim.py` (§6 easing/interp). Screens compose these — no raw
  `cv2.putText`/`rectangle` with literal colors in test files.
- Use **Pillow** for text (real fonts, anti-aliasing, weights); convert
  PIL↔NumPy once per frame. Use `cv2.LINE_AA` for every shape. Fake rounded rects
  via filled rect + circles at corners, or draw the panel in PIL.
- Interpolate all animated values by `now`-based elapsed time; never assume a
  fixed frame rate.

### Web hub (`launcher.py`)
- Mirror the same tokens in CSS custom properties (`--brand`, `--surface`, …) so
  the hub and the tests share one palette; use the light theme there.

### Future front-end
- If the app migrates to **PySide6/Qt** or a richer web UI, these tokens,
  type scale, components, motion, and accessibility rules carry over unchanged —
  only the rendering layer changes. Keep this file framework-neutral.

---

## 12. Quick Reference (copy for a new screen)

1. Background = video; put content on a `surface` panel (radius 16, 72–90% alpha,
   1 px `border`, shadow).
2. One H1 title, ≤ 50-char instruction lines at Body-L, one primary Button.
3. Persistent status bar (hand + quality + mode).
4. Any status uses color **+ icon + label**.
5. Animate transitions with `base`/`slow` easing; beat/tap feedback per §6.3;
   honor reduced-motion.
6. Include the disclaimer ribbon.
7. Type ≥ 18 px, contrast AA, focus rings, ≥ 44 px targets.
