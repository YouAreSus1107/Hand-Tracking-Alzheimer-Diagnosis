/* ── Glove map: every glove channel drawn where it sits on a 3D hand ──────
   ES module (three.js), a sibling of hand3d.js, on the Developer page.

   It owns NO sensor maths. Each tick it reads window.devGloveSnapshot() from
   dev.js, which runs the same force/bend conversions as the channel tiles, so
   the map can never show a number a tile does not. This file only decides
   WHERE a channel sits, and how that looks.

   Layout: docs/glove/GLOVE_EXPANSION_PLAN.md §4 (decided 2026-09-21) —
   flex f0-f3 on the backs of thumb..ring, FSR402 p0-p3 on the same fingertips,
   FlexiForce A401 h0-h2 on the thenar, hypothenar and distal palm, and the
   board's IMU on the back of the hand. Design: GLOVE_FIRMWARE_PLAN.md §7b —
   fill = now, ring = peak since Z, and a site with no sensor fitted draws
   faint and empty, so the map fills in as sensors are soldered on with no
   code change per sensor. Sites are matched by CHANNEL NAME from the banner.

   Motion: the board's raw 100 Hz accelerometer + gyro are fused into an
   orientation (glove_fusion.js), mapped onto the hand through a two-pose
   mounting calibration, and drive the whole hand; flex drives the fingers.

   The model is assets/models/hand.gltf (the same rigged hand the home page shows).
   Its bones point along local +Y and curl about local +Z — read off the
   model's own "OK hand" pose (CURL_SIGN below). */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as fusionLib from './glove_fusion.js';

const stage   = document.getElementById('g3d-stage');
const canvas  = document.getElementById('g3d-canvas');
const tagsEl  = document.getElementById('g3d-tags');
const listEl  = document.getElementById('g3d-list');
const viewsEl = document.getElementById('g3d-views');
const emptyEl = document.getElementById('g3d-empty');
if (!stage || !canvas) throw new Error('glove map elements missing');

const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* i18n.js is a classic script; reach its translator through window. Never
   bind it to a bare `t` here, which is the name every loop wants. */
const tr = (s, p) => {
  if (window.t) return window.t(s, p);
  return p ? s.replace(/\{(\w+)\}/g, (m, k) => (k in p ? p[k] : m)) : s;
};

/* ── where each channel lives ─────────────────────────────────────────── */

const FINGER_BONES = {
  thumb:  ['thumb_meta_18', 'thumb_prox_17', 'thumb_dist_16'],
  index:  ['index_prox_14', 'index_midd_13', 'index_dist_12'],
  middle: ['midd_prox_10',  'midd_midd_9',   'midd_dist_8'],
  ring:   ['ring_prox_6',   'ring_midd_5',   'ring_dist_4'],
};

/* Joint flexion at 100 % bend, radians, per bone above. ILLUSTRATIVE: flex.py
   reports a position within a recorded span, never degrees (plan §5c), so
   these only decide how a full-span reading looks. */
const CURL = {
  thumb:  [0.30, 0.75, 1.00],
  finger: [1.25, 1.50, 1.05],
};

/* Offsets in the model's bone units (a middle-finger proximal phalanx is
   ~2.8 units, so one unit is roughly 1.6 cm of real hand). */
const PAD_DEPTH  = 0.55;   // fingertip pad, below the bone
const BACK_DEPTH = 0.55;   // flex strip, above the finger
const PALM_DEPTH = 0.95;   // palm pads, below the metacarpals
const IMU_DEPTH  = 1.05;   // board, on the back of the hand

/* `at` is [bone, fraction along it] for finger sites. Palm sites are blends of
   two such points, because the thenar pad lies between two bones. */
const SITES = [
  {name: 'p0', kind: 'fsr', group: 'tip',  site: 'thumb tip',  at: ['thumb_dist_16', 0.80]},
  {name: 'p1', kind: 'fsr', group: 'tip',  site: 'index tip',  at: ['index_dist_12', 0.80]},
  {name: 'p2', kind: 'fsr', group: 'tip',  site: 'middle tip', at: ['midd_dist_8',   0.80]},
  {name: 'p3', kind: 'fsr', group: 'tip',  site: 'ring tip',   at: ['ring_dist_4',   0.80]},
  {name: 'h0', kind: 'flexiforce', group: 'palm', site: 'thenar (thumb base)',
   blend: [['thumb_meta_18', 0.15], ['index_meta_15', 0.30], 0.45]},
  {name: 'h1', kind: 'flexiforce', group: 'palm', site: 'hypothenar (heel)',
   blend: [['pinky_meta_3', 0.35], ['ring_meta_7', 0.35], 0.25]},
  {name: 'h2', kind: 'flexiforce', group: 'palm', site: 'distal palm',
   blend: [['index_meta_15', 0.82], ['ring_meta_7', 0.82], 0.50]},
  {name: 'f0', kind: 'flex', group: 'flex', site: 'thumb',  finger: 'thumb'},
  {name: 'f1', kind: 'flex', group: 'flex', site: 'index',  finger: 'index'},
  {name: 'f2', kind: 'flex', group: 'flex', site: 'middle', finger: 'middle'},
  {name: 'f3', kind: 'flex', group: 'flex', site: 'ring',   finger: 'ring'},
];
const GROUPS = [
  {id: 'tip',  title: 'Fingertips — FSR402'},
  {id: 'palm', title: 'Palm — FlexiForce A401'},
  {id: 'flex', title: 'Fingers — flex strip'},
  {id: 'imu',  title: 'Back of hand — IMU'},
];

