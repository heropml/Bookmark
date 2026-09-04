const fxCanvas = document.getElementById("fx-canvas");
const fxCtx = fxCanvas.getContext("2d");
let skyType = null;
let populatedType = null;
let skyDrops = [];
let starTrail = [];
let trailScale = 1;
try { trailScale = Math.min(2.5, Math.max(0.5, parseFloat(localStorage.getItem("bm-trail-size")) || 1)); } catch (e) {}
let skyScale = 1;
let skyCount = 1;
try { skyScale = Math.min(2.5, Math.max(0.5, parseFloat(localStorage.getItem("bm-sky-size")) || 1)); } catch (e) {}
try { skyCount = Math.min(2.5, Math.max(0.25, parseFloat(localStorage.getItem("bm-sky-count")) || 1)); } catch (e) {}
let skyRunning = false;
let skyRaf = 0;
let skyLast = 0;
let currentWeatherCode = null;
const weatherScene = document.getElementById("weatherScene");
const SKY_BASE_COUNTS = Object.freeze({
  rain: 108, storm: 136, snow: 72, stars: 46, meteor: 5, fireflies: 34, blossom: 26,
  aurora: 7, bubbles: 34, fireworks: 72, matrix: 56, nebula: 12, ripples: 16, beams: 12, confetti: 58
});
function weatherPeriod() {
  const h = new Date().getHours();
  return h >= 19 || h < 6 ? "night" : "day";
}
function weatherSceneClass(code) {
  if (code === 0) return "clear";
  if (code === 1 || code === 2) return "clouds";
  if (code === 3) return "overcast";
  if (code === 45 || code === 48) return "fog";
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return "rain";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code >= 95 && code <= 99) return "storm";
  return "";
}
function weatherIntensity(code) {
  if (code == null) return 1;
  if (code >= 95) return 1.35;
  if ([55, 57, 65, 67, 75, 77, 82, 86].includes(code)) return 1.16;
  if ([53, 63, 73, 81].includes(code)) return 1.04;
  return .88;
}
function skyClass(code) {
  const mode = document.documentElement.dataset.sky || "auto";
  if (mode === "none") return null;
  if (mode !== "auto") return mode;
  if (code == null) return null;
  if (code >= 95) return "storm";
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return "rain";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code <= 2 && weatherPeriod() === "night") return "stars";
  return null;
}
function fxResize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  fxCanvas.width = Math.round(innerWidth * dpr);
  fxCanvas.height = Math.round(innerHeight * dpr);
  fxCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function placeFirework(d, center) {
  d.cx = center ? center.x : innerWidth * (.12 + Math.random() * .76);
  d.cy = center ? center.y : innerHeight * (.12 + Math.random() * .54);
}
function skyPopulate() {
  skyDrops = [];
  const intensity = weatherIntensity(currentWeatherCode);
  const base = SKY_BASE_COUNTS[skyType] || 0;
  const n = Math.round(base * skyCount);
  const S = skyScale;
  const fireworkCenters = skyType === "fireworks" ? Array.from({ length: 6 }, () => ({
    x: innerWidth * (.12 + Math.random() * .76),
    y: innerHeight * (.12 + Math.random() * .54)
  })) : [];
  for (let i = 0; i < n; i++) {
    const d = { x: Math.random() * innerWidth, y: Math.random() * innerHeight, ph: Math.random() * 6.28 };
    if (skyType === "rain" || skyType === "storm") {
      const depth = .56 + Math.random() * 1.04;
      d.depth = depth;
      d.v = (5.5 + Math.random() * 4.5) * intensity * depth;
      d.len = (9 + Math.random() * 12) * S * depth;
      d.wind = (skyType === "storm" ? .35 : .18) + Math.random() * (skyType === "storm" ? .2 : .13);
      d.alpha = (.11 + Math.random() * .26) * Math.min(1.2, depth);
    }
    else if (skyType === "snow") {
      const depth = .55 + Math.random() * .95;
      d.depth = depth;
      d.v = (0.45 + Math.random() * .85) * intensity * depth;
      d.r = (1 + Math.random() * 2.1) * S * depth;
      d.wind = .22 + Math.random() * .38;
      d.alpha = .16 + Math.random() * .36;
    }
    else if (skyType === "stars") { d.v = 0.1 + Math.random() * 0.22; d.r = (0.7 + Math.random() * 1.5) * S; }
    else if (skyType === "meteor") {
      d.x = Math.random() * innerWidth * 0.9;
      d.y = -60 - Math.random() * innerHeight * 0.6;
      d.v = 9 + Math.random() * 5;
      d.len = (90 + Math.random() * 100) * S;
      d.wait = Math.random() * 280;
    }
    else if (skyType === "fireflies") { d.ph2 = Math.random() * 6.28; d.r = (1.1 + Math.random() * 1.6) * S; }
    else if (skyType === "blossom") { d.v = 0.4 + Math.random() * 0.6; d.r = (2.4 + Math.random() * 2.6) * S; d.rot = Math.random() * 6.28; d.spin = (Math.random() - 0.5) * 0.06; }
    else if (skyType === "aurora") { d.y = innerHeight * (.12 + i / Math.max(n, 1) * .56); d.v = .006 + Math.random() * .008; d.r = (55 + Math.random() * 90) * S; d.hue = 155 + Math.random() * 145; d.alpha = .05 + Math.random() * .055; }
    else if (skyType === "bubbles") { d.v = (.18 + Math.random() * .48) * S; d.r = (3 + Math.random() * 9) * S; d.wind = .12 + Math.random() * .32; d.alpha = .12 + Math.random() * .3; }
    else if (skyType === "fireworks") {
      const center = fireworkCenters[i % fireworkCenters.length];
      placeFirework(d, center); d.angle = (i % 12) / 12 * 6.28 + Math.random() * .16;
      d.r = (1 + Math.random() * 1.6) * S; d.v = (1.1 + Math.random() * 1.1) * S;
      d.dist = Math.random() * 24; d.max = (45 + Math.random() * 52) * S; d.hue = (i * 47 + Math.random() * 35) % 360;
      d.wait = Math.floor(i / 12) * 45 + Math.random() * 20;
    }
    else if (skyType === "matrix") { d.x = (i + .5) / Math.max(n, 1) * innerWidth; d.y = Math.random() * innerHeight; d.v = (1.1 + Math.random() * 2.6) * S; d.r = (10 + Math.random() * 5) * S; d.alpha = .2 + Math.random() * .55; d.glyph = Math.random() > .5 ? "1" : "0"; }
    else if (skyType === "nebula") { d.v = .025 + Math.random() * .045; d.r = (65 + Math.random() * 115) * S; d.hue = 190 + Math.random() * 125; d.alpha = .025 + Math.random() * .04; d.ph2 = Math.random() * 6.28; }
    else if (skyType === "ripples") { d.r = Math.random() * 80 * S; d.v = (.35 + Math.random() * .65) * S; d.max = (70 + Math.random() * 110) * S; d.alpha = .12 + Math.random() * .24; }
    else if (skyType === "beams") { d.x = Math.random() * (innerWidth + 240) - 120; d.y = -innerHeight * .25; d.v = .25 + Math.random() * .48; d.len = (innerHeight * .7 + Math.random() * innerHeight * .4) * S; d.r = (4 + Math.random() * 14) * S; d.hue = 180 + Math.random() * 100; d.alpha = .025 + Math.random() * .055; }
    else if (skyType === "confetti") { d.v = (.8 + Math.random() * 1.8) * S; d.wind = (Math.random() - .5) * .8; d.r = (2 + Math.random() * 3.5) * S; d.rot = Math.random() * 6.28; d.spin = (Math.random() - .5) * .16; d.hue = Math.random() * 360; }
    skyDrops.push(d);
  }
}
const TRAIL_SPECS = Object.freeze({
  comet: { max: 380, make: (x, y, R, S) => ({ x, y, vx: 0, vy: 0, r: (2.4 + R() * 2.2) * S, life: 1, decay: .075 + R() * .03, hue: (Date.now() / 24) % 360 }) },
  bubble: { chance: .22, max: 110, make: (x, y, R, S) => ({ x, y, vy: -(.5 + R() * .9) * S, r: (2 + R() * 3.6) * S, ph: R() * 6.28, life: 1, decay: .011 }) },
  petal: { chance: .3, max: 150, make: (x, y, R, S) => ({ x, y, vy: (.55 + R() * .7) * S, r: (2.2 + R() * 2.4) * S, ph: R() * 6.28, rot: R() * 6.28, spin: (R() - .5) * .14, life: 1, decay: .008 + R() * .004 }) },
  firefly: { chance: .3, max: 110, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .8 * S, vy: (R() - .5) * .8 * S, r: (1 + R() * 1.6) * S, ph: R() * 6.28, life: 1, decay: .006 + R() * .004 }) },
  rainbow: { max: 260, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .9, vy: (R() - .5) * .9 - .35, r: (.9 + R() * 1.8) * S, life: 1, decay: .045, hue: (Date.now() / 6) % 360 }) },
  sparkle: { chance: .4, max: 150, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .6 * S, vy: -(.2 + R() * .5) * S, r: (3.2 + R() * 2.8) * S, rot: R() * 1.57, spin: (R() - .5) * .06, life: 1, decay: .025 + R() * .01 }) },
  sparks: { chance: .58, max: 180, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * 3.2 * S, vy: -(1.2 + R() * 2.2) * S, r: (1.2 + R() * 1.8) * S, life: 1, decay: .025 + R() * .018, hue: 24 + R() * 32 }) },
  ribbon: { chance: .5, max: 130, make: (x, y, R, S) => ({ x, y, px: x, py: y, vx: (R() - .5) * .8, vy: -(.2 + R() * .45), r: (8 + R() * 10) * S, ph: R() * 6.28, life: 1, decay: .018 + R() * .008, hue: (Date.now() / 12 + R() * 80) % 360 }) },
  notes: { chance: .24, max: 80, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .6, vy: -(.55 + R() * .55) * S, r: (13 + R() * 7) * S, ph: R() * 6.28, life: 1, decay: .012 + R() * .007, glyph: R() > .5 ? "♪" : "♫" }) },
  pixels: { chance: .55, max: 170, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * 1.7, vy: (R() - .5) * 1.7, r: (2 + R() * 3) * S, life: 1, decay: .025 + R() * .018, hue: R() * 360 }) },
  crystal: { chance: .35, max: 110, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .7, vy: -(.2 + R() * .65), r: (4 + R() * 3.5) * S, rot: R() * 6.28, spin: (R() - .5) * .12, life: 1, decay: .018 + R() * .01 }) },
  ink: { chance: .38, max: 95, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .32, vy: (R() - .5) * .32, r: (3.5 + R() * 5) * S, life: 1, decay: .01 + R() * .006 }) },
  hearts: { chance: .28, max: 90, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .45, vy: -(.5 + R() * .6) * S, r: (4 + R() * 3.5) * S, ph: R() * 6.28, rot: (R() - .5) * .35, life: 1, decay: .012 + R() * .007 }) },
  smoke: { chance: .42, max: 100, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .34, vy: -(.32 + R() * .38) * S, r: (4 + R() * 5) * S, ph: R() * 6.28, life: 1, decay: .009 + R() * .006 }) },
  stardust: { max: 260, make: (x, y, R, S) => ({ x, y, vx: (R() - .5) * .9, vy: (R() - .5) * .9 - .35, r: (.8 + R() * 1.7) * S, life: 1, decay: .045 }) }
});
function spawnTrail(x, y) {
  const kind = document.documentElement.dataset.trail || "stardust";
  const spec = TRAIL_SPECS[kind];
  if (!spec || starTrail.length > spec.max) return false;
  const R = Math.random;
  if (spec.chance && R() > spec.chance) return false;
  starTrail.push({ kind, ...spec.make(x, y, R, trailScale) });
  return true;
}
const LIGHT_SKINS = new Set(["paper", "snow", "sakura", "celadon", "shuimo", "daiqing", "zhusha"]);
function fxInk() {
  const sk = document.documentElement.dataset.skin;
  if (sk === "shuimo") return "72, 68, 60";
  if (sk === "daiqing") return "72, 100, 106";
  if (sk === "zhusha") return "178, 62, 46";
  if (sk === "yemo") return "226, 220, 206";
  if (sk === "snow") return "70, 100, 150";
  if (sk === "sakura") return "190, 100, 140";
  if (sk === "celadon") return "70, 140, 115";
  return LIGHT_SKINS.has(sk) ? "96, 76, 44" : "185, 216, 255";
}
function skyFrame(ts) {
  skyRaf = 0;
  if (!skyRunning) return;
  const dt = Math.min(ts - skyLast || 16.7, 50) / 16.7;
  skyLast = ts;
  fxCtx.clearRect(0, 0, innerWidth, innerHeight);
  const ink = fxInk();
  const skyInk = weatherScene.hidden ? ink : "235, 246, 255";
  if (skyType === "rain" || skyType === "storm") {
    // 按景深和风向分层：远处是细密雨幕，近处才有清晰、较长的雨线。
    const weatherRain = !weatherScene.hidden;
    const layers = weatherRain ? 3 : 1;
    for (let layer = 0; layer < layers; layer++) {
      const depth = weatherRain ? .62 + layer * .46 : 1;
      const slant = skyType === "storm" ? .38 : weatherRain ? .21 : .12;
      const alpha = weatherRain ? [.12, .22, .38][layer] : .3;
      fxCtx.strokeStyle = "rgba(" + skyInk + ", " + alpha + ")";
      fxCtx.lineWidth = Math.max(.55, skyScale * (weatherRain ? .58 + layer * .42 : 1));
      fxCtx.lineCap = "round";
      fxCtx.beginPath();
      for (let i = layer; i < skyDrops.length; i += layers) {
        const d = skyDrops[i];
        d.y += d.v * dt;
        d.x += d.v * dt * (d.wind || slant);
        const len = d.len;
        const edge = weatherRain ? len : 24;
        if (d.y > innerHeight + edge) { d.y = -edge; d.x = Math.random() * innerWidth; }
        fxCtx.moveTo(d.x, d.y);
        fxCtx.lineTo(d.x - len * (d.wind || slant), d.y - len);
      }
      fxCtx.stroke();
    }
  } else if (skyType === "snow" || skyType === "stars") {
    for (const d of skyDrops) {
      if (skyType === "snow") {
        d.y += d.v * dt;
        d.ph += (0.009 + d.depth * .006) * dt;
        d.x += (Math.sin(d.ph) * d.wind + d.wind * .34) * dt;
        if (d.y > innerHeight + 6) { d.y = -6; d.x = Math.random() * innerWidth; }
        fxCtx.fillStyle = "rgba(" + skyInk + ", " + d.alpha.toFixed(3) + ")";
      } else {
        d.y -= d.v * dt;
        d.ph += 0.02 * dt;
        if (d.y < -6) { d.y = innerHeight + 6; d.x = Math.random() * innerWidth; }
        fxCtx.fillStyle = "rgba(" + skyInk + ", " + (0.1 + 0.3 * Math.abs(Math.sin(d.ph))).toFixed(3) + ")";
      }
      fxCtx.beginPath();
      if (skyType === "snow") fxCtx.ellipse(d.x, d.y, d.r, d.r * .72, Math.sin(d.ph) * .45, 0, 6.29);
      else fxCtx.arc(d.x, d.y, d.r, 0, 6.29);
      fxCtx.fill();
    }
  } else if (skyType === "meteor") {
    for (const d of skyDrops) {
      if (d.wait > 0) { d.wait -= dt; continue; }
      d.x += d.v * dt * 0.55;
      d.y += d.v * dt;
      const tx = d.x - d.len * 0.55, ty = d.y - d.len;
      const g = fxCtx.createLinearGradient(d.x, d.y, tx, ty);
      g.addColorStop(0, "rgba(" + ink + ", 0.9)");
      g.addColorStop(1, "rgba(" + ink + ", 0)");
      fxCtx.strokeStyle = g;
      fxCtx.lineWidth = Math.max(0.8, 1.6 * skyScale);
      fxCtx.beginPath();
      fxCtx.moveTo(d.x, d.y);
      fxCtx.lineTo(tx, ty);
      fxCtx.stroke();
      fxCtx.fillStyle = "rgba(255, 255, 255, 0.9)";
      fxCtx.beginPath();
      fxCtx.arc(d.x, d.y, Math.max(1, 1.5 * skyScale), 0, 6.29);
      fxCtx.fill();
      if (d.y > innerHeight + 60 || d.x > innerWidth + 60) {
        d.x = Math.random() * innerWidth * 0.85;
        d.y = -40 - Math.random() * 260;
        d.v = 9 + Math.random() * 5;
        d.len = (90 + Math.random() * 100) * skyScale;
        d.wait = 60 + Math.random() * 320;
      }
    }
  } else if (skyType === "fireflies") {
    for (const d of skyDrops) {
      d.ph += 0.02 * dt;
      d.ph2 += 0.013 * dt;
      d.x += Math.sin(d.ph) * 0.55 * dt;
      d.y += Math.cos(d.ph2) * 0.42 * dt;
      if (d.x < -8) d.x = innerWidth + 8; else if (d.x > innerWidth + 8) d.x = -8;
      if (d.y < -8) d.y = innerHeight + 8; else if (d.y > innerHeight + 8) d.y = -8;
      const glow = 0.25 + 0.55 * Math.abs(Math.sin(d.ph * 1.7));
      fxCtx.fillStyle = "rgba(190, 242, 100, " + (glow * 0.16).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(d.x, d.y, d.r * 3.4, 0, 6.29);
      fxCtx.fill();
      fxCtx.fillStyle = "rgba(232, 255, 170, " + glow.toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(d.x, d.y, d.r, 0, 6.29);
      fxCtx.fill();
    }
  } else if (skyType === "blossom") {
    for (const d of skyDrops) {
      d.y += d.v * dt;
      d.ph += 0.02 * dt;
      d.rot += d.spin * dt;
      d.x += Math.sin(d.ph) * 0.7 * dt;
      if (d.y > innerHeight + 8) { d.y = -8; d.x = Math.random() * innerWidth; }
      fxCtx.save();
      fxCtx.translate(d.x, d.y);
      fxCtx.rotate(d.rot);
      fxCtx.fillStyle = "rgba(244, 114, 182, 0.55)";
      fxCtx.beginPath();
      fxCtx.ellipse(0, 0, d.r, d.r * 0.55, 0, 0, 6.29);
      fxCtx.fill();
      fxCtx.restore();
    }
  } else if (skyType === "aurora") {
    fxCtx.save();
    fxCtx.globalCompositeOperation = "screen";
    for (const d of skyDrops) {
      d.ph += d.v * dt;
      const wave = Math.sin(d.ph) * 36 * skyScale;
      const g = fxCtx.createLinearGradient(0, d.y, innerWidth, d.y + wave);
      g.addColorStop(0, "hsla(" + d.hue.toFixed(0) + ", 88%, 62%, 0)");
      g.addColorStop(.45, "hsla(" + d.hue.toFixed(0) + ", 88%, 62%, " + d.alpha.toFixed(3) + ")");
      g.addColorStop(1, "hsla(" + ((d.hue + 70) % 360).toFixed(0) + ", 88%, 66%, 0)");
      fxCtx.strokeStyle = g;
      fxCtx.lineWidth = d.r;
      fxCtx.beginPath();
      fxCtx.moveTo(-d.r, d.y + wave);
      fxCtx.bezierCurveTo(innerWidth * .28, d.y - wave, innerWidth * .68, d.y + wave, innerWidth + d.r, d.y - wave * .4);
      fxCtx.stroke();
    }
    fxCtx.restore();
  } else if (skyType === "bubbles") {
    for (const d of skyDrops) {
      d.y -= d.v * dt;
      d.ph += .018 * dt;
      d.x += Math.sin(d.ph) * d.wind * dt;
      if (d.y < -d.r - 4) { d.y = innerHeight + d.r; d.x = Math.random() * innerWidth; }
      fxCtx.strokeStyle = "rgba(" + ink + ", " + d.alpha.toFixed(3) + ")";
      fxCtx.lineWidth = Math.max(.6, skyScale);
      fxCtx.beginPath(); fxCtx.arc(d.x, d.y, d.r, 0, 6.29); fxCtx.stroke();
      fxCtx.fillStyle = "rgba(255,255,255," + (d.alpha * .7).toFixed(3) + ")";
      fxCtx.beginPath(); fxCtx.arc(d.x - d.r * .32, d.y - d.r * .32, Math.max(.5, d.r * .12), 0, 6.29); fxCtx.fill();
    }
  } else if (skyType === "fireworks") {
    fxCtx.save();
    fxCtx.globalCompositeOperation = "screen";
    for (const d of skyDrops) {
      if (d.wait > 0) { d.wait -= dt; continue; }
      d.dist += d.v * dt;
      const fade = Math.max(0, 1 - d.dist / d.max);
      const x = d.cx + Math.cos(d.angle) * d.dist;
      const y = d.cy + Math.sin(d.angle) * d.dist + d.dist * d.dist * .0022;
      fxCtx.fillStyle = "hsla(" + d.hue.toFixed(0) + ", 96%, 68%, " + (fade * .85).toFixed(3) + ")";
      fxCtx.beginPath(); fxCtx.arc(x, y, Math.max(.4, d.r * fade), 0, 6.29); fxCtx.fill();
      if (d.dist > d.max) {
        d.dist = 0; d.wait = 80 + Math.random() * 180;
        placeFirework(d);
        d.hue = Math.random() * 360;
      }
    }
    fxCtx.restore();
  } else if (skyType === "matrix") {
    fxCtx.font = "600 " + Math.max(8, 12 * skyScale) + "px ui-monospace, monospace";
    fxCtx.textAlign = "center";
    for (const d of skyDrops) {
      d.y += d.v * dt;
      if (d.y > innerHeight + d.r) { d.y = -d.r; d.glyph = Math.random() > .5 ? "1" : "0"; }
      if (Math.random() < .018 * dt) d.glyph = d.glyph === "1" ? "0" : "1";
      fxCtx.fillStyle = "rgba(74, 222, 128, " + d.alpha.toFixed(3) + ")";
      fxCtx.fillText(d.glyph, d.x, d.y);
      fxCtx.fillStyle = "rgba(34, 197, 94, " + (d.alpha * .22).toFixed(3) + ")";
      fxCtx.fillRect(d.x - 1, d.y - d.v * 11, 2, d.v * 9);
    }
  } else if (skyType === "nebula") {
    fxCtx.save();
    fxCtx.globalCompositeOperation = "screen";
    for (const d of skyDrops) {
      d.ph += d.v * .12 * dt; d.ph2 += d.v * .09 * dt;
      d.x += Math.sin(d.ph) * .12 * dt; d.y += Math.cos(d.ph2) * .09 * dt;
      const g = fxCtx.createRadialGradient(d.x, d.y, 0, d.x, d.y, d.r);
      g.addColorStop(0, "hsla(" + d.hue.toFixed(0) + ", 82%, 64%, " + d.alpha.toFixed(3) + ")");
      g.addColorStop(1, "hsla(" + d.hue.toFixed(0) + ", 82%, 50%, 0)");
      fxCtx.fillStyle = g; fxCtx.beginPath(); fxCtx.arc(d.x, d.y, d.r, 0, 6.29); fxCtx.fill();
    }
    fxCtx.restore();
  } else if (skyType === "ripples") {
    for (const d of skyDrops) {
      d.r += d.v * dt;
      if (d.r > d.max) { d.r = 0; d.x = Math.random() * innerWidth; d.y = Math.random() * innerHeight; }
      const alpha = d.alpha * (1 - d.r / d.max);
      fxCtx.strokeStyle = "rgba(" + ink + ", " + Math.max(0, alpha).toFixed(3) + ")";
      fxCtx.lineWidth = Math.max(.6, 1.2 * skyScale);
      fxCtx.beginPath(); fxCtx.ellipse(d.x, d.y, d.r, d.r * .38, 0, 0, 6.29); fxCtx.stroke();
    }
  } else if (skyType === "beams") {
    fxCtx.save();
    fxCtx.globalCompositeOperation = "screen";
    for (const d of skyDrops) {
      d.x += d.v * dt;
      if (d.x > innerWidth + 160) d.x = -160;
      const g = fxCtx.createLinearGradient(d.x, d.y, d.x + d.len * .28, d.len);
      g.addColorStop(0, "hsla(" + d.hue.toFixed(0) + ", 90%, 72%, 0)");
      g.addColorStop(.35, "hsla(" + d.hue.toFixed(0) + ", 90%, 72%, " + d.alpha.toFixed(3) + ")");
      g.addColorStop(1, "hsla(" + d.hue.toFixed(0) + ", 90%, 72%, 0)");
      fxCtx.strokeStyle = g; fxCtx.lineWidth = d.r; fxCtx.beginPath(); fxCtx.moveTo(d.x, d.y); fxCtx.lineTo(d.x + d.len * .28, d.len); fxCtx.stroke();
    }
    fxCtx.restore();
  } else if (skyType === "confetti") {
    for (const d of skyDrops) {
      d.y += d.v * dt; d.x += d.wind * dt; d.rot += d.spin * dt;
      if (d.y > innerHeight + 10) { d.y = -10; d.x = Math.random() * innerWidth; }
      fxCtx.save(); fxCtx.translate(d.x, d.y); fxCtx.rotate(d.rot);
      fxCtx.fillStyle = "hsla(" + d.hue.toFixed(0) + ", 90%, 65%, .72)";
      fxCtx.fillRect(-d.r, -d.r * .45, d.r * 2, d.r * .9); fxCtx.restore();
    }
  }
  for (let i = starTrail.length - 1; i >= 0; i--) {
    const p = starTrail[i];
    p.life -= p.decay * dt;
    if (p.life <= 0) { starTrail.splice(i, 1); continue; }
    if (p.kind === "comet") {
      fxCtx.fillStyle = "hsla(" + p.hue.toFixed(0) + ", 90%, 76%, " + (p.life * 0.85).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, Math.max(p.r * p.life, 0.3), 0, 6.29);
      fxCtx.fill();
    } else if (p.kind === "bubble") {
      p.y += p.vy * dt;
      p.ph += 0.07 * dt;
      p.x += Math.sin(p.ph) * 0.4 * dt;
      fxCtx.strokeStyle = "rgba(" + ink + ", " + (p.life * 0.65).toFixed(3) + ")";
      fxCtx.lineWidth = 1;
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, p.r, 0, 6.29);
      fxCtx.stroke();
      fxCtx.fillStyle = "rgba(255, 255, 255, " + (p.life * 0.5).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(p.x - p.r * 0.35, p.y - p.r * 0.35, Math.max(p.r * 0.18, 0.4), 0, 6.29);
      fxCtx.fill();
    } else if (p.kind === "petal") {
      p.y += p.vy * dt;
      p.ph += 0.05 * dt;
      p.x += Math.sin(p.ph) * 0.7 * dt;
      p.rot += p.spin * dt;
      fxCtx.save();
      fxCtx.translate(p.x, p.y);
      fxCtx.rotate(p.rot);
      fxCtx.fillStyle = "hsla(338, 85%, 80%, " + (p.life * 0.8).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.ellipse(0, 0, p.r, p.r * 0.55, 0, 0, 6.29);
      fxCtx.fill();
      fxCtx.restore();
    } else if (p.kind === "sparkle") {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.rot += p.spin * dt;
      const radius = p.r * (0.45 + 0.55 * Math.sin(p.life * Math.PI));
      const gold = LIGHT_SKINS.has(document.documentElement.dataset.skin) ? "170, 105, 25" : "255, 219, 137";
      fxCtx.save();
      fxCtx.translate(p.x, p.y);
      fxCtx.rotate(p.rot);
      fxCtx.fillStyle = "rgba(" + gold + ", " + (p.life * 0.9).toFixed(3) + ")";
      fxCtx.shadowColor = "rgba(251, 191, 36, 0.55)";
      fxCtx.shadowBlur = radius;
      fxCtx.beginPath();
      for (let point = 0; point < 8; point++) {
        const angle = point * Math.PI / 4 - Math.PI / 2;
        const reach = point % 2 ? radius * 0.3 : radius;
        const px = Math.cos(angle) * reach, py = Math.sin(angle) * reach;
        if (point === 0) fxCtx.moveTo(px, py);
        else fxCtx.lineTo(px, py);
      }
      fxCtx.closePath();
      fxCtx.fill();
      fxCtx.restore();
    } else if (p.kind === "sparks") {
      p.x += p.vx * dt; p.y += p.vy * dt; p.vy += .12 * dt;
      fxCtx.strokeStyle = "hsla(" + p.hue.toFixed(0) + ", 100%, 64%, " + (p.life * .9).toFixed(3) + ")";
      fxCtx.lineWidth = Math.max(.7, p.r * p.life);
      fxCtx.beginPath(); fxCtx.moveTo(p.x, p.y); fxCtx.lineTo(p.x - p.vx * 2.4, p.y - p.vy * 2.4); fxCtx.stroke();
    } else if (p.kind === "ribbon") {
      p.px = p.x; p.py = p.y; p.ph += .16 * dt;
      p.x += (p.vx + Math.sin(p.ph) * .75) * dt; p.y += p.vy * dt;
      fxCtx.strokeStyle = "hsla(" + p.hue.toFixed(0) + ", 90%, 68%, " + (p.life * .68).toFixed(3) + ")";
      fxCtx.lineWidth = Math.max(1, p.r * p.life * .45); fxCtx.lineCap = "round";
      fxCtx.beginPath(); fxCtx.moveTo(p.px, p.py); fxCtx.quadraticCurveTo((p.px + p.x) / 2 + Math.sin(p.ph) * p.r, (p.py + p.y) / 2, p.x, p.y); fxCtx.stroke();
    } else if (p.kind === "notes") {
      p.ph += .06 * dt; p.x += (p.vx + Math.sin(p.ph) * .35) * dt; p.y += p.vy * dt;
      fxCtx.font = "700 " + Math.max(9, p.r * p.life) + "px Georgia, serif";
      fxCtx.textAlign = "center"; fxCtx.fillStyle = "rgba(196, 181, 253, " + (p.life * .82).toFixed(3) + ")";
      fxCtx.fillText(p.glyph, p.x, p.y);
    } else if (p.kind === "pixels") {
      p.x += p.vx * dt; p.y += p.vy * dt;
      const size = Math.max(1, p.r * p.life);
      fxCtx.fillStyle = "hsla(" + p.hue.toFixed(0) + ", 90%, 68%, " + (p.life * .78).toFixed(3) + ")";
      fxCtx.fillRect(Math.round(p.x - size / 2), Math.round(p.y - size / 2), size, size);
    } else if (p.kind === "crystal") {
      p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.spin * dt;
      fxCtx.save(); fxCtx.translate(p.x, p.y); fxCtx.rotate(p.rot);
      fxCtx.strokeStyle = "rgba(207, 250, 254, " + (p.life * .85).toFixed(3) + ")"; fxCtx.lineWidth = 1;
      fxCtx.beginPath(); fxCtx.moveTo(0, -p.r); fxCtx.lineTo(p.r * .48, 0); fxCtx.lineTo(0, p.r); fxCtx.lineTo(-p.r * .48, 0); fxCtx.closePath(); fxCtx.stroke(); fxCtx.restore();
    } else if (p.kind === "ink") {
      p.x += p.vx * dt; p.y += p.vy * dt; p.r += .08 * dt;
      const g = fxCtx.createRadialGradient(p.x - p.r * .2, p.y - p.r * .2, 0, p.x, p.y, p.r);
      g.addColorStop(0, "rgba(30, 41, 59, " + (p.life * .55).toFixed(3) + ")"); g.addColorStop(1, "rgba(15, 23, 42, 0)");
      fxCtx.fillStyle = g; fxCtx.beginPath(); fxCtx.arc(p.x, p.y, p.r, 0, 6.29); fxCtx.fill();
    } else if (p.kind === "hearts") {
      p.ph += .045 * dt; p.x += (p.vx + Math.sin(p.ph) * .24) * dt; p.y += p.vy * dt;
      const r = p.r * (.7 + .3 * p.life);
      fxCtx.save(); fxCtx.translate(p.x, p.y); fxCtx.rotate(p.rot); fxCtx.scale(r, r);
      fxCtx.fillStyle = "rgba(251, 113, 133, " + (p.life * .78).toFixed(3) + ")";
      fxCtx.beginPath(); fxCtx.moveTo(0, .35); fxCtx.bezierCurveTo(-1.25, -.45, -.72, -1.25, 0, -.55); fxCtx.bezierCurveTo(.72, -1.25, 1.25, -.45, 0, .35); fxCtx.fill(); fxCtx.restore();
    } else if (p.kind === "smoke") {
      p.ph += .035 * dt; p.x += (p.vx + Math.sin(p.ph) * .18) * dt; p.y += p.vy * dt; p.r += .12 * dt;
      const g = fxCtx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
      g.addColorStop(0, "rgba(203, 213, 225, " + (p.life * .2).toFixed(3) + ")"); g.addColorStop(1, "rgba(148, 163, 184, 0)");
      fxCtx.fillStyle = g; fxCtx.beginPath(); fxCtx.arc(p.x, p.y, p.r, 0, 6.29); fxCtx.fill();
    } else if (p.kind === "firefly") {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.ph += 0.16 * dt;
      const fa = p.life * (0.3 + 0.7 * Math.abs(Math.sin(p.ph)));
      fxCtx.fillStyle = "rgba(214, 255, 140, " + (fa * 0.22).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, p.r * 2.6, 0, 6.29);
      fxCtx.fill();
      fxCtx.fillStyle = "rgba(232, 255, 170, " + (fa * 0.9).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, p.r, 0, 6.29);
      fxCtx.fill();
    } else {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      fxCtx.fillStyle = p.kind === "rainbow"
        ? "hsla(" + p.hue.toFixed(0) + ", 95%, 72%, " + (p.life * 0.6).toFixed(3) + ")"
        : "rgba(" + ink + ", " + (p.life * 0.5).toFixed(3) + ")";
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, Math.max(p.r * p.life, 0.2), 0, 6.29);
      fxCtx.fill();
    }
  }
  if (skyType || starTrail.length) skyRaf = requestAnimationFrame(skyFrame);
  else skyRunning = false;
}
function startSky() {
  if (skyRunning) return;
  skyRunning = true;
  skyLast = 0;
  skyRaf = requestAnimationFrame(skyFrame);
}
function syncParticles() {
  const root = document.documentElement;
  const scene = root.dataset.sky === "auto" && root.dataset.fx !== "off" ? weatherSceneClass(currentWeatherCode) : "";
  weatherScene.hidden = !scene;
  weatherScene.dataset.weather = scene;
  weatherScene.dataset.period = weatherPeriod();
  root.dataset.weatherScene = scene;
  const run = root.dataset.fx !== "off";
  skyType = run ? skyClass(currentWeatherCode) : null;
  if (skyType !== populatedType) {
    skyPopulate();
    populatedType = skyType;
  }
  if (run && (skyType || starTrail.length)) {
    startSky();
  } else if (skyRunning) {
    skyRunning = false;
    cancelAnimationFrame(skyRaf);
    skyRaf = 0;
    starTrail.length = 0;
    fxCtx.clearRect(0, 0, innerWidth, innerHeight);
  }
}

