"""
Confidence primitives shared by every test's confidence module.

The tapping test established the idea (core/tapping/confidence.py): a score
computed from thin data and one computed from plenty are not the same
measurement, so each run carries an error bar and a 0-100 confidence score and
a thin-but-scoreable run gets reported instead of thrown away. The gaze test
now does the same thing (core/gaze/confidence.py) with different statistics —
a proportion rather than a CV — so the pieces that must mean the *same* thing
across tests live here.

That is the point of this module: the 75/45 level split and the band-straddle
rule are read side by side on the Analysis page, where a confidence figure from
a tapping session sits next to one from an eye session and the chart dims low-
confidence points from every test with one threshold. If the two tests drifted
apart on what "moderate" means, that view would quietly be comparing nothing.

Pure and stdlib-only. The per-test factor shaping stays in each test's own
module, because none of it generalises.
"""

from __future__ import annotations

# Level thresholds on the 0-100 score.
HIGH, MODERATE = 75.0, 45.0

Z95 = 1.959964              # normal quantile for a 95% interval


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def level_of(confidence_pct: float) -> str:
    if confidence_pct >= HIGH:
        return "high"
    if confidence_pct >= MODERATE:
        return "moderate"
    return "low"


def straddles_band(ci_low: float | None, ci_high: float | None,
                   *edges: float) -> bool:
    """True when the interval spans a band boundary -- the point estimate's
    band call is then not the only one the data supports."""
    if ci_low is None or ci_high is None:
        return False
    return any(ci_low < edge < ci_high for edge in edges)
