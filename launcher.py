"""
Hand-Detection-3D — Launcher Hub
================================
A self-contained local web app that connects every tool in this project and
presents the research behind it. Run it, and it opens a dashboard in your
browser with:

  - System status  (Python, model file, OpenCV, MediaPipe)
  - One-click launch for each tool:
        * IIV Finger Tapping Test   (iiv_test.py)
        * Spiral Tracing Test       (spiral_test.py)
        * Hand Tracking / UDP       (hand_tracking.py)
  - The Alzheimer's motor-biomarker research summary
  - A link to the full analysis document

Standard library only — no extra pip installs — so it also packages into a
single .exe with PyInstaller (see BUILD_LAUNCHER.md).

Run:   python launcher.py
Quit:  press Ctrl+C in this console, or close the window.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.path.join(BASE_DIR, "model", "hand_landmarker.task")
ANALYSIS_FILE = os.path.join(BASE_DIR, "docs", "alzheimers_hand_tracking_analysis.md")

HOST = "127.0.0.1"
PORT = 8770

# ── Tool registry ──────────────────────────────────────────────────────────
# key -> (script filename, human title)
TOOLS: dict[str, tuple[str, str]] = {
    "iiv":      (os.path.join("screening_tests", "iiv_test.py"),    "IIV Finger Tapping Test"),
    "spiral":   (os.path.join("screening_tests", "spiral_test.py"), "Spiral Tracing Test"),
    "tracking": (os.path.join("core", "hand_tracking.py"),          "Hand Tracking / UDP Broadcast"),
}

# key -> live subprocess.Popen (only while running)
_procs: dict[str, subprocess.Popen] = {}
_procs_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────

def _dep_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _running(key: str) -> bool:
    """True if the tool's process exists and has not exited."""
    with _procs_lock:
        proc = _procs.get(key)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        # Exited — clean it up.
        _procs.pop(key, None)
        return False


def launch_tool(key: str) -> tuple[bool, str]:
    """Spawn the tool's script in its own console. Returns (ok, message)."""
    if key not in TOOLS:
        return False, f"Unknown tool: {key}"

    if _running(key):
        return False, "Already running."

    # Only one tool can hold the webcam at a time.
    for other in TOOLS:
        if other != key and _running(other):
            return False, f"'{TOOLS[other][1]}' is using the camera. Stop it first."

    script, _title = TOOLS[key]
    script_path = os.path.join(BASE_DIR, script)
    if not os.path.exists(script_path):
        return False, f"Script not found: {script}"

    # Give each tool its own console so print()/input() (e.g. the camera
    # prompt in hand_tracking.py) have somewhere to go.
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=BASE_DIR,
            creationflags=creationflags,
        )
    except OSError as exc:
        return False, f"Failed to launch: {exc}"

    with _procs_lock:
        _procs[key] = proc
    return True, "Launched."


def stop_tool(key: str) -> tuple[bool, str]:
    with _procs_lock:
        proc = _procs.get(key)
    if proc is None or proc.poll() is not None:
        return False, "Not running."
    try:
        proc.terminate()
    except OSError as exc:
        return False, f"Failed to stop: {exc}"
    return True, "Stopping."


def status_payload() -> dict:
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "model_present": os.path.exists(MODEL_FILE),
        "opencv": _dep_present("cv2"),
        "mediapipe": _dep_present("mediapipe"),
        "analysis_present": os.path.exists(ANALYSIS_FILE),
        "running": {key: _running(key) for key in TOOLS},
    }