/* ── colours (tokens from styles.css :root) ──────────────────────────────
   One sequential hue for "how much", status colours kept for status only:
   amber = beyond the part's rated band, grey = not fitted / raw only. */
const RAMP = [new THREE.Color('#134E4A'), new THREE.Color('#12A594'), new THREE.Color('#A7F3E4')];
const C_WARN  = new THREE.Color('#F5A524');
const C_GHOST = new THREE.Color('#8C9BB2');
const C_HAND  = new THREE.Color('#9FB3C8');
function ramp(x, out) {
  x = Math.max(0, Math.min(1, x));
  return x < 0.5 ? out.lerpColors(RAMP[0], RAMP[1], x * 2)
                 : out.lerpColors(RAMP[1], RAMP[2], (x - 0.5) * 2);
}

/* ── scene ───────────────────────────────────────────────────────────── */

const scene  = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 10);
/* Slightly above, looking down at the hand: reads both a raised hand and one
   lying flat, which are the two calibration poses. */
const CAM_HOME = new THREE.Vector3(0, 0.26, 0.74);
camera.position.copy(CAM_HOME);

let renderer = null, controls = null;
const tiltG = new THREE.Group();          // IMU orientation: hand + anchors
scene.add(tiltG);
/* The rig is a LEFT hand (palm to the camera, thumb on screen-left). A right
   glove mirrors it here, below the orientation, so the IMU maths never sees
   the flip: calibration measures hand axes geometrically (x = fingers x palm),
   which lands on the thumb side of a right hand and the little-finger side of
   a left one — exactly where the mirrored and unmirrored rig put them. */
const mirrorG = new THREE.Group();
tiltG.add(mirrorG);
const markers = new THREE.Group();        // world-space markers, billboarded
scene.add(markers);

scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(0.6, 1, 1.2);
scene.add(keyLight);
const rim = new THREE.DirectionalLight(0x12A594, 0.5);
rim.position.set(-1, 0.4, -1);
scene.add(rim);

/* ── state ───────────────────────────────────────────────────────────── */

let loaded = false, loading = false, failed = false;
let running = false, raf = null, listTimer = null;
let follow = true;                       // hand follows the IMU once calibrated
let handSide = 'right';                  // which hand the glove is on
const fusion = fusionLib.createFusion();
const _qShow = new THREE.Quaternion();
const STORE_KEY = 'hand3d.gloveMount';
try {
  const saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
  if (saved) {
    fusionLib.importMount(fusion, saved.mount);
    if (saved.hand === 'left' || saved.hand === 'right') handSide = saved.hand;
  }
} catch (e) { /* private window or blocked storage: start uncalibrated */ }
function saveMount() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({mount: fusionLib.exportMount(fusion), hand: handSide}));
  } catch (e) { /* not fatal: the calibration just will not survive a reload */ }
}
let unit = 1;                            // world units per bone unit
/* Which way about local Z is flexion. Not measurable from the rig alone (a
   trial rotation moves the tip toward -X whichever way is "real"), so it is
   read off the model's own Pose_OK clip: index_midd sits at +0.64 rad about Z
   there, ~79°, and a PIP joint cannot hyperextend 79°. So +Z curls, and a
   curling tip moves toward the bone's -X side — the palmar side. */
const CURL_SIGN = 1;
const bones = {};                        // name -> Bone
const rest = {};                         // name -> rest quaternion
const bend = {};                         // finger -> smoothed 0..1
const sites = [];                        // runtime per site
let imuSite = null;
let snap = null;                         // last devGloveSnapshot()

const _v = new THREE.Vector3(), _q = new THREE.Quaternion(), _z = new THREE.Vector3(0, 0, 1);

/* ── model ───────────────────────────────────────────────────────────── */

function boneLength(b) {
  const child = b.children.find(c => c.isBone);
  if (child) return child.position.length();
  return 0.75 * b.position.length();     // distal bone: no child, estimate
}

