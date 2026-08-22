/* ── Reaction-diffusion background (Gray-Scott, universal WebGL) ── */
/* Worm/labyrinthine regime (F~0.029, k~0.057): dense twisting patterns
   that connect and disconnect. Zero required extensions:
   - Runs on WebGL1 AND WebGL2 (GLSL ES 1.0 shaders work on both)
   - State lives in plain RGBA8 textures (renderable on every device).
     U and V are packed as 16-bit fixed point across two 8-bit channels,
     so no float-texture extensions are needed at all.
   - No blending into FBOs (avoids EXT_float_blend entirely)
   - CLAMP_TO_EDGE + NEAREST (NPOT-safe on WebGL1, no float filtering) */
(function(){
  const canvas = document.getElementById("rd-bg");
  function cssFallback(){
    canvas.style.background =
      "radial-gradient(ellipse at 15% 50%,rgba(18,165,148,.08),transparent 55%),"
      + "radial-gradient(ellipse at 85% 50%,rgba(18,165,148,.08),transparent 55%)";
  }
  const attrs = {alpha:true, premultipliedAlpha:false, antialias:false, depth:false, stencil:false};
  const gl = canvas.getContext("webgl2", attrs)
          || canvas.getContext("webgl", attrs)
          || canvas.getContext("experimental-webgl", attrs);
  if(!gl){ cssFallback(); return; }
  let dead = false;

  const SCALE = 0.333;
  let W, H, simW, simH;
  function resize(){
    W = innerWidth; H = innerHeight;
    canvas.style.width = W+"px"; canvas.style.height = H+"px";
    simW = Math.max(1, Math.floor(W*SCALE));
    simH = Math.max(1, Math.floor(H*SCALE));
    canvas.width = simW; canvas.height = simH;
    gl.viewport(0,0,simW,simH);
    initTextures();
    seedPattern();
  }

  function makeShader(type, src){
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if(!gl.getShaderParameter(s, gl.COMPILE_STATUS))
      console.error("Shader:", gl.getShaderInfoLog(s));
    return s;
  }
  function makeProg(vs, fs){
    const p = gl.createProgram();
    gl.attachShader(p, makeShader(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, makeShader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if(!gl.getProgramParameter(p, gl.LINK_STATUS))
      console.error("Program link:", gl.getProgramInfoLog(p));
    return p;
  }

  const quadBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
  function bindQuad(prog){
    const a = gl.getAttribLocation(prog,"a_pos");
    gl.enableVertexAttribArray(a);
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.vertexAttribPointer(a,2,gl.FLOAT,false,0,0);
  }

  /* ── Shaders: GLSL ES 1.0 — runs unchanged on WebGL1 and WebGL2 ── */
  const PRECISION = [
    "#ifdef GL_FRAGMENT_PRECISION_HIGH",
    "precision highp float;",
    "#else",
    "precision mediump float;",
    "#endif"
  ].join("\n");

  /* 16-bit fixed-point pack/unpack across two 8-bit channels.
     pk: value -> (high byte, low fraction); up: inverse; st: decode (u,v) */
  const PACK = [
    "vec2 pk(float x){ x = clamp(x, 0.0, 1.0)*255.0; return vec2(floor(x)/255.0, fract(x)); }",
    "float up(vec2 e){ return (e.x*255.0 + e.y)/255.0; }",
    "vec2 st(sampler2D t, vec2 uv){ vec4 c = texture2D(t, uv); return vec2(up(c.rg), up(c.ba)); }"
  ].join("\n");

  const simVS = [
    "attribute vec2 a_pos;",
    "varying vec2 vUv;",
    "void main(){ vUv = a_pos*0.5+0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }"
  ].join("\n");

  /* Gray-Scott, worm/labyrinthine regime. 9-point Laplacian (isotropic →
     smooth curved worms). F/k drift slowly over space+time so branches
     keep connecting and disconnecting instead of settling. */
  const simFS = [
    PRECISION,
    "varying vec2 vUv;",
    "uniform sampler2D uState;",
    "uniform vec2 uTexel;",
    "uniform vec2 uMouse;",
    "uniform float uMouseR;",
    "uniform float uAspect;",
    "uniform float uTime;",
    PACK,
    "const float Du = 0.2097, Dv = 0.105;",
    "void main(){",
    "  vec2 s = st(uState, vUv);",
    "  vec2 lap = -s*(20.0/6.0);",
    "  lap += st(uState, vUv+vec2( uTexel.x, 0.0))*(4.0/6.0);",
    "  lap += st(uState, vUv+vec2(-uTexel.x, 0.0))*(4.0/6.0);",
    "  lap += st(uState, vUv+vec2(0.0,  uTexel.y))*(4.0/6.0);",
    "  lap += st(uState, vUv+vec2(0.0, -uTexel.y))*(4.0/6.0);",
    "  lap += st(uState, vUv+vec2( uTexel.x,  uTexel.y))*(1.0/6.0);",
    "  lap += st(uState, vUv+vec2(-uTexel.x,  uTexel.y))*(1.0/6.0);",
    "  lap += st(uState, vUv+vec2( uTexel.x, -uTexel.y))*(1.0/6.0);",
    "  lap += st(uState, vUv+vec2(-uTexel.x, -uTexel.y))*(1.0/6.0);",
    "  /* Slow traveling wave: the spatial phase itself drifts with uTime, so the",
    "     F/k modulation sweeps across the canvas (left->right) and the branch",
    "     reorganization visibly propagates as a gentle 'twist'. wave2 gives k an",
    "     independent drift so F and k don't move in lockstep (lockstep just scales",
    "     the pattern; decorrelated motion is what makes branches split and rejoin). */",
    "  float phase = vUv.x*3.0 - uTime*0.0006;",
    "  float wave  = sin(phase) * cos(vUv.y*2.5 + uTime*0.0004);",
    "  float wave2 = sin(vUv.y*3.0 - uTime*0.0005);",
    "  /* Barely-there drift: amplitudes kept inside the worm band so F/k never",
    "     reach the solid-fill or spots regimes, but the labyrinth still keeps",
    "     crossing the split/merge boundary and never fully settles. */",
    "  float F = 0.029 + wave  * 0.003;",
    "  float k = 0.057 + wave2 * 0.0015;",
    "  float u = s.x, v = s.y;",
    "  float uvv = u*v*v;",
    "  float nu = u + (Du*lap.x - uvv + F*(1.0-u));",
    "  float nv = v + (Dv*lap.y + uvv - (F+k)*v);",
    "  if(uMouse.x > -0.5 && uMouseR > 0.001){",
    "    vec2 diff = vUv - uMouse; diff.x *= uAspect;",
    "    float md = length(diff);",
    "    if(md < uMouseR){",
    "      float b = smoothstep(0.0, uMouseR, md); b *= b;",
    "      nu = mix(1.0, nu, b);",
    "      nv = mix(0.0, nv, b);",
    "    }",
    "  }",
    "  gl_FragColor = vec4(pk(nu), pk(nv));",
    "}"
  ].join("\n");

  /* Display: decode V, sharpen worms, brand teal, center mask */
  const dispFS = [
    PRECISION,
    "varying vec2 vUv;",
    "uniform sampler2D uState;",
    PACK,
    "void main(){",
    "  float v = st(uState, vUv).y;",
    "  float cx = abs(vUv.x - 0.5)*2.0;",
    "  float mask = smoothstep(0.1, 0.5, cx);",
    "  float edgeBoost = smoothstep(0.5, 0.95, cx)*0.15;",
    "  float sig = smoothstep(0.06, 0.30, v);",
    "  vec3 teal = vec3(0.071, 0.647, 0.580);",
    "  vec3 bright = vec3(0.10, 0.75, 0.70);",
    "  vec3 col = mix(teal, bright, sig*0.5);",
    "  gl_FragColor = vec4(col, sig * mask * (0.35 + edgeBoost));",
    "}"
  ].join("\n");

  /* GPU-side seeding: procedural noise clusters on left/right margins.
     Avoids CPU float-format uploads entirely. */
  const seedFS = [
    PRECISION,
    "varying vec2 vUv;",
    "uniform float uSeed;",
    "uniform vec2 uRes;",
    PACK,
    "float hash(vec2 p){ p = mod(p, 289.0);",
    "  return fract(sin(dot(p, vec2(127.1, 311.7)) + uSeed)*43758.5453123); }",
    "float vnoise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);",
    "  return mix(mix(hash(i), hash(i+vec2(1.0,0.0)), f.x),",
    "             mix(hash(i+vec2(0.0,1.0)), hash(i+vec2(1.0,1.0)), f.x), f.y); }",
    "void main(){",
    "  vec2 px = vUv * uRes;",
    "  float m = (vUv.x < 0.35 || vUv.x > 0.65) ? 1.0 : 0.0;",
    "  float blob  = step(0.60, vnoise(px/12.0)) * m;",
    "  float speck = step(0.992, hash(px)) * m;",
    "  float sd = min(blob + speck, 1.0);",
    "  gl_FragColor = vec4(pk(mix(1.0, 0.5, sd)), pk(mix(0.0, 0.25, sd)));",
    "}"
  ].join("\n");

  const simProg = makeProg(simVS, simFS);
  const dispProg = makeProg(simVS, dispFS);
  const seedProg = makeProg(simVS, seedFS);

  const uState_sim = gl.getUniformLocation(simProg, "uState");
  const uTexel = gl.getUniformLocation(simProg, "uTexel");
  const uMouse = gl.getUniformLocation(simProg, "uMouse");
  const uMouseR = gl.getUniformLocation(simProg, "uMouseR");
  const uAspect = gl.getUniformLocation(simProg, "uAspect");
  const uTime = gl.getUniformLocation(simProg, "uTime");
  const uState_disp = gl.getUniformLocation(dispProg, "uState");
  const uSeedLoc = gl.getUniformLocation(seedProg, "uSeed");
  const uResLoc = gl.getUniformLocation(seedProg, "uRes");

  let texA, texB, fboA, fboB;
  /* Plain RGBA8: universally renderable + NPOT-safe with CLAMP/NEAREST */
  function makeTex(w,h){
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }
  function makeFBO(tex){
    const f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    if(gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE){
      console.error("FBO incomplete — falling back to CSS gradient");
      dead = true; cssFallback();
    }
    return f;
  }

  function initTextures(){
    if(texA) gl.deleteTexture(texA);
    if(texB) gl.deleteTexture(texB);
    if(fboA) gl.deleteFramebuffer(fboA);
    if(fboB) gl.deleteFramebuffer(fboB);
    texA = makeTex(simW, simH, null);
    texB = makeTex(simW, simH, null);
    fboA = makeFBO(texA);
    fboB = makeFBO(texB);
  }

  function seedPattern(){
    /* Render procedural noise seeds directly on the GPU into texA */
    if(dead) return;
    gl.useProgram(seedProg);
    gl.bindFramebuffer(gl.FRAMEBUFFER, fboA);
    gl.uniform1f(uSeedLoc, Math.random()*100.0);
    gl.uniform2f(uResLoc, simW, simH);
    bindQuad(seedProg);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  /* Mouse tracking: idle→no spot, circular scoop, speed-based sizing */
  let mx = -1, my = -1, smx = -1, smy = -1;
  let pmx = -1, pmy = -1, lastMoveT = 0, mSpeed = 0;
  const IDLE_MS = 120;        /* ms without movement → retract scoop */
  const MAX_R  = 0.08;        /* cap radius (UV units, same as old oval) */
  const SPEED_K = 32.0;       /* exponential sensitivity → reaches cap at low speed */
  addEventListener("mousemove", e => {
    const nx = e.clientX/W, ny = 1.0 - e.clientY/H;
    if(pmx > -0.5){
      const dx = (nx-pmx)*W, dy = (ny-pmy)*H; /* pixel-space delta */
      mSpeed = Math.sqrt(dx*dx + dy*dy);
    }
    pmx = nx; pmy = ny; mx = nx; my = ny;
    lastMoveT = performance.now();
  });
  addEventListener("mouseleave", ()=>{ mx = -1; my = -1; pmx = -1; pmy = -1; mSpeed = 0; });

  /* Click pulse: a temporary max-cap scoop that eases in then out at the click point */
  let clickT = -1e9, clickX = -1, clickY = -1;
  const CLICK_RISE = 170;     /* ms: smoothstep ease up to MAX_R */
  const CLICK_FALL = 720;     /* ms: smoothstep ease back to 0 */
  addEventListener("mousedown", e => {
    clickX = e.clientX / W; clickY = 1.0 - e.clientY / H;
    clickT = performance.now();
  });

  function simStep(src, dst, dstFBO, time){
    gl.useProgram(simProg);
    gl.bindFramebuffer(gl.FRAMEBUFFER, dstFBO);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, src);
    gl.uniform1i(uState_sim, 0);
    gl.uniform2f(uTexel, 1.0/simW, 1.0/simH);
    /* Hover scoop: speed → radius (exponential ramp, capped), retracts when idle */
    const now = performance.now();
    const idle = (now - lastMoveT) > IDLE_MS;
    const hoverActive = mx > -0.5 && !idle;
    const hoverR = hoverActive ? MAX_R * (1.0 - Math.exp(-mSpeed * SPEED_K / Math.max(W,1))) : 0.0;

    /* Click pulse: smoothstep ease-in to MAX_R, then smoothstep ease-out to 0 */
    let pulseR = 0.0;
    const ct = now - clickT;
    if(ct >= 0 && ct < CLICK_RISE + CLICK_FALL){
      const t = ct < CLICK_RISE ? ct / CLICK_RISE
                                : 1.0 - (ct - CLICK_RISE) / CLICK_FALL; /* ramp up then down, 0..1 */
      pulseR = MAX_R * (t * t * (3.0 - 2.0 * t)); /* smoothstep — no abrupt edges */
    }

    /* Drive the single scoop with whichever is larger; anchor at the click point
       while the pulse dominates so it stays put even if the cursor moves off */
    let cx, cy, rad;
    if(pulseR >= hoverR && pulseR > 0.0001){
      cx = clickX; cy = clickY; rad = pulseR;
      smx = clickX; smy = clickY;   /* keep smoothed pos synced for a seamless handoff */
    } else if(hoverActive){
      smx += (mx-smx)*0.15; smy += (my-smy)*0.15;
      cx = smx; cy = smy; rad = hoverR;
    } else {
      smx = -1; smy = -1; cx = -1; cy = -1; rad = 0.0;
    }
    gl.uniform2f(uMouse, cx, cy);
    gl.uniform1f(uMouseR, rad);
    gl.uniform1f(uAspect, W / Math.max(H, 1));
    gl.uniform1f(uTime, time);
    bindQuad(simProg);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
  }

  function display(src){
    gl.useProgram(dispProg);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, src);
    gl.uniform1i(uState_disp, 0);
    bindQuad(dispProg);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
  }

  const WARMUP = 500;          /* steps to develop worms before steady state */
  const STEPS_PER_FRAME = 6;
  let warmupLeft = WARMUP;
  let tick = 0;
  let running = false;

  resize();
  addEventListener("resize", ()=>{
    resize();
    warmupLeft = WARMUP;
    if(!running && !dead) start();  /* restart if frozen (reduced motion) */
  });

  function loop(){
    if(dead){ running = false; return; }
    const steps = warmupLeft > 0 ? 50 : STEPS_PER_FRAME;
    for(let i=0; i<steps; i++){
      simStep(texA, texB, fboB, tick++);
      let tmp;
      tmp=texA; texA=texB; texB=tmp;
      tmp=fboA; fboA=fboB; fboB=tmp;
    }
    if(warmupLeft > 0) warmupLeft -= steps;
    display(texA);
    /* Reduced motion: show the fully-developed static pattern, then stop */
    if(warmupLeft <= 0 && reducedMotion){ running = false; return; }
    requestAnimationFrame(loop);
  }
  function start(){ running = true; requestAnimationFrame(loop); }
  if(!dead) start();
})();
