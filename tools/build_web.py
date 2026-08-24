#!/usr/bin/env python3
"""
Build the static, publicly hostable copy of the dashboard.

    python tools/build_web.py        ->  web-build/

launcher_web/ is normally served by launcher.py, which also answers /api/*,
serves /assets/ and serves the local-only research doc at /analysis. A static
host does none of that, so this script assembles a build that:

  * copies launcher_web/ to the web root and assets/ to /assets/
  * injects tools/web_static/static-api.js, which bridges /api/* to the hub
    running on the visitor's own machine and falls back to a preview when
    there is none (see that file)
  * runs tools/build_release.py, which puts the downloadable setup bundle in
    web-build/download/
  * rewrites the footer, which links to /analysis -- a docs/ file that is
    deliberately never published

Nothing from results/, docs/ or research/ is copied. Deploy with:

    firebase deploy --only hosting

Stdlib only, matching launcher.py and install.py.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_release  # noqa: E402 -- needs the path set above

REPO = Path(__file__).resolve().parents[1]
WEB_SRC = REPO / "launcher_web"
ASSETS_SRC = REPO / "assets"
# The participant's page (docs/REMOTE_SESSION_PLAN.md). Served at /s/<token>;
# firebase.json rewrites every /s/** path onto its index.html, which reads the
# token out of location.pathname.
PARTICIPANT_SRC = REPO / "participant"
SHIM_SRC = REPO / "tools" / "web_static" / "static-api.js"
OUT = REPO / "web-build"

# Injected ahead of every other script so the fetch wrapper is installed
# before app.js makes its first /api/status call.
SHIM_TAG = '<script src="/static-api.js"></script>\n'
SHIM_ANCHOR = '<script src="/i18n.zh.js"></script>'

# The footer is matched exactly: if index.html changes, fail loudly rather
# than silently shipping the /analysis link to a public host.
FOOTER_OLD = """    <div class="footer" data-i18n="home.footer">
      Local hub &#183; 127.0.0.1 &#183; no data leaves this machine &#183;
      <a href="/analysis" target="_blank">Full research analysis</a>
    </div>"""

FOOTER_NEW = """    <div class="footer" data-i18n="home.footer">
      Published dashboard &#183; drives the hub on your own machine &#183;
      results stay there, nothing is stored on this site
    </div>"""

FOOTER_ZH = (
    "\n/* Hosted-preview override, appended by tools/build_web.py. */\n"
    "window.ZH[\"home.footer\"] = `線上儀表板 &#183; 由您自己電腦上的 Hub 執行 &#183;\n"
    "      結果留在該電腦，本站不儲存任何資料`;\n"
)


def fail(msg: str) -> None:
    print(f"build_web: {msg}", file=sys.stderr)
    raise SystemExit(1)


def clean(out: Path) -> None:
    """Empty the build directory, deepest entry first.

    Not shutil.rmtree: the repo lives under OneDrive, which keeps a handle on
    directories it is syncing and makes rmdir fail with WinError 5. Removing
    the *files* is what actually prevents a stale build; a directory that
    refuses to go is harmless, since the copy below writes straight into it.
    """
    if not out.exists():
        return
    for p in sorted(out.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        try:
            p.unlink() if p.is_file() or p.is_symlink() else p.rmdir()
        except OSError:
            pass


def replace_once(text: str, old: str, new: str, what: str) -> str:
    n = text.count(old)
    if n != 1:
        fail(f"expected exactly one {what} in index.html, found {n}. "
             "The markup changed -- update tools/build_web.py.")
    return text.replace(old, new)


def main() -> None:
    for p in (WEB_SRC, ASSETS_SRC, SHIM_SRC, PARTICIPANT_SRC):
        if not p.exists():
            fail(f"missing {p.relative_to(REPO)}")

    clean(OUT)
    shutil.copytree(WEB_SRC, OUT, dirs_exist_ok=True)
    # assets/fonts/ is the bundled CJK subset for the OpenCV overlays; the
    # site never draws with it, so it stays out of the published build.
    shutil.copytree(ASSETS_SRC, OUT / "assets", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("fonts"))
    shutil.copy2(SHIM_SRC, OUT / "static-api.js")

    # Participant page -> /s/. Its tests/ and package.json are development
    # files and must not ship; vectors.json alone is 71 KB of fixtures.
    if PARTICIPANT_SRC.exists():
        shutil.copytree(
            PARTICIPANT_SRC, OUT / "s", dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("tests", "package.json", "*.md"))

    index = OUT / "index.html"
    html = index.read_text(encoding="utf-8")
    html = replace_once(html, SHIM_ANCHOR, SHIM_TAG + SHIM_ANCHOR, "i18n.zh.js script tag")
    html = replace_once(html, FOOTER_OLD, FOOTER_NEW, "local-hub footer")
    index.write_text(html, encoding="utf-8")

    zh = OUT / "i18n.zh.js"
    zh.write_text(zh.read_text(encoding="utf-8") + FOOTER_ZH, encoding="utf-8")

    build_release.main()   # after clean(), which would have removed download/

    files = sorted(p for p in OUT.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"build_web: {len(files)} files, {total / 1_048_576:.1f} MB -> {OUT}")
    if not (OUT / "s" / "index.html").exists():
        fail("participant page did not reach web-build/s/")
    print("build_web: participant page -> /s/<token>")
    print("build_web: next step -> firebase deploy --only hosting,firestore:rules")


if __name__ == "__main__":
    main()
