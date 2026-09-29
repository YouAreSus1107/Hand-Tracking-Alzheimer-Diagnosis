/* ── SVG Icon library (style guide section 8: 2px stroke, rounded) ── */
const I = {
  hand: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 12V6.5a1.25 1.25 0 0 1 2.5 0V11"/><path d="M10.5 11V5a1.25 1.25 0 0 1 2.5 0v6"/><path d="M13 11.5V6a1.25 1.25 0 0 1 2.5 0v6"/><path d="M15.5 12.5V9a1.25 1.25 0 0 1 2.5 0v4.5a6 6 0 0 1-6 6h-.5a6 6 0 0 1-5.3-3.2l-1.5-2.9a1.25 1.25 0 0 1 2.1-1.3L10 13"/></svg>',
  spiral: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 12a1.5 1.5 0 0 1 1.5 1.5A3 3 0 0 1 10.5 16.5 4.5 4.5 0 0 1 6 12a6 6 0 0 1 6-6 7.5 7.5 0 0 1 7.5 7.5A9 9 0 0 1 10.5 22.5"/></svg>',
  broadcast: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="13" rx="2"/><circle cx="12" cy="11.5" r="3.5"/><circle cx="17.5" cy="7.5" r="1" fill="currentColor" stroke="none"/><path d="M8 21h8"/><path d="M12 18v3"/></svg>',
  mic: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="8" y1="22" x2="16" y2="22"/></svg>',
  eye: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>',
  wave: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l2-5 3 10 3-12 3 12 2-5h4"/></svg>',
  walk: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="13" cy="4" r="2"/><path d="M11 21l2-6-3-3 1-5 4 3 3 1"/><path d="M10 12l-2 4-3 1"/><path d="M13 15l3 6"/></svg>',
  play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="6,3 20,12 6,21"/></svg>',
  stop: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>',
  check: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  x: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  arrowLeft: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>',
  arrowRight: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>',
  clock: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  wave: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12c2-3 4-3 6 0s4 3 6 0 4-3 6 0"/><path d="M2 18c2-3 4-3 6 0s4 3 6 0 4-3 6 0"/></svg>',
  beaker: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6v7l4 8H5l4-8V3z"/><line x1="8" y1="3" x2="16" y2="3"/></svg>',
  home: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5L12 3l9 7.5"/><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/><path d="M9.5 21v-5.5a2.5 2.5 0 0 1 5 0V21"/></svg>',
  chart: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/><circle cx="7" cy="14" r="1.1" fill="currentColor" stroke="none"/><circle cx="11" cy="10" r="1.1" fill="currentColor" stroke="none"/><circle cx="14" cy="13" r="1.1" fill="currentColor" stroke="none"/><circle cx="19" cy="7" r="1.1" fill="currentColor" stroke="none"/></svg>',
  up: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="6 11 12 5 18 11"/></svg>',
  down: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="6 13 12 19 18 13"/></svg>',
  minus: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  scale: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M7 21h10"/><path d="M6 7l-4 6a4 4 0 0 0 8 0L6 7z"/><path d="M18 7l-4 6a4 4 0 0 0 8 0l-4-6z"/><path d="M4 7h16"/></svg>',
  code: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
  lock: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
  layers: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
  shield: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>',
  camera: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h4l2-2h6l2 2h4v12H3z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  person: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/></svg>',
  image: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M21 16l-5-5-9 9"/></svg>',
  chevron: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
  refresh: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><polyline points="20 4 20 11 13 11"/></svg>',
  stream: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="20" rx="2"/><line x1="11" y1="18" x2="13" y2="18"/></svg>',
};

const TOOLS = [
  { key:"iiv", title:"Finger Tapping Test", file:"finger_tapping.py", icon:"hand",
    tags:["30 s test","1 hand","Audio metronome","Paced tapping"],
    video:"/assets/videos/finger-tapping.mp4" },
  { key:"spiral", title:"Spiral Tracing Test", file:"spiral_test.py", icon:"spiral",
    tags:["40 s test","1 hand","On-screen guide","Air tracing"],
    video:"/assets/videos/spiral-test.mp4" },
  { key:"oculomotor", title:"Eye Movement Test", file:"oculomotor_test.py", icon:"eye",
    tags:["~4 min test","Pro + anti-saccade","Webcam gaze","Error rate headline"],
    // This clip is a capture of the test UI, which already dims its own camera
    // feed; the idle veil on top of that leaves it unreadable. Play it bright.
    video:"/assets/videos/eye-movement.mp4", dimPreview:false },
  { key:"ddk", title:"Speech Test", file:"speech_test.py", icon:"mic",
    tags:["2 short parts","Microphone only","Pa-ta-ka","Sustained ahh"],
    // No preview clip yet: a still of the loudness envelope the test scores,
    // one peak per syllable with its onset dot, stands in for it.
    art:(()=>{
      const xs = [0,1,2,3,4,5,6,7,8,9,10,11].map(i => 22 + i*30);
      const peaks = xs.map((x,i)=>{
        const h = 38 + ((i*37)%3)*9;
        return `M${x-10},120 C${x-6},120 ${x-5},${120-h} ${x},${120-h} C${x+5},${120-h} ${x+6},120 ${x+12},120`;
      }).join(" ");
      return `<svg class="card-art" viewBox="0 0 380 150" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <line x1="10" y1="120" x2="370" y2="120" stroke="var(--border)" stroke-width="1"/>
        <path d="${peaks}" fill="none" stroke="var(--brand)" stroke-width="2.2" stroke-linejoin="round"/>
        ${xs.map(x=>`<circle cx="${x-5}" cy="120" r="3" fill="var(--success)"/>`).join("")}
      </svg>`;
    })() },
  { key:"tremor", title:"Hand Tremor Test", file:"tremor_test.py", icon:"wave",
    // A supporting check, not a screening result (the way paced tapping sits
    // beside Big & Fast): docs/tests/TREMOR_RESTRUCTURE_PLAN.md §2.
    tags:["Supporting check","~2 min test","2 hands","Glove IMU optional"],
    // No preview clip yet: a still of what the test computes — one hand's
    // tremor-band spectrum with a single peak standing out of the noise.
    art:(()=>{
      const pts = [];
      for(let i=0;i<=60;i++){
        const f = i/60, x = 20 + f*340;
        const peak = 70*Math.exp(-Math.pow((f-0.36)/0.035,2));
        const noise = 6 + 4*Math.abs(Math.sin(i*1.7)) + 3*Math.abs(Math.sin(i*0.61));
        pts.push(`${x.toFixed(1)},${(122-noise-peak).toFixed(1)}`);
      }
      return `<svg class="card-art" viewBox="0 0 380 150" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <rect x="${20+340*0.15}" y="20" width="${340*0.72}" height="102" fill="var(--brand)" opacity=".07"/>
        <line x1="10" y1="122" x2="370" y2="122" stroke="var(--border)" stroke-width="1"/>
        <polyline points="${pts.join(" ")}" fill="none" stroke="var(--brand)" stroke-width="2.2" stroke-linejoin="round"/>
        <circle cx="${20+340*0.36}" cy="${122-6-70}" r="4" fill="var(--warning)"/>
      </svg>`;
    })() },
  { key:"gait", title:"Walking Test", file:"gait_test.py", icon:"walk",
    tags:["~2 min, seated","Side-on camera","Leg stamps","5 sit-to-stands"],
    // No preview clip yet: a still of the sit-to-stand trace the test scores,
    // the hip rising to standing and back, five times, each stand marked.
    art:(()=>{
      const pts = [];
      for(let i=0;i<=100;i++){
        const f = i/100, x = 20 + f*340;
        const ph = (f*5) % 1;
        const s = Math.max(0, Math.min(1, ph < .45 ? ph/.3 : ph < .6 ? 1 : 1 - (ph-.6)/.3));
        pts.push(`${x.toFixed(1)},${(122 - 86*s).toFixed(1)}`);
      }
      const ups = [0,1,2,3,4].map(k => 20 + ((k + .3)/5)*340);
      return `<svg class="card-art" viewBox="0 0 380 150" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <line x1="10" y1="122" x2="370" y2="122" stroke="var(--border)" stroke-width="1"/>
        <line x1="10" y1="${122-86*.75}" x2="370" y2="${122-86*.75}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 4"/>
        <polyline points="${pts.join(" ")}" fill="none" stroke="var(--brand)" stroke-width="2.2" stroke-linejoin="round"/>
        ${ups.map(x=>`<circle cx="${x.toFixed(1)}" cy="${122-86*.75}" r="3.5" fill="var(--success)"/>`).join("")}
      </svg>`;
    })() },
  { key:"tracking", title:"Hand Tracking / UDP", file:"hand_tracking.py", icon:"broadcast",
    tags:["Live stream","2 hands","UDP :5052","21 landmarks"],
    video:"/assets/videos/hand-tracking.mp4" },
];

const RESEARCH = [
  { icon:"clock", title:"Motor \u2014 rhythm and movement",
    text:"Finger tapping measures how much the gaps between taps vary. That variability is higher in neurodegenerative groups than in controls. Spiral tracing adds movement smoothness (SPARC), speed variation, and normalized jerk.",
    cite:"Roalf et al. (2018) \u00b7 Wang et al. (2025) \u00b7 PMC11496774" },
  { icon:"eye", title:"Oculomotor \u2014 inhibitory control",
    text:"The anti-saccade error rate counts how often the eyes are pulled toward a target you were told to look away from. Meta-analysis puts the effect separating Alzheimer's groups from controls at SMD 1.59.",
    cite:"Opwonya et al. (2022) \u00b7 Crawford et al. (2005) \u00b7 PMC9090874" },
  { icon:"mic", title:"Speech \u2014 articulatory rhythm",
    text:"Repeating pa-ta-ka as fast and evenly as possible is the speech counterpart of finger tapping, scored the same way: how much the gaps between syllables vary. Language measures such as word-finding pauses are planned next.",
    cite:"Li et al., TapTalk (2024) \u00b7 docs/tests/SPEECH_TEST_PLAN.md" },
  { icon:"home", title:"The method works at home",
    text:"MediaPipe tapping matched Polhemus electromagnetic sensors within \u00b11 Hz about 90% of the time, and 404 adults with no symptoms completed unsupervised webcam testing at home. Both studies validate the approach, not this implementation.",
    cite:"Li et al., TapTalk (2024) \u00b7 TAS Test (2022\u20132025) \u00b7 PMC10809289" },
];

/* ── "Why This" page data (differentiation) ──────────────────────────
   Source of truth: docs/research/README.md (TAS Test framing),
   docs/research/01-webcam-hand-motor.md (finger-tapping vs TapTalk table),
   docs/overview/ROADMAP.md §1 & §7. Keep claims honest — the validation row
   deliberately shows where TAS Test is ahead. */
const WHY_PILLARS = [
  { icon:"code", title:"Open source",
    text:"Every script is on GitHub, including the scoring code." },
  { icon:"lock", title:"Runs locally",
    text:"Nothing leaves the machine. The hub serves on 127.0.0.1 and results stay on disk." },
  { icon:"layers", title:"Three domains, one system",
    text:"Hand-motor, oculomotor and speech tests in the same session, written to the same results format." },
  { icon:"shield", title:"Thresholds shown as provisional",
    text:"Each metric links the paper it came from, and bands not yet fitted to data are labelled as such." },
];

// Cell states → status token + word. Word is always shown next to the icon so
// meaning never rides on colour alone (UI_STYLE_GUIDE §2.4).
const CMP_STATES = {
  yes:     { icon:"check", word:"Yes",     cls:"st-yes" },
  no:      { icon:"x",     word:"No",      cls:"st-no" },
  partial: { icon:"minus", word:"Partial", cls:"st-partial" },
  planned: { icon:"clock", word:"Planned", cls:"st-planned" },
  notyet:  { icon:"clock", word:"Not yet", cls:"st-planned" },
};
const CMP_COLS = ["This suite", "Consumer apps", "TAS Test (research)"];
const WHY_MATRIX = [
  { cap:"Motor biomarkers (tapping, spiral)",      cells:["yes","no","yes"] },
  { cap:"Oculomotor anti-saccade",                 cells:["yes","no","no"] },
  { cap:"Speech tasks",                            cells:["partial","no","yes"] },
  { cap:"Camera-only, no wearable needed",         cells:["yes","yes","yes"] },
  { cap:"Open-source / inspectable",               cells:["yes","no","no"] },
  { cap:"Fully local, no data upload",             cells:["yes","no","no"] },
  { cap:"Longitudinal self-tracking",              cells:["yes","partial","yes"] },
  { cap:"Literature-cited metrics shown in-app",   cells:["yes","no","partial"] },
  // Partial: tapping checked on HUBU-FIS (Parkinson's, UPDRS), not yet on cognitive decline.
  { cap:"Validated on patient cohorts",            cells:["partial","no","yes"] },
  { cap:"Wearable co-contraction twin",            cells:["planned","no","no"] },
];

