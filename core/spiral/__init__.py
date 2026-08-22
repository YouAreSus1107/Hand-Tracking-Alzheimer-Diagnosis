"""
Spiral-tracing engine — pure geometry + scoring, no camera/UI (parallels
core/tapping/ and core/gaze/). See docs/SPIRAL_TEST_PLAN.md.
"""

from .geometry import (generate_spiral, generate_warmup_circle,
                       scale_spiral_to_frame, nearest_spiral_point,
                       resample_by_arclength)
from .metrics import (compute_metrics, sparc, smoothness_index, sparc_band,
                      live_smoothness_status, compute_normalized_jerk,
                      compute_velocity_cv, compute_tremor, compute_completion,
                      compute_active_ratio)

__all__ = [
    "generate_spiral", "generate_warmup_circle", "scale_spiral_to_frame",
    "nearest_spiral_point", "resample_by_arclength",
    "compute_metrics", "sparc", "smoothness_index", "sparc_band",
    "live_smoothness_status", "compute_normalized_jerk", "compute_velocity_cv",
    "compute_tremor", "compute_completion", "compute_active_ratio",
]
