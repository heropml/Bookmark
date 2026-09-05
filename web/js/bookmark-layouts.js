// Structural layouts share the existing bookmark cards, filtering and theme system.
const BOARD_PAGE = 8;
const boardLimits = new Map();
const treeExpanded = new Set();
const accordionCollapsed = new Set();
let layoutFolder = null;
let layoutQuery = null;

function prepareLayoutState(tree) {
  const query = state.q.trim().toLowerCase();
  if (layoutFolder !== state.folder || layoutQuery !== query) {
    boardLimits.clear();
    accordionCollapsed.clear();
  }
  if (layoutFolder !== state.folder) {
    const parts = state.folder.split("/");
    for (let i = 1; i <= parts.length; i++) treeExpanded.add(parts.slice(0, i).join("/"));
  }
  // Reveal search matches without preventing users from collapsing a result branch.
  if (query && layoutQuery !== query) {
    const expand = (node) => {
      for (const child of Object.values(node.kids)) {
        if (Object.keys(child.kids).length) treeExpanded.add(child.path);
        expand(child);
      }
    };
    expand(tree);
  }
  layoutFolder = state.folder;
  layoutQuery = query;
}

function boardHtml(sections, order) {
  return `<div class="board-columns">${order.map((name) => {
    const items = sections.get(name);
    const shown = items.slice(0, boardLimits.get(name) || BOARD_PAGE);
    const remaining = items.length - shown.length;
    const shortName = name.split("/").pop();
    return `<section class="board-column nav-col" data-board="${escapeHtml(name)}" style="--h:${hue(name)}">
      <h2 class="board-heading"><button type="button" data-folder="${escapeHtml(name)}" title="查看 ${escapeHtml(name)}">
        <em class="dot" aria-hidden="true"></em><span>${escapeHtml(shortName)}</span><b>${items.length}</b>
      </button></h2>
      <p class="board-path" title="${escapeHtml(name)}">${escapeHtml(name)}</p>
      <div class="grid">${shown.map(cardHtml).join("")}</div>
      ${remaining ? `<button type="button" class="board-more" data-board-more="${escapeHtml(name)}">再显示 ${Math.min(BOARD_PAGE, remaining)} 个 <span>· 还有 ${remaining} 个</span></button>` : ""}
    </section>`;
  }).join("")}</div>`;
}

