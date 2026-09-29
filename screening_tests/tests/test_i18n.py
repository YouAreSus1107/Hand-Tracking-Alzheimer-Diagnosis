"""
Unit tests for the overlay language layer (OVERLAY_I18N_PLAN.md) — the
dictionary, the lookups, and the font resolution that decides whether Chinese
can be drawn at all.

These run on one machine, so they cannot prove the font situation on somebody
else's laptop. What they *can* pin down is the degrade path: with no CJK face
found, the run must fall back to English rather than paint tofu. That is the
property that has to hold everywhere.

Run:  python -m pytest screening_tests/tests/test_i18n.py
 or:  python screening_tests/tests/test_i18n.py   (self-runs without pytest)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core import i18n
from core.i18n_zh import ZH

_SOURCE_DIRS = ("screening_tests", "core")


def _reset(lang="en", capable=True):
    i18n.set_lang(lang)
    i18n.set_render_capable(capable)


def _source_files():
    for d in _SOURCE_DIRS:
        for p in (_REPO_ROOT / d).rglob("*.py"):
            if "__pycache__" in p.parts or p.name.startswith("i18n"):
                continue
            yield p


def _source_strings() -> set:
    """Every string literal in the overlay sources.

    Parsed rather than grepped: a long line is usually written as two adjacent
    literals, and the key they form only exists once Python has joined them.
    """
    import ast

    found = set()
    for p in _source_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
    return found


# ── Lookups ────────────────────────────────────────────────────────────────

def test_english_passes_through_untouched():
    _reset("en")
    assert i18n.t("Start Test") == "Start Test"
    assert i18n.active_lang() == "en"


def test_chinese_translates_known_strings():
    _reset("zh")
    assert i18n.t("Start Test") == "開始測驗"


def test_unknown_string_degrades_to_english():
    """A missing translation must show English, never a raw key or a blank."""
    _reset("zh")
    assert i18n.t("A string nobody has translated") == \
        "A string nobody has translated"
    assert i18n.t(None) == ""


def test_params_are_substituted_in_both_languages():
    for lang in ("en", "zh"):
        _reset(lang)
        out = i18n.t("Scored test begins in {secs} s", secs="7")
        assert "7" in out and "{secs}" not in out


def test_stray_brace_does_not_raise_mid_frame():
    """str.format would blow up here; a render loop must not."""
    _reset("zh")
    assert i18n.t("100% {unknown} literal", secs="7") == "100% {unknown} literal"


def test_tk_falls_back_to_the_english_lines():
    _reset("zh")
    en = ["line one", "line two"]
    assert i18n.tk("no.such.key", en) == en


# ── Dictionary hygiene ─────────────────────────────────────────────────────

def test_every_plain_key_exists_in_the_source():
    """No orphans: a translation whose English string no longer exists is dead
    weight and, worse, hides the fact that the live string is untranslated."""
    literals = _source_strings()
    orphans = [k for k in ZH
               if "." not in k.split(" ")[0] and k not in literals]
    assert not orphans, f"zh keys not found in any source file: {orphans}"


def test_placeholders_match_between_languages():
    ph = re.compile(r"\{(\w+)\}")
    for en, zh in ZH.items():
        if not isinstance(zh, str):
            continue
        assert set(ph.findall(en)) == set(ph.findall(zh)), \
            f"placeholder mismatch: {en!r} -> {zh!r}"


def test_list_values_are_lists_of_strings():
    for key, value in ZH.items():
        if isinstance(value, list):
            assert all(isinstance(x, str) for x in value), key


def test_translations_actually_contain_chinese():
    """Guards against an entry left as a copy of the English."""
    for en, zh in ZH.items():
        text = zh if isinstance(zh, str) else "".join(zh)
        assert any("一" <= c <= "鿿" for c in text), \
            f"no Chinese in translation of {en!r}"


# ── Wrapping ───────────────────────────────────────────────────────────────

def test_wrap_keeps_latin_words_whole():
    text = "Your hand was out of view for part of the test"
    lines = i18n.wrap(text, 24)
    assert len(lines) > 1
    assert " ".join(lines) == text            # nothing lost, no word split
    assert all(len(line) <= 24 for line in lines)


def test_wrap_breaks_chinese_between_characters():
    """Chinese has no spaces: a whitespace split returns one unbreakable token
    and the line runs off the panel, which is the bug this exists to avoid."""
    text = "測驗過程中您的手有一段時間不在畫面內請保持手在畫面中並再試一次"
    assert len(text.split()) == 1             # the failure mode, made explicit
    lines = i18n.wrap(text, 20)
    assert len(lines) > 1
    assert "".join(lines) == text
    for line in lines:
        assert sum(2 for _ in line) <= 20     # every char here is full-width


def test_wrap_does_not_open_a_line_with_closing_punctuation():
    text = "一二三四五六七八九十，十九八七六五四三二一。"
    for cols in range(8, 24, 2):
        for line in i18n.wrap(text, cols):
            assert line[0] not in "、。，）」", (cols, line)


def test_wrap_handles_the_empty_string():
    assert i18n.wrap("", 20) == [""]
    assert i18n.wrap(None, 20) == [""]


# ── Rules: strings the engine formatted before storing them ────────────────

def test_formatted_reason_is_translated_and_keeps_its_numbers():
    _reset("zh")
    out = i18n.t("Only 7 taps detected - at least 12 are needed "
                 "for a reliable score.")
    assert "7" in out and "12" in out
    assert any("一" <= c <= "鿿" for c in out), out


def test_rules_do_not_fire_in_english():
    _reset("en")
    text = "Only 7 taps detected - at least 12 are needed for a reliable score."
    assert i18n.t(text) == text


# Every module that can put a sentence in front of the user when a run cannot
# be scored. Each is checked for both `out["reason"] = ...` and `self.reason = ...`.
_REASON_MODULES = (
    ("core", "tapping", "metrics.py"),
    ("core", "spiral", "metrics.py"),
    ("core", "gaze", "metrics.py"),
    ("core", "gaze", "calibrate.py"),
    ("core", "speech", "metrics.py"),
    ("core", "speech", "phonation.py"),
    ("core", "tremor", "metrics.py"),
    ("core", "gait", "seated.py"),
)

_BAND_MODULES = (
    ("core", "tapping", "metrics.py"),
    ("core", "spiral", "metrics.py"),
    ("core", "gaze", "metrics.py"),
    ("core", "gaze", "fixation.py"),
    ("core", "speech", "metrics.py"),
    ("core", "speech", "phonation.py"),
    ("core", "tremor", "metrics.py"),
    ("core", "gait", "metrics.py"),
)

_STATUS_TOKENS = {"success", "warning", "danger", "info"}


def _is_chinese(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def _reason_strings(path) -> list:
    """Every `reason` sentence a module can produce, with its numbers filled in
    the way the engine would fill them."""
    import ast

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(
                part.value if isinstance(part, ast.Constant) else "7"
                for part in node.values)
        return None

    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            name = None
            if isinstance(target, ast.Subscript) and \
                    isinstance(target.slice, ast.Constant):
                name = target.slice.value
            elif isinstance(target, ast.Attribute):
                name = target.attr
            if name not in ("reason", "fail_reason"):
                continue
            text = literal(node.value)
            if text:
                found.append(text)
    return found


def _band_labels(path) -> list:
    """The plain-language label out of every `return "status", "Label"` pair."""
    import ast

    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Tuple):
            continue
        parts = node.value.elts
        if len(parts) != 2:
            continue
        head, tail = parts
        if (isinstance(head, ast.Constant) and head.value in _STATUS_TOKENS
                and isinstance(tail, ast.Constant)
                and isinstance(tail.value, str)):
            found.append(tail.value)
    return found


def test_every_failure_reason_is_translated():
    """Every `reason` any engine can produce must resolve — from the dictionary
    or from a rule. A new one added without a translation would otherwise
    surface as English inside an otherwise Chinese panel."""
    _reset("zh")
    checked = 0
    for parts in _REASON_MODULES:
        path = _REPO_ROOT.joinpath(*parts)
        reasons = _reason_strings(path)
        assert reasons, f"no reasons found in {path.name} - did it move?"
        for reason in reasons:
            assert _is_chinese(i18n.t(reason)), \
                f"untranslated reason in {'/'.join(parts)}: {reason!r}"
            checked += 1
    assert checked >= 12, checked


def test_every_band_label_is_translated():
    """The badge under the headline number on every results screen."""
    _reset("zh")
    checked = 0
    for parts in _BAND_MODULES:
        path = _REPO_ROOT.joinpath(*parts)
        labels = _band_labels(path)
        assert labels, f"no band labels found in {path.name} - did it move?"
        for label in labels:
            assert _is_chinese(i18n.t(label)), \
                f"untranslated band label in {'/'.join(parts)}: {label!r}"
            checked += 1
    assert checked >= 11, checked


def test_every_instruction_block_is_translated():
    """The pre-split instruction panels. These are keyed rather than translated
    line by line, so a missing key degrades silently to the English lines."""
    from core.gaze.tasks import TASKS
    from core.speech.tasks import PHONATION, TASKS as SPEECH_TASKS
    from core.tapping.modes import MODES
    from core.tremor.phases import PHASES as TREMOR_PHASES
    from core.gait.phases import BLOCKS as GAIT_BLOCKS

    _reset("zh")
    blocks = [(f"tap.{k}.instructions", m.instructions) for k, m in MODES.items()]
    blocks += [(f"gaze.{k}.instructions", t.instructions) for k, t in TASKS.items()]
    blocks += [(f"ddk.{k}.instructions", t.instructions)
               for k, t in SPEECH_TASKS.items()]
    blocks.append(("phon.ahh.instructions", PHONATION.instructions))
    blocks += [(f"tremor.{k}.instructions", p.instructions)
               for k, p in TREMOR_PHASES.items()]
    blocks += [(f"gait.{k}.instructions", b.instructions)
               for k, b in GAIT_BLOCKS.items()]
    blocks.append(("gaze.fix.instructions", ("x",)))
    blocks.append(("spiral.instructions", ("x",)))
    for key, english in blocks:
        lines = i18n.tk(key, english)
        assert lines is not english, f"no Chinese instruction block for {key}"
        assert all(isinstance(line, str) and line.strip() for line in lines), key
        assert _is_chinese("".join(lines)), key


def test_every_screen_title_is_translated():
    """The h1/h2 a user reads first on each tool."""
    from core.gaze.tasks import TASKS
    from core.speech.tasks import PHONATION, TASKS as SPEECH_TASKS
    from core.tapping.modes import MODES
    from core.tremor.phases import PHASES as TREMOR_PHASES
    from core.gait.phases import BLOCKS as GAIT_BLOCKS

    _reset("zh")
    titles = ["Finger Tapping Test", "Spiral Tracing Test", "Eye Movement Test",
              "Part 3 - Hold Still", "Speech Test", "Hand Tremor Test",
              "Hand Tremor - Results", "Walking Test", "Walking Test - Results"]
    titles += [m.title for m in MODES.values()]
    titles += [t.title for t in TASKS.values()]
    titles += [t.title for t in SPEECH_TASKS.values()] + [PHONATION.title]
    titles += [p.title for p in TREMOR_PHASES.values()]
    titles += [p.cue for p in TREMOR_PHASES.values()]
    titles += [b.title for b in GAIT_BLOCKS.values()]
    titles += [b.cue for b in GAIT_BLOCKS.values()]
    for title in titles:
        assert _is_chinese(i18n.t(title)), f"untranslated title: {title!r}"

def test_tapping_modes_are_translated_title_and_instructions():
    from core.tapping.modes import MODES

    _reset("zh")
    for key, mode in MODES.items():
        assert i18n.t(mode.title) != mode.title, f"mode title: {mode.title}"
        lines = i18n.tk(f"tap.{key}.instructions", mode.instructions)
        assert lines is not mode.instructions, f"instructions: {key}"
        assert all(isinstance(line, str) for line in lines)


# ── Fonts and the degrade path ─────────────────────────────────────────────

def test_probe_rejects_latin_only_and_accepts_cjk():
    """The coverage probe is the whole basis for the fallback decision, so it
    has to be right: a font *name* proves nothing about its glyphs."""
    from PIL import ImageFont

    from core.ui import components as C

    latin = C._load("segoeui.ttf", 28) or C._load("DejaVuSans.ttf", 28) \
        or C._load("arial.ttf", 28)
    if latin is None:
        return                          # no Latin face to test against
    assert not C._covers_cjk(latin), "probe passed a font with no CJK glyphs"

    for name in C._CJK_FILES["regular"]:
        font = C._load(name, 28)
        if font is not None:
            assert C._covers_cjk(font), f"probe rejected a real CJK face: {name}"
            return


def test_missing_font_forces_english_not_tofu():
    """The portability guarantee: on a laptop with no Traditional Chinese face,
    zh must render as English."""
    from core.ui import components as C

    saved_paths = dict(C._path_cache)
    saved_fonts = dict(C._font_cache)
    try:
        for name in C._CJK_FILES["regular"] + C._CJK_FILES["semibold"]:
            C._path_cache[name] = None
        C._font_cache.clear()

        i18n.set_lang("zh")
        assert C.cjk_available() is False
        i18n.set_render_capable(False, "simulated")

        assert i18n.requested_lang() == "zh"    # the choice is remembered
        assert i18n.active_lang() == "en"       # but English is what draws
        assert i18n.t("Start Test") == "Start Test"
    finally:
        C._path_cache.clear()
        C._path_cache.update(saved_paths)
        C._font_cache.clear()
        C._font_cache.update(saved_fonts)
        _reset("en")


def test_mono_stack_is_never_asked_for_chinese():
    """Numeric readouts keep tabular figures, so the mono stack stays Latin.
    That is only safe while no translated string reaches a mono call site."""
    mono_calls = re.compile(r"mono\s*=\s*True")
    # A bare t(...) call — not the t in .text(, textbbox(, format( …
    translator = re.compile(r"(?<![\w.])t\(")
    for d in _SOURCE_DIRS:
        for p in (_REPO_ROOT / d).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if mono_calls.search(line):
                    assert not translator.search(line), \
                        f"translated string at a mono call site: {p.name}: {line.strip()}"


def test_language_comes_from_the_environment():
    """How launcher.py hands the choice to a spawned tool."""
    i18n._requested = None
    saved = os.environ.get(i18n.ENV_LANG)
    try:
        os.environ[i18n.ENV_LANG] = "zh"
        assert i18n.requested_lang() == "zh"
        i18n._requested = None
        os.environ[i18n.ENV_LANG] = "klingon"
        assert i18n.requested_lang() in ("en", "zh")   # never the raw value
    finally:
        if saved is None:
            os.environ.pop(i18n.ENV_LANG, None)
        else:
            os.environ[i18n.ENV_LANG] = saved
        i18n._requested = None
        _reset("en")


def test_bundled_subset_covers_every_translated_character():
    """The bundled subset is the only font layer we control, so it has to cover
    the whole dictionary. Rebuild it with tools/build_cjk_subset.py after
    adding strings, or a new character draws as tofu on a machine with no
    system CJK face."""
    from core.ui import components as C

    path = C._find_font("NotoSansTC-Subset-Regular.ttf")
    if path is None:
        return                          # not built here; the system stack covers it

    from fontTools.ttLib import TTFont

    font = TTFont(path)
    cmap = font.getBestCmap()
    font.close()

    wanted = set()
    for key, value in ZH.items():
        wanted |= set(key)
        wanted |= set("".join(value) if isinstance(value, list) else value)
    missing = sorted(c for c in wanted
                     if c.strip() and ord(c) not in cmap)
    assert not missing, ("characters missing from the bundled subset "
                         f"(rerun tools/build_cjk_subset.py): {missing}")


def test_canvas_demotes_mono_for_chinese_text():
    """The mono face is Latin-only by design. Anything wide that reaches a mono
    call site has to be re-routed, or it draws as boxes."""
    assert i18n.has_wide("次數") is True
    assert i18n.has_wide("12.3 Hz") is False
    assert i18n.has_wide("") is False


# ── Console text (phase 3: splash, camera prompt) ──────────────────────────

def _console(lang, can_show):
    i18n.set_lang(lang)
    i18n.set_render_capable(True)
    i18n._console_cjk = can_show


def test_console_translates_when_it_can_show_chinese():
    _console("zh", True)
    try:
        assert i18n.ct("Camera source:") == "相機來源："
        assert i18n.ct("webcam {n}", n=1) == "網路攝影機 1"
    finally:
        i18n._console_cjk = None


def test_console_stays_english_when_it_cannot_show_chinese():
    """A legacy code page or a Latin-only conhost font must get English, not
    '???' or boxes -- even when the overlay itself can draw Chinese."""
    _console("zh", False)
    try:
        assert i18n.ct("Camera source:") == "Camera source:"
        assert i18n.ct("webcam {n}", n=1) == "webcam 1"
    finally:
        i18n._console_cjk = None


def test_console_does_not_follow_the_overlay_font():
    """The console has its own font; a missing overlay CJK face is no reason
    to print English there, and vice versa."""
    _console("zh", True)
    i18n.set_render_capable(False)
    try:
        assert i18n.ct("Ready") == "準備完成"
    finally:
        i18n._console_cjk = None
        _reset("en")


def test_console_is_english_when_english_is_asked_for():
    _console("en", True)
    try:
        assert i18n.ct("Ready") == "Ready"
    finally:
        i18n._console_cjk = None


def test_text_width_counts_cjk_as_two_columns():
    assert i18n.text_width("Ready") == 5
    assert i18n.text_width("準備完成") == 8
    assert i18n.text_width("") == 0


def _ct_literals() -> set:
    """Every literal passed as the first argument to i18n.ct()."""
    import ast

    found = set()
    for p in _source_files():
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and node.args
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "ct"
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    return found


def _splash_literals() -> set:
    """Titles, subtitles and stage labels handed to core.splash, which
    translates them itself."""
    import ast
    from core import splash

    found = {label for steps in (splash.IMPORT_STEPS, splash.GAZE_IMPORT_STEPS,
                                 splash.SPEECH_IMPORT_STEPS)
             for label, _ in steps}
    for p in _source_files():
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "Splash"):
                found |= {a.value for a in node.args[:2]
                          if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    return found


# Product names, kept Latin by house style.
_CONSOLE_LATIN = {"OpenCV", "MediaPipe"}


def test_every_console_string_is_translated():
    """A console line added without a translation would print English inside
    an otherwise Chinese console."""
    wanted = (_ct_literals() | _splash_literals()) - _CONSOLE_LATIN
    assert len(wanted) > 20, "the console walk found almost nothing"
    missing = sorted(s for s in wanted if s not in ZH)
    assert not missing, f"console strings with no translation: {missing}"


if __name__ == "__main__":
    fns =[v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:                 # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
