"""
Design tokens — single source of truth is docs/UI_STYLE_GUIDE.md.
Hex values here mirror the guide; BGR tuples are derived so the two
representations can never drift apart.
"""

from __future__ import annotations

import os

# ── Color tokens (hex, from UI_STYLE_GUIDE.md §2) ──────────────────────────
HEX = {
    # Brand & interactive
    "brand":             "#12A594",
    "brand-strong":      "#0E8577",
    "interactive":       "#2D7FF9",
    "interactive-hover": "#5197FB",
    # Status
    "success": "#22C55E",
    "warning": "#F5A524",
    "danger":  "#EF4444",
    "info":    "#38BDF8",
    # Neutrals (dark clinical theme)
    "bg":            "#0E1520",
    "surface":       "#111827",
    "surface-2":     "#1C2430",
    "border":        "#2A3442",
    "text":          "#F8FAFC",
    "text-muted":    "#B4C0D0",
    "text-disabled": "#8C9BB2",
}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


RGB = {k: _hex_to_rgb(v) for k, v in HEX.items()}
BGR = {k: (b, g, r) for k, (r, g, b) in RGB.items()}


def rgb(token: str) -> tuple[int, int, int]:
    return RGB[token]


def bgr(token: str) -> tuple[int, int, int]:
    return BGR[token]


def rgba(token: str, alpha: float) -> tuple[int, int, int, int]:
    r, g, b = RGB[token]
    return (r, g, b, int(round(255 * max(0.0, min(1.0, alpha)))))


# ── Type scale (UI_STYLE_GUIDE.md §3, px @ ~720p; callers may scale) ───────
# role -> (px, weight)
TYPE_SCALE = {
    "display": (56, "bold"),
    "h1":      (32, "semibold"),
    "h2":      (24, "semibold"),
    "body_l":  (20, "regular"),
    "body":    (18, "regular"),
    "body_sb": (18, "semibold"),
    "caption": (14, "regular"),
}

# ── Layout (§4) ────────────────────────────────────────────────────────────
SPACE = (4, 8, 12, 16, 24, 32, 48)
RADIUS_PANEL = 16
RADIUS_BUTTON = 12
SAFE_MARGIN = 24
PANEL_ALPHA = 0.82

# ── Motion (§6) ────────────────────────────────────────────────────────────
DUR_FAST = 0.120
DUR_BASE = 0.200
DUR_SLOW = 0.320

# Reduced-motion setting (§6.4): env override, no pulsing/rippling when on.
REDUCED_MOTION = os.environ.get("HD3_REDUCED_MOTION", "0") == "1"

DISCLAIMER = "Screening tool, not a diagnosis - consult a healthcare professional."
