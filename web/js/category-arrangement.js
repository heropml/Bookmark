// Category presentation is local to this browser; imported bookmarks and pins keep their order.
const CATEGORY_LAYOUT_KEY = "bm-category-layout";
const categoryPreferences = new Map();
try {
  const saved = JSON.parse(localStorage.getItem(CATEGORY_LAYOUT_KEY) || "{}");
  if (saved && typeof saved === "object" && !Array.isArray(saved)) {
    for (const [scope, value] of Object.entries(saved)) {
      if (!value || typeof value !== "object" || Array.isArray(value)) continue;
      const preference = {};
      if (Array.isArray(value.order)) preference.order = [...new Set(value.order.filter(name => typeof name === "string"))];
      if (["small", "medium", "large"].includes(value.width)) preference.width = value.width;
      categoryPreferences.set(scope, preference);
    }
  }
} catch (error) {}
let categoryArrangementActive = false;
let categoryArrangementScope = null;
let categoryOriginalOrder = [];
let categoryArrangePanel = null;
let categoryDragSource = "";
let categoryArrangementAxis = "vertical";

function updateCategoryArrangementDirection() {
  if (!categoryArrangementActive) return;
  const blocks = [...document.querySelectorAll("#main [data-category-block]")];
  if (!blocks.length) return;
  const style = getComputedStyle(blocks[0].parentElement);
  // Grid reads across rows; CSS multicolumn layouts read down each column.
  const columns = style.gridTemplateColumns.split(/\s+/).filter(value => parseFloat(value) > 0);
  const horizontal = style.display.includes("grid") && columns.length > 1;
  categoryArrangementAxis = horizontal ? "horizontal" : "vertical";
  document.documentElement.dataset.categoryAxis = categoryArrangementAxis;
  const labels = horizontal ? ["左移", "右移"] : ["上移", "下移"];
  const arrows = horizontal ? ["←", "→"] : ["↑", "↓"];
  for (const block of blocks) {
    for (const button of block.querySelectorAll("[data-category-move]")) {
      const index = Number(button.dataset.categoryStep) < 0 ? 0 : 1;
      button.textContent = arrows[index];
      button.title = labels[index];
      button.setAttribute("aria-label", labels[index] + " " + button.dataset.categoryMove.split("/").join(" › "));
    }
    const handle = block.querySelector("[data-category-drag]");
    if (handle) {
      handle.title = "拖动排序，也可按 Alt+" + arrows.join(" / ");
      handle.setAttribute("aria-keyshortcuts", horizontal ? "Alt+ArrowLeft Alt+ArrowRight" : "Alt+ArrowUp Alt+ArrowDown");
    }
  }
  const hint = categoryArrangePanel?.querySelector(".category-arrange-hint");
  if (hint) hint.textContent = "拖动分类把手或用" + (horizontal ? "左右" : "上下") + "箭头移动整组分类，自动保存。";
}

function orderedCategories(names, scope = activeFolder()) {
  const available = new Set(names);
  const saved = categoryPreferences.get(scope)?.order || [];
  const known = saved.filter(name => available.has(name));
  const seen = new Set(known);
  return [...known, ...names.filter(name => !seen.has(name))];
}

function prepareCategoryArrangement(names) {
  const scope = activeFolder();
  const layout = document.documentElement.dataset.layout;
  const searching = !!state.q.trim();
  if (scope !== categoryArrangementScope || searching || layout === "table" || names.length < 2) categoryArrangementActive = false;
  categoryArrangementScope = scope;
  categoryOriginalOrder = names;
  document.documentElement.dataset.categoryArranging = categoryArrangementActive ? "on" : "off";
  document.documentElement.dataset.categoryWidth = categoryPreferences.get(scope)?.width || "";
  const button = document.getElementById("categoryArrangeBtn");
  if (button) {
    button.hidden = layout === "table" || (!searching && names.length < 2);
    button.disabled = searching;
    button.textContent = categoryArrangementActive ? "完成整理" : "整理分类";
    button.title = searching ? "清空搜索后整理分类" : "调整当前分类中的区块顺序";
    button.setAttribute("aria-pressed", String(categoryArrangementActive));
  }
  if (categoryArrangePanel) {
    categoryArrangePanel.hidden = !categoryArrangementActive;
    categoryArrangePanel.innerHTML = categoryArrangementActive ? `<span class="category-arrange-hint">拖动分类把手或用上下箭头移动整组分类，自动保存。</span>
      <button type="button" class="library-button" data-category-reset>恢复默认顺序</button>
      ${["board", "waterfall"].includes(layout) ? `<div class="category-width-options" role="group" aria-label="分类列宽"><span>列宽</span>${[["small", "小"], ["medium", "中"], ["large", "大"]].map(([value, label]) => `<button type="button" class="library-button" data-category-width="${value}" aria-pressed="${(categoryPreferences.get(scope)?.width || "medium") === value}">${label}</button>`).join("")}</div>` : ""}` : "";
  }
  return orderedCategories(names, scope);
}

