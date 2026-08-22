# FPS Investigation Plan (temporary)

> **Status:** investigation-only. No engine/detector/metric changes are made
> from this document — those fixes stay *held* until the bottleneck is localized
> by measurement. Delete this file once the finding lands in code + commit
> message.

## Why this exists

The Big & Fast tapping test runs at **~16 fps** (measured 61–62 ms/frame across
the last three sessions — only ~7–8 samples per tap cycle). That low rate is a
primary driver of the inflated CV%:

- It puts a **~5% CV floor** under every run from pure timing quantization
  (each tap edge snaps to a ~62 ms frame boundary).
- More importantly, it **undersamples the brief re-open between fast taps**, so
  the detector's hysteresis re-arm threshold isn't reached and taps are silently
  dropped — producing ~2× inter-tap intervals. One such dropped tap (a 908 ms
  gap) spiked session `20260723_211144` from a true ~8% to **19%**.

**Key signal: Task Manager shows ~40% CPU during the test.** The pipeline is
**not compute-bound** — the single-threaded loop is spending most of each frame
*waiting*, most likely on the camera.

Two code facts narrow the search:

- At 16 fps, `preprocess_for_mediapipe(frame, enable=self.fps >= 20)`
  (`screening_tests/finger_tapping.py:172`) is **already bypassed** — CLAHE +
  sharpen is *not* the current bottleneck and is ruled out.
- `open_capture` (`core/camera.py:33`) sets only width/height. It never sets
  `CAP_PROP_FOURCC` (MJPG) or `CAP_PROP_FPS`, and uses OpenCV's default Windows
  backend (**MSMF**).

**Environment (confirmed):** built-in laptop webcam, bright / well-lit room →
auto-exposure fps throttling is effectively ruled out.

## Ranked hypotheses (confirm/refute — do not assume)

| # | Hypothesis | Prior | How the 40%-CPU clue bears on it |
|---|------------|-------|----------------------------------|
| H1 | **Camera format + backend cap.** MSMF + no MJPG/FPS request → cam delivers uncompressed YUY2/NV12 at a driver-capped ~15 fps. | Highest | Matches exactly: cam-limited read, CPU idle. |
| H2 | **Synchronous loop coupling.** `read → detect → compose → imshow → waitKey` all on one thread (`finger_tapping.py:521–579`). | High | Serialization wastes wall-clock even if the cam can do 30. |
| H3 | **MediaPipe inference cost.** `detect_for_video` on CPU is synchronous; ~40 ms/frame alone caps ~16 fps. | Medium | 40% total CPU argues *against* dominance — but measure it. |
| H4 | **PIL `Canvas.compose()` render.** Full-frame overlay composite every frame. | Med-low | — |
| H5 | `imshow` / `waitKey(5)` + window overhead. | Low | — |

## Investigation steps

Scratch scripts live in the session scratchpad (not the repo). Venv interpreter:
`.venv/Scripts/python`.

### A. Per-stage frame-time instrumentation — **do first** (localizes the bottleneck)
Time each stage of the real loop with `time.perf_counter()`: `read` (`cap.read`),
`flip`, `detect` (`detect_hand`), `render` (`Canvas` build + `compose`), `show`
(`imshow` + `waitKey`). Print rolling averages or write a scratch CSV. Run a 10 s
Big & Fast session.
- **Decision:** the stage that dominates the ~62 ms budget is the bottleneck.
  `read` → H1/H2 · `detect` → H3 · `render` → H4.

### B. Camera capability probe (independent of the app) — tests H1
Open the built-in cam and, for each backend (`cv2.CAP_MSMF`, `cv2.CAP_DSHOW`),
report `CAP_PROP_FPS`, current `FOURCC`, and **measured** read fps over ~200
frames at 640×480. Repeat after setting `FOURCC=MJPG` and `CAP_PROP_FPS=30`.
- **Decision:** if MJPG and/or DSHOW measures ~30 fps while the default measures
  ~15, H1 is confirmed and the fix is a capture-config change in `open_capture`.

