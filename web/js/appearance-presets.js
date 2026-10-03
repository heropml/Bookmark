const APPEARANCE_PRESETS_KEY = "bm-appearance-presets";
const APPEARANCE_PRESET_CHOICES = { skin: SKINS, icon: ICONS, layout: LAYOUTS, motion: MOTIONS, trail: TRAILS, sky: SKYS, fx: FX };

function validateAppearanceSnapshot(value) {
  if (!value || typeof value !== "object") return null;
  const result = {};
  for (const [key, choices] of Object.entries(APPEARANCE_PRESET_CHOICES)) {
    if (!choices.some(item => item.id === value[key])) return null;
    result[key] = value[key];
  }
  if (typeof value.fxFollowsSystem !== "boolean" || !["on", "off"].includes(value.focus)) return null;
  if (![60, 70, 80, 90, 100, 110, 120].includes(value.density)) return null;
  for (const [key, min, step] of [["trailSize", .5, .1], ["skySize", .5, .1], ["skyCount", .25, .25]]) {
    const number = value[key];
    if (!Number.isFinite(number) || number < min || number > 2.5 || Math.abs(number / step - Math.round(number / step)) > .00001) return null;
    result[key] = number;
  }
  return { ...result, fxFollowsSystem: value.fxFollowsSystem, focus: value.focus, density: value.density };
}

// An entry this version cannot apply (e.g. saved by a version with another theme list) is hidden
// but written back unchanged, so one such entry no longer makes every other preset unreadable.
function readAppearancePresets() {
  const raw = localStorage.getItem(APPEARANCE_PRESETS_KEY);
  if (raw === null) return { presets: [], incompatible: [] };
  const value = JSON.parse(raw);
  if (!Array.isArray(value)) throw new Error("外观方案数据无效，无法读取。");
  const names = new Set();
  const presets = [];
  const incompatible = [];
  for (const item of value) {
    const settings = validateAppearanceSnapshot(item?.settings);
    const name = typeof item?.name === "string" ? item.name.trim() : "";
    if (settings && name && name.length <= 40 && !names.has(name)) {
      names.add(name);
      presets.push({ name, settings });
    } else incompatible.push(item);
  }
  return { presets, incompatible };
}

function captureAppearanceSnapshot() {
  const value = {};
  for (const key of Object.keys(APPEARANCE_PRESET_CHOICES)) value[key] = appearanceChoices[key].value();
  return {
    ...value, fxFollowsSystem: appearanceChoices.fx.followsSystem(), density: appearanceDensity.value(),
    focus: document.documentElement.dataset.focus === "on" ? "on" : "off",
    trailSize: trailScale, skySize: skyScale, skyCount
  };
}

function applyAppearanceSnapshot(value) {
  const settings = validateAppearanceSnapshot(value);
  if (!settings) throw new Error("方案设置无效，未应用。");
  let persisted = true;
  try {
    for (const key of Object.keys(APPEARANCE_PRESET_CHOICES)) {
      if (key === "fx" && settings.fxFollowsSystem) localStorage.removeItem("bm-fx");
      else localStorage.setItem("bm-" + key, settings[key]);
    }
    for (const [key, field] of [["card-density", "density"], ["focus", "focus"], ["trail-size", "trailSize"], ["sky-size", "skySize"], ["sky-count", "skyCount"]]) {
      localStorage.setItem("bm-" + key, String(settings[field]));
    }
  } catch (e) { persisted = false; }
  const previousLayout = document.documentElement.dataset.layout;
  for (const key of Object.keys(APPEARANCE_PRESET_CHOICES)) appearanceChoices[key].apply(settings[key], false, key === "fx" && settings.fxFollowsSystem);
  appearanceDensity.apply(settings.density, false);
  setTrailSize(settings.trailSize, false);
  setSkySize(settings.skySize, false);
  setSkyCount(settings.skyCount, false);
  skyPopulate();
  if ((document.documentElement.dataset.focus === "on" ? "on" : "off") !== settings.focus) document.getElementById("focusPreset").click();
  if (previousLayout !== settings.layout) render();
  window.dispatchEvent(new Event("bm-fx"));
  return persisted;
}

