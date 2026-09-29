"""Pure tapping-engine tests; no camera or MediaPipe required."""
import math
import random
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.tapping.confidence import confidence, cv_rel_se
from core.tapping.detector import TapDetector
from core.tapping import baseline
from core.tapping.gaps import label_gaps
from core.tapping.metrics import compute_metrics
from core.tapping.modes import MODES

MODE = MODES["big_and_fast"]

def score(times, **kw):
    return compute_metrics(MODE, times, [], 0.0, 15.0, **kw)

class ConfidenceTests(unittest.TestCase):
    def test_miller_table(self):
        for n in (5, 9, 18, 30, 60):
            self.assertAlmostEqual(cv_rel_se(0.15, n), math.sqrt((.5+.15**2)/n))

    def test_long_regular_run_is_high_confidence(self):
        times = [0.0]
        for i in range(75):
            times.append(times[-1] + .2 + (.01 if i % 2 else -.01))
        m = score(times, camera_fps=120)
        self.assertTrue(m["scoreable"])
        self.assertGreaterEqual(m["confidence_pct"], 75)
        self.assertEqual(m["n_intervals"], 73)

    def test_sparse_run_scores_but_admits_limited_confidence(self):
        # 2 Hz is a normal pace for this mode; 12 intervals is still thin
        # support, so confidence should land in the middle band.
        m = score([i * 0.5 for i in range(15)], camera_fps=30)
        self.assertTrue(m["scoreable"])
        self.assertGreaterEqual(m["confidence_pct"], 45)
        self.assertLess(m["confidence_pct"], 75)

    def test_ordinary_pace_is_scored_not_gated(self):
        # 1 Hz, perfectly regular. This is the centre of what real runs of
        # this test produce (observed 0.38-2.42 Hz over 75 sessions), so it
        # must be scored. A gate that rejects it rejects the whole cohort --
        # the regression this floor was retuned to fix.
        m = score([float(i) for i in range(15)], camera_fps=30)
        self.assertTrue(m["scoreable"])
        self.assertEqual(m["status"], "success")

    def test_pauses_below_the_rhythm_floor_are_not_scored(self):
        # One tap every 2.5 s: the hand is pausing between taps rather than
        # tapping, so there is no rhythm for CV% to describe.
        m = score([i * 2.5 for i in range(15)], camera_fps=30)
        self.assertFalse(m["scoreable"])
        self.assertIn("too slow to score a rhythm", m["reason"])

    def test_effort_floor_sits_under_the_real_distribution(self):
        # The floor is an absolute number precisely so it cannot drift back up
        # into the real distribution when the expected pace is retuned. Set
        # against 71 recorded runs it rejects 3, all of them 6-tap attempts
        # (two with CV% of 52 and 91) -- abandoned runs, not unhurried ones.
        # The slowest run it admits is 0.52 Hz.
        self.assertEqual(MODE.min_effort_hz, 0.5)
        self.assertLess(MODE.min_effort_hz, 0.52)
        self.assertLess(MODE.min_effort_hz, MODE.expected_rate_hz / 2)

    def test_a_clean_run_of_this_mode_can_actually_be_believed(self):
        # Ties duration_s, expected_rate_hz and the confidence saturation
        # together. A clean run performed exactly as the mode specifies -- its
        # own duration, at its own expected pace -- must clear "moderate",
        # otherwise the trial is too short to ever support its own headline
        # metric. At 15 s x 1.2 Hz it could not (~15 intervals, capped ~58%);
        # this is the guard that would have caught that.
        step = 1.0 / MODE.expected_rate_hz
        n_taps = int(MODE.duration_s * MODE.expected_rate_hz)
        times = [i * step + (0.012 if i % 2 else -0.012) for i in range(n_taps)]
        m = compute_metrics(MODE, times, [], 0.0, MODE.duration_s, camera_fps=30)
        self.assertTrue(m["scoreable"])
        self.assertGreaterEqual(m["n_intervals"], 20)
        self.assertGreaterEqual(m["confidence_pct"], 45)

    def test_debounce_does_not_follow_the_expected_pace(self):
        # Correcting expected_rate_hz to the real 1.2 Hz must not clip the
        # fastest genuine tappers -- the debounce tracks max_rate_hz instead.
        self.assertAlmostEqual(MODE.min_intertap_s, 0.1)

    def test_six_taps_score_five_refuse(self):
        self.assertTrue(score([0, 0.3, 0.63, 0.9, 1.26, 1.5])["scoreable"])
        m = score([0, 1, 2, 3, 4])
        self.assertFalse(m["scoreable"])
        self.assertEqual(m["reason"], "Only 5 taps detected - at least 6 are needed for a reliable score.")

    def test_quality_factors_penalise_tracking_continuity_and_camera(self):
        base = dict(n_intervals=20, cv_pct=15, mean_iti_ms=200, band_width_pct=10)
        good = confidence(**base, camera_fps=120)
        slow_camera = confidence(**base, camera_fps=30)
        hidden = confidence(**base, hand_visible_ratio=.75)
        paused = confidence(**base, rejected_frac=.15)
        self.assertLess(slow_camera["factors"]["timing"], good["factors"]["timing"])
        self.assertLess(hidden["factors"]["tracking"], 1)
        self.assertLess(paused["factors"]["continuity"], 1)

    def test_near_miss_diagnostic(self):
        d = TapDetector(0.1, 1.0, 0.1, 1.0)
        for i, value in enumerate((.8, .55, .50, .55, .7)):
            d.update(i / 30, value)
        self.assertEqual(d.tap_times, [])
        self.assertEqual(d.near_miss, 1)
        m = score([], near_miss=2)
        self.assertIn("too shallow", m["reason"])

    def test_compat_window_matches_a_truncated_run(self):
        times = [i * .25 + (.015 if i % 3 == 0 else 0) for i in range(61)]
        full = score(times)
        short_times = [t for t in times if t <= 10]
        short = compute_metrics(MODE, short_times, [], 0, 10)
        self.assertEqual(full["taps_w10"], len(short_times))
        self.assertAlmostEqual(full["cv_pct_w10"], short["cv_pct"])

