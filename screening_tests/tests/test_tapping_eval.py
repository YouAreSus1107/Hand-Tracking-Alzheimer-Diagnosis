"""Offline tapping-evaluation tests; synthetic data, no video or MediaPipe."""
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np

from tools import tapping_eval as te
from tools.eval_tapping_videos import detect, mode_for, score_one


def tapping_wave(t, hz, lo=0.2, hi=1.2):
    """Distance trace that closes (reaches lo) once per cycle, at t = k/hz."""
    return lo + (hi - lo) * 0.5 * (1 - math.cos(2 * math.pi * hz * t))


def write_motive_csv(path, times, thumb, index):
    """Mimics a Motive export: metadata, a blank line, type/name/ID rows,
    a Rotation/Position row, the axis row, then data with blank occlusions."""
    lines = [
        "Format Version,1.23,Take Name,FTN1,Capture Frame Rate,120.000000",
        "",
        ",,Marker,Marker,Marker,Marker,Marker,Marker",
        ",,Hand:Thumb,Hand:Thumb,Hand:Thumb,Hand:Index,Hand:Index,Hand:Index",
        ",,1,1,1,2,2,2",
        ",,Position,Position,Position,Position,Position,Position",
        "Frame,Time (Seconds),X,Y,Z,X,Y,Z",
    ]
    for k, (t, a, b) in enumerate(zip(times, thumb, index)):
        fa = ",".join(f"{v:.6f}" for v in a) if a else ",,"
        fb = ",".join(f"{v:.6f}" for v in b) if b else ",,"
        lines.append(f"{k},{t:.6f},{fa},{fb}")
    Path(path).write_text("\n".join(lines) + "\n")


class SignalTests(unittest.TestCase):
    def test_moving_average_matches_numpy_same(self):
        rng = random.Random(1)
        v = [rng.random() for _ in range(37)]
        for n in (3, 4, 5):
            want = np.convolve(v, np.ones(n) / n, mode="same")
            got = te.moving_average(v, n)
            self.assertEqual(len(got), len(want))
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, places=12)

    def test_local_minima_spacing_keeps_deeper(self):
        sig = [5, 1, 5, 0.5, 5, 5, 5, 5, 2, 5]
        self.assertEqual(te.local_minima(sig, min_sep=3, below=4), [3, 8])

    def test_local_minima_plateau_resolves_to_middle(self):
        self.assertEqual(te.local_minima([3, 1, 1, 1, 3], 1, 2), [2])

    def test_fill_gaps(self):
        self.assertEqual(te.fill_gaps([None, 1.0, None, 3.0, None]),
                         [1.0, 1.0, 2.0, 3.0, 3.0])

    def test_parse_task(self):
        self.assertEqual(te.parse_task("master_FTN2.mp4"), ("N", 2))
        self.assertEqual(te.parse_task("FTS1.csv"), ("S", 1))
        self.assertIsNone(te.parse_task("master_OCN1.mp4"))


class MocapTests(unittest.TestCase):
    def test_reads_motive_export_and_finds_every_tap(self):
        bpm = 115.0
        hz = bpm / 60
        times = [k / te.MOCAP_FPS for k in range(int(10 * te.MOCAP_FPS))]
        thumb, index = [], []
        for k, t in enumerate(times):
            d = 0.01 + 0.08 * 0.5 * (1 - math.cos(2 * math.pi * hz * t))
            if k % 97 == 5:                       # occluded frames
                thumb.append(None)
                index.append((0.0, 0.0, 0.0))
            else:
                thumb.append((d, 0.0, 0.0))
                index.append((0.0, 0.0, 0.0))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "FTN1.csv"
            write_motive_csv(p, times, thumb, index)
            t, a, b = te.read_mocap(p)
        self.assertEqual(len(t), len(times))
        self.assertIsNone(a[5])
        dist = te.fill_gaps(te.marker_distance(a, b))
        taps = te.mocap_taps(t, dist, bpm, method="min")
        want = [k / hz for k in range(1, int(10 * hz) + 1) if k / hz < 10]
        self.assertEqual(len(taps), len(want))
        for got, w in zip(taps, want):
            self.assertLess(abs(got - w), 0.02)
        # Onset: the cosine comes within 20% of its floor at cos(phi) = 0.6,
        # i.e. acos(0.6)/(2*pi) of a period before each minimum.
        lead = math.acos(0.6) / (2 * math.pi) / hz
        onset = te.mocap_taps(t, dist, bpm)
        self.assertEqual(len(onset), len(want))
        for got, w in zip(onset, want):
            self.assertLess(abs(got - (w - lead)), 0.02)

    def test_onset_is_stable_on_a_flat_floor(self):
        # Fingers resting together: a long flat floor with sensor noise. The
        # minimum wanders across the floor; the onset must not.
        rng = random.Random(2)
        fps, period = te.MOCAP_FPS, 0.8
        times = [k / fps for k in range(int(12 * fps))]
        dist = []
        for t in times:
            ph = (t % period) / period
            # open-close hump over the first half, then the fingers rest
            # together for the second half (400 ms)
            v = 0.02 + 0.06 * math.sin(math.pi * ph / 0.5) ** 2 if ph < 0.5 else 0.02
            dist.append(v + rng.gauss(0, 0.0004))
        onset = te.mocap_taps(times, dist, 75.0)
        mins = te.mocap_taps(times, dist, 75.0, method="min")
        self.assertEqual(len(onset), len(mins))
        # 15 closures in 12 s; the last is still resting on the floor when
        # the recording ends, so it never completes a dip.
        self.assertEqual(len(onset), 14)

        def sd_iti(ts):
            iti = [b - a for a, b in zip(ts, ts[1:])]
            m = sum(iti) / len(iti)
            return math.sqrt(sum((x - m) ** 2 for x in iti) / (len(iti) - 1))
        self.assertLess(sd_iti(onset), 0.01)
        self.assertGreater(sd_iti(mins), 3 * sd_iti(onset))


