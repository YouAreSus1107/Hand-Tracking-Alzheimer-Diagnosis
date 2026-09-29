"""
Overlay language for the screening tools — English / 繁體中文.

The Python counterpart to launcher_web/i18n.js, and deliberately the same
shape: **only Chinese is stored**. English stays where it already lives, in the
source strings, so there is one copy of it and an untranslated string degrades
to English instead of printing a raw key.

Two lookups, matching the JS side:

    t("Start Test")                     English source string as its own key
    tk("tap.big_and_fast.instructions", [...])   dotted key + English fallback

`tk` exists for the pre-split instruction blocks in core/tapping/modes.py and
core/gaze/tasks.py. Chinese needs its own line breaks, not the English ones, so
those values are lists and the two languages need not have the same line count.

Where the language comes from, in order:

    HAND3D_LANG           set by launcher.py on the spawned process
    .launcher_settings.json   so a directly-run script still follows the hub
    "en"

**Translate at draw time only.** core/tapping/modes.py, core/gaze/tasks.py and
core/spiral/metrics.py hold labels that are both drawn *and* saved through
core/session.py into results/*.json and index.csv. Translating those at the data
layer would split the Analysis page's longitudinal history the first time
somebody toggles the language. The dataclasses, the session JSON and the CSV
stay English; only the string handed to Canvas.text() is translated.

This module is stdlib-only and import-cheap on purpose — it is imported above
the cv2/mediapipe block in the entry scripts, alongside core.splash. In
particular it never imports PIL; the font layer depends on this module, not the
other way round (see `set_render_capable`).
"""

from __future__ import annotations

import json
import os
import re
import sys

ENV_LANG = "HAND3D_LANG"
LANGS = ("en", "zh")
DEFAULT_LANG = "en"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETTINGS_FILE = os.path.join(_REPO_ROOT, ".launcher_settings.json")

# A character every CJK face has and no Latin-only face does — used both for the
# font coverage probe and for the console encodability test.
PROBE_CHAR = "測"

_requested: str | None = None       # resolved once, then cached
_render_capable = True              # cleared by the font layer if zh can't draw
_capability_note = ""


# ── Which language was asked for ───────────────────────────────────────────

def _from_settings() -> str | None:
    """The hub's stored choice, for a tool started outside the launcher."""
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    value = data.get("lang") if isinstance(data, dict) else None
    return value if value in LANGS else None


def requested_lang() -> str:
    """The language asked for, regardless of whether it can be rendered."""
    global _requested
    if _requested is None:
        env = os.environ.get(ENV_LANG, "").strip().lower()
        _requested = env if env in LANGS else (_from_settings() or DEFAULT_LANG)
    return _requested


def set_lang(code: str) -> None:
    """Override the resolved language. For tests and manual runs."""
    global _requested
    _requested = code if code in LANGS else DEFAULT_LANG


# ── Whether it can actually be drawn ───────────────────────────────────────

def set_render_capable(ok: bool, note: str = "") -> None:
    """Called by core.ui.components once it knows if a CJK face was found.

    A missing font must degrade to English, never to tofu boxes, so the
    capability gates `t()` rather than only the font choice.
    """
    global _render_capable, _capability_note
    _render_capable = bool(ok)
    _capability_note = note
    if not ok and requested_lang() != DEFAULT_LANG:
        print(f"[i18n] Falling back to English: {note or 'no CJK font found'}",
              file=sys.stderr)


def capability_note() -> str:
    return _capability_note


def active_lang() -> str:
    """The language that will actually be rendered."""
    lang = requested_lang()
    return lang if (lang == DEFAULT_LANG or _render_capable) else DEFAULT_LANG


def is_zh() -> bool:
    return active_lang() == "zh"


def console_supports(text: str) -> bool:
    """Whether stdout's encoding can carry `text`.

    The console may sit on a code page that cannot encode CJK (cp437, cp950
    partially), where printing Chinese yields '?????'. core/splash.py already
    degrades its bar glyphs this way; the same test applies to the words.
    """
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# OEM code pages whose default console font carries CJK glyphs:
# Japanese, Simplified Chinese, Korean, Traditional Chinese.
_CJK_CODE_PAGES = (932, 936, 949, 950)
_console_cjk: bool | None = None


def _console_font_has_cjk() -> bool:
    """Whether the console will draw CJK as glyphs rather than boxes.

    Encoding is only half of it. Python writes UTF-16 to a Windows console, so
    `console_supports()` passes everywhere there, but legacy conhost does no
    font fallback: on an English Windows it draws Chinese in Consolas, as boxes.
    Windows Terminal (WT_SESSION, also set when it is the default terminal the
    launcher's CREATE_NEW_CONSOLE is delegated to) falls back per glyph, and a
    CJK-locale conhost defaults to a CJK face. Elsewhere, terminals fall back.
    """
    if os.name != "nt" or os.environ.get("WT_SESSION"):
        return True
    try:
        import ctypes
        return ctypes.windll.kernel32.GetOEMCP() in _CJK_CODE_PAGES
    except Exception:                       # noqa: BLE001 - no Win32 at all
        return False


