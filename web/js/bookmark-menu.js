function bookmarkMenuButtonHtml(item) {
  return `<button type="button" class="bookmark-more" data-bookmark-menu="${escapeHtml(item.href)}" data-bookmark-path="${escapeHtml(item.path || "")}" aria-label="更多操作：${escapeHtml(item.title || item.host || "书签")}" aria-haspopup="menu" aria-expanded="false" title="更多操作"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg></button>`;
}

let bookmarkMenuInitialized = false;
function initBookmarkMenu() {
  if (bookmarkMenuInitialized) return;
  bookmarkMenuInitialized = true;
  const menu = document.createElement("div");
  menu.id = "bookmarkContextMenu";
  menu.className = "bookmark-context-menu";
  menu.hidden = true;
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", "书签操作");
  menu.innerHTML = `<button type="button" role="menuitem" data-bookmark-action="open">在新标签页打开</button><button type="button" role="menuitem" data-bookmark-action="copy">复制网址</button><button type="button" role="menuitem" data-bookmark-action="details">查看详情</button><p class="bookmark-menu-status" role="status"></p>`;
  const details = document.createElement("dialog");
  details.id = "bookmarkDetailsDialog";
  details.className = "bookmark-details-dialog";
  details.setAttribute("aria-labelledby", "bookmarkDetailsHeading");
  details.innerHTML = `<div class="bookmark-details-heading"><h2 id="bookmarkDetailsHeading">书签详情</h2><button type="button" data-bookmark-close aria-label="关闭书签详情">×</button></div><dl><dt>完整名称</dt><dd data-bookmark-title></dd><dt>分类</dt><dd data-bookmark-folder></dd></dl><label for="bookmarkDetailsUrl">网址</label><textarea id="bookmarkDetailsUrl" rows="3" readonly spellcheck="false"></textarea><p class="bookmark-menu-status" role="status"></p><div class="bookmark-details-actions"><button type="button" data-bookmark-copy>复制网址</button><button type="button" data-bookmark-close>关闭</button></div>`;
  document.body.append(menu, details);

  const openButton = menu.querySelector('[data-bookmark-action="open"]');
  const menuStatus = menu.querySelector('[role="status"]');
  const detailStatus = details.querySelector('[role="status"]');
  const urlField = details.querySelector("textarea");
  let currentItem = null;
  let returnFocus = null;
  let trigger = null;
  let generation = 0;
  const restoreFocus = () => { if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true }); };

  function closeMenu(restore = true) {
    if (menu.hidden) return;
    generation++;
    menu.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
    if (restore) restoreFocus();
  }
  function bookmarkAt(target) {
    const wrapper = target.closest?.(".bookmark-item");
    const card = wrapper?.querySelector(".card[data-key]");
    if (!card) return null;
    const more = wrapper.querySelector(".bookmark-more");
    const item = ITEMS.find(item => item.href === card.dataset.key && (!more || (item.path || "") === more.dataset.bookmarkPath));
    return item ? { item, card, more } : null;
  }
  function openMenu(bookmark, invoker, x, y) {
    if (details.open) return;
    closeMenu(false);
    generation++;
    currentItem = bookmark.item;
    returnFocus = invoker;
    trigger = bookmark.more;
    trigger?.setAttribute("aria-expanded", "true");
    openButton.disabled = !safeHref(currentItem.href);
    menuStatus.textContent = openButton.disabled ? "此类书签不能在主页中运行。" : "";
    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    const height = document.documentElement.clientHeight;
    menu.style.left = Math.max(8, Math.min(x, width - rect.width - 8)) + "px";
    menu.style.top = Math.max(8, Math.min(y, height - rect.height - 8)) + "px";
    menu.querySelector('button:not(:disabled)').focus({ preventScroll: true });
  }
  function showDetails(message = "", selectUrl = false) {
    closeMenu(false);
    details.querySelector("[data-bookmark-title]").textContent = currentItem.title || currentItem.host || "未命名书签";
    details.querySelector("[data-bookmark-folder]").textContent = currentItem.path || currentItem.group || "未分类";
    urlField.value = currentItem.href;
    detailStatus.textContent = message;
    if (!details.open) details.showModal();
    if (selectUrl) { urlField.focus(); urlField.select(); }
  }
  async function copyUrl(inDetails) {
    const item = currentItem;
    const request = generation;
    const status = inDetails ? detailStatus : menuStatus;
    status.textContent = "正在复制…";
    try {
      await navigator.clipboard.writeText(item.href);
      if (request === generation && item === currentItem) status.textContent = "网址已复制。";
    } catch (error) {
      if (request !== generation || item !== currentItem) return;
      showDetails("无法写入剪贴板，请选择下方网址后手动复制。", true);
    }
  }
  document.addEventListener("contextmenu", event => {
    const bookmark = bookmarkAt(event.target);
    if (!bookmark) return;
    event.preventDefault();
    openMenu(bookmark, bookmark.card.hasAttribute("href") ? bookmark.card : bookmark.more, event.clientX, event.clientY);
  });
  document.addEventListener("click", event => {
    const button = event.target.closest?.(".bookmark-more");
    const bookmark = button && bookmarkAt(button);
    if (!bookmark) return;
    event.preventDefault();
    const rect = button.getBoundingClientRect();
    openMenu(bookmark, button, rect.left, rect.bottom + 4);
  });
  document.addEventListener("pointerdown", event => {
    if (!menu.hidden && !menu.contains(event.target) && !event.target.closest?.(".bookmark-more")) closeMenu(false);
  });
  document.addEventListener("focusin", event => {
    if (!menu.hidden && !menu.contains(event.target) && event.target !== trigger) closeMenu(false);
  });
  document.addEventListener("keydown", event => {
    if (event.isComposing) return;
    if ((event.shiftKey && event.key === "F10") || event.key === "ContextMenu") {
      const bookmark = bookmarkAt(event.target);
      if (!bookmark) return;
      event.preventDefault();
      event.stopPropagation();
      const rect = event.target.getBoundingClientRect();
      openMenu(bookmark, event.target, rect.left, rect.bottom + 4);
    } else if (!menu.hidden) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeMenu();
      } else if (event.key === "Tab") closeMenu();
      else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        event.stopPropagation();
        const buttons = [...menu.querySelectorAll('button:not(:disabled)')];
        let next = buttons.indexOf(document.activeElement);
        if (event.key === "Home") next = 0;
        else if (event.key === "End") next = buttons.length - 1;
        else next = (next + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
        buttons[next].focus();
      }
    }
  }, true);
  menu.addEventListener("click", event => {
    const action = event.target.closest?.("[data-bookmark-action]")?.dataset.bookmarkAction;
    if (action === "open") {
      const href = safeHref(currentItem.href);
      if (href) { window.open(href, "_blank", "noopener,noreferrer"); closeMenu(); }
    } else if (action === "copy") copyUrl(false);
    else if (action === "details") showDetails();
  });
  details.addEventListener("click", event => {
    if (event.target.closest?.("[data-bookmark-close]")) details.close();
    else if (event.target.closest?.("[data-bookmark-copy]")) copyUrl(true);
    else if (event.target === details) {
      const rect = details.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) details.close();
    }
  });
  details.addEventListener("close", () => { generation++; restoreFocus(); });
  window.addEventListener("resize", () => closeMenu(false));
  document.addEventListener("scroll", event => { if (event.target !== menu) closeMenu(false); }, true);
}