let currentRunning = {};
let cardsBuilt = false;
let carousel = null;
// A language switch rebuilds the cards, so initCarousel runs again; its
// window-level listeners are torn down with this rather than stacking up.
let carouselAbort = null;
let whyBuilt = false;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ── Inject SVG icons into detail pages + research cards ─────────── */
function renderStaticBits(){
  // Detail page icons
  const map = {iiv:"hand", spiral:"spiral", oculomotor:"eye", ddk:"mic", tremor:"wave", gait:"walk", tracking:"broadcast"};
  for(const [k,v] of Object.entries(map)){
    const el = document.getElementById("detail-icon-"+k);
    if(el) el.innerHTML = I[v];
  }
  // Back buttons
  document.querySelectorAll(".detail-back").forEach(b=>{
    b.innerHTML = I.arrowLeft + " " + t("Back to Dashboard");
  });
  // Placeholder frames for illustrations not drawn yet
  document.querySelectorAll(".art-slot .slot-ico").forEach(el => el.innerHTML = I.image);
  // Analysis header icon
  const ai = document.getElementById("analysis-icon");
  if(ai) ai.innerHTML = I.chart;
  // Why-this header icon
  const wi = document.getElementById("why-icon");
  if(wi) wi.innerHTML = I.scale;
  // About-me header icon
  const bi = document.getElementById("about-icon");
  if(bi) bi.innerHTML = I.person;
  // Research cards
  const rc = document.getElementById("research-cards");
  if(rc) rc.innerHTML = RESEARCH.map(r => `<div class="r-card">
    <div class="r-content">
      <h4>${I[r.icon]} ${t(r.title)}</h4>
      <p>${t(r.text)}</p>
      <div class="r-cite">${t(r.cite)}</div>
    </div>
    <div class="r-peel">
      <div class="peel-layer peel-l1"></div>
      <div class="peel-layer peel-l2"></div>
      <div class="peel-layer peel-l3"></div>
      <div class="peel-layer peel-cover">
        <div class="peel-face">${I[r.icon]}<span>${t(r.title)}</span></div>
      </div>
    </div>
  </div>`).join("");
}
renderStaticBits();

/* ── Page navigation ─────────────────────────────────────────────── */
function showPage(id){
  // The report panel belongs to the Analysis page; leaving it open over
  // another page would be a dialog with nothing behind it.
  // Resolve the target before deactivating anything: an unknown id used to
  // clear every page and then throw inside the callback, leaving the app blank
  // with no way back.
  const next = document.getElementById("page-"+id);
  if(!next) return;
  window.closeReport?.();
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  // The frame gap lets the fade-in play. rAF is suspended while the tab is
  // hidden, so activate straight away there — otherwise every page stays off
  // and the dashboard is blank until it returns to the foreground.
  const activate = ()=>{
    next.classList.add("active");
    window.scrollTo({top:0,behavior:"smooth"});
  };
  if(document.hidden) activate(); else requestAnimationFrame(activate);
  document.querySelectorAll(".nav-link").forEach(n =>
    n.classList.toggle("active", n.dataset.page===id));
  // A drop-down trigger carries the marker for whichever of its pages is on.
  document.querySelectorAll(".nav-group").forEach(g =>
    g.querySelector(".nav-trigger").classList.toggle(
      "active", !!g.querySelector(".nav-link.active")));
  if(TOOLS.find(tool=>tool.key===id)) renderDetailActions(id);
  if(id==="analysis") loadAnalysis();
  if(id==="why") renderWhy();
  // dev.js owns a ~100 ms poll; it must only run while its page is on screen.
  if(id==="dev") window.startDev?.(); else window.stopDev?.();
  // remote.js owns a 10 s poll; same rule as dev.js.
  if(id==="remote") window.startRemote?.(); else window.stopRemote?.();
}
document.querySelectorAll(".nav-link").forEach(n =>
  n.addEventListener("click", ()=> showPage(n.dataset.page)));

/* ── Nav drop-downs ──────────────────────────────────────────────── */
const navGroups = Array.from(document.querySelectorAll(".nav-group"));
function openNavGroup(g, open){
  g.classList.toggle("open", open);
  g.querySelector(".nav-trigger").setAttribute("aria-expanded", open ? "true" : "false");
}
function closeNavMenus(except){
  navGroups.forEach(g => { if(g!==except) openNavGroup(g, false); });
}
navGroups.forEach(g => {
  const trigger = g.querySelector(".nav-trigger");
  // Hover opens it (mouse only — a touch tap has no hover to leave, so it
  // would open and never close). A short close delay survives the gap
  // between the trigger and the menu below it and moving diagonally onto
  // the menu itself, rather than snapping shut mid-move.
  let closeTimer = null;
  const hoverOpen = () => {
    if(!matchMedia("(hover: hover)").matches) return;
    clearTimeout(closeTimer);
    closeNavMenus(g);
    openNavGroup(g, true);
  };
  const hoverClose = () => {
    if(!matchMedia("(hover: hover)").matches) return;
    clearTimeout(closeTimer);
    closeTimer = setTimeout(()=> openNavGroup(g, false), 150);
  };
  g.addEventListener("mouseenter", hoverOpen);
  g.addEventListener("mouseleave", hoverClose);
  trigger.addEventListener("click", e => {
    // Without this the document handler below would close it again in the
    // same click. Still needed for touch/keyboard, which get no hover.
    e.stopPropagation();
    const open = !g.classList.contains("open");
    closeNavMenus(g);
    openNavGroup(g, open);
  });
});
// A pick inside the menu bubbles here too, so choosing a page also closes it.
document.addEventListener("click", ()=> closeNavMenus());
document.addEventListener("keydown", e => { if(e.key==="Escape") closeNavMenus(); });

/* ── Card rendering (build once, update surgically) ──────────────── */
const cardsEl = document.getElementById("cards");

function buildCards(){
  cardsEl.innerHTML = "";
  // `tool`, not `t` — `t` is the translator (i18n.js).
  TOOLS.forEach((tool,i) => {
    const on = !!currentRunning[tool.key];
    const card = document.createElement("div");
    card.className = "card";
    card.setAttribute("data-key", tool.key);
    card.setAttribute("data-index", i);
    const title = t(tool.title);
    const tagsHtml = tool.tags.map(x=>`<span class="card-tag">${t(x)}</span>`).join("");
    card.innerHTML = `
      <div class="card-glow"></div>
      <div class="card-body">
        <div class="card-header"><div class="card-icon">${I[tool.icon]}</div><div class="card-tags">${tagsHtml}</div></div>
        <h3>${title}</h3>
        <div class="live-badge ${on?"on":""}"><span class="live-pulse"></span>${t("Running — check the camera window")}</div>
        <div class="card-video${tool.video?" has-video":""}${tool.dimPreview===false?" no-veil":""}">${tool.video?`<video muted loop autoplay playsinline preload="auto" src="${tool.video}"></video>`:(tool.art||"")}</div>
        <div class="card-actions">
          <button class="btn btn-primary" data-go="${tool.key}" ${on?"disabled":""} aria-label="${t("Launch {name}",{name:title})}">${on?t("Running..."):I.play+" "+t("Launch")}</button>
          <button class="btn btn-danger" data-stop="${tool.key}" ${on?"":"disabled"} aria-label="${t("Stop {name}",{name:title})}">${I.stop} ${t("Stop")}</button>
          <button class="card-more" data-detail="${tool.key}" aria-label="${t("View details for {name}",{name:title})}">${t("Details")} ${I.arrowRight}</button>
        </div>
      </div>`;
    card.addEventListener("mousemove", e=>{
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX-r.left)/r.width*100)+"%");
      card.style.setProperty("--my", ((e.clientY-r.top)/r.height*100)+"%");
    });
    cardsEl.appendChild(card);
  });
  // Card actions only fire on the centered card; on a side card any click
  // recenters that card instead (see initCarousel).
  const guard = (card, run) => e => {
    e.stopPropagation();
    if(carousel && carousel.dragged()) return;                // ignore a drag that ended on a button
    if(carousel && !carousel.isActive(card)){ carousel.goTo(+card.dataset.index); return; }
    run(e);
  };
  cardsEl.querySelectorAll("[data-go]").forEach(b =>
    b.onclick = guard(b.closest(".card"), e => { addRipple(b,e); act("launch", b.dataset.go); }));
  cardsEl.querySelectorAll("[data-stop]").forEach(b =>
    b.onclick = guard(b.closest(".card"), () => act("stop", b.dataset.stop)));
  cardsEl.querySelectorAll("[data-detail]").forEach(s =>
    s.onclick = guard(s.closest(".card"), () => showPage(s.dataset.detail)));
  cardsBuilt = true;
  initCarousel();
}

/* ── 3D coverflow carousel controller ────────────────────────────────
   Cards ride an infinite wrap-around ring: one faces forward (active,
   fully interactive), neighbours angle inward and dim. Auto-advances every
   ~4 s; drag / arrows / wheel / dots / click-a-side-card rotate manually and
   pause the auto-spin until the user idles. Under reduced-motion we bail out
   and let CSS render a flat, fully-interactive fallback grid. */