class AdaptiveThresholdTests(unittest.TestCase):
    """The warm-up records a wide-open hand; real tapping is a smaller motion
    and shrinks further over the trial. Frozen thresholds silently drop the
    shallow half of a run, and a dropped tap merges two intervals into a
    double-length one -- which inflates CV% far more than the missing tap does.
    """

    FPS, D_CLOSED, D_OPEN = 30.0, 0.15, 1.15

    def _run(self, amp_at, *, adaptive, rate=2.0, seconds=15.0, noise=0.0):
        rng = random.Random(4)
        det = TapDetector(0.5 / 5.0, 0.6, self.D_CLOSED, self.D_OPEN,
                          adaptive=adaptive)
        for i in range(int(seconds * self.FPS)):
            t = i / self.FPS
            amp = amp_at(t / seconds)
            d = self.D_CLOSED + amp * (0.5 - 0.5 * math.cos(2 * math.pi * rate * t))
            det.update(t, d + (rng.gauss(0, noise) if noise else 0.0))
        return det

    def test_constant_amplitude_is_unchanged_by_adaptation(self):
        """Adaptation must not move an answer that was already right."""
        frozen = self._run(lambda f: 1.0, adaptive=False)
        adaptive = self._run(lambda f: 1.0, adaptive=True)
        self.assertEqual(frozen.tap_times, adaptive.tap_times)

    def test_decaying_amplitude_no_longer_drops_taps(self):
        """The reported failure: excursion fades over the run, and the frozen
        threshold stops registering the later, shallower taps."""
        decay = lambda f: 1.0 - 0.55 * f
        frozen = self._run(decay, adaptive=False, noise=0.03)
        adaptive = self._run(decay, adaptive=True, noise=0.03)
        self.assertLess(len(frozen.tap_times), 26)      # taps silently lost
        self.assertGreaterEqual(len(adaptive.tap_times), 30)

    def test_small_excursion_run_is_scoreable_at_all(self):
        """Some participants never open wide, so every tap sits above a
        threshold derived from the warm-up: the frozen detector sees one tap."""
        small = lambda f: 0.30
        self.assertLessEqual(len(self._run(small, adaptive=False).tap_times), 1)
        self.assertGreaterEqual(len(self._run(small, adaptive=True).tap_times), 28)

    def _wobbling(self, adaptive, noise, seed, rate=2.0, seconds=15.0):
        """Decaying excursion plus a slight rhythm wobble, so the threshold
        crossings scatter and taps are dropped intermittently rather than only
        at the end -- the pattern behind the double-length interval seen in a
        real recording."""
        rng = random.Random(seed)
        det = TapDetector(0.5 / 5.0, 0.6, self.D_CLOSED, self.D_OPEN,
                          adaptive=adaptive)
        for i in range(int(seconds * self.FPS)):
            t = i / self.FPS
            amp = 1.0 - 0.55 * (t / seconds)
            phase = rate * t + 0.02 * math.sin(2.7 * t)
            d = self.D_CLOSED + amp * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
            det.update(t, d + rng.gauss(0, noise))
        return compute_metrics(MODE, det.tap_times, det.series, 0.0, seconds)

    def test_dropped_taps_make_the_verdict_unstable(self):
        """The headline harm. The true rhythm is identical across these seeds --
        only the sensor noise differs -- so a detector worth trusting returns
        near-identical CV%. Dropping taps intermittently merges intervals and
        swings the reading across the whole scale, which is how a healthy run
        lands on 'recommend follow-up'."""
        seeds = (11, 12, 13, 14, 15)
        frozen = [self._wobbling(False, 0.05, s)["cv_pct"] for s in seeds]
        adaptive = [self._wobbling(True, 0.05, s)["cv_pct"] for s in seeds]
        self.assertGreater(max(frozen) - min(frozen), 10.0)
        self.assertLess(max(adaptive) - min(adaptive), 2.0)
        # Frozen crosses into the follow-up band on noise alone; adaptive never.
        self.assertGreater(max(frozen), MODE.cv_monitor)
        self.assertLess(max(adaptive), MODE.cv_typical)

    def test_contiguous_losses_cost_taps_rather_than_cv(self):
        """The quieter failure: when the excursion fades smoothly the misses
        bunch at the end, so CV% still looks fine while a fifth of the run --
        and the decrement signal that lives in it -- is simply gone."""
        decay = lambda f: 1.0 - 0.55 * f
        frozen = self._run(decay, adaptive=False, noise=0.03)
        adaptive = self._run(decay, adaptive=True, noise=0.03)
        self.assertLessEqual(len(frozen.tap_times), 25)
        self.assertGreaterEqual(len(adaptive.tap_times), 30)

    def _still(self, adaptive, level, noise, seed=9):
        rng = random.Random(seed)
        det = TapDetector(0.5 / 5.0, 0.6, self.D_CLOSED, self.D_OPEN,
                          adaptive=adaptive)
        for i in range(int(15.0 * self.FPS)):
            det.update(i / self.FPS, level + rng.gauss(0, noise))
        return det

    def test_still_hand_never_manufactures_taps(self):
        """What the range floor exists for. With nothing moving, the envelope
        must not collapse onto the noise and start scoring jitter as tapping --
        adaptation may never invent a tap the frozen detector would not also
        have seen. (A hand held closed latches one crossing either way; that is
        the threshold doing its job, not the envelope.)"""
        for level in (1.10, 0.60, 0.16):
            for noise in (0.01, 0.03, 0.05):
                frozen = self._still(False, level, noise)
                adaptive = self._still(True, level, noise)
                where = f"level={level} noise={noise}"
                self.assertLessEqual(len(adaptive.tap_times),
                                     len(frozen.tap_times), where)
                self.assertLessEqual(len(adaptive.tap_times), 1, where)