### C. Inference-only timing — tests H3
Loop that does only `cap.read()` + `landmarker.detect_for_video()` (no render, no
UI). Print mean / 95p inference ms.
- **Decision:** > ~45 ms → H3 is a real cap (evaluate GPU delegate / lighter
  model). < ~25 ms → H3 is minor.

### D. Render-only timing — tests H4
Time `Canvas(frame)` build + `c.compose()` per frame in isolation.
- **Decision:** > ~20 ms/frame → the PIL overlay is a meaningful share.

### E. Threaded-capture spike (only if A/B show read-wait dominates) — tests H2
Prototype a background reader thread that always holds the latest frame so the
main loop never blocks on `cap.read()`. Measure loop fps.
- **Decision:** if fps rises materially with a threaded reader even when the cam
  can deliver 30, H2 (serialization) is a confirmed co-factor.

## Outcomes → held fixes (documented, deferred)

| Confirmed | Candidate remedy (not yet applied) | Where |
|-----------|-----------------------------------|-------|
| H1 | Set `CAP_PROP_FOURCC=MJPG`, request `CAP_PROP_FPS=30`, try `CAP_DSHOW` backend | `core/camera.py` `open_capture` |
| H2 | Threaded frame grabber feeding the loop | `finger_tapping.py` run loop |
| H3 | GPU delegate / model-complexity / resolution trade-off | `App.__init__` landmarker options |
| H4 | Throttle/skip overlay redraws; cache static layers | `core/ui/components.py` |
| — | Detector/metric hardening (re-arm threshold, 2×-median missed-tap handling) as a *second* layer once fps is raised | `core/tapping/detector.py`, `metrics.py` |

## Findings (measured 2026-07-23, built-in laptop webcam, well-lit room)

Instrumented with a scratch script (`.venv/Scripts/python`) mirroring the real
per-frame pipeline; stages timed with `time.perf_counter()`, first 15 frames
dropped as warm-up, means over ~120–150 frames at 640×480.

- **B. Camera probe — H1 REFUTED.** Raw `cap.read()` measures **~30 fps on both
  backends** with only width/height set (no MJPG/FPS request):
  - MSMF: `prop_fps=30`, measured **30.0 fps**
  - DSHOW: `prop_fps=-1`, fourcc `YUY2`, measured **29.6 fps**
  - Requesting `FOURCC=MJPG`+`FPS=30` changed nothing (fourcc stayed `YUY2` on
    DSHOW — this cam offers no MJPG mode; MSMF reports an internal subtype enum,
    not a real FOURCC). **The camera is not format-capped at 15 fps.** The plan's
    premise that the loop is "waiting on the camera" is wrong — raw read is 30 fps.

- **C. Inference-only — the long pole, and highly variable.** `detect_for_video`
  alone: **mean 12.6 ms** (median 11.8, 95p 18.7) on a quiet CPU, but a second
  run minutes later measured **mean 46 ms** (95p 73). Inference cost swings ~4×
  with background CPU load. It is still the single largest per-frame term.

- **D. Render-only — H4 REFUTED.** `Canvas` build + `status_bar` + `compose()`:
  **mean 3.2 ms** (95p 4.6). The PIL overlay is negligible.

- **A. Per-stage full pipeline — `detect` dominates.** Two sessions, backend
  varied:

  | run | read | flip | detect | render | show | total | fps |
  |-----|------|------|--------|--------|------|-------|-----|
  | MSMF (system busy) | 15.7 | 0.4 | **57.9** | 9.8 | 13.3 | 97.0 | 10.3 |
  | DSHOW (settled)    | 7.8  | 0.2 | **15.8** | 3.2  | 6.3  | 33.3 | 30.1 |
  | DSHOW (confirm)    | 4.9  | 0.2 | **26.4** | 4.8  | 8.1  | 44.3 | 32.1 |
  | MSMF (confirm)     | 2.3  | 0.2 | **20.4** | 3.6  | 11.4 | 38.0 | 29.8 |

  `detect` is the largest term in **every** run. `read` is 2–16 ms, `render`
  3–10 ms, `show` 6–13 ms — none dominate.