function initCarousel(){
  const wrap = document.getElementById("carousel");
  const stage = cardsEl;
  const dotsEl = document.getElementById("carousel-dots");
  const prevBtn = document.getElementById("carousel-prev");
  const nextBtn = document.getElementById("carousel-next");
  if(!wrap) return;
  if(carouselAbort) carouselAbort.abort();
  carouselAbort = new AbortController();
  const sig = {signal: carouselAbort.signal};
  prevBtn.innerHTML = I.arrowLeft;
  nextBtn.innerHTML = I.arrowRight;

  const cards = Array.from(stage.querySelectorAll(".card"));
  const count = cards.length;
  if(!count) return;

  if(reducedMotion){ carousel = null; return; } // CSS flat fallback

  let active = 0, autoTimer = null, idleTimer = null;
  const AUTO_MS = 4000, IDLE_MS = 5000;

  dotsEl.innerHTML = "";
  const dots = cards.map((c,i) => {
    const d = document.createElement("button");
    d.className = "carousel-dot";
    d.setAttribute("role","tab");
    d.setAttribute("aria-label", TOOLS[i] ? t(TOOLS[i].title) : t("Tool {n}",{n:i+1}));
    d.onclick = () => { poke(); goTo(i); };
    dotsEl.appendChild(d);
    return d;
  });

  function signedDist(i){
    let d = i - active;
    if(d >  count/2) d -= count;
    if(d < -count/2) d += count;
    return d;
  }
  function layout(){
    const GAP = wrap.clientWidth < 640 ? 150 : 250;
    cards.forEach((card,i) => {
      const d = signedDist(i), ad = Math.abs(d), isActive = d === 0;
      const scale = isActive ? 1 : Math.max(.7, 1 - ad*.12);
      const op = ad > 2 ? 0 : (isActive ? 1 : .55);
      card.style.transform =
        `translateX(-50%) translateX(${d*GAP}px) translateZ(${-ad*220}px) `+
        `rotateY(${d*-34}deg) scale(${scale}) `+
        // Hover growth (styles.css): the translate cancels the upward half of
        // the scale, so the card grows down and out, never into the header.
        `translateY(calc((var(--hover-scale,1) - 1) * 50%)) scale(var(--hover-scale,1))`;
      card.style.opacity = op;
      card.style.filter = isActive ? "none" : "brightness(.6)";
      card.style.zIndex = String(100 - ad);
      card.style.pointerEvents = ad > 2 ? "none" : "auto";
      card.classList.toggle("is-active", isActive);
      card.setAttribute("aria-hidden", isActive ? "false" : "true");
      card.querySelectorAll("button").forEach(b =>
        isActive ? b.removeAttribute("tabindex") : b.setAttribute("tabindex","-1"));
    });
    dots.forEach((dot,i) => {
      const on = i === active;
      dot.classList.toggle("on", on);
      dot.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function goTo(i){ active = ((i % count) + count) % count; layout(); }
  function go(dir){ goTo(active + dir); }

  function startAuto(){ stopAuto(); autoTimer = setInterval(() => go(1), AUTO_MS); }
  function stopAuto(){ if(autoTimer){ clearInterval(autoTimer); autoTimer = null; } }
  function poke(){ stopAuto(); clearTimeout(idleTimer); idleTimer = setTimeout(startAuto, IDLE_MS); }

  prevBtn.onclick = () => { poke(); go(-1); };
  nextBtn.onclick = () => { poke(); go(1); };

  wrap.addEventListener("keydown", e => {
    if(e.key === "ArrowLeft"){ poke(); go(-1); e.preventDefault(); }
    else if(e.key === "ArrowRight"){ poke(); go(1); e.preventDefault(); }
  });

  let wheelLock = false;
  wrap.addEventListener("wheel", e => {
    const amt = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : (e.shiftKey ? e.deltaY : 0);
    if(!amt) return;
    e.preventDefault(); poke();
    if(wheelLock) return;
    wheelLock = true; go(amt > 0 ? 1 : -1);
    setTimeout(() => wheelLock = false, 350);
  }, {passive:false});

  // Drag vs click: a press that moves < SLOP px stays a click; a drag past STEP
  // px advances the ring by at most ONE card per gesture (the `stepped` guard).
  // Move/up listen on window so a drag that leaves the stage still tracks; the
  // recenter rides the native click event so 3D-transformed cards hit-test right.
  const SLOP = 8, STEP = 60;
  let downX = null, downY = null, moved = false, stepped = false;
  stage.addEventListener("pointerdown", e => {
    if(e.button !== 0) return;
    downX = e.clientX; downY = e.clientY; moved = false; stepped = false;
    poke();
  });
  window.addEventListener("pointermove", e => {
    if(downX === null) return;
    if(Math.abs(e.clientX - downX) > SLOP || Math.abs(e.clientY - downY) > SLOP) moved = true;
    if(!stepped){
      const dx = e.clientX - downX;
      if(Math.abs(dx) > STEP){ go(dx > 0 ? -1 : 1); stepped = true; }  // one card max
    }
  }, sig);
  window.addEventListener("pointerup", () => { downX = downY = null; }, sig);
  // Click a non-active card's body to bring it forward. Buttons handle their own
  // clicks via the guard in buildCards; a drag (moved) suppresses the recenter.
  stage.addEventListener("click", e => {
    if(moved) return;
    const card = e.target.closest(".card");
    if(card && !card.classList.contains("is-active")){ poke(); goTo(+card.dataset.index); }
  });

  wrap.addEventListener("mouseenter", stopAuto);
  wrap.addEventListener("mouseleave", () => { if(downX === null) startAuto(); });
  window.addEventListener("resize", layout, sig);

  layout();
  startAuto();

  carousel = {
    isActive: card => card.classList.contains("is-active"),
    dragged: () => moved,
    goTo: i => { poke(); goTo(i); },
  };
}

function updateCardStates(running){
  currentRunning = running || {};
  TOOLS.forEach(tool => {
    const card = cardsEl.querySelector(`[data-key="${tool.key}"]`);
    if(!card) return;
    const on = !!running[tool.key];
    card.querySelector(".live-badge").classList.toggle("on", on);
    const goBtn = card.querySelector("[data-go]");
    goBtn.disabled = on;
    goBtn.innerHTML = on ? t("Running...") : I.play + " " + t("Launch");
    card.querySelector("[data-stop]").disabled = !on;
  });
  TOOLS.forEach(tool => renderDetailActions(tool.key));
}

/* Built once, then only the two buttons are touched. This runs on every 3 s
   status poll, and it used to rewrite the whole row — which deleted the camera
   and profile chips in it, so an open popover (or a native <select> dropdown
   inside one) vanished mid-choice every few seconds. */
function renderDetailActions(key){
  const el = document.getElementById(key+"-actions");
  if(!el) return;
  if(!el.querySelector("[data-act-go]")){
    el.innerHTML = `
      <button class="btn btn-primary" data-act-go onclick="act('launch','${key}')"></button>
      <button class="btn btn-danger" data-act-stop onclick="act('stop','${key}')"></button>
      <span class="cam-slot" data-cam></span>
      <span class="pf-slot" data-profile></span>`;
  }
  const on = !!currentRunning[key];
  const go = el.querySelector("[data-act-go]");
  const stop = el.querySelector("[data-act-stop]");
  go.disabled = on;
  go.setAttribute("aria-label", t("Launch test"));
  go.innerHTML = on ? t("Running...") : I.play + " " + t("Launch Test");
  stop.disabled = !on;
  stop.setAttribute("aria-label", t("Stop test"));
  stop.innerHTML = I.stop + " " + t("Stop");
  renderCamChips();
  window.renderProfileChips?.();      // profiles.js loads after this file
}

/* ── Camera-source chip ───────────────────────────────────────────────
   The tools used to stop at a console prompt asking for a camera; the
   choice is made here instead and travels to the spawned process as an
   env var (launcher.py `_tool_env`). A small chip that reads as status —
   "which camera will be used" — and folds open into a list of the cameras
   actually plugged in. One click on a row saves it: there is no Save
   button, because a picker that forgets your choice when you click away
   is a picker people think is broken. One shared setting rendered into
   every `[data-cam]` slot: the dashboard section head and each test
   page's action row. */
let camState = {mode:"webcam", index:0, url:"", name:"", label:"Webcam 0", mirror:null};
// Cameras plugged in, by name, in index order (GET /api/cameras, from
// core/camera_list.py). null until first asked. `camListed` is false when the
// OS could not be asked, which must not read as "nothing is plugged in".
let camList = null;
let camListed = false;

const esc = s => String(s??"").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function camChipText(){
  return camState.mode === "stream" ? t("Phone / IP stream")
       : camState.name || t("Webcam {n}", {n: camState.index});
}

// The saved camera is known by name and the list says it is not plugged in.
function camMissing(){
  return camState.mode !== "stream" && !!camState.name && camListed
      && Array.isArray(camList) && !camList.some(c => c.name === camState.name);
}

// camState.mirror is true / false / null (never checked), from core/orientation.py
function mirrorVal(){
  return camState.mirror === true ? "on" : camState.mirror === false ? "off" : "auto";
}

function buildCamChip(root){
  const missing = camMissing();
  const tip = t("Camera the tests will use")
    + (camState.mode === "stream" && camState.url ? " — " + camState.url : "")
    + (missing ? " — " + t("not plugged in") : "");
  const seg = [["auto", "Auto"], ["on", "Mirrored"], ["off", "Normal"]];
  root.innerHTML = `
    <button class="cam-chip${missing?" cam-warn":""}" type="button" aria-expanded="false"
            aria-haspopup="dialog" title="${esc(tip)}">
      ${I.camera}<span class="cam-chip-text">${esc(camChipText())}</span>
      ${missing ? '<span class="cam-dot" aria-hidden="true"></span>' : ""}${I.chevron}
    </button>
    <div class="cam-pop" role="dialog" aria-label="${t("Camera")}" hidden>
      <div class="cam-head">
        <span class="cam-pop-title">${t("Camera")}</span>
        <button class="cam-refresh" type="button" title="${t("Look for cameras again")}"
                aria-label="${t("Look for cameras again")}">${I.refresh}</button>
      </div>
      <div class="cam-list" role="radiogroup" aria-label="${t("Camera")}"></div>
      <div class="cam-url-row" hidden>
        <input class="cam-url" type="url" placeholder="http://192.168.1.5:8080/video"
               value="${esc(camState.url||"")}" aria-label="${t("Stream URL")}">
        <button class="cam-connect btn-mini" type="button">${t("Use")}</button>
      </div>
      <div class="cam-sec" title="${esc(t("Some cameras send a mirrored picture. The hand tests check each camera once and correct it."))}">
        <span class="cam-lbl">${t("Picture")}</span>
        <div class="cam-seg" role="radiogroup" aria-label="${t("Mirrored picture")}">
          ${seg.map(([v, label]) => `<button type="button" role="radio" data-mirror="${v}"
              aria-checked="${mirrorVal()===v}">${t(label)}</button>`).join("")}
        </div>
      </div>
      <div class="cam-note" hidden></div>
    </div>`;

  root.querySelector(".cam-chip").addEventListener("click", e => {
    e.stopPropagation();
    toggleCam(root, !root.classList.contains("open"));
  });
  root.querySelector(".cam-refresh").addEventListener("click", async e => {
    const btn = e.currentTarget;
    btn.classList.add("spin");
    await loadCamList();
    btn.classList.remove("spin");
    if(root.classList.contains("open")) fillCamList(root);
    renderCamChips();                              // the chip's missing dot too
  });
  root.querySelector(".cam-list").addEventListener("click", e => {
    if(e.target.closest(".cam-use")){
      const n = parseInt(root.querySelector(".cam-idx").value, 10) || 0;
      saveCam(root, {mode:"webcam", index:n, name:"", url:camState.url}, true);
      return;
    }
    const item = e.target.closest(".cam-item");
    if(!item || item.disabled) return;
    if(item.dataset.kind === "stream"){
      showCamUrl(root, true);
      // A stream already saved is one click like a camera; a new one needs its URL.
      if(camState.url) saveCam(root, {mode:"stream", url:camState.url, index:camState.index, name:camState.name}, true);
      return;
    }
    saveCam(root, {mode:"webcam", index:+item.dataset.index,
                   name:item.dataset.name || "", url:camState.url}, true);
  });
  root.querySelector(".cam-connect").addEventListener("click", () => saveStream(root));
  root.querySelector(".cam-seg").addEventListener("click", e => {
    const b = e.target.closest("[data-mirror]");
    if(!b || b.getAttribute("aria-checked") === "true") return;
    // Only sent when touched, so switching camera never copies the old
    // camera's answer onto the new one.
    saveCam(root, {mode:camState.mode, index:camState.index, url:camState.url,
                   name:camState.name, mirror:b.dataset.mirror}, false);
  });
  root.addEventListener("click", e => e.stopPropagation());
  root.addEventListener("keydown", e => {
    if(e.key === "Escape"){ toggleCam(root, false); root.querySelector(".cam-chip").focus(); return; }
    if(e.key === "Enter" && e.target.classList.contains("cam-url")){ e.preventDefault(); saveStream(root); return; }
    if(e.key === "Enter" && e.target.classList.contains("cam-idx")){
      e.preventDefault(); root.querySelector(".cam-use")?.click(); return;
    }
    // Arrow keys walk the list, as in any radio group.
    if((e.key === "ArrowDown" || e.key === "ArrowUp") && e.target.closest(".cam-list")){
      const items = [...root.querySelectorAll(".cam-item:not([disabled])")];
      const i = items.indexOf(e.target.closest(".cam-item"));
      if(i < 0) return;
      e.preventDefault();
      items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
    }
  });
}

function renderCamChips(){
  // Signature covers the setting *and* its rendered text, so a language
  // switch rebuilds but the 3 s status poll does not churn the DOM.
  const sig = [camState.mode, camState.index, camState.url||"", camState.name||"",
               mirrorVal(), camChipText(), camMissing()].join("|");
  document.querySelectorAll("[data-cam]").forEach(root => {
    // Never rebuild a chip that is open — it would close under the pointer.
    if(root.classList.contains("open") || root.dataset.camSig === sig) return;
    buildCamChip(root);
    root.dataset.camSig = sig;
  });
}

function toggleCam(root, open){
  if(open) closeCamChips();                       // one open at a time
  root.classList.toggle("open", open);
  root.querySelector(".cam-pop").hidden = !open;
  root.querySelector(".cam-chip").setAttribute("aria-expanded", String(open));
  if(!open){
    renderCamChips();                             // catch up on anything the poll skipped
    return;
  }
  // The URL field only shows for a stream, or once "Phone / IP stream" is clicked.
  root.querySelector(".cam-url-row").hidden = true;
  fillCamList(root);                              // last known list, instantly
  camRunningNote(root);
  const focusCurrent = () => (root.querySelector(".cam-item[aria-checked='true']")
                             || root.querySelector(".cam-item"))?.focus();
  focusCurrent();
  // Re-listed on every open, so a camera plugged in since the last look appears.
  loadCamList().then(() => {
    if(!root.classList.contains("open")) return;
    const had = document.activeElement?.closest?.(".cam-list");
    fillCamList(root);
    if(had) focusCurrent();
  });
}

async function loadCamList(){
  try{
    const r = await fetch("/api/cameras");
    const data = await r.json();
    camList = Array.isArray(data.cameras) ? data.cameras : [];
    // An older hub sends no `listed`; a non-empty list proves it listed.
    camListed = data.listed === true || camList.length > 0;
  }catch(e){ camList = camList || []; }
}

function fillCamList(root){
  const list = root.querySelector(".cam-list");
  const cams = camList || [];
  const stream = camState.mode === "stream";
  const rows = cams.map(c => ({index:c.index, name:c.name, virtual:!!c.virtual}));
  // The saved camera is unplugged: keep it listed rather than silently
  // showing a different one as the choice.
  if(!stream && camState.name && camList && !cams.some(c => c.name === camState.name))
    rows.push({index:camState.index, name:camState.name, gone:true});
  // Prefer the saved name (its index may have shifted), then the index.
  const hit = stream ? null
    : (camState.name ? rows.find(r => r.name === camState.name && r.index === camState.index)
                       || rows.find(r => r.name === camState.name)
                     : rows.find(r => r.index === camState.index));
  const item = (attrs, body, on, extra="") => `<button type="button" role="radio"
      class="cam-item${extra}" aria-checked="${on}" ${attrs}>${body}
      <span class="cam-tick" aria-hidden="true">${on ? I.check : ""}</span></button>`;
  let html = rows.map(r => item(
    `data-kind="webcam" data-index="${r.index}" data-name="${esc(r.name)}" ${r.gone?"disabled":""}`,
    `<span class="cam-ic">${I.camera}</span>
     <span class="cam-nm">${esc(r.name)}</span>
     ${r.gone ? `<span class="cam-tag cam-tag-warn">${t("not plugged in")}</span>` : ""}
     ${r.virtual ? `<span class="cam-tag" title="${esc(t("Listed by DirectShow only. Usually a virtual camera, such as OBS."))}">${t("virtual")}</span>` : ""}`,
    r === hit, r.gone ? " cam-gone" : "")).join("");
  if(!rows.length){
    // No names to show: say why, and keep a plain number as the way through.
    html += `<div class="cam-empty">${camList === null ? t("Looking for cameras...")
      : camListed ? t("No cameras found. Plug one in, then refresh.")
      : t("Camera names are not available here. Choose by number.")}</div>`;
    if(camList !== null) html += `<div class="cam-idx-row">
        <span>${t("Camera number")}</span>
        <input class="cam-idx" type="number" min="0" max="9" step="1"
               value="${camState.index}" aria-label="${t("Camera number")}">
        <button type="button" class="cam-use btn-mini">${t("Use")}</button>
      </div>`;
  }
  html += item('data-kind="stream"',
    `<span class="cam-ic">${I.stream}</span>
     <span class="cam-nm">${t("Phone / IP stream")}</span>
     ${camState.url ? `<span class="cam-sub">${esc(camState.url)}</span>` : ""}`,
    stream, " cam-item-stream");
  list.innerHTML = html;
  showCamUrl(root, stream || !root.querySelector(".cam-url-row").hidden);
}

function showCamUrl(root, on){
  const row = root.querySelector(".cam-url-row");
  const wasHidden = row.hidden;
  row.hidden = !on;
  if(on && wasHidden && !camState.url) root.querySelector(".cam-url").focus();
}

// Changing camera mid-run is allowed but only reaches the next launch; say so
// only when it applies, rather than printing it under every choice.
function camRunningNote(root){
  const note = root.querySelector(".cam-note");
  const tool = TOOLS.find(tool => currentRunning[tool.key]);
  note.hidden = !tool;
  if(tool) note.textContent = t("{test} is running. A change here applies to its next launch.",
                                {test: t(tool.title)});
}

function closeCamChips(){
  document.querySelectorAll("[data-cam].open").forEach(r => toggleCam(r, false));
}
document.addEventListener("click", closeCamChips);
document.addEventListener("keydown", e => { if(e.key === "Escape") closeCamChips(); });

function saveStream(root){
  const url = root.querySelector(".cam-url").value.trim();
  saveCam(root, {mode:"stream", url, index:camState.index, name:camState.name}, true);
}

async function saveCam(root, camera, close){
  if(root.classList.contains("busy")) return;
  root.classList.add("busy");
  try{
    const r = await fetch("/api/camera", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({camera})
    });
    const data = await r.json();
    toast(tMsg(data.message) || t(data.ok?"Done":"Failed"), data.ok?"ok":"fail");
    if(!data.ok){                                 // leave it open to be fixed
      if(camera.mode === "stream") root.querySelector(".cam-url")?.focus();
      return;
    }
    camState = data.camera;
    if(close){
      toggleCam(root, false);
      root.querySelector(".cam-chip")?.focus();
    } else {
      // Stays open (the Picture switch): refresh its contents in place.
      root.querySelectorAll("[data-mirror]").forEach(b =>
        b.setAttribute("aria-checked", String(b.dataset.mirror === mirrorVal())));
      fillCamList(root);
    }
    renderCamChips();
  }catch(e){ toast(t("Request failed"),"fail"); }
  finally{ root.classList.remove("busy"); }
}

// Asked once up front so the chip can show a saved camera that is unplugged
// before anyone opens it.
loadCamList().then(renderCamChips);

/* ── "Why This" page render (build once) ─────────────────────────── */
function renderWhy(){
  if(whyBuilt) return;

  const pillars = document.getElementById("why-pillars");
  if(pillars) pillars.innerHTML = WHY_PILLARS.map(p => `<div class="pillar">
    <div class="pillar-ic">${I[p.icon]}</div>
    <h4>${t(p.title)}</h4><p>${t(p.text)}</p></div>`).join("");

  const legend = document.getElementById("why-legend");
  if(legend) legend.innerHTML = ["yes","partial","planned","no"].map(k => {
    const s = CMP_STATES[k];
    return `<span class="cmp-key ${s.cls}">${I[s.icon]}${t(s.word)}</span>`;
  }).join("");

  const matrix = document.getElementById("why-matrix");
  if(matrix){
    const head = `<tr><th scope="col" class="cmp-cap-h">${t("Capability")}</th>${
      CMP_COLS.map((c,i) => `<th scope="col"${i===0?' class="cmp-own"':''}>${t(c)}</th>`).join("")}</tr>`;
    const rows = WHY_MATRIX.map(r => `<tr><th scope="row">${t(r.cap)}</th>${
      r.cells.map((state,i) => {
        const s = CMP_STATES[state], w = t(s.word);
        return `<td${i===0?' class="cmp-own"':''}>
          <span class="cmp-cell ${s.cls}" aria-label="${w}" title="${w}">
            ${I[s.icon]}<span>${w}</span></span></td>`;
      }).join("")}</tr>`).join("");
    matrix.innerHTML = `<table class="cmp"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
  }

  whyBuilt = true;
}

/* ── Ripple effect ───────────────────────────────────────────────── */
function addRipple(btn, e){
  const r = btn.getBoundingClientRect();
  const ripple = document.createElement("span");
  ripple.className = "ripple";
  const size = Math.max(r.width, r.height);
  ripple.style.width = ripple.style.height = size+"px";
  ripple.style.left = (e.clientX-r.left-size/2)+"px";
  ripple.style.top = (e.clientY-r.top-size/2)+"px";
  btn.appendChild(ripple);
  setTimeout(()=>ripple.remove(), 500);
}

/* ── Status pills ────────────────────────────────────────────────── */
const statusEl = document.getElementById("status");
let wasRunning = false;

/* Signature-guarded, like renderCamChips(): the 3 s poll must not churn the
   DOM, but the row still has to follow the payload. It used to be built once
   behind a `statusBuilt` latch, and on the published dashboard the first
   /api/status answer is the connector's canned offline one (static-api.js) —
   fetched before the hub probe resolves. The pills then read "null / Missing"
   for the rest of the session, including after a hub connected. */
function renderStatus(s){
  const sig = [s.python, s.model_present, s.face_model_present,
               s.opencv, s.mediapipe, getLang()].join("|");
  if(statusEl.dataset.sig !== sig){
    let html = "";
    html += pill(s.python == null ? null : true, "Python", s.python);
    html += pill(s.model_present, t("Hand model"), t(s.model_present ? "Ready" : "Missing"));
    html += pill(s.face_model_present, t("Face model"), t(s.face_model_present ? "Ready" : "Missing"));
    html += pill(s.opencv, "OpenCV", t(s.opencv ? "OK" : "Missing"));
    html += pill(s.mediapipe, "MediaPipe", t(s.mediapipe ? "OK" : "Missing"));
    statusEl.innerHTML = html;
    statusEl.dataset.sig = sig;
  }
  if(s.camera){
    camState = s.camera;
    renderCamChips();
  }
  // Same rail as the camera: the chip follows the poll rather than needing an
  // endpoint of its own. `profile` is a snapshot, so an absent one is {}.
  window.setActiveProfile?.(s.profile || {});
  if(!cardsBuilt){
    currentRunning = s.running || {};
    buildCards();
  } else {
    updateCardStates(s.running);
  }
  // A test that just stopped has written its session to results/; refetch so
  // the readings strip shows it without a reload.
  const busy = Object.values(s.running || {}).some(Boolean);
  if(wasRunning && !busy){
    // The session it just wrote is the one the assign card offers to move, so
    // profiles.js does the refetch and calls renderVitals() when it lands.
    if(window.afterRun) window.afterRun();
    else loadVitals(true);
  }
  wasRunning = busy;
}

/* `ok` is tri-state: null means "not known yet" — a hub that has not answered
   is not the same thing as a missing dependency, and a green dot beside the
   literal `null` was the worst of both readings. */
function pill(ok, label, value){
  const cls = ok == null ? "unknown" : (ok ? "ok" : "bad");
  const shown = value == null || value === "" ? "&#8212;" : value;
  return `<div class="s-pill"><span class="s-dot ${cls}"></span><b>${label}</b>&#160;<span>${shown}</span></div>`;
}

/* ── Toast ────────────────────────────────────────────────────────── */
const toastEl = document.getElementById("toast");
let toastTimer = null;
function toast(msg, type){
  const icons = {ok:I.check, fail:I.x, info:I.info};
  toastEl.innerHTML = `<span class="toast-icon">${icons[type]||icons.info}</span> ${msg}`;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>toastEl.classList.remove("show"), 2800);
}

/* ── API ──────────────────────────────────────────────────────────── */
async function refresh(){
  try{
    const r = await fetch("/api/status");
    renderStatus(await r.json());
  }catch(e){}
}

/* The hub state changed under us (static-api.js). Everything cached from the
   previous state has to go: `analysisSessions` holds the canned empty list
   while offline, and keeping it would leave the readings strip blank after a
   pairing. */
window.rehydrate = function(){
  analysisSessions = null;
  refresh();
  window.reloadProfiles?.();          // the roster came from the old hub too
  loadCamList().then(renderCamChips); // and so did the camera list
  loadVitals(true);
  const page = document.getElementById("page-analysis");
  if(page && page.classList.contains("active")) loadAnalysis();
};

async function act(kind, key){
  try{
    const r = await fetch("/api/"+kind, {
      method:"POST", headers:{"Content-Type":"application/json"},
      // The language rides along so a switch made a moment ago cannot lose
      // the race against the /api/lang POST that persists it.
      body: JSON.stringify({test:key, lang:getLang()})
    });
    const data = await r.json();
    // Server text is English; tMsg maps the known strings (i18n.zh.js).
    toast(tMsg(data.message) || t(data.ok?"Done":"Failed"), data.ok?"ok":"fail");
    if(data.running) updateCardStates(data.running);
    setTimeout(refresh, 400);
  }catch(e){ toast(t("Request failed"),"fail"); }
}

/* ── Scroll reveal ───────────────────────────────────────────────── */
const observer = new IntersectionObserver((entries)=>{
  entries.forEach(e=>{
    if(e.isIntersecting) e.target.classList.add("visible");
  });
}, {threshold:.15});
document.querySelectorAll(".reveal").forEach(el=>observer.observe(el));

/* ── Longitudinal Analysis ───────────────────────────────────────────
   Reads /api/sessions and charts each test's headline metric over time.
   Reference bands are provisional (mirrors the detail-page copy). Colours
   are the shared status tokens; the chart line is a neutral accent so it
   reads over every band. Status is never colour-alone — dots carry a hover
   label, the readout names the band, and a legend maps colour → word. */

const TREND = {
  finger_tapping: {
    label:"Finger Tapping", icon:"hand", page:"iiv",
    headline:{ key:"cv_pct", name:"Rhythm variability", unit:"%", lowerBetter:true,
      bands:[{max:15,status:"ok"},{max:25,status:"warn"},{max:Infinity,status:"bad"}] },
    supporting:[
      {key:"frequency_hz", name:"Tap frequency", unit:"Hz"},
      {key:"confidence_pct", name:"Confidence", unit:"%"},
      {key:"amplitude_cv_pct", name:"Amplitude CV", unit:"%"},
      {key:"decrement_pct_per_s", name:"Speed decrement", unit:"%/s"},
    ],
    // Two test types share the CV% headline; each foregrounds its own third metric
    // (Big & Fast → speed decrement, Paced → beat-sync tightness).
    modes:[
      { key:"big_and_fast", label:"Big & Fast", supporting:[
        {key:"frequency_hz", name:"Tap frequency", unit:"Hz"},
        {key:"confidence_pct", name:"Confidence", unit:"%"},
        {key:"amplitude_cv_pct", name:"Amplitude CV", unit:"%"},
        {key:"decrement_pct_per_s", name:"Speed decrement", unit:"%/s"},
      ]},
      { key:"paced", label:"Paced", supporting:[
        {key:"frequency_hz", name:"Tap frequency", unit:"Hz"},
        {key:"confidence_pct", name:"Confidence", unit:"%"},
        {key:"amplitude_cv_pct", name:"Amplitude CV", unit:"%"},
        {key:"sync_sd_ms", name:"Beat-sync SD", unit:"ms"},
      ]},
    ],
  },
  spiral: {
    label:"Spiral Tracing", icon:"spiral", page:"spiral",
    headline:{ key:"vel_cv_pct", name:"Velocity variability", unit:"%", lowerBetter:true, bands:null },
    supporting:[
      {key:"smoothness_index", name:"Smoothness index", unit:""},
      {key:"norm_jerk", name:"Normalized jerk", unit:""},
      {key:"completion_pct", name:"Completion", unit:"%"},
    ],
  },
  oculomotor: {
    label:"Eye Movement", icon:"eye", page:"oculomotor",
    headline:{ key:"error_rate_pct", name:"Anti-saccade error rate", unit:"%", lowerBetter:true,
      bands:[{max:20,status:"ok"},{max:40,status:"warn"},{max:Infinity,status:"bad"}] },
    supporting:[
      {key:"anti_minus_pro_ms", name:"Anti − Pro latency", unit:"ms"},
      {key:"confidence_pct", name:"Confidence", unit:"%"},
      {key:"corrected_rate_pct", name:"Corrected errors", unit:"%"},
      {key:"valid_trials", name:"Valid trials", unit:""},
    ],
  },
  ddk: {
    label:"Speech Rhythm", icon:"mic", page:"ddk",
    headline:{ key:"rhythm_cv_pct", name:"Syllable rhythm variability", unit:"%", lowerBetter:true,
      bands:[{max:15,status:"ok"},{max:25,status:"warn"},{max:Infinity,status:"bad"}] },
    // Not the phoneme model's order errors: they are experimental and not
    // charted until validated on real voices (SPEECH_TEST_PLAN.md §3.1b).
    supporting:[
      {key:"syllable_rate_hz", name:"Syllable rate", unit:"/s"},
      {key:"confidence_pct", name:"Confidence", unit:"%"},
      {key:"npvi", name:"nPVI", unit:""},
      {key:"decrement_pct_per_s", name:"Speed decrement", unit:"%/s"},
    ],
  },
  phonation: {
    label:"Voice Steadiness", icon:"mic", page:"ddk",
    // Lower edge is the MDVP jitter threshold (1.04%); the upper edge is not
    // from a source — both provisional (core/speech/tasks.py).
    headline:{ key:"jitter_pct", name:"Jitter", unit:"%", lowerBetter:true,
      bands:[{max:1.04,status:"ok"},{max:2.08,status:"warn"},{max:Infinity,status:"bad"}] },
    supporting:[
      {key:"shimmer_pct", name:"Shimmer", unit:"%"},
      {key:"confidence_pct", name:"Confidence", unit:"%"},
      {key:"hnr_db", name:"HNR", unit:"dB"},
      {key:"vocal_tremor_hz", name:"Vocal tremor", unit:"Hz"},
    ],
  },
  tremor: {
    label:"Hand Tremor", icon:"wave", page:"tremor",
    // A supporting check (TREMOR_RESTRUCTURE_PLAN.md §2): off the home
    // readings strip, charted after the screening tests, and its dots drawn
    // as Logged whatever the recorded verdict. The verdict itself is still
    // saved and read out in words (tremorFinding); only the colour goes.
    secondary:true,
    headline:{ key:"tremor_amp_pct", name:"Tremor-band movement (estimate)", unit:"%", lowerBetter:true,
      bands:null, neutral:true },
    supporting:[
      {key:"tremor_peak_hz", name:"Tremor peak", unit:"Hz"},
      {key:"confidence_pct", name:"Confidence", unit:"%"},
      {key:"asymmetry_ratio", name:"Left / right ratio", unit:"×"},
      {key:"cam_glove_hz_diff", name:"Camera vs glove", unit:"Hz"},
    ],
  },
  gait: {
    label:"Walking", icon:"walk", page:"gait",
    // Seated part only so far. The bands mirror core/gait/metrics.py and are
    // provisional (Bohannon 2006 / Duncan 2011, still to be verified).
    headline:{ key:"sts5_s", name:"Five sit-to-stands", unit:"s", lowerBetter:true,
      bands:[{max:13,status:"ok"},{max:16,status:"warn"},{max:Infinity,status:"bad"}] },
    supporting:[
      {key:"leg_right_rate_hz", name:"Right leg stamps", unit:"/s"},
      {key:"confidence_pct", name:"Confidence", unit:"%"},
      {key:"leg_left_rate_hz", name:"Left leg stamps", unit:"/s"},
      {key:"failed_attempts", name:"Failed rises", unit:""},
    ],
  },
};
// Supporting checks (TREND[k].secondary) go last: the Analysis page opens a
// "Supporting checks" group before the first of them.
const TREND_ORDER = ["finger_tapping","spiral","oculomotor","ddk","phonation","gait","tremor"];
const ST = {
  ok:  {word:"Typical",   dot:"#22C55E", band:"rgba(34,197,94,.13)"},
  warn:{word:"Monitor",   dot:"#F5A524", band:"rgba(245,165,36,.14)"},
  bad: {word:"Follow-up", dot:"#EF4444", band:"rgba(239,68,68,.14)"},
  none:{word:"Logged",    dot:"#5197FB", band:"transparent"},
};
const INK_MUTED = "#B4C0D0", INK_DIM = "#8C9BB2", GRID = "#2A3442", LINE_C = "#5197FB";

let analysisFilter = "all";
/* Whose history is on screen. "all" pools everyone - what this page did before
   profiles existed - "none" is the sessions nobody claimed, and anything else
   is a profile id. null means the person has not chosen yet, and resolves to
   whoever the chip is set to, so the dashboard opens on the patient who is
   about to be tested rather than on a pooled line. */
let analysisProfile = null;
let analysisSessions = null;
let analysisModes = {};   // per-test selected sub-mode (e.g. finger_tapping → "paced")
let sessionCalendarState = {}; // per trend/mode: visible month + selected day

function fmtNum(v){
  if(v==null || !isFinite(v)) return "—";
  const a = Math.abs(v);
  if(a >= 1000) return Math.round(v).toLocaleString();
  if(a >= 100)  return v.toFixed(0);
  if(a >= 10)   return v.toFixed(1);
  return v.toFixed(2);
}
function fmtDate(iso){
  return new Date(iso).toLocaleDateString(i18nLocale(),{month:"short",day:"numeric"});
}
function fmtDateTime(iso){
  return new Date(iso).toLocaleString(i18nLocale(),
    {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
}
function bandFor(v, bands){
  if(!bands) return "none";
  for(const b of bands){ if(v <= b.max) return b.status; }
  return "none";
}
// Every test scores its own recording and stores that verdict on the session
// (core/*/metrics.py). Prefer it: it is the same judgement the test showed the
// person at the time, and it exists for the spiral, which has no chart bands.
// Older records without one still fall back to the provisional bands.
const VERDICT = {success:"ok", warning:"warn", danger:"bad", info:"none"};
function statusOf(session, h){
  if(h.neutral) return "none";            // a supporting check: no verdict colour
  const m = session.metrics || {};
  if(m.status && VERDICT[m.status]) return VERDICT[m.status];
  return bandFor(m[h.key], h.bands);
}

/* A tremor run's finding in words, in place of a coloured verdict. The saved
   verdict (metrics.status) is unchanged; this only says it neutrally. */
const TREMOR_HOLDS = {rest_palm_up:"Palms up", rest_palm_down:"Palms down", postural:"Arms out",
                      rest:"Rest", rest_count:"Rest, counting"};
function tremorFinding(m){
  if(!m || m.scoreable === false) return m && m.reason ? t(m.reason) : "";
  if(m.tremor_peak_hz == null) return t("No rhythmic shaking found");
  const [hold, hand] = String(m.tremor_where || ":").split(":");
  const where = [TREMOR_HOLDS[hold] ? t(TREMOR_HOLDS[hold]) : hold,
                 hand ? t(hand === "left" ? "Left hand" : "Right hand") : ""]
    .filter(Boolean).join(", ");
  const hz = fmtNum(m.tremor_peak_hz);
  return m.status === "warning"
    ? t("A weak rhythm at {hz} Hz ({where}) - repeat to confirm", {hz, where})
    : t("Rhythmic shaking at {hz} Hz ({where})", {hz, where});
}

function profileFilter(){
  const list = analysisSessions || [];
  const has = id => id === "none"
    ? list.some(sn => !(sn.profile && sn.profile.id))
    : list.some(sn => sn.profile && sn.profile.id === id);
  // A pin can outlive its sessions: move the last one to somebody else and the
  // person it names has no button left to click back from. Drop it rather than
  // strand the page on an empty view it cannot leave. Only once sessions have
  // actually loaded — an empty list is "not yet", not "nobody".
  if(analysisProfile === "all") return "all";     // an explicit choice to pool
  if(analysisProfile){
    if(!list.length || has(analysisProfile)) return analysisProfile;
    analysisProfile = null;
  }
  const active = window.activeProfileId?.();
  return active && has(active) ? active : "all";
}

/* The one place the person filter is applied. The chart, the calendar and the
   home readings strip all read through it, so they cannot disagree about which
   sessions exist. */
function visibleSessions(){
  const list = analysisSessions || [];
  const f = profileFilter();
  if(f === "all") return list;
  if(f === "none") return list.filter(sn => !(sn.profile && sn.profile.id));
  return list.filter(sn => sn.profile && sn.profile.id === f);
}

function setAnalysisProfile(id){
  analysisProfile = id;
  renderAnalysis();
  renderVitals();
}

async function loadAnalysis(){
  const body = document.getElementById("analysis-body");
  if(!body) return;
  if(!analysisSessions) body.innerHTML = `<div class="analysis-empty">${t("Loading sessions…")}</div>`;
  try{
    const r = await fetch("/api/sessions");
    analysisSessions = (await r.json()).sessions || [];
  }catch(e){ analysisSessions = []; }
  renderAnalysis();
}

function renderAnalysis(){
  const sessions = visibleSessions();
  const byTest = {};
  TREND_ORDER.forEach(k => byTest[k] = []);
  sessions.forEach(s => { if(byTest[s.test]) byTest[s.test].push(s); });

  renderAnalysisSummary(sessions, byTest);
  renderAnalysisPeople();
  renderAnalysisFilter(byTest);

  const body = document.getElementById("analysis-body");
  if(!body) return;                       // same guard loadAnalysis() already has
  if(!sessions.length && (analysisSessions || []).length){
    // Someone has sessions, just not this person - never the fresh-install copy.
    body.innerHTML = `<div class="analysis-empty">
      <div class="analysis-empty-icon">${I.chart}</div>
      <h3>${t("Nothing logged for this person yet")}</h3>
      <p>${t("Set them on the profile chip before you launch a test, or move an existing session to them from its report.")}</p>
      <button class="btn btn-primary" onclick="showPage('home')">${I.play} ${t("Go to tests")}</button>
    </div>`;
    return;
  }
  if(!sessions.length){
    body.innerHTML = `<div class="analysis-empty">
      <div class="analysis-empty-icon">${I.chart}</div>
      <h3>${t("No sessions logged yet")}</h3>
      <p>${t("Run a screening test from the dashboard. Each session is saved locally, and its metrics will chart here so you can watch the trend over time.")}</p>
      <button class="btn btn-primary" onclick="showPage('home')">${I.play} ${t("Go to tests")}</button>
    </div>`;
    return;
  }
  const show = TREND_ORDER.filter(k =>
    (analysisFilter==="all" || analysisFilter===k) && byTest[k].length);
  if(!show.length){
    body.innerHTML = `<div class="analysis-empty"><p>${t("No sessions for this test yet.")}</p></div>`;
    return;
  }
  const firstSecondary = show.find(k => TREND[k].secondary);
  body.innerHTML = show.map(k =>
    (k === firstSecondary
      ? `<h3 class="analysis-group">${t("Supporting checks")}
           <span>${t("Not screening results: they help explain the readings above.")}</span></h3>`
      : "") + trendCard(k, byTest[k])).join("");
}

function renderAnalysisSummary(sessions, byTest){
  const el = document.getElementById("analysis-summary");
  const withData = TREND_ORDER.filter(k => byTest[k].length).length;
  let span = "—";
  if(sessions.length){
    const a = fmtDate(sessions[0].timestamp), b = fmtDate(sessions[sessions.length-1].timestamp);
    span = a===b ? a : `${a} – ${b}`;
  }
  const tiles = [
    [t("Total sessions"), sessions.length],
    [t("Tests tracked"), `${withData} / ${TREND_ORDER.length}`],
    [t("Date range"), span],
  ];
  el.innerHTML = tiles.map(([l,v]) =>
    `<div class="sum-tile"><div class="sum-val">${v}</div><div class="sum-label">${l}</div></div>`
  ).join("");
}

/* Who the page can be read as. Only profiles that actually hold sessions get a
   button - a roster of ten with one tested would be a row of dead ends - plus
   "Unassigned" when any session has no profile. */
function renderAnalysisPeople(){
  const el = document.getElementById("analysis-profile");
  const who = document.getElementById("analysis-who");
  if(!el) return;
  const all = analysisSessions || [];
  const roster = window.profileList?.() || [];
  const counts = {};
  let unassigned = 0;
  all.forEach(sn => {
    const id = sn.profile && sn.profile.id;
    if(id) counts[id] = (counts[id] || 0) + 1; else unassigned++;
  });

  const opts = [["all", t("All people")]];
  roster.forEach(pr => { if(counts[pr.id]) opts.push([pr.id, pr.name]); });
  // A session outlives the profile it names - the record keeps its own
  // snapshot - so offer those names too rather than hiding the sessions.
  all.forEach(sn => {
    const pr = sn.profile;
    if(pr && pr.id && !opts.some(o => o[0] === pr.id))
      opts.push([pr.id, pr.name || t("Removed profile")]);
  });
  if(unassigned) opts.push(["none", t("Unassigned")]);

  // One person and nothing unassigned: the row would be a single button that
  // does nothing. Hide it and let the line below carry the name.
  const cur = profileFilter();
  el.hidden = opts.length < 3;
  el.innerHTML = opts.map(([k, label]) =>
    `<button class="seg-btn ${cur===k?"active":""}" role="tab"
       aria-selected="${cur===k}" data-person="${esc(k)}">${esc(label)}</button>`).join("");
  el.querySelectorAll("[data-person]").forEach(b =>
    b.onclick = () => setAnalysisProfile(b.dataset.person));

  if(who){
    who.innerHTML = whoLine(cur);
    // profiles.js owns the form; this page only says which person it is for.
    who.querySelector("[data-add-person]")?.addEventListener("click",
      () => window.openProfileEditor?.(""));
    who.querySelector("[data-edit-person]")?.addEventListener("click", ev =>
      window.openProfileEditor?.(ev.currentTarget.dataset.editPerson));
  }
  // A rebuild while the editor is open would leave it orphaned above a filter
  // row that no longer matches it.
  window.closeProfileEditor?.();
}

/* "Jane Chen - Female - 68 - right-handed". Age and sex are the reason the
   profile exists, so they stay visible while the trend is being read. */
function whoLine(filterId){
  // Editing is offered only for a person still on the roster: a session can
  // outlive the profile it names, and there is nothing left to edit then.
  const onRoster = filterId !== "all" && filterId !== "none"
    && !!window.profileById?.(filterId);
  const acts = `<span class="who-acts">
      ${onRoster ? `<button class="who-act" type="button"
        data-edit-person="${esc(filterId)}">${t("Edit details")}</button>` : ""}
      <button class="who-act" type="button" data-add-person>${t("Add a person")}</button>
    </span>`;

  if(filterId === "none")
    return `<span class="who-name">${t("Unassigned sessions")}</span>
      <span class="who-note">${t("Recorded with no profile set.")}</span>${acts}`;
  if(filterId === "all") return acts;
  const pr = window.profileById?.(filterId)
    || (visibleSessions().slice(-1)[0] || {}).profile;
  if(!pr || !pr.name) return acts;
  const detail = window.describeProfile?.(pr) || "";
  return `<span class="who-name">${esc(pr.name)}</span>`
    + (detail ? `<span class="who-detail">${esc(detail)}</span>` : "") + acts;
}

function renderAnalysisFilter(byTest){
  const el = document.getElementById("analysis-filter");
  const opts = [["all",t("All tests")]].concat(
    TREND_ORDER.filter(k=>byTest[k].length).map(k=>[k, t(TREND[k].label)]));
  el.innerHTML = opts.map(([k,label]) =>
    `<button class="seg-btn ${analysisFilter===k?"active":""}" role="tab"
       aria-selected="${analysisFilter===k}" data-filter="${k}">${label}</button>`).join("");
  el.querySelectorAll("[data-filter]").forEach(b =>
    b.onclick = () => { analysisFilter = b.dataset.filter; renderAnalysis(); });
}

function trendCard(key, allSessions){
  const cfg = TREND[key], h = cfg.headline;

  // Optional per-mode split (finger tapping: Big & Fast vs Paced). The toggle
  // swaps everything below the header — chart, readout, and supporting tiles.
  let sessions = allSessions, supporting = cfg.supporting, modeBar = "";
  let calendarKey = key;
  if(cfg.modes){
    const active = activeMode(key, cfg, allSessions);
    calendarKey = `${key}:${active}`;
    const m = cfg.modes.find(x => x.key===active) || cfg.modes[0];
    sessions = allSessions.filter(s => s.mode === active);
    supporting = m.supporting || cfg.supporting;
    modeBar = `<div class="trend-modes" role="tablist" aria-label="${t("Test type")}">${cfg.modes.map(md =>
      `<button class="seg-btn seg-sm ${md.key===active?"active":""}" role="tab"
        aria-selected="${md.key===active}"
        onclick="setTrendMode('${key}','${md.key}')">${t(md.label)}</button>`).join("")}</div>`;
  }

  const calendarPts = cardPoints(sessions, h);
  const pts = calendarPts.filter(p=>p.scoreable);

  const head = `<div class="trend-head">
      <div class="trend-title"><span class="trend-ic">${I[cfg.icon]}</span>
        <div><h3>${t(cfg.label)}</h3>
          <div class="trend-metric">${t(h.name)}${h.unit?` (${h.unit})`:""}</div></div>
      </div>
      <button class="trend-open" onclick="showPage('${cfg.page}')">${t("Details")} ${I.arrowRight}</button>
    </div>`;

  if(!pts.length){
    return `<div class="trend-card">${head}${modeBar}
      <div class="analysis-note">${cfg.modes
        ? t("{n} session(s) logged for this type, but none were scoreable for this metric yet.",{n:sessions.length})
        : t("{n} session(s) logged, but none were scoreable for this metric yet.",{n:sessions.length})}</div>
      ${sessionCalendar(calendarPts,h,calendarKey)}</div>`;
  }

  const latest = pts[pts.length-1], prev = pts.length>1 ? pts[pts.length-2] : null;
  const st = ST[latest.status];
  const readout = `<div class="trend-readout">
      <div class="trend-now"><span class="trend-now-val">${fmtNum(latest.v)}</span>
        <span class="trend-now-unit">${h.unit}</span></div>
      <span class="badge badge-${latest.status}"><span class="badge-dot"></span>${t(st.word)}</span>
      ${prev ? deltaChip(latest.v, prev.v, h.lowerBetter) : ""}
    </div>`;
  const dateSpan = pts.length>1
    ? `${fmtDate(pts[0].iso)} – ${fmtDate(latest.iso)} · ${t("{n} sessions",{n:pts.length})}`
    : t("1 session · a trend line appears after your next");

  const legend = `<div class="trend-legend">
      <span><i style="background:${ST.ok.dot}"></i>${t(ST.ok.word)}</span>
      <span><i style="background:${ST.warn.dot}"></i>${t(ST.warn.word)}</span>
      <span><i style="background:${ST.bad.dot}"></i>${t(ST.bad.word)}</span>
      <span class="trend-legend-note">${t("colour is the verdict the test gave that session")}</span>
    </div>`;

  const support = `<div class="trend-support">${supporting.map(m =>
    supportTile(sessions, m)).join("")}</div>`;

  // The legend explains the chart's dot colours, so it sits with the chart —
  // below the calendar it would be a key to something a screen away.
  return `<div class="trend-card">${head}${modeBar}${readout}
    <div class="trend-span">${dateSpan}</div>
    <div class="trend-chart">${trendSvg(pts, h)}</div>
    ${legend}
    <div class="trend-hint" role="note" tabindex="0">
      <span class="hint-ic">${I.info}</span><span class="hint-text">${t("Open a report from any chart point, or choose a date in the calendar")}</span>
    </div>
    ${sessionCalendar(calendarPts, h, calendarKey)}
    ${support}</div>`;
}

/* One session as the Analysis page thinks of it. The chart plots only the
   scoreable ones, but the calendar keeps every saved session — a run that
   failed the quality gate still has a report explaining why. */
function cardPoints(sessions, h){
  return sessions.map(s => {
    const v = s.metrics ? s.metrics[h.key] : null;
    const scoreable = v!=null && isFinite(v);
    return {v, iso:s.timestamp, id:s.session_id, mode:s.mode, scoreable,
            label:s.metrics ? (h.neutral ? tremorFinding(s.metrics)
                                        : (s.metrics.reason || s.metrics.label)) : null,
            status:scoreable ? statusOf(s,h) : "none"};
  });
}

/* The points behind one calendar, rebuilt from its state key alone
   (`test` or `test:mode`), so a day or month change can redraw that one
   section without re-rendering every card on the page. */
function calendarFor(key){
  const [test, mode] = String(key).split(":");
  const cfg = TREND[test];
  if(!cfg) return null;
  const sessions = visibleSessions().filter(s =>
    s.test===test && (mode ? s.mode===mode : true));
  return {pts: cardPoints(sessions, cfg.headline), h: cfg.headline};
}

// Selected sub-mode for a test: explicit choice, else the mode with the most
// scoreable sessions (so the card opens on its richest trend).
function activeMode(key, cfg, sessions){
  if(analysisModes[key]) return analysisModes[key];
  const hk = cfg.headline.key;
  let best = cfg.modes[0].key, bestN = -1;
  cfg.modes.forEach(md => {
    const n = sessions.filter(s => s.mode===md.key && s.metrics
      && s.metrics[hk]!=null && isFinite(s.metrics[hk])).length;
    if(n > bestN){ bestN = n; best = md.key; }
  });
  return best;
}
function setTrendMode(key, mode){ analysisModes[key] = mode; renderAnalysis(); }

function deltaChip(cur, prev, lowerBetter){
  const d = cur - prev;
  if(Math.abs(d) < 1e-9) return `<span class="delta delta-flat">${t("no change")}</span>`;
  const improved = lowerBetter ? d < 0 : d > 0;
  const arrow = d > 0 ? I.up : I.down;
  const cls = improved ? "delta-good" : "delta-bad";
  return `<span class="delta ${cls}">${arrow}${fmtNum(Math.abs(d))} ${t("vs last")}</span>`;
}

/* ── SVG line chart with status bands ─────────────────────────────── */
function trendSvg(pts, h){
  const W=640, H=210, padL=46, padR=18, padT=18, padB=36;
  const iw=W-padL-padR, ih=H-padT-padB;
  let vals = pts.map(p=>p.v);
  let lo=Math.min(...vals), hi=Math.max(...vals);
  if(h.bands) h.bands.forEach(b=>{ if(isFinite(b.max)){ lo=Math.min(lo,b.max); hi=Math.max(hi,b.max);} });
  if(lo===hi){ const e=Math.abs(lo)*0.15||1; lo-=e; hi+=e; }
  const p=(hi-lo)*0.12; lo-=p; hi+=p;
  const x = i => padL + (pts.length===1 ? iw/2 : iw*i/(pts.length-1));
  const y = v => padT + ih*(1-(v-lo)/(hi-lo));
  const clampY = v => Math.max(padT, Math.min(padT+ih, y(v)));

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img"
    aria-label="${t("{metric} across {n} sessions",{metric:t(h.name),n:pts.length})}">`;

  // Status bands (value ranges → clamped rects).
  if(h.bands){
    let prevMax = -Infinity;
    for(const b of h.bands){
      const top = clampY(isFinite(b.max)? b.max : hi);
      const bot = clampY(isFinite(prevMax)? prevMax : lo);
      const fill = ST[b.status].band;
      if(bot-top > 0.5) svg += `<rect x="${padL}" y="${top}" width="${iw}" height="${bot-top}" fill="${fill}"/>`;
      prevMax = b.max;
    }
  }

  // Horizontal gridlines + y tick labels (4 ticks).
  const ticks = 4;
  for(let i=0;i<=ticks;i++){
    const v = lo + (hi-lo)*i/ticks, yy = y(v);
    svg += `<line x1="${padL}" y1="${yy}" x2="${padL+iw}" y2="${yy}" stroke="${GRID}" stroke-width="1" opacity="${i===0?0:.55}"/>`;
    svg += `<text x="${padL-8}" y="${yy+3.5}" text-anchor="end" font-size="11" fill="${INK_DIM}" font-family="'JetBrains Mono',monospace">${fmtNum(v)}</text>`;
  }

  // Area fill + line.
  if(pts.length>1){
    const line = pts.map((pt,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(pt.v).toFixed(1)}`).join("");
    const area = `M${x(0).toFixed(1)},${(padT+ih)} `
      + pts.map((pt,i)=>`L${x(i).toFixed(1)},${y(pt.v).toFixed(1)}`).join(" ")
      + ` L${x(pts.length-1).toFixed(1)},${(padT+ih)} Z`;
    svg += `<path d="${area}" fill="${LINE_C}" opacity=".08"/>`;
    svg += `<path d="${line}" fill="none" stroke="${LINE_C}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`;
  }

  // Dots (status-coloured), each a button that opens that session's report.
  // The generous transparent circle underneath is the real hit target - a 4.5px
  // dot is not one. `fill="transparent"`, not "none": "none" takes no pointer.
  pts.forEach((pt,i)=>{
    const last = i===pts.length-1, r = last?6:4.5;
    const title = `${fmtDateTime(pt.iso)} — ${fmtNum(pt.v)}${h.unit} (${t(ST[pt.status].word)})`;
    svg += `<g class="pt" ${pt.id?`data-sid="${pt.id}" tabindex="0" role="button"`:""}`
      + ` aria-label="${t("Open the report for {when}",{when:title})}">`
      + `<title>${title} — ${t("click for the full report")}</title>`
      + `<circle cx="${x(i)}" cy="${y(pt.v)}" r="15" fill="transparent"/>`
      + `<circle class="pt-ring" cx="${x(i)}" cy="${y(pt.v)}" r="${r+4}" fill="${ST[pt.status].dot}"`
      + ` opacity="${last?".22":"0"}"/>`
      + `<circle cx="${x(i)}" cy="${y(pt.v)}" r="${r}" fill="${ST[pt.status].dot}"`
      + ` stroke="#0E1520" stroke-width="${last?2.5:2}"/></g>`;
  });

  // Direct label on the latest value.
  const lx = x(pts.length-1), lv = y(latestVal(pts));
  const above = lv - 14 > padT+6;
  svg += `<text x="${Math.min(lx, W-padR)}" y="${above? lv-12 : lv+18}" text-anchor="${pts.length===1?"middle":"end"}"
    font-size="12.5" font-weight="700" fill="#E2E8F0" font-family="'JetBrains Mono',monospace">${fmtNum(latestVal(pts))}${h.unit}</text>`;

  // X-axis end labels.
  svg += `<text x="${padL}" y="${H-12}" text-anchor="start" font-size="11" fill="${INK_MUTED}">${fmtDate(pts[0].iso)}</text>`;
  if(pts.length>1)
    svg += `<text x="${padL+iw}" y="${H-12}" text-anchor="end" font-size="11" fill="${INK_MUTED}">${fmtDate(pts[pts.length-1].iso)}</text>`;

  return svg + `</svg>`;
}
function latestVal(pts){ return pts[pts.length-1].v; }

function localDateKey(iso){
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function monthKeyFor(iso){ return localDateKey(iso).slice(0,7); }
function fmtTime(iso){
  return new Date(iso).toLocaleTimeString(i18nLocale(),{hour:"numeric",minute:"2-digit"});
}

/* Picking a month or a day redraws that one calendar, not the page. A full
   renderAnalysis() rebuilds all three cards, which throws focus to <body> and
   makes the page jump under the pointer. The section carries its own state
   key, so it can rebuild itself from `analysisSessions` alone. */
function renderCalendar(key){
  const host = document.getElementById("cal-" + key);   // keys contain ":" -
  const ctx = calendarFor(key);                          // getElementById is fine
  if(!host || !ctx) return;
  const active = document.activeElement;
  const keepDay = active && active.classList && active.classList.contains("cal-day");
  host.outerHTML = sessionCalendar(ctx.pts, ctx.h, key);
  if(keepDay){
    const back = document.getElementById("cal-" + key);
    const sel = back && back.querySelector(".cal-day.is-selected");
    if(sel) sel.focus();
  }
}

function setSessionCalendarMonth(key, month){
  if(!month) return;
  sessionCalendarState[key] = {month, day:null};
  renderCalendar(key);
}
function setSessionCalendarDay(key, day){
  const state = sessionCalendarState[key] || {};
  sessionCalendarState[key] = {...state, day};
  renderCalendar(key);
}

/* The report panel's arrows walk every session in the card, so it can land on
   a day - or a month - the calendar is not showing. It calls this to bring the
   calendar to whatever is open; no-op when it is already there, so stepping
   within one day costs nothing. */
window.revealSession = function(id){
  const s = (analysisSessions || []).find(x => x.session_id === id);
  const cfg = s && TREND[s.test];
  if(!cfg) return;
  const key = cfg.modes ? `${s.test}:${s.mode}` : s.test;
  const state = sessionCalendarState[key] || {};
  const month = monthKeyFor(s.timestamp), day = localDateKey(s.timestamp);
  if(state.month===month && state.day===day) return;
  sessionCalendarState[key] = {month, day};
  renderCalendar(key);
};

/* A month calendar of the sessions in this card: the grid is the index, the
   list beside it is the day. Only months that actually hold sessions are
   reachable, because there is no reason to walk through empty ones. */
function sessionCalendar(pts, h, key){
  if(!pts.length) return "";
  const months = [...new Set(pts.map(p=>monthKeyFor(p.iso)))].sort();
  let state = sessionCalendarState[key] || {};
  if(!months.includes(state.month)) state = {month:months[months.length-1], day:null};

  const inMonth = pts.filter(p=>monthKeyFor(p.iso)===state.month);
  const grouped = {};
  inMonth.forEach(p => (grouped[localDateKey(p.iso)] ||= []).push(p));
  const activeDays = Object.keys(grouped).sort();
  if(!activeDays.includes(state.day)) state.day = activeDays[activeDays.length-1];
  sessionCalendarState[key] = state;

  const [year, month] = state.month.split("-").map(Number);
  const first = new Date(year, month-1, 1);
  const offset = (first.getDay()+6)%7;                 // Monday-first
  const nDays = new Date(year, month, 0).getDate();
  const monthAt = months.indexOf(state.month);
  const monthTitle = first.toLocaleDateString(i18nLocale(),{month:"long",year:"numeric"});
  // Jan 1 2024 was a Monday, so this walks Mon..Sun in the page's language.
  const weekdays = Array.from({length:7},(_,i)=>
    new Date(2024,0,1+i).toLocaleDateString(i18nLocale(),{weekday:"narrow"}));
  const todayKey = localDateKey(new Date().toISOString());

  const cells = Array.from({length:offset},()=>`<span class="cal-day cal-blank"></span>`);
  for(let day=1; day<=nDays; day++){
    const dk = `${state.month}-${String(day).padStart(2,"0")}`;
    const runs = grouped[dk] || [];
    const today = dk===todayKey ? " is-today" : "";
    if(!runs.length){
      cells.push(`<span class="cal-day${today}">${day}</span>`);
      continue;
    }
    // One bar under the number, split by how that day's verdicts came out -
    // the mix at a glance without four separate dots competing with the date.
    const mix = ["ok","warn","bad","none"]
      .map(k => [k, runs.filter(p=>p.status===k).length])
      .filter(([,n]) => n)
      .map(([k,n]) => `<i class="vs-${k}" style="flex:${n}"></i>`).join("");
    const when = new Date(year, month-1, day).toLocaleDateString(i18nLocale(),
      {weekday:"long", month:"long", day:"numeric"});
    cells.push(`<button class="cal-day cal-active${dk===state.day?" is-selected":""}${today}"
        data-day="${dk}" onclick="setSessionCalendarDay('${esc(key)}','${dk}')"
        aria-pressed="${dk===state.day}"
        aria-label="${esc(t("{date}: {n} session(s)",{date:when,n:runs.length}))}">
        <span class="cal-num">${day}</span>
        ${runs.length>1?`<span class="cal-count">${runs.length}</span>`:""}
        <span class="cal-bar">${mix}</span></button>`);
  }
  while(cells.length%7) cells.push(`<span class="cal-day cal-blank"></span>`);

  const selected = grouped[state.day] || [];
  const selectedTitle = selected.length
    ? new Date(selected[0].iso).toLocaleDateString(i18nLocale(),
        {weekday:"long", month:"long", day:"numeric"}) : "";
  const rows = selected.map(p=>`<button class="cal-session vs-${p.status}" data-sid="${p.id}"
      title="${esc(p.label ? t(p.label) : t(ST[p.status].word))}">
      <span class="cal-time">${fmtTime(p.iso)}</span>
      <span class="cal-value${p.scoreable?"":" cal-unscored"}">${p.scoreable
        ? `${fmtNum(p.v)}<small>${h.unit}</small>` : "—"}</span>
      <span class="cal-verdict"><i></i>${p.scoreable?t(ST[p.status].word):t("Not scoreable")}</span>
      <span class="cal-go">${I.arrowRight}</span>
    </button>`).join("");

  return `<section class="session-calendar" id="cal-${esc(key)}"
    data-context="${pts.map(p=>p.id).filter(Boolean).join(",")}">
    <div class="cal-head">
      <div class="cal-month">
        <button class="cal-step" ${monthAt>0?"":"disabled"}
          onclick="setSessionCalendarMonth('${esc(key)}','${months[monthAt-1]||""}')"
          aria-label="${t("Previous month with sessions")}">${I.arrowLeft}</button>
        <h4>${monthTitle}</h4>
        <button class="cal-step" ${monthAt<months.length-1?"":"disabled"}
          onclick="setSessionCalendarMonth('${esc(key)}','${months[monthAt+1]||""}')"
          aria-label="${t("Next month with sessions")}">${I.arrowRight}</button>
      </div>
      <span class="cal-tally">${t("{days} active days · {n} sessions",
        {days:activeDays.length, n:inMonth.length})}</span>
    </div>
    <div class="cal-body">
      <div class="cal-grid-wrap">
        <div class="cal-weekdays" aria-hidden="true">${weekdays.map(w=>`<span>${w}</span>`).join("")}</div>
        <div class="cal-grid">${cells.join("")}</div>
      </div>
      <div class="cal-day-panel">
        <div class="cal-day-head"><strong>${selectedTitle}</strong>
          <span>${t("{n} session(s)",{n:selected.length})}</span></div>
        <div class="cal-list">${rows}</div>
      </div>
    </div>
  </section>`;
}
/* One listener for the whole page: charts and calendars are re-rendered on every
   filter change, so per-element handlers would have to be re-bound each time.
   openReport lives in report.js, which loads after this file. */
const analysisBodyEl = document.getElementById("analysis-body");
if(analysisBodyEl){
  const open = el => { if(el && el.dataset.sid) window.openReport?.(el.dataset.sid); };
  analysisBodyEl.addEventListener("click", e => {
    open(e.target.closest("[data-sid]"));
  });
  analysisBodyEl.addEventListener("keydown", e => {
    if(e.key!=="Enter" && e.key!==" ") return;
    // Native <button>s already turn Enter/Space into click. This handler is
    // only for the SVG chart points; handling both caused duplicate opens.
    const el = e.target.closest(".pt[data-sid]");
    if(el){ e.preventDefault(); open(el); }
  });
}

function supportTile(sessions, m){
  const series = sessions
    .map(s => s.metrics ? s.metrics[m.key] : null)
    .filter(v => v!=null && isFinite(v));
  if(!series.length)
    return `<div class="sup-tile"><div class="sup-name">${t(m.name)}</div><div class="sup-val">—</div></div>`;
  const cur = series[series.length-1];
  return `<div class="sup-tile">
    <div class="sup-name">${t(m.name)}</div>
    <div class="sup-row"><span class="sup-val">${fmtNum(cur)}<span class="sup-unit">${m.unit}</span></span>
    ${miniSpark(series)}</div></div>`;
}

function miniSpark(vals){
  if(vals.length<2) return "";
  const W=64, H=22, p=3;
  const lo=Math.min(...vals), hi=Math.max(...vals), rng=(hi-lo)||1;
  const x=i=>p+(W-2*p)*i/(vals.length-1);
  const y=v=>p+(H-2*p)*(1-(v-lo)/rng);
  const d=vals.map((v,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return `<svg class="sup-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${d}" fill="none" stroke="${LINE_C}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${x(vals.length-1)}" cy="${y(vals[vals.length-1])}" r="2.2" fill="${LINE_C}"/></svg>`;
}

/* ── Readings strip (home) ─────────────────────────────
   The dashboard's headline row: each test's latest headline metric, its band,
   and a spark of the sessions behind it — the same TREND config the Analysis
   page charts, so the two can never disagree. Nothing logged yet still says
   what the tile will measure, which is what a fresh install sees. */

async function loadVitals(force){
  if(force || !analysisSessions){
    try{
      const r = await fetch("/api/sessions");
      analysisSessions = (await r.json()).sessions || [];
    }catch(e){ analysisSessions = analysisSessions || []; }
  }
  renderVitals();
}

function renderVitals(){
  const el = document.getElementById("vitals");
  if(!el) return;
  const byTest = {};
  TREND_ORDER.forEach(k => byTest[k] = []);
  visibleSessions().forEach(s => { if(byTest[s.test]) byTest[s.test].push(s); });
  el.innerHTML = TREND_ORDER.filter(k => !TREND[k].secondary)
    .map(k => vitalTile(k, byTest[k])).join("");

  // The strip follows the same person as the Analysis page, so it has to say
  // whose readings these are - one patient's numbers must not read as pooled.
  const who = document.getElementById("vitals-who");
  if(who){
    const cur = profileFilter();
    const pr = cur !== "all" && cur !== "none" ? window.profileById?.(cur) : null;
    who.textContent = pr ? t("for {name}", {name: pr.name})
      : cur === "none" ? t("unassigned sessions") : "";
  }
}

function vitalTile(key, sessions){
  const cfg = TREND[key], h = cfg.headline;
  const pts = sessions
    .map(s => ({ v:s.metrics ? s.metrics[h.key] : null, iso:s.timestamp,
                 confidence:s.metrics ? s.metrics.confidence_pct : null,
                 status:bandFor(s.metrics ? s.metrics[h.key] : null, h.bands) }))
    .filter(p => p.v!=null && isFinite(p.v));
  const head = `<span class="vital-ic">${I[cfg.icon]}</span><span class="vital-test">${t(cfg.label)}</span>`;
  const name = `<div class="vital-name">${t(h.name)}${h.unit?` <span class="vital-unit-i">(${h.unit})</span>`:""}</div>`;

  if(!pts.length){
    return `<button class="vital vital-idle" onclick="showPage('${cfg.page}')">
      <div class="vital-head">${head}<span class="vital-wait">${t("Not run yet")}</span></div>
      <div class="vital-val vital-dim">—</div>
      ${name}
      <div class="vital-spark">${idleSpark()}</div>
      <div class="vital-foot"><span>${t("Run it once to set your baseline")}</span>
        <span class="vital-go">${I.arrowRight}</span></div>
    </button>`;
  }

  const latest = pts[pts.length-1], prev = pts.length>1 ? pts[pts.length-2] : null;
  const st = ST[latest.status];
  const count = pts.length===1 ? t("first reading") : t("{n} sessions",{n:pts.length});
  return `<button class="vital" onclick="showPage('analysis')">
    <div class="vital-head">${head}
      <span class="badge badge-${latest.status}"><span class="badge-dot"></span>${t(st.word)}</span></div>
    <div class="vital-val">${fmtNum(latest.v)}<span class="vital-unit">${h.unit}</span></div>
    ${name}
    <div class="vital-spark">${vitalSpark(pts, h, key)}</div>
    <div class="vital-foot"><span>${count} · ${fmtDate(latest.iso)}</span>
      ${prev ? deltaChip(latest.v, prev.v, h.lowerBetter) : ""}</div>
  </button>`;
}

// Spark for one tile: status bands behind, the last few sessions as a line,
// each dot coloured by its band. Same band geometry as trendSvg, no axes.
function vitalSpark(all, h, key){
  const pts = all.slice(-14);
  const W=280, H=64, pad=7;
  const vals = pts.map(p=>p.v);
  let lo=Math.min(...vals), hi=Math.max(...vals);
  if(h.bands) h.bands.forEach(b=>{ if(isFinite(b.max)){ lo=Math.min(lo,b.max); hi=Math.max(hi,b.max);} });
  if(lo===hi){ const e=Math.abs(lo)*0.15||1; lo-=e; hi+=e; }
  const m=(hi-lo)*0.15; lo-=m; hi+=m;
  const x=i=>pad+(pts.length===1 ? (W-2*pad)/2 : (W-2*pad)*i/(pts.length-1));
  const y=v=>pad+(H-2*pad)*(1-(v-lo)/(hi-lo));
  const clampY=v=>Math.max(0, Math.min(H, y(v)));
  const gid = `vspark-${key}`;

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">`
    + `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${LINE_C}" stop-opacity=".26"/>
        <stop offset="1" stop-color="${LINE_C}" stop-opacity="0"/></linearGradient></defs>`;

  if(h.bands){
    let prevMax = -Infinity;
    for(const b of h.bands){
      const top = clampY(isFinite(b.max)? b.max : hi);
      const bot = clampY(isFinite(prevMax)? prevMax : lo);
      if(bot-top > 0.5) svg += `<rect x="0" y="${top}" width="${W}" height="${bot-top}" fill="${ST[b.status].band}"/>`;
      prevMax = b.max;
    }
  }
  if(pts.length>1){
    const line = pts.map((p,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    svg += `<path d="${line} L${x(pts.length-1).toFixed(1)},${H} L${x(0).toFixed(1)},${H} Z" fill="url(#${gid})"/>`;
    svg += `<path d="${line}" fill="none" stroke="${LINE_C}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  pts.forEach((p,i)=>{
    const last = i===pts.length-1;
    if(last) svg += `<circle cx="${x(i)}" cy="${y(p.v)}" r="7" fill="${ST[p.status].dot}" opacity=".24"/>`;
    const opacity = p.confidence != null && p.confidence < 45 ? ".35" : "1";
    svg += `<circle cx="${x(i)}" cy="${y(p.v)}" r="${last?4:2.8}" fill="${ST[p.status].dot}"`
      + ` opacity="${opacity}" stroke="#0E1520" stroke-width="${last?2:1.5}"/>`;
  });
  return svg + `</svg>`;
}

function idleSpark(){
  const W=280, H=64;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <line x1="7" y1="${H/2}" x2="${W-7}" y2="${H/2}" stroke="${GRID}" stroke-width="2"
      stroke-linecap="round" stroke-dasharray="3 9"/></svg>`;
}

/* ── Finger tapping: mode switcher ────────────────────────────────────
   The two modes share their first two steps, so they are one filmstrip each
   behind a tablist rather than two half-width columns. The choice is a
   per-viewer convenience, so browser storage is enough (and optional). */
const TAP_MODE_KEY = "hand3d.tapMode";
function setTapMode(mode, focus){
  const tabs = document.querySelectorAll("#iiv-seg [role=tab]");
  if(![...tabs].some(b => b.dataset.mode === mode)) return;
  tabs.forEach(b => {
    const on = b.dataset.mode === mode;
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
    if(on && focus) b.focus();
  });
  document.querySelectorAll("#page-iiv .filmstrip[data-mode]")
    .forEach(p => { p.hidden = p.dataset.mode !== mode; });
  try{ localStorage.setItem(TAP_MODE_KEY, mode); }catch(e){ /* private window */ }
  renderTapRecording();
}
function tapMode(){
  const on = document.querySelector("#iiv-seg [aria-selected=true]");
  return on ? on.dataset.mode : "fast";
}

/* ── "What we measure": one real run per test page ────────────────────
   Each test page shows a real recording rather than a diagram of one. The
   files are de-identified copies of sessions from results/ (the raw trace and
   the metrics; no profile, name or timestamp), so the page draws the same
   thing on the local hub and on the published site, where there is no results
   folder. The charts are report.js's own, so this is exactly what a session
   report shows. A test with no clean run yet has `file: null` and keeps the
   placeholder frame its markup ships with; see launcher_web/img/<test>/. */
const recNum = (v, d) => v == null || !isFinite(v) ? null : (+v).toFixed(d);
const RECORDINGS = {
  iiv: {
    file: "img/tapping/example-recordings.json",
    pick: all => all[tapMode()],
    body: rec => {
      const c = window.tapCharts(rec);
      return `<div class="rec-block"><h3>${t("Finger distance, every tap marked")}</h3>${c.trace}</div>`
        + `<div class="rec-block"><h3>${t("Gap between taps")}</h3>${c.intervals}</div>`;
    },
    tiles: m => [
      [t("Rhythm") + " · CV", recNum(m.cv_pct, 1), "%", true],
      [t("Speed"), recNum(m.frequency_hz, 2), "Hz"],
      [t("Slowdown"), recNum(m.decrement_pct_per_s, 2), "%/s"],
      [t("Tap size") + " · CV", recNum(m.amplitude_cv_pct, 1), "%"],
      [t("Beat sync") + " · SD", recNum(m.sync_sd_ms, 0), "ms"],
    ],
  },
  spiral: {
    file: "img/spiral/example-recording.json",
    tiles: m => [
      [t("Smoothness"), recNum(m.smoothness_index, 0), "/100", true],
      [t("Speed variation") + " · CV", recNum(m.vel_cv_pct, 1), "%"],
      [t("Completion"), recNum(m.completion_pct, 0), "%"],
      [t("Tremor band"), recNum(m.tremor_power_frac == null ? null : m.tremor_power_frac * 100, 1), "%"],
    ],
  },
  oculomotor: {
    file: "img/oculomotor/example-recording.json",
    tiles: m => [
      [t("Wrong-way looks"), recNum(m.error_rate_pct, 1), "%", true],
      ["Anti − Pro", recNum(m.anti_minus_pro_ms, 0), "ms"],
      [t("Self-corrected"), recNum(m.corrected_rate_pct, 1), "%"],
      [t("Valid trials"), recNum(m.valid_trials, 0), ""],
    ],
  },
  ddk: {
    file: null,   // the only run on record was too noisy to score
    tiles: m => [
      [t("Rhythm") + " · CV", recNum(m.rhythm_cv_pct, 1), "%", true],
      [t("Rate"), recNum(m.syllable_rate_hz, 1), "/s"],
      ["nPVI", recNum(m.npvi, 0), ""],
      [t("Order errors"), recNum(m.sequence_error_pct, 1), "%"],
    ],
  },
  tremor: {
    file: null,   // not run live yet
    tiles: m => [
      [t("Peak frequency"), recNum(m.tremor_peak_hz, 1), "Hz", true],
      [t("Tremor size"), recNum(m.tremor_amp_pct, 2), "%"],
      [t("Left / right"), recNum(m.asymmetry_ratio, 2), "×"],
    ],
  },
  gait: {
    file: null,   // not run live yet
    tiles: m => [
      [t("Five sit-to-stands"), recNum(m.sts5_s, 1), "s", true],
      [t("Right leg stamps"), recNum(m.leg_right_rate_hz, 1), "/s"],
      [t("Left leg stamps"), recNum(m.leg_left_rate_hz, 1), "/s"],
      [t("Failed rises"), recNum(m.failed_attempts, 0), ""],
    ],
  },
};
const recFiles = {};
function loadRecording(path){
  return recFiles[path] || (recFiles[path] = fetch(path)
    .then(r => r.ok ? r.json() : null).catch(() => null));
}
async function renderRecording(key){
  const cfg = RECORDINGS[key];
  const card = document.querySelector(`.rec-card[data-rec="${key}"]`);
  // No file yet: the markup's placeholder stays. Before report.js has run:
  // the DOMContentLoaded call below draws it.
  if(!cfg || !card || !cfg.file || !window.recordingSections) return;
  const want = key === "iiv" ? tapMode() : "";
  const all = await loadRecording(cfg.file);
  if(key === "iiv" && want !== tapMode()) return;   // the tab changed while loading
  const rec = all && (cfg.pick ? cfg.pick(all) : all);
  const body = card.querySelector(".rec-body");
  const stats = card.querySelector(".rec-stats");
  const chips = card.querySelector(".metric-chips");
  card.classList.remove("is-empty");
  if(!rec){
    body.innerHTML = `<div class="rec-empty">${t("The example recording could not be loaded.")}</div>`;
    stats.innerHTML = chips.innerHTML = "";
    return;
  }
  body.innerHTML = cfg.body ? cfg.body(rec)
    : window.recordingSections(rec, {trial: card.dataset.trial || null});
  const m = rec.metrics || {};
  const k = VERDICT[m.status] || "none", st = ST[k];
  const ico = {ok:I.check, warn:I.info, bad:I.x}[k] || I.info;
  stats.innerHTML = `<span class="rec-verdict" style="color:${st.dot};background:${st.band}">${ico} ${t(st.word)}</span>`;
  chips.innerHTML = cfg.tiles(m).filter(r => r[1] != null).map(([label, v, unit, lead]) =>
    `<div class="metric-chip${lead ? " lead" : ""}"><b>${v}<small>${unit}</small></b><span>${label}</span></div>`).join("");
}
function renderRecordings(){ Object.keys(RECORDINGS).forEach(renderRecording); }
function renderTapRecording(){ renderRecording("iiv"); }

// The eye test's trials open one at a time, as they do in the report.
document.addEventListener("click", e => {
  const chip = e.target.closest(".rec-card [data-trial]");
  if(!chip) return;
  const card = chip.closest(".rec-card");
  const cfg = RECORDINGS[card.dataset.rec];
  const sel = card.dataset.trial === chip.dataset.trial ? "" : chip.dataset.trial;
  card.dataset.trial = sel;
  card.querySelectorAll("[data-trial]").forEach(c => c.classList.toggle("is-open", c.dataset.trial === sel));
  loadRecording(cfg.file).then(rec => {
    const panel = card.querySelector("[data-trial-panel]");
    if(rec && panel) panel.innerHTML = window.trialPanelFor(rec, sel || null);
  });
});

(function initTapMode(){
  const seg = document.getElementById("iiv-seg");
  if(seg){
    seg.addEventListener("keydown", e => {
      const tabs = [...seg.querySelectorAll("[role=tab]")];
      const i = tabs.indexOf(document.activeElement);
      if(i < 0) return;
      const next = {ArrowRight:i+1, ArrowLeft:i-1, Home:0, End:tabs.length-1}[e.key];
      if(next === undefined) return;
      e.preventDefault();
      setTapMode(tabs[(next + tabs.length) % tabs.length].dataset.mode, true);
    });
    let saved = null;
    try{ saved = localStorage.getItem(TAP_MODE_KEY); }catch(e){}
    if(saved) setTapMode(saved);
  }
  // report.js (which owns the charts) loads after this file, so the first
  // draw waits for the page to finish parsing.
  document.addEventListener("DOMContentLoaded", renderRecordings);
})();

/* ── Language switch ──────────────────────────────────────────────────
   Almost everything on these pages is built from JS, so a switch has to ask
   each builder to run again. The "built once" flags are cleared first. */
onLang(lang => {
  cardsBuilt = false; whyBuilt = false;   // the status row keys off getLang()
  // Each section is guarded on its own. As one sequence, a throw in any of
  // them skipped every later one and left the DOM half-rebuilt — losing the
  // Launch buttons that buildCards() owns because a chart failed to draw.
  const step = fn => { try{ fn(); }catch(e){ console.error(e); } };
  step(renderStaticBits);
  step(buildCards);
  step(renderWhy);
  step(refresh);
  step(() => window.renderProfileChips?.(true));
  step(renderVitals);
  step(renderRecordings);
  if(analysisSessions) step(renderAnalysis);
  saveLang(lang);
});

/* The switch also picks the language of the OpenCV overlays. The hub stores it
   so a tool started straight from a terminal follows the same choice; it takes
   effect at launch, so a switch mid-run applies to the next start. */
async function saveLang(lang){
  try{
    await fetch("/api/lang", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({lang})
    });
  }catch(e){ /* hub not reachable: the page still switches, the tools don't */ }
}

/* ── Init ─────────────────────────────────────────────────────────── */
refresh();
loadVitals();
saveLang(getLang());   // onLang only fires on a change; seed the stored value
setInterval(refresh, 3000);
