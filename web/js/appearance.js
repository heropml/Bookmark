const MOTION_ART = {
  float: `<defs><linearGradient id="motionFloat" x2="1" y2="1"><stop stop-color="#7dd3fc"/><stop offset="1" stop-color="#6366f1"/></linearGradient></defs>
    <ellipse cx="32" cy="47" rx="18" ry="4" fill="#818cf8" opacity=".16"/>
    <path d="M8 32V20m-4 4 4-4 4 4M56 32V20m-4 4 4-4 4 4" stroke="#38bdf8" stroke-width="2" opacity=".65"/>
    <g class="motion-anim motion-lift"><path d="m32 9 17 10v17L32 46 15 36V19Z" fill="url(#motionFloat)"/>
    <path d="m15 19 17 10 17-10M32 29v17" stroke="#e0f2fe" stroke-width="1.5" opacity=".75"/>
    <path d="m24 16 8-4 8 4-8 5Z" fill="#fff" opacity=".45"/></g>`,
  pulse: `<defs><radialGradient id="motionPulse" cx=".35" cy=".3"><stop stop-color="#ffe4f0"/><stop offset=".55" stop-color="#fb7185"/><stop offset="1" stop-color="#a855f7"/></radialGradient></defs>
    <g class="motion-anim motion-breathe"><circle cx="32" cy="28" r="23" fill="#f472b6" opacity=".1"/>
    <circle cx="32" cy="28" r="20" stroke="#f472b6" stroke-width="1.5" stroke-dasharray="3 5" opacity=".6"/>
    <circle cx="32" cy="28" r="15" fill="url(#motionPulse)"/>
    <path d="M23 23c1-4 4-6 8-6" stroke="#fff" stroke-width="2.5" opacity=".7"/>
    <path d="M20 29h6l3-5 5 10 3-5h7" stroke="#fff" stroke-width="1.8" opacity=".9"/></g>`,
  sweep: `<defs><linearGradient id="motionSweep" x2="1" y2="1"><stop stop-color="#38bdf8"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient><clipPath id="motionSweepClip"><rect x="12" y="12" width="40" height="34" rx="8"/></clipPath></defs>
    <rect x="8" y="16" width="40" height="34" rx="8" fill="#818cf8" opacity=".13"/>
    <rect x="12" y="12" width="40" height="34" rx="8" fill="url(#motionSweep)"/>
    <path d="M19 36h14M19 40h8" stroke="#e0f2fe" stroke-width="2" opacity=".65"/>
    <g clip-path="url(#motionSweepClip)"><path class="motion-anim motion-shine" d="m29 9 10 0-13 40H16Z" fill="#fff" opacity=".65"/></g>
    <path d="m51 3 2.3 6.7L60 12l-6.7 2.3L51 21l-2.3-6.7L42 12l6.7-2.3Z" fill="#fcd34d"/>`,
  sway: `<defs><linearGradient id="motionSway" x2="1" y2="1"><stop stop-color="#fde68a"/><stop offset="1" stop-color="#f59e0b"/></linearGradient></defs>
    <path d="M7 24c-2 8 1 16 8 21m-1-7 1 7-7-1M57 24c2 8-1 16-8 21m1-7-1 7 7-1" stroke="#f59e0b" stroke-width="1.8" opacity=".55"/>
    <g class="motion-anim motion-swing"><circle cx="32" cy="9" r="3" fill="#fbbf24"/>
    <path d="M18 29c0-9 5-15 14-15s14 6 14 15v5l4 6H14l4-6Z" fill="url(#motionSway)"/>
    <path d="M24 28c0-5 2-8 6-9" stroke="#fff7d6" stroke-width="2.5"/>
    <path d="M27 44a5 5 0 0 0 10 0" fill="#d97706"/>
    <path d="M15 40h34" stroke="#b45309" stroke-width="1.5" opacity=".5"/></g>`,
  bounce: `<defs><radialGradient id="motionBounce" cx=".3" cy=".25"><stop stop-color="#dbeafe"/><stop offset=".5" stop-color="#818cf8"/><stop offset="1" stop-color="#7c3aed"/></radialGradient></defs>
    <ellipse cx="33" cy="47" rx="18" ry="4" fill="#8b5cf6" opacity=".16"/>
    <path d="M12 41c0-19 6-28 14-29" stroke="#a78bfa" stroke-width="1.8" stroke-dasharray="3 4" fill="none"/>
    <path d="m21 9 6 2-3 6M46 20v7m5-3v8" stroke="#a78bfa" stroke-width="2"/>
    <g class="motion-anim motion-ball"><circle cx="34" cy="31" r="14" fill="url(#motionBounce)"/>
    <path d="M25 28c1-4 3-6 7-6" stroke="#eef2ff" stroke-width="2.5" opacity=".8"/></g>`,
  spin: `<defs><linearGradient id="motionSpin" x2="1" y2="1"><stop stop-color="#5eead4"/><stop offset="1" stop-color="#3b82f6"/></linearGradient></defs>
    <circle cx="32" cy="28" r="23" fill="#38bdf8" opacity=".07"/>
    <g class="motion-anim motion-turn"><path d="M12 23a21 21 0 0 1 37-9M52 33a21 21 0 0 1-37 9" stroke="url(#motionSpin)" stroke-width="3.5" fill="none"/>
    <path d="m42 13 9 3-1-10M22 43l-9-3 1 10" stroke="#2dd4bf" stroke-width="3" fill="none"/>
    <path d="m32 15 11 13-11 13-11-13Z" fill="url(#motionSpin)"/>
    <path d="m32 15 0 26 11-13Z" fill="#2563eb" opacity=".4"/></g>`,
  ripple: `<defs><linearGradient id="motionRipple" x2="1" y2="1"><stop stop-color="#a5f3fc"/><stop offset="1" stop-color="#0ea5e9"/></linearGradient></defs>
    <ellipse class="motion-anim motion-wave" cx="32" cy="41" rx="25" ry="10" fill="#38bdf8" fill-opacity=".08" stroke="#38bdf8" stroke-opacity=".55" stroke-width="1.5"/>
    <ellipse class="motion-anim motion-wave motion-wave-late" cx="32" cy="41" rx="16" ry="6" fill="none" stroke="#0ea5e9" stroke-opacity=".7" stroke-width="1.5"/>
    <path d="M32 5c-4 6-12 13-12 20a12 12 0 0 0 24 0C44 18 36 11 32 5Z" fill="url(#motionRipple)"/>
    <path d="M25 25c0 4 2 6 5 7" stroke="#ecfeff" stroke-width="2.5" stroke-linecap="round"/>`,
  still: `<defs><linearGradient id="motionStill" x2="1" y2="1"><stop stop-color="#94a3b8"/><stop offset="1" stop-color="#475569"/></linearGradient></defs>
    <rect x="9" y="6" width="46" height="44" rx="13" fill="#94a3b8" opacity=".13"/>
    <rect x="14" y="10" width="36" height="36" rx="10" fill="url(#motionStill)"/>
    <rect x="24" y="20" width="5" height="16" rx="1.5" fill="#f1f5f9"/>
    <rect x="35" y="20" width="5" height="16" rx="1.5" fill="#f1f5f9"/>
    <path d="M24 51h16" stroke="#94a3b8" stroke-width="2" stroke-linecap="round"/>`
};
function choicePreview(key, id) {
  if (key === "skin") return '<span class="skin-swatch"></span>';
  if (key === "icon") return '<span class="icon-swatch"><i>A</i></span>';
  if (key === "layout" && id === "board") return '<span class="layout-art" aria-hidden="true"><svg viewBox="0 0 72 48" fill="none"><g stroke="currentColor" stroke-width="1.4"><rect x="2" y="3" width="20" height="42" rx="4"/><rect x="26" y="3" width="20" height="42" rx="4"/><rect x="50" y="3" width="20" height="42" rx="4"/></g><path d="M7 10h10m14 0h10m14 0h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><g fill="currentColor" opacity=".3"><rect x="6" y="16" width="12" height="10" rx="2"/><rect x="6" y="29" width="12" height="10" rx="2"/><rect x="30" y="16" width="12" height="10" rx="2"/><rect x="54" y="16" width="12" height="10" rx="2"/><rect x="54" y="29" width="12" height="10" rx="2"/></g></svg></span>';
  if (key === "layout" && id === "tree") return '<span class="layout-art" aria-hidden="true"><svg viewBox="0 0 72 48" fill="none"><path d="M9 13v23h12M9 23h12" stroke="currentColor" stroke-width="1.5"/><g fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-width="1.4"><path d="M3 5h7l3 3h10v9H3Z"/><path d="M21 21h5l2 2h9v8H21ZM21 34h5l2 2h9v8H21Z"/><rect x="45" y="4" width="25" height="40" rx="4"/></g><path d="M51 12h13m-13 8h13m-13 8h13m-13 8h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span>';
  if (key === "layout") return '<span class="layout-swatch"><i></i><i></i><i></i><i></i><i></i><i></i></span>';
  if (key === "motion") return '<span class="motion-swatch" aria-hidden="true"><svg viewBox="0 0 64 56" fill="none" stroke-linecap="round" stroke-linejoin="round">' + MOTION_ART[id] + '</svg></span>';
  if (key === "trail") return '<span class="trail-swatch"><i></i></span>';
  if (key === "sky") return '<span class="sky-swatch"></span>';
  return '<span class="fx-dot"></span>';
}
function setupChoice(list, key, containerId, resolve) {
  const root = document.documentElement;
  let stored = null;
  try { stored = localStorage.getItem("bm-" + key); } catch (e) {}
  const cur = stored && list.some((x) => x.id === stored)
    ? stored
    : root.dataset[key] || list[0].id;
  const container = document.getElementById(containerId);
  container.innerHTML = list.map((item) => `
    <button type="button" class="choice" data-value="${item.id}" aria-pressed="false">
      ${choicePreview(key, item.id)}<b>${item.name}</b>
    </button>`).join("");
  const apply = (id, syncShortcut = false) => {
    const item = list.find((x) => x.id === id) || list[0];
    root.dataset[key] = resolve ? resolve(item.id) : item.id;
    try { localStorage.setItem("bm-" + key, item.id); } catch (e) {}
    for (const btn of container.querySelectorAll(".choice")) {
      btn.setAttribute("aria-pressed", String(btn.dataset.value === item.id));
    }
    const summary = document.querySelector('[data-setting-summary="' + key + '"]');
    if (summary) summary.textContent = item.name;
    if (key === "skin") {
      const fav = document.getElementById("fav");
      if (fav) fav.href = "/__favicon?skin=" + encodeURIComponent(root.dataset.skin);
      document.getElementById("appearanceLabel").textContent = "外观 · " + item.name;
      if (syncShortcut) fetch("/__icon?skin=" + encodeURIComponent(root.dataset.skin)).catch(() => {});
    }
    if (key === "fx" || key === "sky") window.dispatchEvent(new Event("bm-fx"));
  };
  apply(list.some((x) => x.id === cur) ? cur : list[0].id);
  container.addEventListener("click", (event) => {
    const btn = event.target.closest(".choice");
    if (!btn) return;
    const previous = root.dataset[key];
    apply(btn.dataset.value, key === "skin");
    if (key === "layout" && previous !== root.dataset.layout &&
        [previous, root.dataset.layout].some(id => id === "board" || id === "tree")) render();
  });
}