class BlackoutTests(unittest.TestCase):
    """Pauses for a hand out of frame (core/framing.py): the interval that
    spans a pause is not a real interval and must not reach CV%."""

    def steady(self, n=30, iti=0.4):
        return [1.0 + i * iti for i in range(n)]

    def test_no_blackouts_changes_nothing(self):
        t = self.steady()
        self.assertEqual(score(t), score(t, blackouts=None))
        self.assertEqual(score(t), score(t, blackouts=[]))

    def test_interval_spanning_a_pause_is_dropped(self):
        t = self.steady()
        # a detector-state glitch at resume: one interval comes out short
        t[15] = t[14] + 0.05
        bad = score(t)
        good = score(t, blackouts=[(t[14] - 0.01, t[15] + 0.01)])
        self.assertGreater(bad["cv_pct"], 10.0)
        self.assertLess(good["cv_pct"], 1.0)
        # the blackout reaches both taps, so their neighbours go too
        self.assertEqual(good["n_intervals"], bad["n_intervals"] - 3)

    def test_blackout_between_taps_drops_only_that_interval(self):
        t = self.steady()
        m = score(t, blackouts=[(t[10] + 0.1, t[10] + 0.2)])
        self.assertEqual(m["n_intervals"], score(t)["n_intervals"] - 1)