/* An Object3D riding on a bone, at `u` of its length, pushed `depth` along
   local X (palmar = -CURL_SIGN, dorsal = +CURL_SIGN). It follows the finger as
   it bends, which is the whole reason sites are bone children. */
function anchorOn(boneName, u, depth) {
  const b = bones[boneName];
  const a = new THREE.Object3D();
  a.position.set(depth, u * boneLength(b), 0);
  b.add(a);
  return a;
}

function onModel(gltf) {
  const model = gltf.scene;
  model.traverse(o => {
    if (o.isBone) { bones[o.name] = o; rest[o.name] = o.quaternion.clone(); }
    if (o.isMesh) {
      o.frustumCulled = false;           // bent fingers leave the bind-pose bounds
      /* A glass hand: markers on the far side stay visible, and none of them
         is ever hidden behind skin. depthWrite off so it never occludes. */
      o.material = new THREE.MeshStandardMaterial({
        color: C_HAND, roughness: 0.55, metalness: 0.0,
        transparent: true, opacity: 0.30, depthWrite: false, side: THREE.DoubleSide,
      });
      o.renderOrder = 1;
    }
  });
  const need = ['radius_ulna_20', 'midd_meta_11', 'midd_prox_10', ...Object.values(FINGER_BONES).flat()];
  if (need.some(n => !bones[n])) { fail('rig'); return; }

  const align = new THREE.Group(), pivot = new THREE.Group();
  align.add(model); pivot.add(align); mirrorG.add(pivot);
  pivot.updateMatrixWorld(true);

  /* Stand the hand up, palm to the camera: fingers along +Y, palm normal +Z.
     The palm normal is the way a finger moves when it curls, so it is taken
     from a trial curl of the middle finger rather than from the rig's axes —
     the rig could be a left or a right hand. */
  const wrist = bones.radius_ulna_20.getWorldPosition(new THREE.Vector3());
  const knuckle = bones.midd_prox_10.getWorldPosition(new THREE.Vector3());
  const up = knuckle.clone().sub(wrist).normalize();
  const tip0 = bones.midd_dist_8.getWorldPosition(new THREE.Vector3());
  const midd = bones.midd_prox_10;
  midd.quaternion.multiply(_q.setFromAxisAngle(_z, CURL_SIGN * 0.6));
  pivot.updateMatrixWorld(true);
  const tip1 = bones.midd_dist_8.getWorldPosition(new THREE.Vector3());
  midd.quaternion.copy(rest.midd_prox_10);
  pivot.updateMatrixWorld(true);
  const palm = tip1.sub(tip0);
  palm.addScaledVector(up, -palm.dot(up)).normalize();
  const right = new THREE.Vector3().crossVectors(up, palm).normalize();
  const basis = new THREE.Matrix4().makeBasis(right, up, palm);
  align.quaternion.setFromRotationMatrix(basis).invert();
  pivot.updateMatrixWorld(true);

  const box = new THREE.Box3().setFromObject(pivot, true);
  const size = box.getSize(new THREE.Vector3());
  const s = 0.30 / Math.max(size.x, size.y, size.z);
  const centre = box.getCenter(new THREE.Vector3());
  pivot.scale.setScalar(s);
  pivot.position.copy(centre).multiplyScalar(-s);
  pivot.updateMatrixWorld(true);

  unit = bones.midd_prox_10.getWorldPosition(new THREE.Vector3())
    .distanceTo(bones.midd_meta_11.getWorldPosition(new THREE.Vector3()))
    / boneLength(bones.midd_meta_11);

  buildSites();
  applyHand();
  loaded = true; loading = false;
  renderList();
}