- **E. Threaded capture — NOT RUN (precondition not met).** Step E is gated on
  read-wait dominating; it does not (read ≤16 ms). A threaded grabber would only
  claw back the read term, not the `detect` long pole, so it is at best a minor
  co-factor (H2 downgraded).

- **Backend (MSMF vs DSHOW) is a secondary factor, not the cause.** Run 1 showed
  a dramatic MSMF 10.3 fps → DSHOW 30.1 fps delta, but the **reversed-order
  confirmation run put MSMF at 29.8 fps** — MSMF is not inherently slow. The
  first-run MSMF collapse was CPU contention (MediaFoundation decode threads
  competing with inference during a camera-heavy moment), the same contention
  that inflates isolated inference from 12 → 46 ms. DSHOW does consistently cut
  read latency (~16 → ~5–8 ms) and avoids the worst MSMF spikes, so it is a cheap
  worthwhile win — but it is **not** a reliable standalone 3× fix.

- **Conclusion / dominant stage: `detect` (MediaPipe CPU inference) — H3
  CONFIRMED.** The pipeline is inference-latency-bound, not camera-bound. On a
  quiet CPU the full loop reaches ~30 fps; the ~16 fps field sessions come from
  inference stretching to 40–58 ms under CPU contention (consistent with the
  ~40% total CPU: a single inference graph doesn't saturate all cores, but it is
  the per-frame long pole and stalls whenever other threads compete). H1
  (camera-format cap) and H4 (render) are refuted; H2 (read serialization) is a
  minor co-factor at most.

  **Held fixes, in priority order (deferred — no engine change in this doc):**
  1. **Cut/stabilize inference cost (H3):** GPU delegate (`BaseOptions.delegate
     = GPU`) or a lighter `hand_landmarker` model — the only remaining levers on
     the dominant stage. ~~Lower the MediaPipe input resolution~~ **← ruled out,
     see follow-up below.**
  2. **Switch capture to DSHOW on Windows** in `core/camera.open_capture` — cheap
     read-latency + contention win.
  3. Detector/metric hardening (re-arm threshold, 2×-median missed-tap handling)
     as a second layer once fps is raised, per the table above.

## Implementation follow-up (measured 2026-07-23, during the optimization pass)

- **Input-resolution downscaling does NOTHING for inference — ruled out.** An
  interleaved A/B (same landmarker, same load, alternating frames) fed detect
  inputs of 640 / 480 / 320 / 224 px width: median `detect` was **41 ms at every
  size** (640→224 speedup **1.00×**; mean even rose slightly at 224 from the
  extra resize). MediaPipe resizes internally to the model's fixed input, so the
  CNN cost is resolution-independent. The plan's "downscale the detect frame"
  lever was implemented, measured, and **reverted** — it is a no-op and smaller
  inputs only risk missing farther/smaller hands.
- **DSHOW backend landed** in `core/camera.open_capture` (DSHOW→MSMF fallback,
  test-read verified, best-effort MJPG + `BUFFERSIZE=1`); `hand_tracking.py` now
  opens through it too. Confirmed selected at runtime; read latency **15.7 → 0.4
  ms**. This is the only effective *code* lever and reliably reaches ~30 fps
  **when the CPU is otherwise free**.
- **The residual limiter is ambient CPU load, not code.** With ~45 % system CPU
  busy from other processes during this pass, `detect` stretched to ~42 ms
  (~16 fps) even on DSHOW with everything else near-zero — matching the H3
  contention story. Holding 30 fps under load needs GPU inference (declined /
  unsupported on this Windows box) or a lighter model; no capture-side change can
  overcome it.

## Verification / done criteria — MET

Dominant stage named (**`detect` / MediaPipe inference**) and a measured-fps
delta recorded from an isolated change (MSMF-default **10.3 fps** → DSHOW-default
**30.1 fps** in run 1; read latency 15.7 → 0.4 ms) — with the reversed-order
confirmation clarifying that the *stage*, not the backend, is the true cause, and
the follow-up A/B proving input resolution is not a lever. DSHOW backend applied;
resolution downscale ruled out and reverted.