function initAppearancePresets() {
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.id = "appearancePresetsBtn";
  trigger.className = "appearance-category appearance-presets-trigger";
  trigger.innerHTML = `<span class="appearance-art" aria-hidden="true"><svg viewBox="0 0 52 48" fill="none"><rect x="7" y="8" width="30" height="32" rx="6" fill="currentColor" opacity=".15" transform="rotate(-12 22 24)"/><g class="art-animated art-card"><rect x="15" y="7" width="30" height="34" rx="6" fill="currentColor" fill-opacity=".12" stroke="currentColor" stroke-opacity=".65"/><path d="M25 7v16l5-3 5 3V7" fill="currentColor" fill-opacity=".65"/><path d="M23 30h14M23 35h9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></g></svg></span>
    <span class="appearance-category-copy"><b>外观方案</b><small>保存与切换外观</small></span>
    <span class="appearance-category-arrow" aria-hidden="true"><svg viewBox="0 0 12 12" fill="none"><path d="m4.5 3 3 3-3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>`;
  trigger.dataset.setting = "presets";
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-controls", "appearancePanel");
  appearanceCategories.append(trigger);
  const section = document.createElement("section");
  section.className = "appearance-group appearance-presets-section";
  section.dataset.settingPanel = "presets";
  section.dataset.title = "外观方案";
  section.dataset.description = "保存当前主题、布局、密度、动效和专注状态，仅保存在此浏览器。";
  section.hidden = true;
  section.innerHTML = `<form class="appearance-preset-form"><label for="appearancePresetName">方案名称</label><div><input id="appearancePresetName" type="text" maxlength="40" autocomplete="off" placeholder="例如：日常使用" required><button class="appearance-preset-save" type="submit">保存当前外观</button></div></form>
    <p class="sync-status" role="status" aria-live="polite"></p><ul class="appearance-presets-list" aria-label="已保存的外观方案"></ul>`;
  appearancePanel.querySelector(".appearance-body").append(section);
  const form = section.querySelector("form");
  const input = section.querySelector("input");
  const list = section.querySelector("ul");
  const status = section.querySelector(".sync-status");
  let presets = [];
  let incompatible = [];
  let readable = true;
  const showStatus = (message, error = false) => {
    status.textContent = message;
    status.dataset.state = error ? "error" : "";
  };
  const focusAction = (name, action) => {
    const button = [...list.querySelectorAll("button")].find(item => item.getAttribute("aria-label") === action + "方案：" + name);
    (button || input).focus();
  };
  const save = next => {
    try { localStorage.setItem(APPEARANCE_PRESETS_KEY, JSON.stringify([...next, ...incompatible])); }
    catch (e) { showStatus("无法保存到此浏览器，方案未更改。请检查浏览器存储权限或空间。", true); return false; }
    presets = next;
    draw();
    return true;
  };
  const draw = () => {
    list.replaceChildren();
    if (!presets.length) {
      const empty = document.createElement("li");
      empty.className = "appearance-presets-empty";
      empty.textContent = "还没有方案，输入名称即可保存当前外观。";
      list.append(empty);
    }
    for (const preset of presets) {
      const row = document.createElement("li");
      const copy = document.createElement("div");
      copy.className = "appearance-preset-copy";
      const name = document.createElement("strong");
      name.textContent = preset.name;
      const description = document.createElement("small");
      const settings = preset.settings;
      description.textContent = SKINS.find(x => x.id === settings.skin).name + " · " + LAYOUTS.find(x => x.id === settings.layout).name + " · " + settings.density + "%";
      copy.append(name, description);
      const actions = document.createElement("div");
      actions.className = "appearance-preset-actions";
      for (const [label, action] of [["应用", () => {
        const persisted = applyAppearanceSnapshot(preset.settings);
        showStatus(persisted ? "已应用「" + preset.name + "」。" : "已在当前页面应用，但无法保存设置；刷新后可能恢复原外观。", !persisted);
      }], ["更新", () => {
        if (save(presets.map(item => item === preset ? { name: item.name, settings: captureAppearanceSnapshot() } : item))) {
          showStatus("已用当前外观更新「" + preset.name + "」。");
          focusAction(preset.name, "更新");
        }
      }], ["删除", () => {
        const index = presets.indexOf(preset);
        const neighbour = presets[index + 1] || presets[index - 1];
        if (save(presets.filter(item => item !== preset))) {
          showStatus("已删除「" + preset.name + "」。");
          focusAction(neighbour?.name, "删除");
        }
      }]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.setAttribute("aria-label", label + "方案：" + preset.name);
        if (label === "更新") button.title = "用当前外观覆盖这个方案";
        button.addEventListener("click", action);
        actions.append(button);
      }
      row.append(copy, actions);
      list.append(row);
    }
  };
  const load = () => {
    input.value = "";
    showStatus("");
    readable = true;
    form.querySelector("button").disabled = false;
    try {
      ({ presets, incompatible } = readAppearancePresets());
      if (incompatible.length) showStatus(`有 ${incompatible.length} 个方案无法在此版本使用，已隐藏并原样保留。`);
    }
    catch (e) {
      presets = [];
      incompatible = [];
      readable = false;
      form.querySelector("button").disabled = true;
      showStatus("无法读取已存方案，请检查浏览器存储；原数据未更改。", true);
    }
    draw();
  };
  trigger.addEventListener("click", load);
  trigger.addEventListener("pointerover", event => {
    if (event.pointerType === "mouse" && !trigger.contains(event.relatedTarget) && appearanceSection !== "presets") load();
  });
  form.addEventListener("submit", event => {
    event.preventDefault();
    if (!readable) return;
    const name = input.value.trim();
    if (!name || name.length > 40) { showStatus("请输入 1–40 个字符的方案名称。", true); input.focus(); return; }
    if (presets.some(item => item.name === name)) { showStatus("此名称已存在，可点击对应方案的「更新」。", true); return; }
    if (save([...presets, { name, settings: captureAppearanceSnapshot() }])) {
      input.value = "";
      showStatus("已保存「" + name + "」。");
    }
  });
}
