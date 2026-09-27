# assets/

Files the hub, the website and the test tools load, grouped by kind.

| Folder | What | Used by |
|---|---|---|
| `fonts/` | The Noto Sans TC subset for the OpenCV overlays. | `core/ui/components.py`, rebuilt by `tools/build_cjk_subset.py`. Left out of the website build. |
| `models/` | The rigged 3D hand (`hand.gltf`, plus `scene.bin`, which it loads by relative path, so the two stay together). | `launcher_web/hand3d.js` (home page) and `glove3d.js` (Developer page), at `/assets/models/`. |
| `videos/` | The home-page test card preview clips. | `TOOLS[].video` in `launcher_web/app.js`, at `/assets/videos/`. |
| `screenshots/<test>/` | Source screenshots for the test pages' pictures. | Not loaded directly. The pages use 960 px / 600 px WebP copies in `launcher_web/img/<test>/`, and these are left out of the website build. |

Add a new test's screenshots under `screenshots/<test>/` with kebab-case names. Then write their WebP copies into `launcher_web/img/<test>/` under the names that test's `README.md` lists.