function categoryBlockAttrs(name) {
  return `data-category-block="${escapeHtml(name)}"`;
}

function categoryControlsHtml(name) {
  if (!categoryArrangementActive) return "";
  const order = orderedCategories(categoryOriginalOrder);
  const index = order.indexOf(name);
  const label = escapeHtml(name.split("/").join(" › "));
  return `<div class="category-arrange-controls" role="group" aria-label="排列 ${label}">
    <button type="button" class="category-drag-handle" draggable="true" data-category-drag="${escapeHtml(name)}" aria-label="拖动分类 ${label}" aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown" title="拖动排序，也可按 Alt+↑ / ↓"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 4h0m6 0h0M7 10h0m6 0h0M7 16h0m6 0h0"/></svg></button>
    <button type="button" data-category-move="${escapeHtml(name)}" data-category-step="-1" aria-label="上移 ${label}" title="上移"${index <= 0 ? " disabled" : ""}>↑</button>
    <button type="button" data-category-move="${escapeHtml(name)}" data-category-step="1" aria-label="下移 ${label}" title="下移"${index === order.length - 1 ? " disabled" : ""}>↓</button>
  </div>`;
}

function categoryOverviewHtml(name, card) {
  return categoryArrangementActive ? `<div class="category-overview-card" ${categoryBlockAttrs(name)}>${categoryControlsHtml(name)}${card}</div>` : card;
}

function canArrangeCategories() {
  return categoryArrangementActive && !state.q.trim() && document.documentElement.dataset.layout !== "table" && categoryArrangementScope === activeFolder();
}

function saveCategoryPreference(preference) {
  const scope = activeFolder();
  const next = new Map(categoryPreferences);
  next.set(scope, preference);
  try { localStorage.setItem(CATEGORY_LAYOUT_KEY, JSON.stringify(Object.fromEntries(next))); }
  catch (error) {
    setLibraryStatus("无法保存分类排列，请检查浏览器是否允许本地存储。");
    return false;
  }
  categoryPreferences.set(scope, preference);
  return true;
}

function focusCategoryHandle(name) {
  const handle = [...document.querySelectorAll("[data-category-drag]")].find(button => button.dataset.categoryDrag === name);
  handle?.focus({ preventScroll: true });
}

function reorderCategory(source, target, after = false) {
  if (!canArrangeCategories()) return false;
  const order = orderedCategories(categoryOriginalOrder);
  if (source === target || !order.includes(source) || !order.includes(target)) return false;
  const next = order.filter(name => name !== source);
  next.splice(next.indexOf(target) + (after ? 1 : 0), 0, source);
  if (next.every((name, index) => name === order[index])) return false;
  if (!saveCategoryPreference({ ...categoryPreferences.get(activeFolder()), order: next })) return false;
  render();
  focusCategoryHandle(source);
  setLibraryStatus("分类顺序已保存", true);
  return true;
}

function moveCategory(name, step) {
  if (step !== -1 && step !== 1) return false;
  const order = orderedCategories(categoryOriginalOrder);
  const index = order.indexOf(name);
  if (index < 0 || index + step < 0 || index + step >= order.length) return false;
  return reorderCategory(name, order[index + step], step > 0);
}