function buildSites() {
  const palmar = -CURL_SIGN, dorsal = CURL_SIGN;
  for (const def of SITES) {
    const r = {def, marker: null, anchors: [], tag: null, tube: null, tubeKey: ''};
    if (def.at) {
      r.anchors.push(anchorOn(def.at[0], def.at[1], palmar * PAD_DEPTH));
    } else if (def.blend) {
      /* Two points, blended in world space, then parked on the middle
         metacarpal so the pad rides with the palm. The metacarpals are never
         bent, so this stays put. */
      const [[b1, u1], [b2, u2], w] = def.blend;
      const pointOn = (bn, u) => {
        const probe = anchorOn(bn, u, 0);
        const p = probe.getWorldPosition(new THREE.Vector3());
        bones[bn].remove(probe);
        return p;
      };
      const p = pointOn(b1, u1).lerp(pointOn(b2, u2), w);
      p.addScaledVector(new THREE.Vector3(0, 0, 1), PALM_DEPTH * unit);
      const a = new THREE.Object3D();
      a.position.copy(p);
      bones.midd_meta_11.attach(a);
      r.anchors.push(a);
    } else if (def.finger) {
      /* Five points along the back of the finger, for the strip. */
      const [b0, b1, b2] = FINGER_BONES[def.finger];
      r.anchors.push(anchorOn(b0, 0.10, dorsal * BACK_DEPTH),
                     anchorOn(b0, 0.60, dorsal * BACK_DEPTH),
                     anchorOn(b1, 0.50, dorsal * BACK_DEPTH),
                     anchorOn(b2, 0.30, dorsal * BACK_DEPTH),
                     anchorOn(b2, 0.80, dorsal * BACK_DEPTH));
      bend[def.finger] = 0;
    }
    if (def.group !== 'flex') r.marker = makeDisc(def.group === 'palm' ? 0.017 : 0.011);
    else {
      const mat = new THREE.MeshBasicMaterial({color: C_GHOST, transparent: true, opacity: 0.3});
      r.tube = new THREE.Mesh(new THREE.BufferGeometry(), mat);
      r.tube.renderOrder = 2;
      markers.add(r.tube);
      r.marker = makeDisc(0.007);          // the strip's label point, at the knuckle
    }
    sites.push(r);
  }

  /* The board: a flat slab on the back of the hand, oriented with the palm. */
  const a = anchorOn('midd_meta_11', 0.45, dorsal * IMU_DEPTH);
  const slab = new THREE.Mesh(
    new THREE.BoxGeometry(0.004, 0.034, 0.022),
    new THREE.MeshStandardMaterial({color: 0x1C2430, emissive: 0x0E8577, emissiveIntensity: 0.25,
                                    roughness: 0.4, transparent: true, opacity: 0.95}));
  slab.renderOrder = 2;
  markers.add(slab);
  imuSite = {anchor: a, slab, halo: makeDisc(0.024), tag: null};
}

function makeDisc(r) {
  const g = new THREE.Group();
  const fill = new THREE.Mesh(new THREE.CircleGeometry(1, 40),
    new THREE.MeshBasicMaterial({color: C_GHOST, transparent: true, opacity: 0, depthTest: false}));
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.80, 1, 48),
    new THREE.MeshBasicMaterial({color: C_GHOST, transparent: true, opacity: 0.35, depthTest: false}));
  fill.renderOrder = 3; ring.renderOrder = 4;
  g.add(fill, ring);
  g.userData = {r, fill, ring};
  markers.add(g);
  return g;
}

function fail(why) {
  failed = true; loading = false;
  console.warn('Glove map: model unavailable', why);
  emptyEl.textContent = tr('The hand model could not be loaded — the sensor list beside it is still live.');
  emptyEl.style.display = '';
}

/* ── per-frame ───────────────────────────────────────────────────────── */

function chanByName() {
  const m = new Map();
  if (snap && snap.connected) for (const c of snap.channels) m.set(c.name, c);
  return m;
}

function smoothTo(cur, target, dt, rate) {
  return cur + (target - cur) * Math.min(1, dt * rate);
}

function frame(dt) {
  snap = window.devGloveSnapshot ? window.devGloveSnapshot() : null;
  const by = chanByName();

  /* Flex first: bones move, then every anchor is read in its new place. */
  for (const r of sites) {
    const {def} = r;
    if (!def.finger) continue;
    const c = by.get(def.name);
    const target = c && c.kind === 'flex' && c.cur !== null ? c.cur : 0;
    bend[def.finger] = REDUCED ? target : smoothTo(bend[def.finger], target, dt, 12);
    const curl = def.finger === 'thumb' ? CURL.thumb : CURL.finger;
    FINGER_BONES[def.finger].forEach((n, k) => {
      bones[n].quaternion.copy(rest[n])
        .multiply(_q.setFromAxisAngle(_z, CURL_SIGN * curl[k] * bend[def.finger]));
    });
  }

  /* Whole-hand orientation from the fused IMU. The filter already runs at the
     board's 100 Hz (glove3dFeed), so this only eases the display between
     polls; it adds no lag worth measuring. Uncalibrated, or with following
     off, the hand settles back to the upright reference pose. */
  const imu = snap && snap.connected ? snap.imu : null;
  const q = follow && snap && snap.connected ? fusionLib.handToScreen(fusion) : null;
  if (q) _qShow.set(q[1], q[2], q[3], q[0]); else _qShow.identity();
  if (REDUCED) tiltG.quaternion.copy(_qShow);
  else tiltG.quaternion.slerp(_qShow, Math.min(1, dt * (q ? 25 : 4)));
  scene.updateMatrixWorld(true);
  renderCal();

  for (const r of sites) {
    const c = by.get(r.def.name);
    if (r.tube) drawStrip(r, c);
    r.anchors[r.def.finger ? 1 : 0].getWorldPosition(r.marker.position);
    paintDisc(r.marker, c, r.def);
  }

  const on = !!(imu && imu.present);
  imuSite.anchor.getWorldPosition(imuSite.slab.position);
  imuSite.anchor.getWorldQuaternion(imuSite.slab.quaternion);
  imuSite.slab.material.opacity = on ? 0.95 : 0.3;
  imuSite.slab.material.emissiveIntensity = on ? 0.35 : 0.0;
  imuSite.halo.position.copy(imuSite.slab.position);
  /* Halo = share of movement power in the tremor band, when there is one. */
  const band = on && imu.tremor ? imu.tremor.band_frac : null;
  const hu = imuSite.halo.userData;
  hu.fill.material.opacity = 0;
  hu.ring.material.color.copy(band === null ? C_GHOST : ramp(band, new THREE.Color()));
  hu.ring.material.opacity = on ? 0.25 + 0.6 * (band || 0) : 0.15;
  imuSite.halo.scale.setScalar(hu.r * (on ? 1 + 0.6 * (band || 0) : 1));

  for (const g of markers.children) if (g.userData.ring) g.quaternion.copy(camera.quaternion);
}