const trailSizeInput = document.getElementById("trailSize");
const trailSizeVal = document.getElementById("trailSizeVal");
function setTrailSize(v, save) {
  trailScale = Math.round(Math.min(2.5, Math.max(0.5, v)) * 10) / 10;
  trailSizeInput.value = Math.round(trailScale * 100);
  trailSizeVal.textContent = trailScale.toFixed(1) + "×";
  if (save) {
    try { localStorage.setItem("bm-trail-size", String(trailScale)); } catch (e) {}
  }
}

const skySizeInput = document.getElementById("skySize");
const skySizeVal = document.getElementById("skySizeVal");
const skyCountInput = document.getElementById("skyCount");
const skyCountVal = document.getElementById("skyCountVal");
function setSkySize(v, save) {
  skyScale = Math.round(Math.min(2.5, Math.max(0.5, v)) * 10) / 10;
  skySizeInput.value = Math.round(skyScale * 100);
  skySizeVal.textContent = skyScale.toFixed(1) + "×";
  if (save) {
    try { localStorage.setItem("bm-sky-size", String(skyScale)); } catch (e) {}
    skyPopulate();
  }
}
function setSkyCount(v, save) {
  skyCount = Math.round(Math.min(2.5, Math.max(0.25, v)) * 4) / 4;
  skyCountInput.value = Math.round(skyCount * 100);
  skyCountVal.textContent = skyCount.toFixed(2).replace(/0$/, "").replace(/\.$/, "") + "×";
  if (save) {
    try { localStorage.setItem("bm-sky-count", String(skyCount)); } catch (e) {}
    skyPopulate();
  }
}

