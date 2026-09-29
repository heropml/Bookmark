const ITEMS = (window.BOOKMARKS || []).map((it) => {
  // Older data.js files may still carry "user:password@"; never show it or send it to icon services.
  const host = String(it.host || "").replace(/^.*@/, "");
  return {
    ...it,
    host,
    search: [it.title, it.href, it.path, it.group, host].join(" ").toLowerCase(),
    hue: hue(host || it.path)
  };
});
const folderNameTooltip = document.getElementById("folderNameTooltip");
let pinnedUrls = [];
try {
  const saved = JSON.parse(localStorage.getItem("bm-pins") || "[]");
  if (Array.isArray(saved)) pinnedUrls = [...new Set(saved.filter(url => typeof url === "string"))];
} catch (e) {}

function activeFolder() {
  return state.q.trim() && !state.searchLocal ? "" : state.folder;
}

function hue(text) {
  let h = 0;
  for (const ch of String(text)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 360;
}
function inFolder(item) {
  if (!state.folder) return true;
  return item.path === state.folder || item.path.startsWith(state.folder + "/") || item.group === state.folder;
}
function hitSearch(item) {
  const q = state.q.trim().toLowerCase();
  if (!q) return true;
  return q.split(/\s+/).every(word => item.search.includes(word));
}
function matches(item) { return (!activeFolder() || inFolder(item)) && hitSearch(item); }
function sectionKey(item) {
  if (!activeFolder()) return item.group;
  if (item.path === state.folder) return item.path;
  const rest = item.path.startsWith(state.folder + "/")
    ? item.path.slice(state.folder.length + 1)
    : item.path;
  const next = rest.split("/")[0];
  return next ? state.folder + "/" + next : item.path;
}
function buildTree(pathCounts) {
  const root = { kids: {} };
  for (const [path, count] of pathCounts) {
    let node = root;
    const acc = [];
    for (const part of path.split("/")) {
      acc.push(part);
      if (!node.kids[part]) node.kids[part] = { name: part, path: acc.join("/"), count: 0, kids: {} };
      node = node.kids[part];
      node.count += count;
    }
  }
  return root;
}
function nodeAt(root, path) {
  let node = root;
  if (!path) return node;
  for (const part of path.split("/")) {
    node = node.kids[part];
    if (!node) return null;
  }
  return node;
}
function openColumns(folder, tree) {
  const cols = [""];
  if (!folder) return cols;
  const acc = [];
  for (const part of folder.split("/")) {
    acc.push(part);
    const path = acc.join("/");
    const node = nodeAt(tree, path);
    if (node && Object.keys(node.kids).length) cols.push(path);
  }
  return cols;
}

// Script URLs would run inside this local homepage, so such bookmarks stay visible but inert.
function safeHref(href) {
  const scheme = /^([a-z][a-z\d+.-]*):/i.exec(String(href).replace(/[\x00-\x20]/g, ""));
  return scheme && /^(javascript|vbscript|data)$/i.test(scheme[1]) ? "" : href;
}
// Bookmarks without a host (scripts, local files) keep their letter instead of a doomed lookup.
function faviconImg(host) {
  if (!host) return "";
  const encoded = encodeURIComponent(host);
  return `<img src="https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://${encoded}&size=64" data-fallback="https://icons.duckduckgo.com/ip3/${encoded}.ico" alt="" loading="lazy">`;
}
// The section heading already names the folder, so a tag only shows the path below it.
function pathBelowSection(item) {
  const key = sectionKey(item);
  return item.path.startsWith(key + "/") ? item.path.slice(key.length + 1) : "";
}
function sectionTitle(name) {
  const parts = name.split("/");
  const last = parts.pop();
  return (parts.length ? `<span class="section-parent">${escapeHtml(parts.join(" › "))} ›</span>` : "") + escapeHtml(last);
}
// Called as .map(cardHtml), so options must not be positional: the index arrives second.
function cardHtml(item, { shelf = false } = {}) {
  const h = item.hue;
  const letter = (item.title || item.host || "?").trim().charAt(0).toUpperCase();
  // Pinned cards sit outside any section, where a section-relative tag would change with the folder.
  const sub = shelf ? "" : pathBelowSection(item);
  const href = safeHref(item.href);
  const link = href
    ? `href="${escapeHtml(href)}" target="_blank" rel="noreferrer" title="${escapeHtml(item.title)}"${shelf ? ' aria-keyshortcuts="Alt+ArrowLeft Alt+ArrowRight"' : ""}`
    : 'aria-disabled="true" title="书签脚本不能在主页中运行"';
  const pinned = pinnedUrls.includes(item.href);
  return `<div class="bookmark-item"${shelf ? ` draggable="true" data-pinned-url="${escapeHtml(item.href)}"` : ""}>
    <a class="card" style="--h:${h}" ${link} data-key="${escapeHtml(item.href)}">
      <div class="ico">
        <span>${escapeHtml(letter)}</span>
        ${faviconImg(item.host)}
      </div>
      <div>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.host)}</p>
        <div class="meta">
          ${sub ? `<span class="tag">${escapeHtml(sub)}</span>` : ""}
          ${item.href.startsWith("http://") ? '<span class="tag">http</span>' : ""}
        </div>
      </div>
      <i class="card-glow" aria-hidden="true"></i>
    </a>
    <button type="button" class="bookmark-pin" data-pin="${escapeHtml(item.href)}" aria-pressed="${pinned}" aria-label="${pinned ? "取消置顶" : "置顶"}：${escapeHtml(item.title)}" title="${pinned ? "取消置顶" : "置顶到常用"}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/></svg></button>
    </div>`;
}
// A few site icons make each category card recognisable at a glance on the overview.
function peekHtml(items) {
  const hosts = [...new Set(items.map((item) => item.host).filter(Boolean))].slice(0, 4);
  return hosts.length ? `<span class="card-peek" aria-hidden="true">${hosts.map(faviconImg).join("")}</span>` : "";
}
function selectedInCol(itemPath) {
  if (!activeFolder()) return itemPath === "";
  if (itemPath === "") return false;
  return state.folder === itemPath || state.folder.startsWith(itemPath + "/");
}

function folderNameLength(name) {
  return Array.from(name).length;
}
function folderNameWidth(items) {
  return Math.min(4, Math.max(1, ...items.map((item) => folderNameLength(item.name))));
}
function updateFolderNameScroll() {
  for (const label of document.querySelectorAll("#nav .folder > b")) {
    const name = label.querySelector(".folder-name");
    if (!name) continue;
    const overflow = Math.ceil(name.scrollWidth - label.clientWidth);
    const shouldScroll = folderNameLength(name.textContent.trim()) > 4 && overflow > 1;
    label.classList.toggle("is-overflow", shouldScroll);
    if (shouldScroll) label.style.setProperty("--folder-overflow", overflow + "px");
  }
}

let flipSnapshot = null;
function snapshotFlips() {
  flipSnapshot = null;
  if (!motionOk()) return;
  const cards = document.querySelectorAll("#main [data-key]");
  if (!cards.length || cards.length > 300) return;
  const map = new Map();
  for (const el of cards) {
    const r = el.getBoundingClientRect();
    if (r.width || r.height) map.set(el.dataset.key, { x: r.left, y: r.top });
  }
  flipSnapshot = map;
}
function applyFlips() {
  const map = flipSnapshot;
  flipSnapshot = null;
  if (!map) return;
  for (const el of document.querySelectorAll("#main [data-key]")) {
    const old = map.get(el.dataset.key);
    if (!old) continue;
    const r = el.getBoundingClientRect();
    const dx = old.x - r.left;
    const dy = old.y - r.top;
    if (Math.abs(dx) < 2 && Math.abs(dy) < 2) continue;
    el.style.animation = "none";
    el.animate(
      [{ transform: "translate(" + dx.toFixed(1) + "px, " + dy.toFixed(1) + "px)" }, { transform: "none" }],
      { duration: 380, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" }
    );
  }
}
function render() {
  snapshotFlips();
  const searched = ITEMS.filter(hitSearch);
  const visible = searched.filter(matches);
  const groupCounts = new Map();
  const pathCounts = new Map();
  for (const item of searched) {
    groupCounts.set(item.group, (groupCounts.get(item.group) || 0) + 1);
    pathCounts.set(item.path, (pathCounts.get(item.path) || 0) + 1);
  }
  const tree = buildTree(pathCounts);
  prepareLayoutState(tree);
  const cols = openColumns(activeFolder(), tree);

  document.getElementById("nav").innerHTML = document.documentElement.dataset.layout === "tree"
    ? treeNavHtml(tree, searched.length)
    : ["tabs", "start", "accordion", ...EXTRA_LAYOUTS].includes(document.documentElement.dataset.layout)
    ? horizontalNavHtml(tree, searched.length)
    : cols.map((colPath) => {
    const node = nodeAt(tree, colPath);
    let items = [];
    if (colPath === "") {
      const names = Object.keys(tree.kids);
      items = [
        { name: "全部", path: "", count: searched.length, hasKids: false },
        ...names.map((name) => {
          const child = tree.kids[name];
          return { name, path: name, count: groupCounts.get(name), hasKids: Object.keys(child.kids).length > 0 };
        })
      ];
    } else {
      items = Object.keys(node.kids).map((name) => {
        const child = node.kids[name];
        return { name: child.name, path: child.path, count: child.count, hasKids: Object.keys(child.kids).length > 0 };
      });
    }
    const nameWidth = folderNameWidth(items);
    const buttons = items.map((it) => {
      const on = selectedInCol(it.path) || (it.path === "" && !activeFolder());
      const fullName = folderNameLength(it.name) > 4 ? ` data-full-name="${escapeHtml(it.name)}"` : "";
      return `<button class="folder ${it.hasKids ? "has-kids" : ""} ${on ? "on" : ""}" data-folder="${escapeHtml(it.path)}"${fullName} style="--h:${hue(it.path || it.name)}"><em class="dot"></em><b><span class="folder-name">${escapeHtml(it.name)}</span></b><span>${it.count}</span></button>`;
    }).join("");
    return `<div class="nav-col" style="--folder-name-width:${nameWidth}em">${buttons}</div>`;
  }).join("");
  updateFolderNameScroll();

  document.getElementById("stats").textContent = `${visible.length} / ${ITEMS.length}`;
  renderLibraryChrome(visible.length);

  const main = document.getElementById("main");
  if (!visible.length) {
    main.innerHTML = `<div class="empty"><strong>没有找到匹配的书签</strong><p>${activeFolder() ? "试试搜索全部分类，或换一个关键词。" : "试试网站名称、域名或分类名称。"}</p>${activeFolder() && state.q.trim() ? '<button type="button" class="library-button" data-search-all>搜索全部分类</button>' : ""}</div>`;
    return;
  }
  const sections = new Map();
  for (const item of visible) {
    const key = sectionKey(item);
    if (!sections.has(key)) sections.set(key, []);
    sections.get(key).push(item);
  }
  const order = [...sections.keys()];
  if (document.documentElement.dataset.layout === "accordion") {
    main.innerHTML = accordionHtml(sections, order);
    applyFlips();
    return;
  }
  if (["board", "waterfall"].includes(document.documentElement.dataset.layout)) {
    main.innerHTML = boardHtml(sections, order);
    applyFlips();
    return;
  }
  if (["shelves", "index", "text"].includes(document.documentElement.dataset.layout)) {
    main.innerHTML = collectionHtml(sections, order);
    applyFlips();
    return;
  }
  if (document.documentElement.dataset.layout === "table") {
    main.innerHTML = tableHtml(visible);
    applyFlips();
    return;
  }
  if (!state.folder && !state.q.trim() && !EXTRA_LAYOUTS.includes(document.documentElement.dataset.layout)) {
    main.innerHTML = `<div class="grid">${order.map((name) => `
      <button type="button" class="card" data-folder="${escapeHtml(name)}" data-key="folder:${escapeHtml(name)}" title="${escapeHtml(name)}" style="--h:${hue(name)}">
        <div class="ico"><span>${escapeHtml(name.charAt(0))}</span></div>
        <div>
          <h3>${escapeHtml(name)}</h3>
          <p>${sections.get(name).length} 个书签</p>
          ${peekHtml(sections.get(name))}
        </div>
        <i class="card-glow" aria-hidden="true"></i>
      </button>`).join("")}</div>`;
    applyFlips();
    return;
  }
  let used = 0;
  const html = [];
  for (const name of order) {
    const all = sections.get(name);
    if (used >= state.shown) break;
    const shown = all.slice(0, state.shown - used);
    used += shown.length;
    html.push(`
    <section class="section">
      <h2 style="--h:${hue(name)}"><em class="dot"></em>${sectionTitle(name)}<span>${all.length}</span></h2>
      <div class="grid">${shown.map(cardHtml).join("")}</div>
    </section>`);
  }
  if (used < visible.length) {
    html.push(`<button type="button" class="more" id="moreBtn">还有 ${visible.length - used} 个</button>`);
  }
  main.innerHTML = html.join("");
  applyFlips();
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function pickFolder(e) {
  const pin = e.target.closest("[data-pin]");
  if (pin) {
    const url = pin.dataset.pin;
    const next = pinnedUrls.includes(url) ? pinnedUrls.filter(item => item !== url) : [...pinnedUrls, url];
    try { localStorage.setItem("bm-pins", JSON.stringify(next)); }
    catch (error) {
      setLibraryStatus("无法保存置顶，请检查浏览器是否允许本地存储。");
      return;
    }
    pinnedUrls = next;
    setLibraryStatus("");
    render();
    const target = [...document.querySelectorAll('[data-pin]')].find(button => button.dataset.pin === url && !button.closest('[hidden]'));
    target?.focus({ preventScroll: true });
    return;
  }
  if (e.target.closest("[data-search-all]")) {
    state.searchLocal = false;
    state.shown = PAGE;
    render();
    return;
  }
  if (handleLayoutClick(e)) return;
  const more = e.target.closest("#moreBtn");
  if (more) {
    state.shown += PAGE;
    render();
    return;
  }
  const card = e.target.closest("a.card, button.card");
  if (card && motionOk()) {
    const ripple = document.createElement("span");
    ripple.className = "ripple";
    card.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());
  }
  const btn = e.target.closest("[data-folder]");
  if (!btn) return;
  const treeScroll = document.getElementById("nav").firstElementChild?.scrollTop || 0;
  state.folder = btn.getAttribute("data-folder");
  if (state.q.trim()) state.searchLocal = !!state.folder;
  try { localStorage.setItem("bm-folder", state.folder); } catch (e) {}
  state.shown = PAGE;
  render();
  if (document.documentElement.dataset.layout === "tree") {
    const selected = matchMedia("(max-width: 600px)").matches
      ? document.querySelector("[data-tree-menu]")
      : [...document.querySelectorAll(".tree-label")].find(el => el.dataset.folder === state.folder);
    if (selected) {
      selected.focus({ preventScroll: true });
      selected.closest(".tree-nav").scrollTop = treeScroll;
    }
  }
}

function renderLibraryChrome(count) {
  const title = document.getElementById("libraryTitle");
  if (!title) return;
  const searching = !!state.q.trim();
  title.textContent = searching ? "搜索结果" : "我的书签";
  document.getElementById("libraryCount").textContent = searching ? `${count} 个匹配` : `${count} 个书签`;
  document.getElementById("searchScope").hidden = !searching;
  document.getElementById("searchAll").setAttribute("aria-pressed", String(!state.searchLocal));
  const local = document.getElementById("searchLocal");
  local.disabled = !state.folder;
  local.textContent = state.folder ? `仅 ${state.folder.split("/").pop()}` : "当前分类";
  local.setAttribute("aria-pressed", String(state.searchLocal));
  const shelf = document.getElementById("pinnedShelf");
  const byUrl = new Map(ITEMS.map(item => [item.href, item]));
  const pinned = pinnedUrls.map(url => byUrl.get(url)).filter(Boolean);
  shelf.hidden = searching || pinned.length === 0;
  document.getElementById("pinnedCount").textContent = String(pinned.length);
  document.getElementById("pinnedGrid").innerHTML = pinned.map(item => cardHtml(item, { shelf: true })).join("");
}

let libraryStatusTimer = 0;
// Errors stay until the next action; a confirmation fades so it does not linger above the list.
function setLibraryStatus(text, transient = false) {
  const status = document.getElementById("libraryStatus");
  clearTimeout(libraryStatusTimer);
  status.textContent = text;
  if (transient) libraryStatusTimer = setTimeout(() => { if (status.textContent === text) status.textContent = ""; }, 2500);
}

function reorderPinnedBookmark(source, target, after) {
  if (source === target || !pinnedUrls.includes(source) || !pinnedUrls.includes(target)) return false;
  const next = pinnedUrls.filter(url => url !== source);
  next.splice(next.indexOf(target) + (after ? 1 : 0), 0, source);
  if (next.every((url, index) => url === pinnedUrls[index])) return false;
  try { localStorage.setItem("bm-pins", JSON.stringify(next)); }
  catch (error) {
    setLibraryStatus("无法保存置顶顺序，请检查浏览器是否允许本地存储。");
    return false;
  }
  pinnedUrls = next;
  setLibraryStatus("置顶顺序已保存", true);
  render();
  return true;
}

function showFolderNameTooltip(button) {
  if (!folderNameTooltip || !button.dataset.fullName) return;
  folderNameTooltip.textContent = button.dataset.fullName;
  folderNameTooltip.hidden = false;
  const buttonRect = button.getBoundingClientRect();
  const tooltipRect = folderNameTooltip.getBoundingClientRect();
  let left = buttonRect.right + 8;
  if (left + tooltipRect.width > innerWidth - 12) left = Math.max(12, buttonRect.left - tooltipRect.width - 8);
  const top = Math.min(Math.max(12, buttonRect.top + (buttonRect.height - tooltipRect.height) / 2), innerHeight - tooltipRect.height - 12);
  folderNameTooltip.style.left = left + "px";
  folderNameTooltip.style.top = top + "px";
}
function hideFolderNameTooltip() {
  if (folderNameTooltip) folderNameTooltip.hidden = true;
}

function initBookmarks() {
  // The saved or default category may not exist in these bookmarks, e.g. after a sync.
  if (state.folder && !ITEMS.some(inFolder)) {
    state.folder = "";
    try { localStorage.setItem("bm-folder", ""); } catch (e) {}
  }
  const nav = document.getElementById("nav");
  nav.addEventListener("click", pickFolder);
  nav.addEventListener("pointerover", (event) => {
    const button = event.target.closest(".folder[data-full-name]");
    if (button) showFolderNameTooltip(button);
  });
  nav.addEventListener("pointerout", (event) => {
    const button = event.target.closest(".folder[data-full-name]");
    if (button && !button.contains(event.relatedTarget)) hideFolderNameTooltip();
  });
  nav.addEventListener("focusin", (event) => {
    const button = event.target.closest(".folder[data-full-name]");
    if (button) showFolderNameTooltip(button);
  });
  nav.addEventListener("focusout", hideFolderNameTooltip);
  const main = document.getElementById("main");
  main.addEventListener("click", pickFolder);
  // Image errors do not bubble: try the second icon service once, then keep the letter.
  main.addEventListener("error", (event) => {
    const img = event.target;
    if (img.tagName !== "IMG" || !img.dataset.fallback) return;
    if (img.dataset.fb) img.remove();
    else {
      img.dataset.fb = "1";
      img.src = img.dataset.fallback;
    }
  }, true);
  let searchTimer = 0;
  document.getElementById("q").addEventListener("input", (e) => {
    state.q = e.target.value;
    if (!state.q.trim()) state.searchLocal = false;
    document.body.classList.toggle("searching", !!state.q.trim());
    state.shown = PAGE;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(render, 80);
  });
}

function initSearchShortcuts() {
  const searchInput = document.getElementById("q");
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform || "");
  document.getElementById("searchKbd").textContent = isMac ? "\u2318K" : "Ctrl K";
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (!appearanceMenu.hidden) setAppearanceOpen(false, false);
      searchInput.focus();
      searchInput.select();
    }
  });
  window.addEventListener("focus", () => {
    if (!appearanceMenu.hidden) return;
    const ae = document.activeElement;
    if (!ae || ae === document.body || (ae.closest && ae.closest("#main, #nav"))) searchInput.focus();
  });
}