function paintDisc(g, c, def) {
  const {r, fill, ring} = g.userData;
  const fitted = !!c && c.kind !== undefined;
  if (!fitted) {
    fill.material.opacity = 0;
    ring.material.color.copy(C_GHOST);
    ring.material.opacity = 0.28;
    g.scale.setScalar(r * 0.8);
    return;
  }
  g.scale.setScalar(r);
  const known = c.state !== 'raw' && c.cur !== null && c.cur !== undefined;
  if (!known) {
    // Fitted, but no curve for it (or no data yet): say "here", never "how much".
    fill.material.color.copy(C_GHOST);
    fill.material.opacity = 0.45;
    fill.scale.setScalar(0.45);
    ring.material.color.copy(C_GHOST);
    ring.material.opacity = 0.7;
    return;
  }
  const cur = Math.max(0, Math.min(1, c.cur));
  fill.material.color.copy(c.state === 'above' ? C_WARN : ramp(cur, new THREE.Color()));
  fill.material.opacity = 0.95;
  fill.scale.setScalar(def.group === 'flex' ? 0.6 : 0.25 + 0.72 * cur);
  const pk = c.peak === null || c.peak === undefined ? cur : Math.max(0, Math.min(1, c.peak));
  ring.material.color.copy(pk >= 1 && def.kind === 'fsr' ? C_WARN : ramp(Math.max(pk, 0.35), new THREE.Color()));
  ring.material.opacity = 0.9;
}

function drawStrip(r, c) {
  const pts = r.anchors.map(a => a.getWorldPosition(new THREE.Vector3()));
  const key = pts.map(p => p.x.toFixed(4) + p.y.toFixed(4) + p.z.toFixed(4)).join('|');
  if (key !== r.tubeKey) {
    r.tube.geometry.dispose();
    r.tube.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 28, 0.0032, 8, false);
    r.tubeKey = key;
  }
  const live = c && c.kind === 'flex' && c.cur !== null && c.cur !== undefined;
  if (live) ramp(c.cur, r.tube.material.color);
  else r.tube.material.color.copy(C_GHOST);
  r.tube.material.opacity = live ? 0.95 : (c ? 0.6 : 0.22);
}

/* Floating labels, in the DOM so they stay crisp and translatable. Only for
   channels that are actually fitted; the list beside the canvas covers the
   rest. */
function placeTags() {
  const w = stage.clientWidth, h = stage.clientHeight;
  const by = chanByName();
  const want = [];
  for (const r of sites) {
    const c = by.get(r.def.name);
    if (c) want.push([r.def.name, r.marker.position, c.text || '—', c.state]);
  }
  const imu = snap && snap.connected && snap.imu;
  if (imu && imu.present) {
    const tl = imu.tilt || {};
    want.push(['IMU', imuSite.slab.position,
      tl.static ? `${Math.round(tl.pitch_deg)}° / ${Math.round(tl.roll_deg)}°` : tr('moving'), 'live']);
  }
  const sig = want.map(x => x[0]).join(',');
  if (tagsEl.dataset.sig !== sig) {
    tagsEl.innerHTML = want.map(x => `<div class="g3d-tag" data-n="${x[0]}"><b>${x[0]}</b><span></span></div>`).join('');
    tagsEl.dataset.sig = sig;
  }
  const els = tagsEl.children;
  want.forEach(([, pos, text, state], i) => {
    const el = els[i];
    _v.copy(pos).project(camera);
    const behind = _v.z > 1;
    el.style.display = behind ? 'none' : '';
    // Second translate centres the tag above its marker.
    el.style.transform = `translate(${((_v.x + 1) / 2 * w).toFixed(1)}px, ` +
      `${((1 - _v.y) / 2 * h).toFixed(1)}px) translate(-50%, calc(-100% - 12px))`;
    const sp = el.lastChild;
    if (sp.textContent !== text) sp.textContent = text;
    el.classList.toggle('warn', state === 'above');
  });
}