class AlignmentTests(unittest.TestCase):
    def test_recovers_known_offset(self):
        hz, off = 1.6, 0.75
        rng = random.Random(3)
        # Irregular amplitude so the correlation has one clear peak rather
        # than one per metronome period.
        amp = [0.6 + 0.4 * rng.random() for _ in range(40)]

        def dist(t):
            k = int(t * hz)
            return 0.2 + amp[k % 40] * 0.5 * (1 - math.cos(2 * math.pi * hz * t))

        ref_t = [k / 120 for k in range(int(20 * 120))]
        ref_d = [dist(t) for t in ref_t]
        video = [(k / 30, dist(k / 30 + off)) for k in range(int(15 * 30))]
        got, r = te.estimate_offset(video, ref_t, ref_d)
        self.assertAlmostEqual(got, off, delta=1.5 / 120)
        self.assertGreater(r, 0.99)

    def test_matching_is_one_to_one(self):
        m = te.timing_agreement([1.00, 1.05, 2.00, 5.0], [1.02, 2.01, 3.0], 0.1)
        self.assertEqual((m["matched"], m["missed"], m["extra"]), (2, 1, 2))
        self.assertAlmostEqual(m["err_mean_ms"], -15.0)

    def test_constant_lead_is_not_booked_as_misses(self):
        # Every tap 120 ms early with +/-40 ms jitter: without removing the
        # lead, about half would fall outside a 100 ms window.
        rng = random.Random(5)
        ref = [0.8 * k for k in range(1, 26)]
        ours = [r - 0.12 + rng.uniform(-0.04, 0.04) for r in ref]
        m = te.timing_agreement(ours, ref, 0.1)
        self.assertEqual((m["matched"], m["missed"], m["extra"]), (25, 0, 0))
        self.assertAlmostEqual(m["lead_ms"], -120.0, delta=15)

    def test_read_lag(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "X01_L_lags.csv"
            p.write_text(",Task,Lag (at 120 fps)\n0,OCS1,11\n14,FTS1,26\n")
            self.assertEqual(te.read_lag(p, "FTS1"), 26)
            self.assertIsNone(te.read_lag(p, "FTF2"))
        self.assertIsNone(te.read_lag(Path(tmp) / "gone.csv", "FTS1"))

    def test_bland_altman(self):
        ba = te.bland_altman([1.0, 2.0, 3.0], [0.5, 1.5, 2.5])
        self.assertAlmostEqual(ba["bias"], 0.5)
        self.assertAlmostEqual(ba["loa_low"], 0.5)


class ValidationStatsTests(unittest.TestCase):
    """The statistics behind the HUBU-FIS patient validation."""

    def test_ranks_average_ties(self):
        self.assertEqual(te.ranks([3, 1, 3, 2]), [3.5, 1.0, 3.5, 2.0])

    def test_auc_known_cases(self):
        self.assertEqual(te.auc([5, 6], [1, 2]), 1.0)
        self.assertEqual(te.auc([1, 2], [5, 6]), 0.0)
        self.assertEqual(te.auc([3, 3], [3, 3]), 0.5)
        self.assertAlmostEqual(te.auc([2, 3], [1, 2]), 0.875)
        self.assertIsNone(te.auc([], [1]))

    def test_spearman_matches_hand_computation(self):
        # d^2 = 0+1+1+0 = 2 -> 1 - 6*2 / (4*15) = 0.8
        self.assertAlmostEqual(te.spearman([1, 2, 3, 4], [1, 3, 2, 4]), 0.8)
        self.assertAlmostEqual(te.spearman([1, 2, 3], [9, 5, 1]), -1.0)
        # ties: agrees with Pearson on average ranks
        x, y = [1, 2, 2, 3, 4], [0, 1, 1, 1, 3]
        self.assertAlmostEqual(te.spearman(x, y), te._pearson(te.ranks(x), te.ranks(y)))

    def test_cluster_bootstrap_is_seeded_and_brackets_the_estimate(self):
        rng = random.Random(1)
        rows = []
        for p in range(40):
            sev = rng.randint(0, 3)
            for hand in range(2):
                rows.append({"person": p, "x": sev + rng.gauss(0, 1), "y": sev})
        stat = lambda rs: te.spearman([r["x"] for r in rs], [r["y"] for r in rs])
        a = te.cluster_bootstrap(rows, "person", stat, n=300, seed=3)
        b = te.cluster_bootstrap(rows, "person", stat, n=300, seed=3)
        self.assertEqual(a, b)
        est, lo, hi = a
        self.assertLess(lo, est)
        self.assertLess(est, hi)
        self.assertGreater(lo, 0.3)

    def test_old_caches_serve_only_the_old_defaults(self):
        from tools.eval_tapping_videos import CACHE_VERSION, cache_matches
        old = {"version": CACHE_VERSION, "size": 10}          # no pick/max_side
        self.assertTrue(cache_matches(old, 10, "label", None))
        self.assertFalse(cache_matches(old, 10, "largest", 960))
        self.assertFalse(cache_matches(old, 11, "label", None))
        new = dict(old, pick="largest", max_side=960)
        self.assertTrue(cache_matches(new, 10, "largest", 960))
        self.assertFalse(cache_matches(new, 10, "largest", None))


class PipelineTests(unittest.TestCase):
    def _trace(self, hz, secs=20, fps=30.0, off=0.4, noise=0.02, seed=7):
        rng = random.Random(seed)
        t = [k / fps for k in range(int(secs * fps))]
        d = [tapping_wave(x + off, hz) + rng.gauss(0, noise) for x in t]
        return {"fps": fps, "frames": len(t), "t": t, "d": d,
                "label_hits": len(t)}

    def test_detector_finds_metronome_taps_at_every_speed(self):
        for speed, bpm in te.SPEED_BPM.items():
            hz = bpm / 60
            trace = self._trace(hz)
            taps, _, calibrated, _ = detect(trace, mode_for("big_and_fast", bpm))
            self.assertTrue(calibrated, speed)
            want = [k / hz - 0.4 for k in range(1, 60) if 0 < k / hz - 0.4 < 20]
            m = te.timing_agreement(taps, want, 0.15)
            self.assertGreaterEqual(m["recall"], 0.95, speed)
            self.assertGreaterEqual(m["precision"], 0.95, speed)

    def test_paced_mode_is_retuned_to_the_recording(self):
        m = mode_for("paced", 140.0)
        self.assertAlmostEqual(m.interval_s, 60 / 140)
        self.assertLess(m.min_intertap_s, 60 / 140 / 2)

    def test_score_one_end_to_end(self):
        bpm, off = 115.0, 0.9
        hz = bpm / 60
        rng = random.Random(11)
        amp = [0.7 + 0.3 * rng.random() for _ in range(60)]

        def dist(t):
            return 0.01 + 0.08 * amp[int(t * hz) % 60] * 0.5 * (
                1 - math.cos(2 * math.pi * hz * t))

        times = [k / te.MOCAP_FPS for k in range(int(22 * te.MOCAP_FPS))]
        thumb = [(dist(t), 0.0, 0.0) for t in times]
        index = [(0.0, 0.0, 0.0)] * len(times)
        vt = [k / 30 for k in range(int(20 * 30))]
        # Our 2-D trace is span-normalised, so a different scale -- which
        # the correlation must not care about.
        trace = {"fps": 30.0, "frames": len(vt), "t": vt,
                 "d": [0.2 + 12 * dist(x + off) for x in vt], "label_hits": 0}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "FTN1.csv"
            write_motive_csv(p, times, thumb, index)
            item = {"subject": "X01", "side": "Left", "speed": "N", "take": 1,
                    "bpm": bpm, "video": Path("master_FTN1.mp4"), "mocap": p}
            row = score_one(item, trace, mode_for("big_and_fast", bpm), 0.15)
        self.assertAlmostEqual(row["offset_est_s"], off, delta=2 / 120)
        self.assertGreaterEqual(row["recall"], 0.95)
        self.assertGreaterEqual(row["precision"], 0.95)
        self.assertTrue(row["scoreable_ours"] and row["scoreable_ref"])
        self.assertAlmostEqual(row["freq_hz_ours"], row["freq_hz_ref"], delta=0.05)


if __name__ == "__main__":
    unittest.main()
