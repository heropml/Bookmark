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
function skyClass(code) {
  const mode = document.documentElement.dataset.sky || "auto";
  if (mode === "none") return null;
  if (mode !== "auto") return mode;
  if (code == null) return null;
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82) || code >= 95) return "rain";
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
function skyPopulate() {
  skyDrops = [];
  const base = skyType === "rain" ? 130 : skyType === "snow" ? 80 : skyType === "stars" ? 46
    : skyType === "meteor" ? 5 : skyType === "fireflies" ? 34 : skyType === "blossom" ? 26 : 0;
  const n = Math.round(base * skyCount);
  const S = skyScale;
  for (let i = 0; i < n; i++) {
    const d = { x: Math.random() * innerWidth, y: Math.random() * innerHeight, ph: Math.random() * 6.28 };
    if (skyType === "rain") { d.v = 7 + Math.random() * 5; d.len = (10 + Math.random() * 12) * S; }
    else if (skyType === "snow") { d.v = 0.6 + Math.random() * 0.9; d.r = (1 + Math.random() * 2.1) * S; }
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
    skyDrops.push(d);
  }
}
function spawnTrail(x, y) {
  const kind = document.documentElement.dataset.trail || "stardust";
  const R = Math.random;
  const S = trailScale;
  if (kind === "none") return false;
  if (kind === "comet") {
    if (starTrail.length > 380) return false;
    starTrail.push({ kind, x, y, vx: 0, vy: 0, r: (2.4 + R() * 2.2) * S, life: 1, decay: 0.075 + R() * 0.03, hue: (Date.now() / 24) % 360 });
    return true;
  }
  if (kind === "bubble") {
    if (R() > 0.22 || starTrail.length > 110) return false;
    starTrail.push({ kind, x, y, vy: -(0.5 + R() * 0.9) * S, r: (2 + R() * 3.6) * S, ph: R() * 6.28, life: 1, decay: 0.011 });
    return true;
  }
  if (kind === "petal") {
    if (R() > 0.3 || starTrail.length > 150) return false;
    starTrail.push({ kind, x, y, vy: (0.55 + R() * 0.7) * S, r: (2.2 + R() * 2.4) * S, ph: R() * 6.28, rot: R() * 6.28, spin: (R() - 0.5) * 0.14, life: 1, decay: 0.008 + R() * 0.004 });
    return true;
  }
  if (kind === "firefly") {
    if (R() > 0.3 || starTrail.length > 110) return false;
    starTrail.push({ kind, x, y, vx: (R() - 0.5) * 0.8 * S, vy: (R() - 0.5) * 0.8 * S, r: (1 + R() * 1.6) * S, ph: R() * 6.28, life: 1, decay: 0.006 + R() * 0.004 });
    return true;
  }
  if (kind === "rainbow") {
    if (starTrail.length > 260) return false;
    starTrail.push({ kind, x, y, vx: (R() - 0.5) * 0.9, vy: (R() - 0.5) * 0.9 - 0.35, r: (0.9 + R() * 1.8) * S, life: 1, decay: 0.045, hue: (Date.now() / 6) % 360 });
    return true;
  }
  if (kind === "sparkle") {
    if (R() > 0.4 || starTrail.length > 150) return false;
    starTrail.push({ kind, x, y, vx: (R() - 0.5) * 0.6 * S, vy: -(0.2 + R() * 0.5) * S, r: (3.2 + R() * 2.8) * S, rot: R() * 1.57, spin: (R() - 0.5) * 0.06, life: 1, decay: 0.025 + R() * 0.01 });
    return true;
  }
  if (starTrail.length > 260) return false;
  starTrail.push({ kind: "stardust", x, y, vx: (R() - 0.5) * 0.9, vy: (R() - 0.5) * 0.9 - 0.35, r: (0.8 + R() * 1.7) * S, life: 1, decay: 0.045 });
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
  if (skyType === "rain") {
    // 自动天气用远、中、近三层雨幕；手动“细雨”保持原来的样式和速度。
    const weatherRain = !weatherScene.hidden;
    const layers = weatherRain ? 3 : 1;
    for (let layer = 0; layer < layers; layer++) {
      const depth = weatherRain ? .6 + layer * .5 : 1;
      const slant = weatherRain ? .18 : .12;
      fxCtx.strokeStyle = "rgba(" + skyInk + ", " + (weatherRain ? [.18, .34, .56][layer] : .3) + ")";
      fxCtx.lineWidth = Math.max(.6, skyScale * depth);
      fxCtx.beginPath();
      for (let i = layer; i < skyDrops.length; i += layers) {
        const d = skyDrops[i];
        d.y += d.v * dt * depth;
        d.x += d.v * dt * depth * slant;
        const len = d.len * depth;
        const edge = weatherRain ? len : 24;
        if (d.y > innerHeight + edge) { d.y = -edge; d.x = Math.random() * innerWidth; }
        fxCtx.moveTo(d.x, d.y);
        fxCtx.lineTo(d.x - len * slant, d.y - len);
      }
      fxCtx.stroke();
    }
  } else if (skyType === "snow" || skyType === "stars") {
    for (const d of skyDrops) {
      if (skyType === "snow") {
        d.y += d.v * dt;
        d.ph += 0.012 * dt;
        d.x += Math.sin(d.ph) * 0.5 * dt;
        if (d.y > innerHeight + 6) { d.y = -6; d.x = Math.random() * innerWidth; }
        fxCtx.fillStyle = "rgba(" + skyInk + ", 0.5)";
      } else {
        d.y -= d.v * dt;
        d.ph += 0.02 * dt;
        if (d.y < -6) { d.y = innerHeight + 6; d.x = Math.random() * innerWidth; }
        fxCtx.fillStyle = "rgba(" + skyInk + ", " + (0.1 + 0.3 * Math.abs(Math.sin(d.ph))).toFixed(3) + ")";
      }
      fxCtx.beginPath();
      fxCtx.arc(d.x, d.y, d.r, 0, 6.29);
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
  const run = motionOk();
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
  reduceMotionMq.addEventListener("change", syncParticles);

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