/* ── the list beside the canvas (and the whole map, without WebGL) ──────── */

function stateOf(def, c) {
  const connected = !!(snap && snap.connected);
  if (!connected) return ['dim', tr('offline'), '—'];
  if (!c) return ['dim', tr('not fitted'), ''];
  if (def && c.kind !== def.kind) {
    return ['warn', tr('banner says {kind}', {kind: tr(c.kind)}), c.text || '—'];
  }
  if (c.state === 'above') return ['warn', tr('beyond rated — upper bound only'), c.text];
  if (c.state === 'raw') return ['dim', tr('raw only — no {kind} curve on the host yet', {kind: c.kind}), c.text];
  if (c.state === 'waiting') return ['dim', tr('waiting for data'), '—'];
  // Until a strip has been bent through a real range, bend is read against a
  // placeholder span and the finger barely moves. Say so, here where it shows.
  if (c.kind === 'flex' && c.basis !== 'observed' && c.basis !== 'calibrated') {
    return ['warn', tr('bend it fully once to set its range'), c.text];
  }
  return ['ok', tr('live'), c.text];
}

function renderList() {
  if (!listEl) return;
  snap = window.devGloveSnapshot ? window.devGloveSnapshot() : snap;
  const by = new Map();
  if (snap && snap.connected) for (const c of snap.channels) by.set(c.name, c);
  const row = (name, site, [cls, badge, value]) =>
    `<div class="g3d-row"><b>${name}</b><span class="g3d-site">${site}</span>
       <span class="g3d-val">${value}</span>
       <span class="dev-badge dev-badge-${cls}">${badge}</span></div>`;

  let html = '';
  for (const g of GROUPS) {
    html += `<div class="g3d-group">${tr(g.title)}</div>`;
    if (g.id === 'imu') {
      const imu = snap && snap.connected ? snap.imu : null;
      const on = imu && imu.present;
      const tl = on ? imu.tilt || {} : {};
      const val = !on ? '—' : tl.static
        ? `${Math.round(tl.pitch_deg)}° / ${Math.round(tl.roll_deg)}°` : tr('moving');
      const st = !(snap && snap.connected) ? ['dim', tr('offline'), '—']
        : !on ? ['dim', tr('not reporting'), '—']
        : !fusion.mount ? ['warn', tr('press Calibrate motion to follow your hand'), val]
        : ['ok', tr(follow ? 'following your hand' : 'following off'), val];
      html += row('IMU', tr('back of hand'), st);
      continue;
    }
    for (const def of SITES.filter(s => s.group === g.id)) {
      html += row(def.name, tr(def.site), stateOf(def, by.get(def.name)));
    }
  }
  /* Anything the board declares that has no site on the map. Shown, never
     dropped: a channel the map cannot place is still a channel. */
  const placed = new Set(SITES.map(s => s.name));
  const extra = snap && snap.connected
    ? snap.channels.filter(c => !placed.has(c.name) && c.kind !== 'accel' && c.kind !== 'gyro') : [];
  if (extra.length) {
    html += `<div class="g3d-group">${tr('Not on the map')}</div>`;
    for (const c of extra) html += row(c.name, tr(c.kind), stateOf(null, c));
  }
  listEl.innerHTML = html;

  if (!failed) {
    const connected = !!(snap && snap.connected);
    emptyEl.textContent = connected ? '' : tr('Connect the board to light up the fitted sensors.');
    emptyEl.style.display = connected ? 'none' : '';
  }
}

/* ── view controls ───────────────────────────────────────────────────── */

/* Rebuilt only when what it shows changes, so a click is never lost to a
   re-render mid-press. */