function initEffects() {
  window.addEventListener("resize", fxResize);
  fxResize();
  syncParticles();
  window.addEventListener("bm-fx", syncParticles);

  setTrailSize(trailScale, false);
  trailSizeInput.addEventListener("input", () => setTrailSize(parseInt(trailSizeInput.value, 10) / 100, true));
  document.getElementById("trailSizeDown").addEventListener("click", () => setTrailSize(trailScale - 0.1, true));
  document.getElementById("trailSizeUp").addEventListener("click", () => setTrailSize(trailScale + 0.1, true));

  setSkySize(skyScale, false);
  setSkyCount(skyCount, false);
  skySizeInput.addEventListener("input", () => setSkySize(parseInt(skySizeInput.value, 10) / 100, true));
  skyCountInput.addEventListener("input", () => setSkyCount(parseInt(skyCountInput.value, 10) / 100, true));
  document.getElementById("skySizeDown").addEventListener("click", () => setSkySize(skyScale - 0.1, true));
  document.getElementById("skySizeUp").addEventListener("click", () => setSkySize(skyScale + 0.1, true));
  document.getElementById("skyCountDown").addEventListener("click", () => setSkyCount(skyCount - 0.25, true));
  document.getElementById("skyCountUp").addEventListener("click", () => setSkyCount(skyCount + 0.25, true));
}