class ParkinsonianSignsAreScoredTests(unittest.TestCase):
    """Ragged opening size and incomplete closures are what Parkinsonian
    tapping looks like, so they must never make a run unscoreable. A gate on
    exactly these signals (near misses, amplitude CV >= 40%) was tried in
    2026-09 to stop camera tracking failures reading as "follow-up"; on the
    HUBU-FIS patient videos it withheld 11 of 26 UPDRS-3 hands. Removed."""

    @staticmethod
    def trace(times, amps):
        """Closes to 0.2 at every tap and opens by amps[k] midway."""
        series = []
        for k, (a, b) in enumerate(zip(times, times[1:])):
            series += [(a, 0.2), ((a + b) / 2, 0.2 + amps[k])]
        return series + [(times[-1], 0.2)]

    def test_wildly_varying_opening_still_gets_a_verdict(self):
        t = [1.0 + i * 0.5 for i in range(30)]
        amps = [0.15 if k % 2 else 1.0 for k in range(len(t))]
        m = compute_metrics(MODE, t, self.trace(t, amps), 0.0, 20.0)
        self.assertGreaterEqual(m["amplitude_cv_pct"], 40.0)
        self.assertTrue(m["scoreable"])
        self.assertIsNotNone(m["cv_pct"])

    def test_many_incomplete_closures_still_get_a_verdict(self):
        t = [1.0 + i * 0.5 for i in range(30)]
        m = compute_metrics(MODE, t, self.trace(t, [0.8] * len(t)), 0.0, 20.0,
                            near_miss=10)
        self.assertTrue(m["scoreable"])

    def test_irregular_rhythm_is_flagged(self):
        rng = random.Random(4)
        t = [1.0]
        for _ in range(29):
            t.append(t[-1] + 0.5 * min(3.0, max(0.6, math.exp(rng.gauss(0, 0.45)))))
        m = compute_metrics(MODE, t, self.trace(t, [0.8] * len(t)), 0.0, t[-1] + 0.5)
        self.assertTrue(m["scoreable"])
        self.assertGreater(m["cv_pct"], 25.0)
        self.assertEqual(m["status"], "danger")