let viewsSig = '';
function renderViews(force) {
  const calibrated = !!fusion.mount;
  const sig = [calibrated, follow, handSide, !!fusion.cal, !!fingerCal, window.getLang?.() || ''].join('|');
  if (!force && sig === viewsSig) return;
  viewsSig = sig;
  viewsEl.innerHTML =
    `<button class="btn ${calibrated ? 'btn-ghost' : 'btn-primary'}" data-g3d="calibrate"` +
    ` title="${tr('Two held poses teach the map how the board sits on your hand.')}">` +
    `${tr(calibrated ? 'Recalibrate' : 'Calibrate motion')}</button>` +
    `<button class="btn btn-ghost" data-g3d="fingers"` +
    ` title="${tr('Open hand, then a fist: records the range of each flex strip, so a small shift no longer swings the reading.')}">` +
    `${tr('Calibrate fingers')}</button>` +
    `<button class="btn btn-ghost" data-g3d="heading" ${calibrated ? '' : 'disabled'}` +
    ` title="${tr('Point your fingers at the screen, or show it your palm, then press. Heading drifts slowly without a compass.')}">` +
    `${tr('Reset heading')}</button>` +
    `<label class="dev-check"><input type="checkbox" data-g3d="follow" ${follow ? 'checked' : ''}> ${tr('Follow hand')}</label>` +
    `<label class="dev-sel">${tr('Glove on')} <select data-g3d="hand">` +
    `<option value="right" ${handSide === 'right' ? 'selected' : ''}>${tr('right hand')}</option>` +
    `<option value="left" ${handSide === 'left' ? 'selected' : ''}>${tr('left hand')}</option></select></label>` +
    `<button class="btn btn-ghost" data-g3d="view">${tr('Reset view')}</button>`;
}
viewsEl.addEventListener('click', e => {
  const b = e.target.closest('button[data-g3d]');
  if (!b) return;
  const id = b.dataset.g3d;
  if (id === 'view' && controls) {
    camera.position.copy(CAM_HOME);
    controls.target.set(0, 0, 0);
    controls.update();
  }
  if (id === 'calibrate') { fingerCal = null; fusionLib.startCalibration(fusion); renderViews(); }
  if (id === 'fingers') { fusionLib.cancelCalibration(fusion); startFingerCal(); renderViews(); }
  if (id === 'heading') {
    const ok = fusionLib.resetHeading(fusion);
    window.toast?.(tr(ok ? 'Heading reset.' : 'Hold the hand so the fingers or the palm face the screen, then try again.'),
                   ok ? 'ok' : 'info');
  }
});
viewsEl.addEventListener('change', e => {
  const id = e.target.dataset.g3d;
  if (id === 'follow') follow = e.target.checked;
  if (id === 'hand') { handSide = e.target.value; applyHand(); saveMount(); }
  renderViews();
});

function applyHand() { mirrorG.scale.x = handSide === 'right' ? -1 : 1; }

/* ── calibration overlay ─────────────────────────────────────────────── */

const calEl = document.createElement('div');
calEl.className = 'g3d-cal';
calEl.hidden = true;
stage.appendChild(calEl);
calEl.addEventListener('click', e => {
  if (e.target.closest('[data-g3d-cal="cancel"]')) {
    fusionLib.cancelCalibration(fusion);
    fingerCal = null;
    closeCal();
    renderViews();
  }
});
let calSig = '';
/* Closing the overlay here, rather than letting renderCal notice it went
   away, is what keeps a cancel or a finished finger calibration from being
   announced as a finished MOTION calibration. */
function closeCal() { calEl.hidden = true; calSig = ''; }

/* Finger calibration: two timed poses rather than "hold still until it
   settles", because a fist is held with effort and never reads perfectly
   still. The capture itself (median of each strip's last 0.8 s) and the
   check that each strip actually moved live in dev.js, beside the buffers. */
const FINGER_POSE_MS = 3000;
let fingerCal = null;           // {step, due, flat}
function startFingerCal() { fingerCal = {step: 1, due: performance.now() + FINGER_POSE_MS, flat: null}; }
function tickFingerCal() {
  const c = fingerCal;
  if (!c || performance.now() < c.due) return;
  const got = window.devFlexCal ? window.devFlexCal.capture() : {};
  if (!Object.keys(got).length) {
    fingerCal = null;
    closeCal();
    window.toast?.(tr('No flex strips are streaming — connect the board first.'), 'info');
    renderViews();
    return;
  }
  if (c.step === 1) {
    fingerCal = {step: 2, due: performance.now() + FINGER_POSE_MS, flat: got};
    return;
  }
  const {ok, weak} = window.devFlexCal.save(c.flat, got);
  fingerCal = null;
  closeCal();
  if (ok.length) window.toast?.(tr('Fingers calibrated: {names}.', {names: ok.join(', ')}), 'ok');
  if (weak.length) {
    window.toast?.(tr('{names} barely changed between open and fist — check the strip lies over the knuckle, then try again.',
                      {names: weak.join(', ')}), 'info');
  }
  renderViews();
}