const appearanceBtn = document.getElementById("appearanceBtn");
const appearanceMenu = document.getElementById("appearanceMenu");
const appearancePanel = document.getElementById("appearancePanel");
const appearanceCategories = document.getElementById("appearanceCategories");
const appearanceBack = document.getElementById("appearanceBack");
let appearanceSection = null;
function showAppearanceSection(key) {
  const previous = appearanceSection;
  const section = key ? appearancePanel.querySelector('[data-setting-panel="' + key + '"]') : null;
  appearanceSection = section ? key : null;
  for (const group of appearancePanel.querySelectorAll("[data-setting-panel]")) group.hidden = group !== section;
  for (const category of appearanceCategories.querySelectorAll("[data-setting]")) {
    category.setAttribute("aria-expanded", String(category.dataset.setting === appearanceSection));
  }
  appearancePanel.hidden = !section;
  document.body.classList.toggle("appearance-section-open", !!section);
  if (section) {
    document.getElementById("appearanceTitle").textContent = section.dataset.title;
    document.getElementById("appearanceDescription").textContent = section.dataset.description;
    appearancePanel.querySelector(".appearance-body").scrollTop = 0;
  }
  if (!appearanceMenu.hidden) {
    const target = section
      ? section.querySelector('.choice[aria-pressed="true"]')
      : appearanceCategories.querySelector('[data-setting="' + (previous || "skin") + '"]');
    if (target) target.focus({ preventScroll: true });
  }
}
function setAppearanceOpen(open, restoreFocus = true) {
  appearanceMenu.hidden = !open;
  appearanceBtn.setAttribute("aria-expanded", String(open));
  document.body.classList.toggle("appearance-open", open);
  showAppearanceSection(null);
  if (open) appearanceCategories.querySelector("button").focus({ preventScroll: true });
  else if (restoreFocus) appearanceBtn.focus({ preventScroll: true });
}