class MissedTapTests(unittest.TestCase):
    """One missed tap is forgiven; pauses and partial closures never are
    (core/tapping/gaps.py)."""

    LAG = 0.05      # detector fires this long before each closure's minimum

    @staticmethod
    def trace(closures, floors, peaks, fps=30.0):
        """Distance series through closure minima (time, floor) with a peak
        of the given height midway between consecutive closures."""
        knots = []
        for k, c in enumerate(closures):
            knots.append((c, floors[k]))
            if k + 1 < len(closures):
                knots.append(((c + closures[k + 1]) / 2, peaks[k]))
        out, t, j = [], closures[0], 0
        while t <= closures[-1]:
            while knots[j + 1][0] < t:
                j += 1
            (t0, d0), (t1, d1) = knots[j], knots[j + 1]
            w = (t - t0) / (t1 - t0)
            out.append((t, d0 + (d1 - d0) * 0.5 * (1 - math.cos(math.pi * w))))
            t += 1.0 / fps
        return out

    def take(self, n=30, slips=(15,), floor_at=None, pause_at=None):
        closures = [1.0 + 0.5 * k for k in range(n)]
        floors = [0.2] * n
        peaks = [1.0] * (n - 1)
        for k in slips:                      # hand only half re-opens around k
            peaks[k - 1] = peaks[k] = 0.45
        if floor_at is not None:
            floors[floor_at] = 0.6          # that closure never reaches the floor
        if pause_at is not None:            # no closure at all: hold open
            floors[pause_at] = 1.0
            peaks[pause_at - 1] = peaks[pause_at] = 1.0
        series = self.trace(closures, floors, peaks)
        missed = set(slips) | ({floor_at} if floor_at is not None else set())             | ({pause_at} if pause_at is not None else set())
        taps = [c - self.LAG for k, c in enumerate(closures) if k not in missed]
        return compute_metrics(MODE, taps, series, 0.0, closures[-1] + 0.5), taps, series

    def test_one_missed_full_closure_is_forgiven(self):
        m, _, _ = self.take()
        self.assertEqual(m["missed_tap_forgiven"], 1)
        self.assertGreater(m["cv_pct_unrepaired"], 12.0)
        self.assertLess(m["cv_pct"], 3.0)
        self.assertEqual(m["status"], "success")
        self.assertEqual(m["interruptions"], 0)

    def test_two_slips_are_a_pattern_not_a_slip(self):
        m, _, _ = self.take(slips=(10, 20))
        self.assertEqual(m["missed_tap_forgiven"], 0)
        self.assertEqual(m["cv_pct"], m["cv_pct_unrepaired"])

    def test_partial_closure_is_never_forgiven(self):
        m, taps, series = self.take(slips=(), floor_at=15)
        self.assertEqual(m["missed_tap_forgiven"], 0)
        kinds = [k for _, _, k in label_gaps(taps[MODE.trim_taps:], series)]
        self.assertEqual(kinds, ["partial_closure"])
        self.assertEqual(m["interruptions"], 1)

    def test_pause_is_never_forgiven(self):
        m, taps, series = self.take(slips=(), pause_at=15)
        self.assertEqual(m["missed_tap_forgiven"], 0)
        self.assertEqual([k for _, _, k in label_gaps(taps[MODE.trim_taps:], series)], ["pause"])
        self.assertEqual(m["interruptions"], 1)

    def test_forgiveness_moves_the_verdict_one_band_at_most(self):
        # In a short run one doubled interval reads Follow-up; restoring it
        # would read Typical. That jump rests on the inference alone.
        m, _, _ = self.take(n=11, slips=(6,))
        self.assertEqual(m["cv_pct_unrepaired"], m["cv_pct"])
        self.assertEqual(m["status"], "danger")
        self.assertEqual(m["missed_tap_forgiven"], 0)

    def test_no_series_means_no_repair(self):
        _, taps, _ = self.take()
        m = compute_metrics(MODE, taps, [], 0.0, 16.0)
        self.assertEqual(m["missed_tap_forgiven"], 0)
        self.assertEqual(m["interruptions"], 0)