function renderCal() {
  tickFingerCal();
  if (fingerCal) {
    calEl.hidden = false;
    const left = Math.max(0, fingerCal.due - performance.now());
    const sig = ['f', fingerCal.step, Math.ceil(left / 1000), window.getLang?.() || ''].join('|');
    if (sig !== calSig) {
      calSig = sig;
      const n = Math.ceil(left / 1000);
      const step = fingerCal.step === 1
        ? tr('Step 1 of 2 — open your hand, fingers straight and relaxed. Recording in {n} s.', {n})
        : tr('Step 2 of 2 — make a firm fist and hold it. Recording in {n} s.', {n});
      calEl.innerHTML = `<p>${step}</p><div class="g3d-cal-bar"><i></i></div>` +
        `<button class="btn btn-ghost" data-g3d-cal="cancel">${tr('Cancel calibration')}</button>`;
    }
    calEl.querySelector('.g3d-cal-bar i').style.width = (100 * (1 - left / FINGER_POSE_MS)).toFixed(1) + '%';
    return;
  }
  const c = fusion.cal;
  if (!c) {
    if (!calEl.hidden) {
      calEl.hidden = true;
      calSig = '';
      if (fusion.mount) { saveMount(); window.toast?.(tr('Motion calibrated — the hand now follows yours.'), 'ok'); }
      renderViews();
    }
    return;
  }
  calEl.hidden = false;
  const pct = Math.round(100 * c.n / fusionLib.CAL_SAMPLES);
  const sig = [c.step, c.error, window.getLang?.() || ''].join('|');
  if (sig !== calSig) {
    calSig = sig;
    const step = c.step === 1
      ? tr('Step 1 of 2 — lay your hand flat, palm down, and hold still.')
      : tr('Step 2 of 2 — raise it: fingers up, palm facing the screen. Hold still.');
    const err = c.error === 'too-close'
      ? `<p class="g3d-cal-err">${tr('That was too close to the first pose — turn the hand further, then hold still.')}</p>` : '';
    calEl.innerHTML = `<p>${step}</p>${err}<div class="g3d-cal-bar"><i></i></div>` +
      `<button class="btn btn-ghost" data-g3d-cal="cancel">${tr('Cancel calibration')}</button>`;
  }
  calEl.querySelector('.g3d-cal-bar i').style.width = pct + '%';
}

/* ── IMU frames in, from dev.js ──────────────────────────────────────── */

const IMU_COLS = ['ax', 'ay', 'az', 'gx', 'gy', 'gz'];
window.glove3dFeed = (frames, channels) => {
  const idx = IMU_COLS.map(n => channels.indexOf(n));
  if (idx.some(i => i < 0)) return;
  const sc = window.devImuScale ? window.devImuScale() : 1000;
  for (const f of frames) {
    const v = idx.map(i => f[2 + i]);
    if (v.some(x => x === undefined || x === null)) continue;
    fusionLib.step(fusion, [v[0] / sc, v[1] / sc, v[2] / sc], [v[3] / sc, v[4] / sc, v[5] / sc], f[1]);
  }
  /* A mount restored from a previous visit has no heading (the filter's own
     heading restarts at zero). Take one from the first steady moment. */
  if (fusion.mount && !fusion.heading && fusion.stillFor > 0.3) fusionLib.resetHeading(fusion);
};

/* ── lifecycle ───────────────────────────────────────────────────────── */

function resize() {
  if (!renderer) return;
  const w = stage.clientWidth, h = stage.clientHeight;
  if (!w || !h) return;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}

function init() {
  try {
    renderer = new THREE.WebGLRenderer({canvas, alpha: true, antialias: true, powerPreference: 'low-power'});
  } catch (e) {
    fail('webgl');
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  controls = new OrbitControls(camera, canvas);
  controls.enablePan = false;
  controls.enableDamping = !REDUCED;
  controls.minDistance = 0.45;
  controls.maxDistance = 1.4;
  new ResizeObserver(resize).observe(stage);
  resize();
  loading = true;
  new GLTFLoader().load('/assets/models/hand.gltf', onModel, undefined, () => fail('load'));
}

let last = 0;
function loop(now) {
  raf = requestAnimationFrame(loop);
  const dt = Math.min((now - last) / 1000 || 0, 0.1);
  last = now;
  if (!loaded) { renderer && renderer.render(scene, camera); return; }
  frame(dt);
  controls.update();
  renderer.render(scene, camera);
  placeTags();
}

function start() {
  if (running) return;
  running = true;
  renderViews();
  if (!renderer && !failed) init();
  renderList();
  listTimer = setInterval(renderList, 250);
  if (renderer) raf = requestAnimationFrame(loop);
}

function stop() {
  running = false;
  if (raf) cancelAnimationFrame(raf);
  raf = null;
  clearInterval(listTimer);
  listTimer = null;
}

window.glove3d = {start, stop};
if (typeof window.onLang === 'function') {
  window.onLang(() => { renderViews(); renderList(); tagsEl.dataset.sig = ''; });
}
// dev.js may have called start() before this module existed.
if (document.getElementById('page-dev')?.classList.contains('active')) start();