function initAppearance() {
  setupChoice(SKINS, "skin", "skinChoices", (id) => (id === "auto" ? autoSkin() : id));
  setupChoice(ICONS, "icon", "iconChoices");
  setupChoice(LAYOUTS, "layout", "layoutChoices");
  setupChoice(MOTIONS, "motion", "motionChoices");
  setupChoice(TRAILS, "trail", "trailChoices");
  setupChoice(SKYS, "sky", "skyChoices");
  setupChoice(FX, "fx", "fxChoices");
  const colorSchemeMq = matchMedia("(prefers-color-scheme: light)");
  colorSchemeMq.addEventListener("change", () => {
    let s = null;
    try { s = localStorage.getItem("bm-skin"); } catch (e) {}
    if ((s || "") === "auto") {
      const resolved = autoSkin();
      document.documentElement.dataset.skin = resolved;
      const fav = document.getElementById("fav");
      if (fav) fav.href = "/__favicon?skin=" + encodeURIComponent(resolved);
      fetch("/__icon?skin=" + encodeURIComponent(resolved)).catch(() => {});
    }
  });

  appearanceBtn.addEventListener("click", () => setAppearanceOpen(appearanceMenu.hidden));
  appearanceCategories.addEventListener("click", (event) => {
    const category = event.target.closest("[data-setting]");
    if (category) showAppearanceSection(category.dataset.setting);
  });
  appearanceBack.addEventListener("click", () => showAppearanceSection(null));
  document.getElementById("appearanceClose").addEventListener("click", () => showAppearanceSection(null));
  document.getElementById("appearanceMenuClose").addEventListener("click", () => setAppearanceOpen(false));
  document.addEventListener("click", (event) => {
    if (!appearanceMenu.hidden && !appearanceMenu.contains(event.target) && !appearancePanel.contains(event.target) && !appearanceBtn.contains(event.target)) {
      setAppearanceOpen(false, false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || appearanceMenu.hidden) return;
    event.preventDefault();
    if (!appearancePanel.hidden) showAppearanceSection(null);
    else setAppearanceOpen(false);
  });
}
