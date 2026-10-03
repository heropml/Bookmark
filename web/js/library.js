function initLibrary() {
  const search = document.getElementById("q");
  for (const [id, local] of [["searchAll", false], ["searchLocal", true]]) {
    document.getElementById(id).addEventListener("click", () => {
      state.searchLocal = local;
      state.shown = PAGE;
      render();
      search.focus();
    });
  }
  const pins = document.getElementById("pinnedGrid");
  initPinnedSort(pins);
  pins.addEventListener("click", pickFolder);
  pins.addEventListener("error", (event) => {
    const img = event.target;
    if (img.tagName !== "IMG" || !img.dataset.fallback) return;
    if (img.dataset.fb) img.remove();
    else { img.dataset.fb = "1"; img.src = img.dataset.fallback; }
  }, true);
  document.addEventListener("keydown", (event) => {
    // Enter and Esc also pick or cancel IME candidates; they must not open or clear results.
    if (event.isComposing || event.keyCode === 229) return;
    // Every key press arrives here; only these keys need the dialog check and the card list.
    if (!["Escape", "Enter", "ArrowDown", "ArrowUp"].includes(event.key)) return;
    if (document.querySelector("dialog[open]") || !appearanceMenu.hidden) return;
    const input = event.target === search;
    const links = [...document.querySelectorAll('#main a.card[href]')];
    const current = links.indexOf(event.target);
    if (input && event.key === "Escape") {
      search.value = "";
      search.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (input && event.key === "Enter" && state.q.trim()) {
      // Render synchronously so Enter immediately after typing never opens a stale result.
      render();
      document.querySelector('#main a.card[href]')?.click();
      event.preventDefault();
    } else if ((input || current >= 0) && ["ArrowDown", "ArrowUp"].includes(event.key) && links.length) {
      event.preventDefault();
      const next = input ? (event.key === "ArrowDown" ? 0 : links.length - 1) : current + (event.key === "ArrowDown" ? 1 : -1);
      if (next < 0) search.focus();
      else links[Math.min(next, links.length - 1)].focus();
    }
  });
  const focus = document.getElementById("focusPreset");
  const applyFocus = () => {
    const on = document.documentElement.dataset.focus === "on";
    focus.setAttribute("aria-pressed", String(on));
    focus.querySelector("span").textContent = on ? "退出专注" : "专注";
  };
  applyFocus();
  focus.addEventListener("click", () => {
    const next = document.documentElement.dataset.focus === "on" ? "off" : "on";
    document.documentElement.dataset.focus = next;
    try { localStorage.setItem("bm-focus", next); } catch (e) {}
    applyFocus();
    window.dispatchEvent(new Event("bm-fx"));
  });
  initBookmarkBackups();
}

function initPinnedSort(pins) {
  let dragged = null;
  let destination = null;
  let after = false;
  const clearMarker = () => {
    destination?.classList.remove("drop-before", "drop-after");
    destination = null;
  };
  const finish = () => {
    clearMarker();
    dragged?.classList.remove("is-dragging");
    dragged = null;
  };
  pins.addEventListener("dragstart", event => {
    const card = event.target.closest("[data-pinned-url]");
    if (!card || event.target.closest("[data-pin]")) { event.preventDefault(); return; }
    dragged = card;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.dataset.pinnedUrl);
    event.dataTransfer.setDragImage(card, card.offsetWidth / 2, card.offsetHeight / 2);
    card.classList.add("is-dragging");
  });
  pins.addEventListener("dragover", event => {
    // External links and bookmarks outside the pinned shelf must not change its order.
    if (!dragged) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const card = event.target.closest("[data-pinned-url]");
    clearMarker();
    if (!card || card === dragged) return;
    const rect = card.getBoundingClientRect();
    after = event.clientX >= rect.left + rect.width / 2;
    destination = card;
    card.classList.add(after ? "drop-after" : "drop-before");
  });
  pins.addEventListener("dragleave", event => {
    if (!pins.contains(event.relatedTarget)) clearMarker();
  });
  pins.addEventListener("drop", event => {
    if (!dragged) return;
    event.preventDefault();
    const source = dragged.dataset.pinnedUrl;
    const target = destination?.dataset.pinnedUrl;
    const insertAfter = after;
    finish();
    if (target) reorderPinnedBookmark(source, target, insertAfter);
  });
  pins.addEventListener("dragend", finish);
  // Keyboard users move the focused pin one place with Alt+←/→; elsewhere Alt+← stays browser Back.
  pins.addEventListener("keydown", event => {
    const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    const item = event.target.closest("[data-pinned-url]");
    if (!step || !item || !event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    const items = [...pins.querySelectorAll("[data-pinned-url]")];
    const neighbour = items[items.indexOf(item) + step];
    if (!neighbour) return;
    const url = item.dataset.pinnedUrl;
    const control = event.target.closest("[data-pin]") ? "[data-pin]" : "a.card";
    if (!reorderPinnedBookmark(url, neighbour.dataset.pinnedUrl, step > 0)) return;
    const moved = [...pins.querySelectorAll("[data-pinned-url]")].find(node => node.dataset.pinnedUrl === url);
    moved?.querySelector(control)?.focus();
  });
}

function initBookmarkBackups() {
  const dialog = document.getElementById("backupDialog");
  const list = document.getElementById("backupList");
  const status = document.getElementById("backupStatus");
  const panel = document.getElementById("backupConfirmPanel");
  const confirm = document.getElementById("backupRestore");
  const close = document.getElementById("backupClose");
  const cancel = document.getElementById("backupCancel");
  let selected = null;
  let busy = false;
  let backups = [];
  document.getElementById("bookmarkBackups").addEventListener("click", async () => {
    if (document.getElementById("bookmarkSyncConfirm").disabled && document.getElementById("bookmarkSyncCancel").disabled) return;
    document.getElementById("bookmarkSyncDialog").close();
    panel.hidden = true;
    selected = null;
    list.replaceChildren();
    status.textContent = "正在读取本地备份…";
    dialog.showModal();
    try {
      const response = await fetch("/__bookmarks/backups", { cache: "no-store" });
      if (!response.ok) throw new Error("无法读取备份，请确认使用新版后台服务打开主页。");
      const result = await response.json();
      backups = result.backups;
      status.textContent = backups.length ? `共 ${backups.length} 份备份 · 最新的排在前面` : "还没有备份。下次导入书签时，会先保存当前版本。";
      list.innerHTML = backups.map(backup => `<div class="backup-row"><div><strong>${escapeHtml(new Date(backup.created * 1000).toLocaleString("zh-CN", { hour12: false }))}</strong><span>${backup.count} 个书签</span></div><button type="button" class="library-button" data-backup="${escapeHtml(backup.id)}">恢复此版本</button></div>`).join("");
    } catch (error) { status.textContent = error.message || "备份读取失败，请关闭后重试。"; }
  });
  close.addEventListener("click", () => { if (!busy) dialog.close(); });
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  cancel.addEventListener("click", () => {
    panel.hidden = true;
    const button = [...list.querySelectorAll("[data-backup]")].find(item => item.dataset.backup === selected?.id);
    button?.focus();
    selected = null;
  });
  list.addEventListener("click", event => {
    if (busy) return;
    const button = event.target.closest("[data-backup]");
    if (!button) return;
    selected = backups.find(backup => backup.id === button.dataset.backup);
    if (!selected) return;
    document.getElementById("backupConfirmText").textContent = `恢复到 ${new Date(selected.created * 1000).toLocaleString("zh-CN", { hour12: false })} 的 ${selected.count} 个书签？当前书签会先保存为新备份。`;
    panel.hidden = false;
    cancel.focus();
  });
  confirm.addEventListener("click", async () => {
    if (!selected || busy) return;
    busy = true;
    close.disabled = cancel.disabled = confirm.disabled = true;
    for (const button of list.querySelectorAll("button")) button.disabled = true;
    status.textContent = "正在备份当前书签并恢复所选版本…";
    try {
      const response = await fetch("/__bookmarks/restore", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Bookmark-Sync": "1" },
        body: JSON.stringify({ id: selected.id, confirmed: true })
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.message || "恢复失败，请检查目录写入权限。");
      status.textContent = `已恢复 ${result.count} 个书签，正在刷新主页。`;
      location.reload();
    } catch (error) {
      status.textContent = error.message || "恢复结果未确认，请刷新后检查书签。";
      busy = false;
      close.disabled = cancel.disabled = confirm.disabled = false;
      for (const button of list.querySelectorAll("button")) button.disabled = false;
    }
  });
}
