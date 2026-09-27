"""
Spiral progress tracking (pure) -- how far along the spiral the fingertip has
honestly traced, and its radial deviation from the ideal curve.

Progress used to be the furthest *nearest template point* ever reached. The
arms are only 2*pi*b apart (~55 px at 640x480), so a fingertip that drifted
half a gap outward was suddenly nearest the next arm and progress leapt a whole
turn, never to come back: a skipped layer, and sometimes a run that ended early
at the rim.

Here progress follows the **swept angle** about the centre instead. The angle
is continuous, so the only way to be a turn further is to go round once.
Progress advances to the spiral point at that angle only while the fingertip
is radially on its own arm (|r - b*theta| under half the arm gap); drifting
off the arm freezes progress rather than jumping it.

A fingertip speed check was considered as the main guard and rejected: a layer
skip is usually a slow drift of ~30 px, and only the *index* leaps. Speed is
kept as a second guard for what it does catch -- single-frame tracking
teleports -- which are counted and not allowed to move the angle.

The deviation is the same swept-angle radial error the run has always scored
(mean_dev_pct), expressed as a percentage of the outer radius.
"""

from __future__ import annotations

import math

ANGLE_MIN_RADIUS = 18.0      # px: angle about the centre is unstable inside this
ARM_GATE_FRAC = 0.5          # on-arm tolerance, as a fraction of the arm gap
MAX_TIP_SPEED_RADII_S = 6.0  # faster than this (outer radii / s) is a glitch
MAX_GLITCH_RUN = 3           # this many in a row is a real move, not a glitch


def _arc(b: float, theta: float) -> float:
    """Arc length of r = b*theta from 0 to theta (closed form)."""
    return 0.5 * b * (theta * math.sqrt(1.0 + theta * theta) + math.asinh(theta))


class SpiralProgress:
    """Feed it raw fingertip positions; read back deviation and progress.

    `n_points` is the length of the arc-length-resampled template (see
    geometry.generate_spiral), so `max_idx` indexes those points directly."""

    def __init__(self, center, b: float, turns: float, n_points: int):
        self.cx, self.cy = center
        self.b = b
        self.theta_max = turns * 2 * math.pi
        self.n = n_points
        self.radius = b * self.theta_max
        self._arc_max = _arc(b, self.theta_max) if b > 0 else 0.0
        self.gate_px = ARM_GATE_FRAC * 2 * math.pi * b
        self.theta = 0.0             # swept angle (unwrapped)
        self.max_idx = 0             # furthest point honestly reached
        self.glitch_frames = 0
        self.off_arm_frames = 0
        self._prev_angle = None      # last raw angle, for unwrapping
        self._resync = False         # next angle snaps to the nearest wrap
        self._last = None            # (t, x, y) of the last accepted frame
        self._glitch_run = 0

    # ── helpers ────────────────────────────────────────────────────────────
    def index_at(self, theta: float) -> int:
        """Template index of the spiral point at swept angle theta."""
        if self._arc_max <= 0 or self.n < 2:
            return 0
        theta = max(0.0, min(self.theta_max, theta))
        return int(round(_arc(self.b, theta) / self._arc_max * (self.n - 1)))

    def _pct(self, dev_px: float) -> float:
        return dev_px / self.radius * 100.0 if self.radius > 1e-6 else 0.0

    def reset_angle(self):
        """Hand lost: forget the last angle and position. The next frame snaps
        to the wrap of its angle nearest the swept angle so far (within half a
        turn either way), which recovers what was swept out of view without
        ever being able to land on a different arm."""
        self._prev_angle = None
        self._resync = self.theta != 0.0
        self._last = None
        self._glitch_run = 0

    @property
    def progress(self) -> float:
        return self.max_idx / max(1, self.n - 1)

    # ── per frame ──────────────────────────────────────────────────────────
    def update(self, fx: float, fy: float, t: float, trusted: bool = True):
        """Returns (dev_pct, max_idx, on_arm, glitch).

        trusted=False is a frame with the hand part-way out of the picture
        (core/framing.py): the fingertip is still followed round so the swept
        angle stays continuous, but the frame cannot advance progress. When
        the whole hand is back, progress catches up to wherever the finger is
        -- provided it is on the right arm -- so a patient can carry on past a
        stretch the camera could not see without getting stuck.
        Contrast reset_angle(), for a hand not detected at all."""
        dx = fx - self.cx
        dy = self.cy - fy                # screen y is inverted vs. spiral math
        r = math.hypot(dx, dy)

        # Speed guard: a step no hand could make is a tracking glitch. It is
        # measured against the last accepted frame, and a run of them is taken
        # as real (the hand really did move while tracking was poor).
        if self._last is not None and self.radius > 0:
            lt, lx, ly = self._last
            dt = t - lt
            if dt > 0 and (math.hypot(fx - lx, fy - ly) / dt
                           > MAX_TIP_SPEED_RADII_S * self.radius):
                self._glitch_run += 1
                if self._glitch_run < MAX_GLITCH_RUN:
                    self.glitch_frames += 1
                    dev = abs(r - self.b * max(self.theta, 0.0))
                    return self._pct(dev), self.max_idx, dev < self.gate_px, True
                self.reset_angle()
        self._glitch_run = 0
        self._last = (t, fx, fy)

        if r < ANGLE_MIN_RADIUS:         # too near centre: angle is unstable
            self._prev_angle = None
            self._resync = self.theta != 0.0
            dev = abs(r - self.b * max(self.theta, 0.0))
            return self._pct(dev), self.max_idx, True, False

        ang = math.atan2(dy, dx)
        if self._prev_angle is None and self.theta == 0.0 and self.b > 1e-6:
            # First exit from the centre dead-zone: seed the swept angle to the
            # wrap of the fingertip's real angle nearest the ideal theta for
            # this radius. Seeding r/b alone ignored the direction the finger
            # left in, and that angular offset then biased both progress and
            # the scored deviation for the whole run.
            k = round((r / self.b - ang) / (2 * math.pi))
            self.theta = ang + 2 * math.pi * k
        elif self._prev_angle is None and self._resync:
            d = (ang - self.theta + math.pi) % (2 * math.pi) - math.pi
            self.theta += d
        elif self._prev_angle is not None:
            d = ang - self._prev_angle
            if d > math.pi:
                d -= 2 * math.pi
            elif d < -math.pi:
                d += 2 * math.pi
            self.theta += d
        self._prev_angle = ang
        self._resync = False

        dev = abs(r - self.b * max(self.theta, 0.0))
        on_arm = dev < self.gate_px
        if not trusted:
            return self._pct(dev), self.max_idx, on_arm, False
        if on_arm:
            self.max_idx = max(self.max_idx, self.index_at(self.theta))
        else:
            self.off_arm_frames += 1
        return self._pct(dev), self.max_idx, on_arm, False