def console_zh() -> bool:
    """Whether console text should be Chinese: asked for *and* displayable."""
    global _console_cjk
    if requested_lang() != "zh":
        return False
    if _console_cjk is None:
        _console_cjk = console_supports(PROBE_CHAR) and _console_font_has_cjk()
    return _console_cjk


def ct(text: str, **params) -> str:
    """`t()` for console output: Chinese only where the console can show it.

    The console is a separate surface from the overlay. The overlay degrades on
    the font it can find, the console on its code page and its font, and one
    can succeed where the other fails, so this deliberately does not consult
    the overlay's render capability. A miss still prints English, never '???'.
    """
    if text is None:
        return ""
    if not console_zh():
        return _fill(text, params)
    return _fill(_dict_for("zh").get(text, text), params)


def text_width(text: str) -> int:
    """Terminal columns `text` occupies: CJK and full-width forms take two."""
    return sum(2 if _is_wide(ch) else 1 for ch in text or "")


# ── Lookups ────────────────────────────────────────────────────────────────

def _dict() -> dict:
    return _dict_for(active_lang())


def _dict_for(lang: str) -> dict:
    if lang != "zh":
        return {}
    try:
        from core import i18n_zh
    except ImportError:
        return {}
    return i18n_zh.ZH


_PARAM = re.compile(r"\{(\w+)\}")


def _fill(text: str, params: dict) -> str:
    """`{name}` substitution. Deliberately not str.format: a stray brace in a
    translation must not raise in the middle of a frame render."""
    if not params:
        return text
    return _PARAM.sub(
        lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0),
        text)


def _rules():
    """Regex table for strings the engine has already formatted.

    core/tapping/metrics.py builds a few `reason` strings with the numbers
    already substituted, and those same strings are saved to results/*.json —
    so they cannot be turned into templates without changing the stored data.
    They are matched here instead, exactly as launcher_web/i18n.zh.js does for
    the messages launcher.py sends. `$1` in the translation takes group 1.
    """
    if active_lang() != "zh":
        return ()
    try:
        from core import i18n_zh
    except ImportError:
        return ()
    return i18n_zh.ZH_RULES


_GROUP = re.compile(r"\$(\d)")


def t(text: str, **params) -> str:
    """Translate an English source string. Unknown strings pass through."""
    if text is None:
        return ""
    out = _dict().get(text)
    if out is None:
        for pattern, zh in _rules():
            m = pattern.match(text)
            if m:
                out = _GROUP.sub(
                    lambda g: m.group(int(g.group(1))) or "", zh)
                break
    return _fill(text if out is None else out, params)


def tk(key: str, fallback):
    """Translate by dotted key, with the English original as the fallback.

    Handles both strings and lists of lines; the Chinese value may have a
    different number of lines than the English one.
    """
    value = _dict().get(key)
    return fallback if value is None else value


# ── Wrapping ───────────────────────────────────────────────────────────────
# Chinese has no spaces, so splitting on whitespace returns the whole sentence
# as one unbreakable token and the line runs off the panel. Chinese instead
# breaks between characters, which is how the script is normally set.

def _is_wide(ch: str) -> bool:
    """CJK and full-width forms, which occupy roughly two Latin advances."""
    return (
        "ᄀ" <= ch <= "ᅟ" or "⺀" <= ch <= "꓏"
        or "가" <= ch <= "힣" or "豈" <= ch <= "﫿"
        or "︰" <= ch <= "﹯" or "＀" <= ch <= "｠"
        or "￠" <= ch <= "￦")


# Punctuation that may not open a line (a closing bracket, a comma) or may not
# end one (an opening bracket). Breaking there looks broken to a reader.
_NO_LINE_START = "、。，．：；！？）〕］｝〉》」』】”’%,.:;!?)]}"
_NO_LINE_END = "（〔［｛〈《「『【“‘([{"


def _tokens(text: str):
    """Break `text` into the smallest units a line may break between."""
    buf = ""
    for ch in text:
        if _is_wide(ch):
            if buf:
                yield buf
                buf = ""
            yield ch
        elif ch == " ":
            yield buf + ch
            buf = ""
        else:
            buf += ch
    if buf:
        yield buf


def has_wide(text: str) -> bool:
    """True if any character needs a CJK face — the mono stack has none."""
    return any(_is_wide(ch) for ch in text or "")


def wrap(text: str, cols: int) -> list[str]:
    """Wrap `text` to `cols` Latin-character widths, counting CJK as two.

    Works for both languages: Latin keeps whole words together, Chinese breaks
    between characters, honouring the punctuation that cannot start or end a
    line.
    """
    if not text:
        return [""]
    lines: list[str] = []
    cur, width = "", 0
    for token in _tokens(text):
        tw = sum(2 if _is_wide(c) else 1 for c in token)
        starts_forbidden = token[:1] in _NO_LINE_START
        ends_forbidden = cur[-1:] in _NO_LINE_END
        if cur and width + tw > cols and not starts_forbidden and not ends_forbidden:
            lines.append(cur.rstrip())
            cur, width = "", 0
            if not token.strip():
                continue                 # don't open a line with a space
        cur += token
        width += tw
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]