# ── HTTP Handler ───────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    # Silence the default per-request logging noise.
    def log_message(self, *args):  # noqa: D401
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._send_json(status_payload())
        elif self.path == "/analysis":
            if os.path.exists(ANALYSIS_FILE):
                with open(ANALYSIS_FILE, "r", encoding="utf-8") as fh:
                    text = fh.read()
                self._send(200, text.encode("utf-8"), "text/plain; charset=utf-8")
            else:
                self._send(404, b"Analysis document not found.", "text/plain; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            data = {}
        key = data.get("test", "")

        if self.path == "/api/launch":
            ok, msg = launch_tool(key)
            self._send_json({"ok": ok, "message": msg, "running": status_payload()["running"]})
        elif self.path == "/api/stop":
            ok, msg = stop_tool(key)
            self._send_json({"ok": ok, "message": msg, "running": status_payload()["running"]})
        else:
            self._send_json({"ok": False, "message": "Unknown endpoint"}, code=404)


# ── Front-end (single self-contained page) ─────────────────────────────────

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hand-Detection-3D — Control Hub</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel-2:#1c2330; --line:#2a3240;
    --text:#e6edf3; --muted:#8b95a3; --accent:#4c9eff; --accent-2:#7c5cff;
    --green:#3fb950; --amber:#d29922; --red:#f85149;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--text);line-height:1.55;}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  .wrap{max-width:1040px;margin:0 auto;padding:32px 22px 64px;}
  header.hero{padding:8px 0 22px;border-bottom:1px solid var(--line);margin-bottom:26px;}
  .badge{display:inline-block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
         color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:4px 12px;margin-bottom:14px;}
  h1{margin:0 0 8px;font-size:30px;letter-spacing:-.02em;}
  .sub{color:var(--muted);max-width:70ch;margin:0;}
  h2{font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
     margin:34px 0 14px;font-weight:600;}
  /* Status bar */
  .status{display:flex;flex-wrap:wrap;gap:10px;margin-top:6px;}
  .chip{display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);
        border-radius:8px;padding:8px 13px;font-size:13px;}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--muted);flex:none;}
  .dot.ok{background:var(--green);box-shadow:0 0 8px rgba(63,185,80,.5)}
  .dot.bad{background:var(--red);box-shadow:0 0 8px rgba(248,81,73,.5)}
  .chip b{color:var(--text);font-weight:600}
  .chip span{color:var(--muted)}
  /* Tool cards */
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;}
  .card{background:linear-gradient(180deg,var(--panel),var(--panel-2));border:1px solid var(--line);
        border-radius:14px;padding:20px;display:flex;flex-direction:column;position:relative;overflow:hidden;}
  .card::before{content:"";position:absolute;inset:0 0 auto 0;height:3px;
                background:linear-gradient(90deg,var(--accent),var(--accent-2));opacity:.9}
  .card h3{margin:6px 0 4px;font-size:18px;}
  .card .file{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;color:var(--muted);}
  .card p{color:var(--muted);font-size:14px;margin:12px 0 14px;flex:1;}
  .meta{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px;}
  .tag{font-size:11.5px;color:var(--text);background:#20283420;border:1px solid var(--line);
       border-radius:6px;padding:3px 8px;}
  .row{display:flex;align-items:center;gap:10px;}
  button{font:inherit;font-size:14px;font-weight:600;border:none;border-radius:9px;padding:10px 16px;
         cursor:pointer;transition:filter .15s,opacity .15s;}
  .btn-go{background:var(--accent);color:#04122b;flex:1;}
  .btn-go:hover{filter:brightness(1.08)}
  .btn-stop{background:transparent;color:var(--red);border:1px solid var(--red);}
  .btn-stop:hover{background:rgba(248,81,73,.12)}
  button:disabled{opacity:.5;cursor:not-allowed;filter:none}
  .live{display:none;align-items:center;gap:7px;font-size:12.5px;color:var(--green);margin-bottom:12px;}
  .live.on{display:flex}
  .pulse{width:8px;height:8px;border-radius:50%;background:var(--green);animation:pulse 1.2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
  /* Research */
  .research{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:24px 26px;}
  .research p{color:var(--muted);}
  .research strong{color:var(--text)}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:6px;}
  .metric{border-left:2px solid var(--accent);padding-left:14px;}
  .metric h4{margin:0 0 4px;font-size:15px;color:var(--text)}
  .metric span{font-size:13.5px;color:var(--muted)}
  .disclaimer{margin-top:20px;font-size:13px;color:var(--amber);background:rgba(210,153,34,.08);
              border:1px solid rgba(210,153,34,.3);border-radius:8px;padding:12px 14px;}
  footer{margin-top:34px;color:var(--muted);font-size:12.5px;text-align:center;}
  .toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(20px);
         background:var(--panel-2);border:1px solid var(--line);color:var(--text);padding:11px 18px;
         border-radius:10px;font-size:14px;opacity:0;pointer-events:none;transition:.25s;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  .toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
  @media(max-width:640px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <span class="badge">Motor Biomarker Suite</span>
    <h1>Hand-Detection-3D — Control Hub</h1>
    <p class="sub">Real-time hand tracking with OpenCV + MediaPipe. Launch each tool, check your
    environment, and read the research behind the two Alzheimer's motor-screening tests — all from here.</p>
  </header>

  <h2>System Status</h2>
  <div class="status" id="status"><div class="chip"><span>Checking…</span></div></div>

  <h2>Tools</h2>
  <div class="cards" id="cards"></div>

  <h2>Research Background</h2>
  <div class="research">
    <p>Two of the tools above are experimental screening tests grounded in a 2024 systematic review
    (<strong>Namkoong &amp; Roh, <em>Technology and Health Care</em> 32(S1):253–264</strong>), which found hand
    dexterity "strongly correlated with cognitive function in all 17 studies reviewed." The hand acts as a
    <strong>peripheral readout of central neurodegeneration</strong>: fine motor control simultaneously exercises the
    motor cortex, basal ganglia automaticity loops, and cerebellar timing — the same circuits Alzheimer's erodes
    early, often before cognitive symptoms are salient enough to diagnose.</p>
    <div class="grid2">
      <div class="metric">
        <h4>Rhythm variability (IIV)</h4>
        <span>Roalf et al. (2018): intra-individual variability of inter-tap intervals is elevated across
        neurodegenerative groups. The <em>IIV Finger Tapping Test</em> measures tap-to-tap consistency.</span>
      </div>
      <div class="metric">
        <h4>Movement smoothness</h4>
        <span>Schroter et al. (2003) &amp; Kachouri et al. (2021): AD produces irregular, less-automated movement.
        The <em>Spiral Tracing Test</em> measures path deviation, velocity variation, and normalized jerk.</span>
      </div>
    </div>
    <p style="margin-top:20px"><a href="/analysis" target="_blank">Open the full research analysis&nbsp;→</a></p>
    <div class="disclaimer">These tests are research prototypes, <strong>not medical diagnostics</strong>.
    Results are not a diagnosis. Consult a healthcare professional for any clinical concern.</div>
  </div>

  <footer>Local hub · served at 127.0.0.1 · no data leaves this machine</footer>
</div>

<div class="toast" id="toast"></div>

<script>
const TOOLS = [
  { key:"iiv", title:"IIV Finger Tapping Test", file:"iiv_test.py",
    desc:"Tap index-to-thumb on each beep for 30 s. Scores rhythm consistency (intra-individual variability of tap intervals).",
    tags:["30 s test","1 hand","Audio metronome"] },
  { key:"spiral", title:"Spiral Tracing Test", file:"spiral_test.py",
    desc:"Trace an Archimedes spiral with your index fingertip for 40 s. Scores path deviation, velocity variation, and smoothness.",
    tags:["40 s test","1 hand","On-screen guide"] },
  { key:"tracking", title:"Hand Tracking / UDP Broadcast", file:"hand_tracking.py",
    desc:"Streams 21 hand landmarks (x, y, z) over UDP to 127.0.0.1:5052 for the Unity receiver. Prompts for camera in its console.",
    tags:["Live stream","2 hands","UDP :5052"] },
];

const cardsEl = document.getElementById("cards");
const statusEl = document.getElementById("status");
const toastEl = document.getElementById("toast");
let toastTimer = null;

function toast(msg){
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>toastEl.classList.remove("show"), 2600);
}

function renderCards(running){
  cardsEl.innerHTML = "";
  for(const t of TOOLS){
    const on = running && running[t.key];
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="file">${t.file}</div>
      <h3>${t.title}</h3>
      <div class="live ${on?"on":""}"><span class="pulse"></span>Running — check the camera window</div>
      <p>${t.desc}</p>
      <div class="meta">${t.tags.map(x=>`<span class="tag">${x}</span>`).join("")}</div>
      <div class="row">
        <button class="btn-go" data-go="${t.key}" ${on?"disabled":""}>${on?"Running…":"▶ Launch"}</button>
        <button class="btn-stop" data-stop="${t.key}" ${on?"":"disabled"}>Stop</button>
      </div>`;
    cardsEl.appendChild(card);
  }
  cardsEl.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>act("launch", b.dataset.go));
  cardsEl.querySelectorAll("[data-stop]").forEach(b=>b.onclick=()=>act("stop", b.dataset.stop));
}

function chip(ok, label, value){
  const cls = ok ? "ok" : "bad";
  return `<div class="chip"><span class="dot ${cls}"></span><b>${label}</b>&nbsp;<span>${value}</span></div>`;
}

function renderStatus(s){
  let html = "";
  html += chip(true, "Python", s.python);
  html += chip(s.model_present, "Model", s.model_present ? "hand_landmarker.task" : "missing");
  html += chip(s.opencv, "OpenCV", s.opencv ? "installed" : "missing");
  html += chip(s.mediapipe, "MediaPipe", s.mediapipe ? "installed" : "missing");
  statusEl.innerHTML = html;
  renderCards(s.running);
}

async function refresh(){
  try{
    const r = await fetch("/api/status");
    renderStatus(await r.json());
  }catch(e){ /* server closing */ }
}

async function act(kind, key){
  try{
    const r = await fetch("/api/"+kind, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({test:key})
    });
    const data = await r.json();
    toast(data.message || (data.ok?"Done":"Failed"));
    if(data.running) renderCards(data.running);
    setTimeout(refresh, 400);
  }catch(e){ toast("Request failed"); }
}

refresh();
setInterval(refresh, 2500);
</script>
</body>
</html>
"""


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    global PORT
    server = None
    # Find a free port starting at the default.
    for candidate in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer((HOST, candidate), Handler)
            PORT = candidate
            break
        except OSError:
            continue
    if server is None:
        print("[ERROR] Could not bind to a port in range.")
        sys.exit(1)

    url = f"http://{HOST}:{PORT}/"
    print("=" * 56)
    print("  Hand-Detection-3D — Control Hub")
    print("=" * 56)
    print(f"  Dashboard:  {url}")
    print("  Opening your browser… (Ctrl+C here to quit)")
    print("=" * 56)

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down hub.")
    finally:
        # Leave launched tools running; just close the server.
        server.server_close()


if __name__ == "__main__":
    main()