function treeNavHtml(tree, groupCounts, total) {
  const label = (name, path, count) => `<button type="button" class="folder tree-label ${selectedInCol("", path) ? "on" : ""}" data-folder="${escapeHtml(path)}" title="${escapeHtml(path || name)}"${state.folder === path ? ' aria-current="page"' : ""}>
    <svg class="tree-folder-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3Z"/></svg>
    <b>${escapeHtml(name)}</b><span>${count}</span></button>`;
  const branch = (node, depth) => {
    const children = Object.values(node.kids);
    const expanded = treeExpanded.has(node.path);
    const id = "tree-" + encodeURIComponent(node.path);
    return `<li>
      <div class="tree-row" style="--tree-depth:${Math.min(depth, 5)};--h:${hue(node.path)}">
        ${children.length ? `<button type="button" class="tree-toggle" data-tree-toggle="${escapeHtml(node.path)}" aria-expanded="${expanded}" aria-controls="${id}" aria-label="展开或收起 ${escapeHtml(node.name)}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg></button>` : '<span class="tree-spacer" aria-hidden="true"></span>'}
        ${label(node.name, node.path, node.count)}
      </div>
      ${children.length ? `<ul id="${id}"${expanded ? "" : " hidden"}>${children.map(child => branch(child, depth + 1)).join("")}</ul>` : ""}
    </li>`;
  };
  return `<nav class="nav-col tree-nav" aria-label="书签目录">
    <div class="tree-caption">书签目录<span>分类 / 层级</span></div>
    <div class="tree-row tree-all" style="--tree-depth:0;--h:210"><span class="tree-spacer" aria-hidden="true"></span>${label("全部", "", total)}</div>
    <ul>${sortNames(Object.keys(tree.kids), groupCounts).map(name => branch(tree.kids[name], 0)).join("")}</ul>
  </nav>`;
}

function horizontalNavHtml(tree, total) {
  const button = (name, path, count, current) => `<button type="button" class="folder ${current ? "on" : ""}" data-folder="${escapeHtml(path)}" style="--h:${hue(path || name)}"${current ? ' aria-current="page"' : ""}><b>${escapeHtml(name)}</b>${count === undefined ? "" : `<span>${count}</span>`}</button>`;
  const roots = Object.values(tree.kids);
  const tabs = button("全部", "", total, !state.folder) + roots.map(node =>
    button(node.name, node.path, node.count, selectedInCol("", node.path))).join("");
  const parts = state.folder ? state.folder.split("/") : [];
  const crumbs = parts.length ? `<nav class="layout-breadcrumbs" aria-label="当前位置">${button("全部", "", undefined, false)}${parts.map((part, i) =>
    `<span aria-hidden="true">/</span>${button(part, parts.slice(0, i + 1).join("/"), undefined, i === parts.length - 1)}`).join("")}</nav>` : "";
  const node = state.folder ? nodeAt(tree, state.folder) : null;
  const children = node ? Object.values(node.kids) : [];
  const subnav = children.length ? `<nav class="horizontal-children" aria-label="下级分类">${children.map(child => button(child.name, child.path, child.count, false)).join("")}</nav>` : "";
  return `<nav class="nav-col horizontal-tabs" aria-label="书签分类">${tabs}</nav>${crumbs}${subnav}`;
}

function accordionHtml(sections, order) {
  return order.map(name => {
    const items = sections.get(name);
    const shown = items.slice(0, boardLimits.get(name) || BOARD_PAGE);
    const remaining = items.length - shown.length;
    const expanded = !accordionCollapsed.has(name);
    const id = "accordion-" + encodeURIComponent(name);
    return `<section class="accordion-group nav-col" data-board="${escapeHtml(name)}" style="--h:${hue(name)}">
      <h2><button type="button" class="accordion-toggle" data-accordion-toggle="${escapeHtml(name)}" aria-expanded="${expanded}" aria-controls="${id}">
        <span class="accordion-arrow" aria-hidden="true">›</span><span class="accordion-name">${escapeHtml(name)}</span><span class="accordion-count">${items.length} 个书签</span>
      </button></h2>
      <div class="accordion-body" id="${id}"${expanded ? "" : " hidden"}>
        <div class="grid">${shown.map(cardHtml).join("")}</div>
        ${remaining ? `<button type="button" class="board-more" data-board-more="${escapeHtml(name)}">再显示 ${Math.min(BOARD_PAGE, remaining)} 个 <span>· 还有 ${remaining} 个</span></button>` : ""}
      </div>
    </section>`;
  }).join("");
}

function handleLayoutClick(event) {
  const accordion = event.target.closest("[data-accordion-toggle]");
  if (accordion) {
    const name = accordion.dataset.accordionToggle;
    const expanded = accordion.getAttribute("aria-expanded") !== "true";
    if (expanded) accordionCollapsed.delete(name);
    else accordionCollapsed.add(name);
    accordion.setAttribute("aria-expanded", String(expanded));
    document.getElementById(accordion.getAttribute("aria-controls")).hidden = !expanded;
    return true;
  }
  const toggle = event.target.closest("[data-tree-toggle]");
  if (toggle) {
    const path = toggle.dataset.treeToggle;
    const expanded = toggle.getAttribute("aria-expanded") !== "true";
    if (expanded) treeExpanded.add(path);
    else treeExpanded.delete(path);
    toggle.setAttribute("aria-expanded", String(expanded));
    document.getElementById(toggle.getAttribute("aria-controls")).hidden = !expanded;
    return true;
  }
  const more = event.target.closest("[data-board-more]");
  if (!more) return false;
  const name = more.dataset.boardMore;
  const before = boardLimits.get(name) || BOARD_PAGE;
  boardLimits.set(name, before + BOARD_PAGE);
  render();
  const column = [...document.querySelectorAll("[data-board]")].find(el => el.dataset.board === name);
  // Continue keyboard reading at the first newly revealed bookmark.
  const next = column?.querySelectorAll("a.card")[before];
  if (next) next.focus({ preventScroll: true });
  return true;
}