class BaselineTests(unittest.TestCase):
    """Own-baseline comparison (core/tapping/baseline.py)."""

    @staticmethod
    def rows(n=14, days=4, rate=1.6, conf=70, pid="p1", hand="left", opening=0.8,
             camera="Cam A"):
        """index.csv-style rows: every value a string, as csv.DictReader gives."""
        out = []
        for k in range(n):
            out.append({"timestamp": f"2026-09-{10 + k % days:02d}T10:{k:02d}:00",
                        "profile_id": pid, "hand": hand, "mode": "big_and_fast",
                        "scoreable": "True", "frequency_hz": str(rate),
                        "confidence_pct": str(conf), "amplitude_mean": str(opening),
                        "camera_name": camera})
        return out

    def cmp(self, rows, rate, conf=70, opening=None, camera=None, pid="p1"):
        prior = baseline.eligible(rows, pid, "left", "big_and_fast")
        return baseline.compare(prior, rate, conf, opening, camera)

    def test_no_profile_no_baseline(self):
        self.assertEqual(baseline.eligible(self.rows(), None, "left", "big_and_fast"), [])
        self.assertIsNone(self.cmp(self.rows(), 0.5, pid="")["rate_vs_usual"])

    def test_needs_enough_runs_and_days(self):
        self.assertIsNone(self.cmp(self.rows(n=9), 0.5)["rate_vs_usual"])
        self.assertIsNone(self.cmp(self.rows(n=20, days=2), 0.5)["rate_vs_usual"])
        self.assertIsNotNone(self.cmp(self.rows(n=14, days=4), 1.6)["rate_vs_usual"])

    def test_low_confidence_runs_are_not_learned_from(self):
        rows = self.rows(conf=30)
        self.assertEqual(baseline.eligible(rows, "p1", "left", "big_and_fast"), [])

    def test_other_hands_and_people_do_not_mix(self):
        rows = self.rows(hand="right") + self.rows(pid="p2")
        self.assertEqual(baseline.eligible(rows, "p1", "left", "big_and_fast"), [])

    def test_one_slow_run_is_not_enough(self):
        # the previous 4 runs are normal, so the 5-run median barely moves
        m = self.cmp(self.rows(n=16), 0.5)
        self.assertEqual(m["slower_than_usual"], 0)

    def test_a_sustained_halving_is_flagged(self):
        rows = self.rows(n=14) + [dict(r, frequency_hz="0.8", timestamp=f"2026-09-20T1{k}:00:00")
                                  for k, r in enumerate(self.rows(n=4))]
        m = self.cmp(rows, 0.8)
        self.assertAlmostEqual(m["rate_vs_usual"], 0.5, places=3)
        self.assertEqual(m["slower_than_usual"], 1)

    def test_opening_needs_the_same_camera(self):
        rows = self.rows(n=16)
        self.assertIsNotNone(self.cmp(rows, 1.6, opening=0.8, camera="Cam A")["opening_vs_usual"])
        self.assertIsNone(self.cmp(rows, 1.6, opening=0.8, camera="Cam B")["opening_vs_usual"])

    def test_the_verdict_only_ever_moves_up_to_monitor(self):
        """The rule in finger_tapping._compare_with_usual, replayed on results."""
        for status in ("success", "warning", "danger"):
            r = {"scoreable": True, "status": status, "label": "x", "slower_than_usual": 1}
            if r["slower_than_usual"] and r["status"] == "success":
                r["status"], r["label"] = "warning", baseline.SLOWER_LABEL
            self.assertEqual(r["status"], {"success": "warning"}.get(status, status))

    def test_shrinking_openings_is_reported(self):
        t = [1.0 + 0.5 * i for i in range(30)]
        amps = [1.0 - 0.02 * i for i in range(len(t))]
        series = []
        for k, (a, b) in enumerate(zip(t, t[1:])):
            series += [(a, 0.2), ((a + b) / 2, 0.2 + amps[k])]
        series.append((t[-1], 0.2))
        m = compute_metrics(MODE, t, series, 0.0, 16.0)
        self.assertLess(m["opening_shrink_ratio"], 0.7)
        self.assertEqual(m["status"], "success")        # information only


if __name__ == "__main__":
    unittest.main()
