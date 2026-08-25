"""Pure tapping-engine tests; no camera or MediaPipe required."""
import math
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.tapping.confidence import confidence, cv_rel_se
from core.tapping.detector import TapDetector
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

    def test_slow_run_scores_but_admits_limited_confidence(self):
        m = score([float(i) for i in range(15)], camera_fps=30)
        self.assertTrue(m["scoreable"])
        self.assertGreaterEqual(m["confidence_pct"], 45)
        self.assertLess(m["confidence_pct"], 75)

    def test_six_taps_score_five_refuse(self):
        self.assertTrue(score([0, 1, 2.1, 3, 4.2, 5])["scoreable"])
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

if __name__ == "__main__":
    unittest.main()
