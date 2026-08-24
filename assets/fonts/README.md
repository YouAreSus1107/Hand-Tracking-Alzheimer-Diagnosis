# Bundled overlay font

`NotoSansTC-Subset-Regular.ttf` and `NotoSansTC-Subset-Bold.ttf` are subsets of
**Noto Sans TC**, cut down to exactly the characters the Traditional-Chinese
overlays use (`core/i18n_zh.py`) plus printable ASCII — about 330 characters,
82 kB per weight instead of ~9 MB.

They exist because PIL does no per-glyph fallback: a face without 敲 draws a box,
not the character. `core/ui/components.py` tries these first, then the machine's
own CJK faces, and if nothing covers the text `core/i18n.py` degrades the whole
run to English rather than paint tofu. Only this layer is under our control, so
a laptop with no Traditional-Chinese language pack still gets Chinese overlays.

Rebuild after adding strings to `core/i18n_zh.py` — new characters are not in
the subset until you do:

    .venv/Scripts/python tools/build_cjk_subset.py

## Licence

Noto Sans TC is licensed under the **SIL Open Font License 1.1**, which permits
subsetting and redistribution provided the licence travels with the font. Put
the upstream `OFL.txt` beside these files (it ships with the Noto Sans TC
download from <https://fonts.google.com/noto/specimen/Noto+Sans+TC>); the build
tool warns while it is missing.

The build tool only accepts recognised OFL sources. System faces such as
`msjh.ttc` (Microsoft JhengHei) are proprietary and must never be used here,
however convenient they are on Windows.