function resetCategoryOrder() {
  if (!canArrangeCategories()) return false;
  const next = { ...categoryPreferences.get(activeFolder()) };
  delete next.order;
  if (!saveCategoryPreference(next)) return false;
  render();
  document.getElementById("categoryArrangeBtn")?.focus();
  setLibraryStatus("已恢复当前分类的默认顺序", true);
  return true;
}

function handleCategoryArrangementClick(event) {
  const move = event.target.closest("[data-category-move]");
  if (!move) return !!event.target.closest("[data-category-drag]");
  moveCategory(move.dataset.categoryMove, Number(move.dataset.categoryStep));
  return true;
}

// While dragging only the drop marker moves; the dragged block stays dimmed until the drag ends.
function clearCategoryDrop(dragEnded = true) {
  const classes = dragEnded ? ["category-drop-before", "category-drop-after", "category-is-dragging"] : ["category-drop-before", "category-drop-after"];
  for (const block of document.querySelectorAll("[data-category-block]")) block.classList.remove(...classes);
}

function categoryDropTarget(event) {
  const block = event.target.closest("[data-category-block]");
  if (!block || block.dataset.categoryBlock === categoryDragSource) return null;
  const rect = block.getBoundingClientRect();
  return { block, after: categoryArrangementAxis === "horizontal"
    ? event.clientX >= rect.left + rect.width / 2
    : event.clientY >= rect.top + rect.height / 2 };
}

function initCategoryArrangement() {
  const button = document.getElementById("categoryArrangeBtn");
  if (!button) return;
  categoryArrangePanel = document.createElement("div");
  categoryArrangePanel.className = "category-arrange-panel";
  categoryArrangePanel.hidden = true;
  button.parentElement.appendChild(categoryArrangePanel);
  button.addEventListener("click", () => {
    if (state.q.trim() || document.documentElement.dataset.layout === "table" || categoryOriginalOrder.length < 2) return;
    categoryArrangementActive = !categoryArrangementActive;
    render();
  });
  categoryArrangePanel.addEventListener("click", event => {
    if (!canArrangeCategories()) return;
    if (event.target.closest("[data-category-reset]")) { resetCategoryOrder(); return; }
    const width = event.target.closest("[data-category-width]");
    if (!width || !["small", "medium", "large"].includes(width.dataset.categoryWidth)) return;
    const value = width.dataset.categoryWidth;
    if (saveCategoryPreference({ ...categoryPreferences.get(activeFolder()), width: value })) {
      render();
      [...categoryArrangePanel.querySelectorAll("[data-category-width]")].find(option => option.dataset.categoryWidth === value)?.focus();
    }
  });
  const main = document.getElementById("main");
  if (typeof ResizeObserver === "function") new ResizeObserver(updateCategoryArrangementDirection).observe(main);
  main.addEventListener("keydown", event => {
    const handle = event.target.closest("[data-category-drag]");
    const keys = categoryArrangementAxis === "horizontal" ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
    if (!handle || !event.altKey || !keys.includes(event.key)) return;
    event.preventDefault();
    moveCategory(handle.dataset.categoryDrag, event.key === keys[0] ? -1 : 1);
  });
  main.addEventListener("dragstart", event => {
    const handle = event.target.closest("[data-category-drag]");
    if (!handle || !canArrangeCategories()) return;
    categoryDragSource = handle.dataset.categoryDrag;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", categoryDragSource);
    handle.closest("[data-category-block]").classList.add("category-is-dragging");
  });
  main.addEventListener("dragover", event => {
    if (!categoryDragSource || !canArrangeCategories()) return;
    const target = categoryDropTarget(event);
    if (!target) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    clearCategoryDrop(false);
    target.block.classList.add(target.after ? "category-drop-after" : "category-drop-before");
  });
  main.addEventListener("drop", event => {
    if (!categoryDragSource || !canArrangeCategories()) return;
    event.preventDefault();
    const target = categoryDropTarget(event);
    if (target) reorderCategory(categoryDragSource, target.block.dataset.categoryBlock, target.after);
    categoryDragSource = "";
    clearCategoryDrop();
  });
  main.addEventListener("dragend", () => { categoryDragSource = ""; clearCategoryDrop(); });
}
