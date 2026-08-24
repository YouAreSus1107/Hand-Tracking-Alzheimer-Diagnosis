"""
Build the bundled Traditional-Chinese overlay font.

The overlays are drawn with PIL, which does **no per-glyph fallback**: if the
face handed to it has no 敲, the box is drawn instead of the character. So a
Chinese run needs a face that really covers the text, and
core/ui/components.py looks for one in this order:

    assets/fonts/NotoSansTC-Subset-*.ttf     <- what this tool builds
    the machine's own CJK faces (msjh, PingFang, Noto CJK, wqy, mingliu)
    nothing found -> core.i18n degrades the run to English

Only the first layer is under our control, which is why it exists: a laptop
with no Traditional-Chinese language pack still shows Chinese overlays. A full
Noto Sans TC is ~9 MB per weight; the overlays use a few hundred characters, so
subsetting to exactly the strings in core/i18n_zh.py gets that under ~100 kB
and the repo can carry it.

Dev-time only, not part of install.py or the app. Run it again after adding
strings to core/i18n_zh.py, or the new characters will be missing:

    .venv/Scripts/python tools/build_cjk_subset.py

**Licensing.** The source must be an SIL Open Font License face — Noto Sans TC
is, and OFL explicitly permits subsetting and redistribution as long as the
licence travels with the font. Microsoft JhengHei (msjh.ttc) is proprietary and
must never be used as the source here, however convenient it is on Windows;
this tool refuses anything it does not recognise as OFL.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

OUT_DIR = _REPO_ROOT / "assets" / "fonts"
WEIGHTS = {"Regular": 400, "Bold": 700}

# Recognised OFL sources, in preference order. Names only — a file called
# msjh.ttc will never match, which is the point.
OFL_SOURCES = (
    "NotoSansTC-VF.ttf",
    "NotoSansTC[wght].ttf",
    "NotoSansCJKtc-Regular.otf",
    "NotoSansTC-Regular.otf",
    "NotoSansTC-Regular.ttf",
)

SEARCH_DIRS = (
    OUT_DIR,
    _REPO_ROOT / "assets",
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    Path("/Library/Fonts"),
    Path("/usr/share/fonts/opentype/noto"),
    Path("/usr/share/fonts/truetype/noto"),
)


def find_source() -> Path | None:
    for d in SEARCH_DIRS:
        for name in OFL_SOURCES:
            p = d / name
            if p.is_file():
                return p
    return None


def wanted_chars() -> str:
    """Every character the overlays can ask of the CJK face.

    That is the Chinese itself, plus the English source strings — in a Chinese
    run the CJK stack is tried first for *all* text, and any string with no
    translation still passes through in English.
    """
    from core import i18n_zh

    chunks = []
    for key, value in i18n_zh.ZH.items():
        chunks.append(key)
        if isinstance(value, (list, tuple)):
            chunks.extend(value)
        else:
            chunks.append(str(value))
    for pattern, zh in i18n_zh.ZH_RULES:
        chunks.append(zh)
        chunks.append(pattern.pattern)
    # Printable ASCII outright: metrics, units, paths and file names are built
    # at runtime and never appear in the dictionary.
    chunks.append("".join(chr(c) for c in range(0x20, 0x7F)))
    # Typographic punctuation the overlays and translations use. The window
    # title's cross is deliberately absent: cv2 draws that, not PIL.
    chunks.append("°±×÷–—…‘’“”•·′″≈≤≥µ")
    return "".join(chunks)


def build(src: Path, chars: str) -> list[tuple[Path, int]]:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for label, wght in WEIGHTS.items():
        font = TTFont(str(src))
        if "fvar" in font:
            font = instancer.instantiateVariableFont(
                font, {"wght": wght}, inplace=True, updateFontNames=True)
        elif wght != 400:
            print(f"  [skip] {label}: {src.name} is a single-weight face; "
                  f"the regular is reused for bold")
            continue

        opts = subset.Options()
        opts.notdef_outline = True
        opts.recalc_bounds = True
        opts.drop_tables += ["DSIG"]
        opts.name_IDs = ["*"]
        opts.name_legacy = True
        opts.name_languages = ["*"]

        subsetter = subset.Subsetter(options=opts)
        subsetter.populate(text=chars)
        subsetter.subset(font)

        out = OUT_DIR / f"NotoSansTC-Subset-{label}.ttf"
        font.save(str(out))
        font.close()
        made.append((out, out.stat().st_size))
    return made


def verify(path: Path, chars: str) -> list[str]:
    """Characters the built face still cannot draw."""
    from fontTools.ttLib import TTFont

    font = TTFont(str(path))
    cmap = font.getBestCmap()
    font.close()
    return sorted({c for c in chars if ord(c) not in cmap and c not in "\n\r\t"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=None,
                    help="OFL source font (default: search the usual places)")
    args = ap.parse_args()

    src = args.source or find_source()
    if src is None:
        print("[ERROR] No OFL source font found. Download Noto Sans TC from")
        print("        https://fonts.google.com/noto/specimen/Noto+Sans+TC and")
        print(f"        put NotoSansTC-VF.ttf in {OUT_DIR}, or pass --source.")
        return 1
    if src.name not in OFL_SOURCES:
        print(f"[ERROR] {src.name} is not a recognised OFL font. The bundled")
        print("        subset is redistributed with the repo, so its source has")
        print("        to be openly licensed - system faces such as msjh.ttc are")
        print("        not. Use Noto Sans TC.")
        return 1

    chars = wanted_chars()
    uniq = sorted(set(chars))
    cjk = [c for c in uniq if ord(c) > 0x2E80]
    print(f"[INFO] Source : {src}")
    print(f"[INFO] Glyphs : {len(uniq)} characters ({len(cjk)} CJK)")

    made = build(src, chars)
    if not made:
        print("[ERROR] Nothing was built.")
        return 1

    ok = True
    for out, size in made:
        missing = verify(out, "".join(uniq))
        # ASCII-safe: this may print on a console code page with no CJK.
        state = ("ok" if not missing else
                 "MISSING %d: %s" % (len(missing),
                                     " ".join(f"U+{ord(c):04X}" for c in missing[:20])))
        print(f"[INFO] {out.relative_to(_REPO_ROOT)}  {size / 1024:.0f} kB  {state}")
        ok = ok and not missing

    licence = OUT_DIR / "OFL.txt"
    if not licence.is_file():
        print()
        print(f"[WARN] {licence.relative_to(_REPO_ROOT)} is missing. OFL requires the")
        print("       licence to be redistributed with the font - copy OFL.txt from")
        print("       the Noto Sans TC download into assets/fonts/ before committing.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
