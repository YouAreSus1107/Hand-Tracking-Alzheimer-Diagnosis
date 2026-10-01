"""
Reusable UI components implementing docs/design/UI_STYLE_GUIDE.md §5.

Rendering model: each frame, a `Canvas` wraps the BGR camera frame. Panels,
text, chips, buttons etc. are drawn into a PIL RGBA overlay (anti-aliased
fonts, rounded corners), which is composited over the frame once. Drawing that
benefits from cv2's anti-aliased primitives (sparklines, rings, ripples) is
queued as post-composite callbacks so it lands on top of the panels.

No screen file should call cv2.putText/rectangle with literal colors —
compose everything from these components + theme tokens.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import i18n
from . import theme

_ASSET_FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# Where each OS keeps its fonts. The suite installs on whatever laptop it lands
# on, so naming a Windows path and stopping there would draw tofu everywhere
# else — PIL does no per-glyph fallback (docs/platform/OVERLAY_I18N_PLAN.md).
if sys.platform == "win32":
    _SYS_FONTS = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
elif sys.platform == "darwin":
    _SYS_FONTS = [Path("/System/Library/Fonts"),
                  Path("/System/Library/Fonts/Supplemental"),
                  Path("/Library/Fonts"),
                  Path.home() / "Library" / "Fonts"]
else:
    _SYS_FONTS = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                  Path.home() / ".fonts", Path.home() / ".local/share/fonts"]

# Linux nests fonts under the roots above (/usr/share/fonts/opentype/noto/…),
# so that branch needs a search rather than a direct hit. Bounded so a huge
# font tree cannot stall startup.
_RECURSIVE_ROOTS = sys.platform not in ("win32", "darwin")
_DIR_SCAN_LIMIT = 4000

# Preference order per weight: bundled Inter → Segoe UI → Arial (guide §3),
# with DejaVu/Helvetica so macOS and Linux resolve something real rather than
# falling through to PIL's bitmap default.
_FONT_FILES = {
    "regular":  ["Inter-Regular.ttf", "segoeui.ttf", "Helvetica.ttc",
                 "DejaVuSans.ttf", "arial.ttf"],
    "semibold": ["Inter-SemiBold.ttf", "seguisb.ttf", "segoeuib.ttf",
                 "HelveticaNeue.ttc", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "bold":     ["Inter-Bold.ttf", "segoeuib.ttf", "HelveticaNeue.ttc",
                 "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    # Tabular figures for live numbers so digits don't jitter (guide §3).
    # Every mono call site draws a numeric value, so this stack is never asked
    # for Chinese and stays Latin in both languages.
    "mono":     ["JetBrainsMono-Regular.ttf", "consola.ttf", "Menlo.ttc",
                 "DejaVuSansMono.ttf", "cour.ttf"],
}

# CJK faces, tried ahead of the Latin stack when the run is in Chinese. A name
# proves nothing about coverage, so whatever is found here is still probed.
_CJK_FILES = {
    "regular":  ["NotoSansTC-Subset-Regular.ttf",     # bundled, phase 1
                 "msjh.ttc",                          # Windows: MS JhengHei
                 "PingFang.ttc",                      # macOS
                 "NotoSansCJKtc-Regular.otf", "NotoSansCJK-Regular.ttc",
                 "NotoSansTC-Regular.otf", "NotoSansTC-VF.ttf",
                 "Hiragino Sans GB.ttc", "STHeiti Light.ttc",
                 "wqy-microhei.ttc", "mingliu.ttc"],
    "semibold": ["NotoSansTC-Subset-Bold.ttf", "msjhbd.ttc", "PingFang.ttc",
                 "NotoSansCJKtc-Bold.otf", "NotoSansCJK-Bold.ttc",
                 "NotoSansTC-Bold.otf", "NotoSansTC-VF.ttf",
                 "Hiragino Sans GB.ttc", "STHeiti Medium.ttc",
                 "wqy-microhei.ttc", "mingliub.ttc"],
}
_CJK_FILES["bold"] = _CJK_FILES["semibold"]

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_path_cache: dict[str, Path | None] = {}


def _find_font(name: str) -> Path | None:
    """Locate a font file by name across the bundled and system directories."""
    if name in _path_cache:
        return _path_cache[name]
    found = None
    for base in [_ASSET_FONTS, *_SYS_FONTS]:
        if not base.is_dir():
            continue
        direct = base / name
        if direct.exists():
            found = direct
            break
        if _RECURSIVE_ROOTS:
            found = _search(base, name)
            if found:
                break
    _path_cache[name] = found
    return found


def _search(base: Path, name: str) -> Path | None:
    """Bounded walk under a root. Only Linux needs it, and only on a miss —
    which is the expensive case, hence the directory cap."""
    scanned = 0
    try:
        for root, _dirs, files in os.walk(base):
            if name in files:
                return Path(root) / name
            scanned += 1
            if scanned > _DIR_SCAN_LIMIT:
                return None
    except OSError:
        pass
    return None


def _load(name: str, px: int):
    """Open a font file. `.ttc` collections need an explicit face index."""
    path = _find_font(name)
    if path is None:
        return None
    try:
        return ImageFont.truetype(str(path), px, index=0)
    except OSError:
        return None


def _covers_cjk(font) -> bool:
    """Whether `font` really has Chinese glyphs.

    A font name is not evidence — Segoe UI happily "renders" 測 as a .notdef
    box. Draw the probe character and compare it against U+FFFE, which is
    permanently unassigned and therefore always .notdef: an identical bitmap
    means there is no glyph. Costs two small renders, once per process.
    """
    def bitmap(ch: str) -> bytes:
        img = Image.new("L", (48, 48), 0)
        ImageDraw.Draw(img).text((4, 4), ch, font=font, fill=255)
        return img.tobytes()

    try:
        return bitmap(i18n.PROBE_CHAR) != bitmap("\ufffe")
    except Exception:                       # a broken face is simply no good
        return False


def get_font(weight: str, px: int):
    key = (weight, px)
    if key not in _font_cache:
        names = list(_FONT_FILES.get(weight, _FONT_FILES["regular"]))
        if i18n.is_zh() and weight in _CJK_FILES:
            names = _CJK_FILES[weight] + names
        font = None
        for name in names:
            font = _load(name, px)
            if font:
                break
        _font_cache[key] = font or ImageFont.load_default()
    return _font_cache[key]


def cjk_available() -> bool:
    """Resolve a CJK face once and tell core.i18n whether Chinese can render.

    Called at import time so the decision is made before any string is
    translated: a missing font has to degrade the whole run to English rather
    than paint a screenful of tofu.
    """
    for name in _CJK_FILES["regular"]:
        font = _load(name, 28)
        if font and _covers_cjk(font):
            return True
    return False


def font_diagnostics() -> dict:
    """What actually resolved — for the unit tests and for reporting a miss."""
    return {
        "lang_requested": i18n.requested_lang(),
        "lang_active": i18n.active_lang(),
        "cjk": {n: str(_find_font(n)) for n in _CJK_FILES["regular"]
                if _find_font(n)},
        "roots": [str(p) for p in [_ASSET_FONTS, *_SYS_FONTS] if p.is_dir()],
    }


# Decide up front, so t() is already gated by the time anything is drawn.
if i18n.requested_lang() != "en" and not cjk_available():
    i18n.set_render_capable(
        False, "no font with Traditional Chinese glyphs found on this system")


def font_for_role(role: str, mono: bool = False):
    px, weight = theme.TYPE_SCALE[role]
    return get_font("mono" if mono else weight, px)


# ── Simple 2px-stroke vector icons (guide §8) — drawn into the PIL overlay ──

def draw_icon(draw: ImageDraw.ImageDraw, name: str, x: int, y: int, size: int,
              color: tuple[int, int, int, int]) -> None:
    """Draw icon with its box's top-left at (x, y)."""
    s = size
    w = max(2, s // 10)
    if name == "check":
        draw.line([(x + s * 0.2, y + s * 0.55), (x + s * 0.42, y + s * 0.75),
                   (x + s * 0.8, y + s * 0.28)], fill=color, width=w, joint="curve")
    elif name == "alert":
        draw.polygon([(x + s * 0.5, y + s * 0.12), (x + s * 0.92, y + s * 0.85),
                      (x + s * 0.08, y + s * 0.85)], outline=color, width=w)
        draw.line([(x + s * 0.5, y + s * 0.38), (x + s * 0.5, y + s * 0.62)],
                  fill=color, width=w)
        draw.ellipse([x + s * 0.46, y + s * 0.70, x + s * 0.54, y + s * 0.78], fill=color)
    elif name == "info":
        draw.ellipse([x + s * 0.1, y + s * 0.1, x + s * 0.9, y + s * 0.9],
                     outline=color, width=w)
        draw.ellipse([x + s * 0.46, y + s * 0.26, x + s * 0.54, y + s * 0.34], fill=color)
        draw.line([(x + s * 0.5, y + s * 0.45), (x + s * 0.5, y + s * 0.72)],
                  fill=color, width=w)
    elif name == "cross":
        draw.line([(x + s * 0.25, y + s * 0.25), (x + s * 0.75, y + s * 0.75)],
                  fill=color, width=w)
        draw.line([(x + s * 0.75, y + s * 0.25), (x + s * 0.25, y + s * 0.75)],
                  fill=color, width=w)
    elif name == "play":
        draw.polygon([(x + s * 0.3, y + s * 0.2), (x + s * 0.3, y + s * 0.8),
                      (x + s * 0.85, y + s * 0.5)], fill=color)
    elif name == "dot":
        draw.ellipse([x + s * 0.3, y + s * 0.3, x + s * 0.7, y + s * 0.7], fill=color)


STATUS_ICON = {"success": "check", "warning": "alert", "danger": "cross", "info": "info"}


class Canvas:
    """Per-frame drawing surface in three layers, bottom to top:

      scene -- cv2 marks that belong to the picture (the spiral, fingertip
               dots, targets); drawn onto the camera frame *before* the
               panels, so a panel always covers them instead of being
               scribbled over;
      overlay -- the PIL layer: panels, text, chips, buttons;
      ui    -- cv2 marks that live inside a panel (a sparkline, a meter's
               tick), drawn last so their own panel does not hide them.

    polyline/dot/ring take `layer="scene"` (default) or `layer="ui"`."""

    def __init__(self, frame_bgr: np.ndarray):
        self.frame = frame_bgr
        self.h, self.w = frame_bgr.shape[:2]
        self.overlay = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.overlay)
        self._pre: list = []           # scene: callables(frame) run before
        self._post: list = []          # ui: callables(frame) run after
        self._dirty = False

    # ── primitives ────────────────────────────────────────────────────────

    def panel(self, x: int, y: int, w: int, h: int, *, alpha: float = theme.PANEL_ALPHA,
              radius: int = theme.RADIUS_PANEL, fill: str = "surface",
              border: bool = True, shadow: bool = True) -> None:
        self._dirty = True
        if shadow:
            self.draw.rounded_rectangle([x - 1, y + 3, x + w + 1, y + h + 5],
                                        radius=radius + 2, fill=(0, 0, 0, 100))
        self.draw.rounded_rectangle(
            [x, y, x + w, y + h], radius=radius, fill=theme.rgba(fill, alpha),
            outline=theme.rgba("border", 1.0) if border else None, width=1)

    def text(self, x: int, y: int, s: str, *, role: str = "body",
             color: str = "text", anchor: str = "la", mono: bool = False) -> None:
        if not s:
            return
        # The mono stack is Latin-only (tabular figures are the point of it), so
        # a translated label routed through it would draw tofu. Numbers keep it.
        mono = mono and not i18n.has_wide(s)
        self._dirty = True
        self.draw.text((x, y), s, font=font_for_role(role, mono=mono),
                       fill=theme.rgba(color, 1.0), anchor=anchor)

    def text_width(self, s: str, role: str = "body", mono: bool = False) -> int:
        f = font_for_role(role, mono=mono)
        box = self.draw.textbbox((0, 0), s, font=f)
        return box[2] - box[0]

    def icon(self, name: str, x: int, y: int, size: int, color: str = "text") -> None:
        self._dirty = True
        draw_icon(self.draw, name, x, y, size, theme.rgba(color, 1.0))

    # ── components (guide §5) ─────────────────────────────────────────────

    def chip(self, x: int, y: int, label: str, *, status: str = "info",
             icon: bool = True) -> int:
        """Pill chip, 28px tall, icon + label. Returns chip width.

        Pass icon=False for a text-only pill (e.g. a plain state label)."""
        h = 28
        icon_s = 16
        pad = 10
        tw = self.text_width(label, "caption")
        w = pad + (icon_s + 6 if icon else 0) + tw + pad
        self._dirty = True
        self.draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                                    fill=theme.rgba("surface", 0.85))
        self.draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                                    fill=theme.rgba(status, 0.18),
                                    outline=theme.rgba("border", 1.0), width=1)
        if icon:
            self.icon(STATUS_ICON.get(status, "info"), x + pad,
                      y + (h - icon_s) // 2, icon_s, status)
        self.text(x + pad + (icon_s + 6 if icon else 0), y + h // 2, label,
                  role="caption", color="text", anchor="lm")
        return w

    def badge(self, cx: int, y: int, label: str, status: str) -> None:
        """Centered status badge: icon + word, never color alone (§2.4)."""
        h = 34
        icon_s = 20
        pad = 14
        tw = self.text_width(label, "body_sb")
        w = pad + icon_s + 8 + tw + pad
        x = cx - w // 2
        self._dirty = True
        self.draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                                    fill=theme.rgba(status, 0.18),
                                    outline=theme.rgba(status, 0.9), width=1)
        self.icon(STATUS_ICON[status], x + pad, y + (h - icon_s) // 2, icon_s, status)
        self.text(x + pad + icon_s + 8, y + h // 2, label, role="body_sb",
                  color=status, anchor="lm")

    def confidence_card(self, x: int, y: int, w: int, *, label: str,
                        value: str, detail: str, progress: float,
                        status: str = "info") -> int:
        """Compact measurement-quality card for result screens.

        Confidence describes the recording, not the clinical result, so it is
        visually subordinate to the result badge and lives in its own neutral
        raised card. Returns the fixed card height for easy screen layout.
        """
        h = 40 if not detail else 48
        progress = max(0.0, min(1.0, progress))
        self._dirty = True
        self.draw.rounded_rectangle(
            [x, y, x + w, y + h], radius=theme.RADIUS_BUTTON,
            fill=theme.rgba("surface-2", 0.92),
            outline=theme.rgba("border", 1.0), width=1)
        self.icon(STATUS_ICON.get(status, "info"), x + 10, y + 8, 15, status)
        self.text(x + 32, y + 15, label, role="caption", color="text",
                  anchor="lm")
        self.text(x + w - 10, y + 15, value, role="caption", color=status,
                  anchor="rm", mono=True)
        if detail:
            self.text(x + 32, y + 34, detail, role="caption",
                      color="text-muted", anchor="lm")
        track_y = y + h - 4
        self.draw.rounded_rectangle([x + 12, track_y, x + w - 12, track_y + 3],
                                    radius=2, fill=theme.rgba("border", 1.0))
        fill_w = int((w - 24) * progress)
        if fill_w > 0:
            self.draw.rounded_rectangle([x + 12, track_y,
                                         x + 12 + fill_w, track_y + 3],
                                        radius=2, fill=theme.rgba(status, 1.0))
        return h

    def button(self, x: int, y: int, w: int, h: int, label: str, *,
               variant: str = "primary", hovered: bool = False,
               icon: str | None = None) -> tuple[int, int, int, int]:
        """Button per §5 spec. Returns its rect for hit-testing."""
        self._dirty = True
        if variant == "primary":
            fill = theme.rgba("interactive-hover" if hovered else "interactive", 1.0)
            txt = "text"
            outline = None
        elif variant == "success":
            fill = theme.rgba("success", 1.0 if hovered else 0.9)
            txt = "text"
            outline = None
        else:  # ghost
            fill = theme.rgba("surface-2", 0.9 if hovered else 0.6)
            txt = "text"
            outline = theme.rgba("interactive" if hovered else "border", 1.0)
        self.draw.rounded_rectangle([x, y, x + w, y + h],
                                    radius=theme.RADIUS_BUTTON, fill=fill,
                                    outline=outline, width=1)
        cx = x + w // 2
        if icon:
            icon_s = 18
            tw = self.text_width(label, "body_sb")
            ix = cx - (icon_s + 8 + tw) // 2
            self.icon(icon, ix, y + (h - icon_s) // 2, icon_s, txt)
            self.text(ix + icon_s + 8, y + h // 2, label, role="body_sb",
                      color=txt, anchor="lm")
        else:
            self.text(cx, y + h // 2, label, role="body_sb", color=txt, anchor="mm")
        return (x, y, w, h)

    def progress_bar(self, x: int, y: int, w: int, frac: float, *,
                     color: str = "brand", label: str | None = None) -> None:
        """8px rounded track with phase-colored fill; optional label above."""
        frac = max(0.0, min(1.0, frac))
        self._dirty = True
        self.draw.rounded_rectangle([x, y, x + w, y + 8], radius=4,
                                    fill=theme.rgba("surface-2", 0.9))
        if frac > 0.01:
            self.draw.rounded_rectangle([x, y, x + int(w * frac), y + 8], radius=4,
                                        fill=theme.rgba(color, 1.0))
        if label:
            self.text(x + w, y - 8, label, role="caption", color="text-muted",
                      anchor="rs", mono=True)

    def toast(self, msg: str, status: str, alpha: float,
              y: int | None = None, compact: bool = False) -> None:
        """Transient bottom-center coach pill (§5/§7). `compact` is a slimmer
        pill for screens whose free strip is narrow (the spiral's)."""
        if alpha <= 0.01 or not msg:
            return
        h = 34 if compact else 40
        icon_s = 16 if compact else 18
        pad = 14 if compact else 16
        tw = self.text_width(msg, "body")
        w = pad + icon_s + 8 + tw + pad
        x = (self.w - w) // 2
        y = y if y is not None else self.h - 96
        self._dirty = True
        self.draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                                    fill=theme.rgba("surface", 0.92 * alpha))
        self.draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                                    fill=theme.rgba(status, 0.16 * alpha),
                                    outline=theme.rgba(status, 0.8 * alpha), width=1)
        col = theme.rgba(status, alpha)
        draw_icon(self.draw, STATUS_ICON.get(status, "info"), x + pad,
                  y + (h - icon_s) // 2, icon_s, col)
        self.draw.text((x + pad + icon_s + 8, y + h // 2), msg,
                       font=font_for_role("body"),
                       fill=theme.rgba("text", alpha), anchor="lm")

    def status_bar(self, chips: list[tuple[str, str]], mode_label: str = "") -> None:
        """Persistent top bar: brand mark left, mode + quality chips right (§5)."""
        h = 48
        self._dirty = True
        self.draw.rectangle([0, 0, self.w, h], fill=theme.rgba("bg", 0.72))
        self.draw.line([(0, h), (self.w, h)], fill=theme.rgba("border", 1.0), width=1)
        # brand mark
        self.draw.ellipse([16, h // 2 - 6, 28, h // 2 + 6], fill=theme.rgba("brand", 1.0))
        self.text(38, h // 2, i18n.t("Motor Screening"), role="body_sb",
                  anchor="lm")
        # chips right-to-left
        x = self.w - 16
        for label, status in reversed(chips):
            wch = self.text_width(label, "caption") + 42
            x -= wch
            self.chip(x, (h - 28) // 2, label, status=status)
            x -= 8
        # mode label left of chips (optional)
        if mode_label:
            self.text(x - 4, h // 2, mode_label, role="caption",
                      color="text-muted", anchor="rm")

    def disclaimer(self) -> None:
        """Always-available disclaimer ribbon (§5/§10)."""
        h = 26
        y = self.h - h
        self._dirty = True
        self.draw.rectangle([0, y, self.w, self.h], fill=theme.rgba("surface", 0.85))
        self.text(self.w // 2, y + h // 2, i18n.t(theme.DISCLAIMER),
                  role="caption", color="text-muted", anchor="mm")

    def metric(self, x: int, y: int, value: str, unit: str, label: str, *,
               color: str = "text") -> None:
        """Big tabular readout + unit + label (§5 Metric Readout)."""
        self._dirty = True
        self.draw.text((x, y), value, font=get_font("mono", 44),
                       fill=theme.rgba(color, 1.0), anchor="ls")
        vw = self.draw.textbbox((0, 0), value, font=get_font("mono", 44))[2]
        self.text(x + vw + 6, y, unit, role="body", color="text-muted", anchor="ls")
        self.text(x, y + 22, label, role="caption", color="text-muted", anchor="ls")

    # ── post-composite (cv2, anti-aliased) ────────────────────────────────

    def sparkline(self, x: int, y: int, w: int, h: int,
                  series: list[tuple[float, float]], tap_times: list[float],
                  now: float, window_s: float = 4.0,
                  lo: float | None = None, hi: float | None = None) -> None:
        """Live distance-signal line with a dot per detected tap (§5)."""
        self.panel(x, y, w, h, alpha=0.75, radius=12, shadow=False)
        pts = [(t, d) for (t, d) in series if t >= now - window_s]
        if len(pts) < 2:
            return
        vals = [d for _, d in pts]
        vlo = lo if lo is not None else min(vals)
        vhi = hi if hi is not None else max(vals)
        if vhi - vlo < 1e-6:
            return
        pad = 8

        def to_px(t: float, d: float) -> tuple[int, int]:
            px = x + pad + (t - (now - window_s)) / window_s * (w - 2 * pad)
            # clamp so out-of-range samples ride the panel edge, never overflow it
            frac = max(0.0, min(1.0, (d - vlo) / (vhi - vlo)))
            py = y + h - pad - frac * (h - 2 * pad)
            return int(px), int(py)

        poly = np.array([to_px(t, d) for t, d in pts], dtype=np.int32)
        taps = [t for t in tap_times if t >= now - window_s]
        tap_px = []
        for tt in taps:
            nearest = min(pts, key=lambda p: abs(p[0] - tt))
            tap_px.append(to_px(nearest[0], nearest[1]))
        brand = theme.bgr("brand")
        success = theme.bgr("success")

        def _draw(frame):
            cv2.polylines(frame, [poly], False, brand, 1, cv2.LINE_AA)
            for p in tap_px:
                cv2.circle(frame, p, 3, success, -1, cv2.LINE_AA)

        self._post.append(_draw)

    def _layer(self, layer: str) -> list:
        if layer == "scene":
            return self._pre
        if layer == "ui":
            return self._post
        raise ValueError(f"unknown layer {layer!r}")

    def polyline(self, points, color: str, *, thickness: int = 2,
                 alpha: float = 1.0, closed: bool = False,
                 layer: str = "scene") -> None:
        """Anti-aliased polyline, under the panels unless layer="ui" (§5).

        Used for reference guides (e.g. the spiral) and traced-path highlights;
        color is a theme token scaled by `alpha`."""
        if not points or len(points) < 2 or alpha <= 0.01:
            return
        col = tuple(int(c * alpha) for c in theme.bgr(color))
        poly = np.array(points, dtype=np.int32).reshape((-1, 1, 2))

        def _draw(frame):
            cv2.polylines(frame, [poly], closed, col, thickness, cv2.LINE_AA)

        self._layer(layer).append(_draw)

    def dot(self, cx: int, cy: int, radius: float, color: str, *,
            alpha: float = 1.0, outline: str | None = None,
            outline_w: int = 2, layer: str = "scene") -> None:
        """Filled anti-aliased marker, under the panels unless layer="ui" (§5).

        Used for guide dots and fingertip markers; optional themed outline."""
        if alpha <= 0.01:
            return
        fill = tuple(int(c * alpha) for c in theme.bgr(color))
        ring_col = (tuple(int(c * alpha) for c in theme.bgr(outline))
                    if outline else None)

        def _draw(frame):
            cv2.circle(frame, (int(cx), int(cy)), int(radius), fill, -1, cv2.LINE_AA)
            if ring_col is not None:
                cv2.circle(frame, (int(cx), int(cy)), int(radius), ring_col,
                           outline_w, cv2.LINE_AA)

        self._layer(layer).append(_draw)

    def ring(self, cx: int, cy: int, radius: float, color: str,
             thickness: int = 2, alpha: float = 1.0,
             sweep_deg: float = 360.0, layer: str = "scene") -> None:
        """Anti-aliased circle/arc, under the panels unless layer="ui"."""
        col = tuple(int(c * alpha) for c in theme.bgr(color))

        def _draw(frame):
            if sweep_deg >= 359.9:
                cv2.circle(frame, (int(cx), int(cy)), int(radius), col,
                           thickness, cv2.LINE_AA)
            else:
                cv2.ellipse(frame, (int(cx), int(cy)), (int(radius), int(radius)),
                            -90, 0, sweep_deg, col, thickness, cv2.LINE_AA)

        self._layer(layer).append(_draw)

    def border_glow(self, color: str, alpha: float) -> None:
        """Gentle 2px border pulse (§6.3) — never a full-screen flash."""
        if alpha <= 0.01 or theme.REDUCED_MOTION:
            return
        col = tuple(int(c * alpha) for c in theme.bgr(color))

        def _draw(frame):
            cv2.rectangle(frame, (1, 1), (self.w - 2, self.h - 2), col, 2, cv2.LINE_AA)

        self._post.append(_draw)

    def edge_alert(self, edges, status: str, along: tuple[float, float]
                   | None = None, strong: bool = False) -> None:
        """Hand leaving the frame: a translucent band on each edge it is
        crossing, with an inward chevron level with the hand (`along` is the
        hand's normalised (x, y)). Colour plus a pointing shape, never colour
        alone (§2.4)."""
        if not edges:
            return
        self._dirty = True
        band = 16 if strong else 10
        fill = theme.rgba(status, 0.55 if strong else 0.30)
        ink = theme.rgba(status, 1.0)
        w, h = self.w, self.h
        ax, ay = along if along else (0.5, 0.5)
        px = int(min(max(ax, 0.08), 0.92) * w)
        py = int(min(max(ay, 0.08), 0.92) * h)
        s = 22                                    # chevron half-size
        for e in edges:
            if e == "left":
                self.draw.rectangle([0, 0, band, h], fill=fill)
                x = band + 14
                pts = [(x, py - s), (x + s, py), (x, py + s)]
            elif e == "right":
                self.draw.rectangle([w - band, 0, w, h], fill=fill)
                x = w - band - 14
                pts = [(x, py - s), (x - s, py), (x, py + s)]
            elif e == "top":
                self.draw.rectangle([0, 0, w, band], fill=fill)
                y = band + 14
                pts = [(px - s, y), (px, y + s), (px + s, y)]
            else:
                self.draw.rectangle([0, h - band, w, h], fill=fill)
                y = h - band - 14
                pts = [(px - s, y), (px, y - s), (px + s, y)]
            if strong:
                self.draw.line(pts, fill=ink, width=6, joint="curve")

    # ── final composite ───────────────────────────────────────────────────

    def compose(self) -> np.ndarray:
        frame = self.frame
        for fn in self._pre:
            fn(frame)
        if self._dirty:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            base = Image.fromarray(rgb).convert("RGBA")
            merged = Image.alpha_composite(base, self.overlay)
            frame = cv2.cvtColor(np.asarray(merged.convert("RGB")), cv2.COLOR_RGB2BGR)
        for fn in self._post:
            fn(frame)
        return frame


def bare_view(frame_bgr: np.ndarray, hint: str) -> np.ndarray:
    """The camera picture with every overlay hidden (V, core/ui/keys.py):
    only a small chip at the bottom-left saying how to bring them back."""
    c = Canvas(frame_bgr)
    m = theme.SPACE[3]
    c.chip(m, c.h - 28 - m, hint, status="info", icon=False)
    return c.compose()


def draw_hand_skeleton(frame: np.ndarray, landmarks, connections,
                       highlight: bool = False) -> None:
    """Hand skeleton in theme colors; brightens briefly on a tap (§6.3)."""
    fh, fw = frame.shape[:2]
    line = theme.bgr("brand") if not highlight else theme.bgr("success")
    tip = theme.bgr("info")
    joint = theme.bgr("surface-2")
    for a, b in connections:
        p1, p2 = landmarks[a], landmarks[b]
        cv2.line(frame, (int(p1[0] * fw), int(p1[1] * fh)),
                 (int(p2[0] * fw), int(p2[1] * fh)), line, 2, cv2.LINE_AA)
    for i, lm in enumerate(landmarks):
        is_tip = i in (4, 8)
        cv2.circle(frame, (int(lm[0] * fw), int(lm[1] * fh)),
                   6 if is_tip else 3, tip if is_tip else joint, -1, cv2.LINE_AA)
