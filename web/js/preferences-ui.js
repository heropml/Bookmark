function initPreferences() {
  const dialog = document.getElementById("preferencesDialog");
  const status = document.getElementById("preferencesStatus");
  const notice = document.getElementById("preferencesNotice");
  const list = document.getElementById("preferencesBackups");
  const draftList = document.getElementById("preferencesDrafts");
  const panel = document.getElementById("preferencesConfirmPanel");
  const confirm = document.getElementById("preferencesConfirm");
  const file = document.getElementById("preferencesFile");
  let selection = null;
  let busy = false;
  let generation = 0;
  let fileRead = 0;
  const showStatus = () => {
    const state = bookmarkPreferences.status();
    document.getElementById("preferencesDescription").textContent = state.local
      ? "本地服务会自动保存配置。浏览器数据清理后，重新打开即可恢复；导入或恢复前会备份当前配置。普通书签请在“同步书签”中备份。"
      : "当前配置保存在浏览器中，清理浏览器数据前请先导出留存。使用项目自带后台可启用本机保存与历史恢复。";
    notice.textContent = state.error || state.pending ? state.message
      : bookmarkPreferences.drafts().length ? "检测到未保存副本，可在“配置备份”中导出留存。" : "";
    notice.dataset.state = state.error ? "error" : "";
    if (!busy) status.textContent = state.message || (state.local
      ? "配置会保存在本机，修改前自动保留历史版本（连续修改每 5 分钟最多一份，共保留最近 20 份）。"
      : "当前为静态页面，配置仅保存在浏览器中；可导出留存。");
    file.disabled = !state.local || state.blocked || busy;
  };
  window.addEventListener("bookmark-preferences-status", showStatus);
  showStatus();
  function exportConfiguration(id) {
    try {
      const data = JSON.stringify(bookmarkPreferences.exportDocument(id), null, 2);
      const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `bookmark-preferences${id ? "-unsaved" : ""}-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { status.textContent = "配置导出失败：" + error.message; }
  }
  function showDrafts() {
    draftList.replaceChildren();
    for (const draft of bookmarkPreferences.drafts()) {
      const row = document.createElement("div");
      row.className = "backup-row";
      const text = document.createElement("span");
      text.textContent = "未保存副本 · " + new Date(draft.created).toLocaleString("zh-CN", { hour12: false });
      const button = document.createElement("button");
      button.type = "button";
      button.className = "library-button";
      button.textContent = "导出副本";
      button.addEventListener("click", () => exportConfiguration(draft.id));
      row.append(text, button);
      draftList.append(row);
    }
  }
  document.getElementById("preferencesOpen").addEventListener("click", async () => {
    const current = ++generation;
    ++fileRead;
    panel.hidden = true;
    selection = null;
    list.replaceChildren();
    showStatus();
    showDrafts();
    dialog.showModal();
    if (!bookmarkPreferences.status().local) return;
    try {
      if (!await bookmarkPreferences.flush() || current !== generation || !dialog.open) return;
      showDrafts();
      const response = await fetch("/__preferences/backups", { cache: "no-store" });
      if (!response.ok) throw new Error("无法读取配置备份。");
      const result = await response.json();
      if (current !== generation || !dialog.open) return;
      for (const backup of result.backups) {
        const row = document.createElement("div");
        row.className = "backup-row";
        const text = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = new Date(backup.created * 1000).toLocaleString("zh-CN", { hour12: false });
        const count = document.createElement("span");
        count.textContent = backup.error || `${backup.pins} 个置顶`;
        text.append(title, count);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "library-button";
        button.textContent = "恢复";
        button.disabled = Boolean(backup.error);
        button.addEventListener("click", () => {
          if (busy) return;
          selection = { id: backup.id };
          document.getElementById("preferencesConfirmText").textContent =
            `恢复 ${title.textContent} 的配置（${backup.pins} 个置顶）？当前配置会先备份。`;
          panel.hidden = false;
        });
        row.append(text, button);
        list.append(row);
      }
      if (!result.backups.length) list.textContent = "暂无历史版本。修改已保存的配置后会自动生成备份。";
    } catch (error) { if (current === generation && dialog.open) status.textContent = error.message; }
  });
  document.getElementById("preferencesExport").addEventListener("click", () => {
    exportConfiguration();
  });
  file.addEventListener("change", async () => {
    const current = ++fileRead;
    const selected = file.files[0];
    file.value = "";
    selection = null;
    panel.hidden = true;
    if (!selected) return;
    try {
      if (selected.size > 512 * 1024 + 4096) throw new Error("配置文件过大。");
      const document = JSON.parse(await selected.text());
      if (current !== fileRead || !dialog.open) return;
      if (!document || document.format !== 1 || !document.values || typeof document.values !== "object"
          || Array.isArray(document.values)) throw new Error("配置文件格式无效。");
      const pins = JSON.parse(document.values["bm-pins"] || "[]");
      if (!Array.isArray(pins)) throw new Error("置顶列表无效。");
      selection = { document };
      window.document.getElementById("preferencesConfirmText").textContent =
        `导入「${selected.name}」（${pins.length} 个置顶）？将替换当前置顶与外观，并先备份当前配置。`;
      panel.hidden = false;
    } catch (error) { if (current === fileRead && dialog.open) status.textContent = error.message; }
  });
  confirm.addEventListener("click", async () => {
    if (busy || !selection) return;
    busy = true;
    confirm.disabled = true;
    file.disabled = true;
    status.textContent = "正在备份并恢复配置…";
    try {
      if (selection.id) await bookmarkPreferences.restore(selection.id);
      else await bookmarkPreferences.importDocument(selection.document);
      location.reload();
    } catch (error) {
      status.textContent = error.message;
      busy = false;
      confirm.disabled = false;
      file.disabled = bookmarkPreferences.status().blocked;
    }
  });
  document.getElementById("preferencesCancel").addEventListener("click", () => {
    if (!busy) { panel.hidden = true; selection = null; }
  });
  document.getElementById("preferencesClose").addEventListener("click", () => {
    if (!busy) dialog.close();
  });
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  dialog.addEventListener("close", () => { ++generation; ++fileRead; });
}
