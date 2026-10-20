// Loaded before bootstrap. The local service embeds its snapshot in index.html; static
// hosting keeps using browser storage. No missing/failed read is ever sent as a reset.
const bookmarkPreferences = (() => {
  const keys = [
    "bm-pins", "bm-skin", "bm-icon", "bm-layout", "bm-motion", "bm-fx", "bm-trail", "bm-sky",
    "bm-focus", "bm-card-density", "bm-trail-size", "bm-sky-size", "bm-sky-count",
    "bm-appearance-presets", "bm-category-layout", "bm-city"
  ];
  // The current category (bm-folder) stays per browser: switching it in one tab must not
  // conflict with other open tabs or turn every click into a disk snapshot.
  const snapshot = window.BOOKMARK_PREFERENCES;
  const local = location.protocol === "http:" && ["127.0.0.1", "localhost"].includes(location.hostname)
    && Boolean(snapshot);
  let migrating = local && snapshot.exists === false;
  const rejected = new Set();
  let values = {};
  // Fields as this page last knew them on disk. Only fields changed here (dirty) are sent, with
  // their base, so other tabs' edits to other fields merge instead of conflicting.
  let base = {};
  const dirty = new Set();
  let pending = false;
  let inFlight = null;
  let replacing = false;
  let timer = 0;
  let blocked = local && Boolean(snapshot.error);
  let message = blocked ? snapshot.error : "";
  let error = blocked;
  const draftPrefix = "bm-preferences-draft:" + (snapshot?.installation || location.hostname) + ":";
  const draftKey = draftPrefix + Date.now() + "-" + Math.random().toString(16).slice(2);
  function drafts() {
    const result = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const id = localStorage.key(i);
        if (!id?.startsWith(draftPrefix)) continue;
        try {
          const draft = JSON.parse(localStorage.getItem(id));
          if (draft?.format === 1 && draft.values && !Array.isArray(draft.values)
              && typeof draft.values === "object") result.push({ ...draft, id });
        } catch (e) {}
      }
    } catch (e) {}
    return result.sort((a, b) => (Number(b.created) || 0) - (Number(a.created) || 0));
  }
  function keepDraft() {
    try {
      localStorage.setItem(draftKey, JSON.stringify({ format: 1, created: Date.now(), values }));
    } catch (e) {}
  }
  function removeDraft(id) {
    try { localStorage.removeItem(id); } catch (e) {}
  }
  const announce = (text, failed = false) => {
    message = text;
    error = failed;
    window.dispatchEvent(new Event("bookmark-preferences-status"));
  };
  if (local && snapshot.exists) {
    values = { ...snapshot.values };
    base = { ...snapshot.values };
    // A blocked/cleared browser cache cannot prevent using the authoritative disk snapshot.
    for (const key of keys) {
      try {
        if (key in values) localStorage.setItem(key, values[key]);
        else localStorage.removeItem(key);
      } catch (e) {}
    }
  } else {
    try {
      for (const key of keys) {
        const value = localStorage.getItem(key);
        if (value !== null) values[key] = value;
      }
      for (const key in values) dirty.add(key);
      pending = local && !blocked && dirty.size > 0;
    } catch (e) {
      // A partial browser read must not become the first authoritative snapshot.
      blocked = local;
      message = "无法完整读取浏览器配置，未迁移到本机。请检查浏览器存储权限。";
      error = true;
    }
  }

  async function request(url, body) {
    const response = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), keepalive: false,
      signal: AbortSignal.timeout(10000)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "配置保存失败，请刷新后检查本地配置。");
    return result;
  }

  async function flush() {
    clearTimeout(timer);
    if (inFlight) {
      await inFlight;
      return flush();
    }
    if (blocked) return false;
    if (!local || !pending) return true;
    const changes = {};
    const sent = {};
    for (const key of dirty) {
      if ((values[key] ?? null) === (base[key] ?? null)) continue;
      changes[key] = values[key] ?? null;
      sent[key] = base[key] ?? null;
    }
    dirty.clear();
    pending = false;
    if (!Object.keys(changes).length) {
      if (!rejected.size) removeDraft(draftKey);
      if (!rejected.size) announce("");
      return true;
    }
    announce("正在保存配置到本机…");
    const migration = migrating;
    inFlight = request("/__preferences", { changes, base: sent, ...(migration ? { migration: true } : {}) }).then(result => {
      migrating = false;
      const skipped = new Set(result.rejected || []);
      for (const [key, value] of Object.entries(changes)) {
        if (skipped.has(key)) {
          rejected.add(key);
          continue;
        }
        rejected.delete(key);
        if (value === null) delete base[key];
        else base[key] = value;
      }
      if (!pending && !rejected.size) removeDraft(draftKey);
      announce(rejected.size
        ? `有 ${rejected.size} 项旧配置无效，未迁移；其余配置已保存。请先导出当前配置留存，再调整无效选项。`
        : pending ? "配置尚未保存…" : "置顶与外观已保存到本机。", rejected.size > 0);
    }).catch(failure => {
      // A lost response might already have committed. Do not retry against an unknown state.
      for (const key in changes) dirty.add(key);
      pending = true;
      blocked = true;
      const retained = drafts().some(draft => draft.id === draftKey);
      announce((failure.message || "配置未保存到本机。") + (retained
        ? " 可先导出当前配置，刷新后也可在“配置备份”查找未保存副本。"
        : " 请先导出当前配置再关闭页面，浏览器无法保留未保存副本。"), true);
    }).finally(() => {
      inFlight = null;
      window.dispatchEvent(new Event("bookmark-preferences-status"));
    });
    await inFlight;
    if (blocked) return false;
    return pending ? flush() : true;
  }

  function change(key, value) {
    if (!keys.includes(key) || !local) {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
      return;
    }
    if (blocked || replacing) throw new Error(replacing ? "正在恢复配置，请稍后再修改。" : message);
    if ((values[key] ?? null) === value) return;
    // Disk persistence does not depend on localStorage being writable.
    if (value === null) delete values[key];
    else values[key] = value;
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) {}
    dirty.add(key);
    pending = true;
    keepDraft();
    announce("配置尚未保存…");
    clearTimeout(timer);
    timer = setTimeout(flush, 200);
  }
  const storage = {
    getItem(key) {
      if (local && keys.includes(key)) return values[key] ?? null;
      return localStorage.getItem(key);
    },
    setItem(key, value) { change(key, String(value)); },
    removeItem(key) { change(key, null); }
  };
  window.addEventListener("beforeunload", event => {
    if (local && (pending || inFlight || replacing)) {
      void flush();
      event.preventDefault();
      event.returnValue = "";
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") void flush();
  });
  if (pending) {
    keepDraft();
    timer = setTimeout(flush, 0);
  }
  async function replace(url, data) {
    if (replacing) throw new Error("正在恢复配置，请稍候。");
    replacing = true;
    try {
      if (!local || !await flush()) throw new Error(message || "请从本地服务恢复配置。");
      const result = await request(url, data);
      values = { ...result.values };
      base = { ...result.values };
      rejected.clear();
      migrating = false;
      dirty.clear();
      for (const draft of drafts()) {
        if (JSON.stringify(draft.values) === JSON.stringify(values)) removeDraft(draft.id);
      }
    } finally {
      replacing = false;
    }
  }
  return {
    storage, flush, drafts,
    status: () => ({ message, error, local, blocked, pending: pending || Boolean(inFlight) || replacing }),
    exportDocument(id) {
      if (id) {
        const draft = drafts().find(item => item.id === id);
        if (!draft) throw new Error("未保存副本已不存在。");
        return { format: 1, values: draft.values };
      }
      const exported = local ? { ...values } : Object.fromEntries(
        keys.map(key => [key, localStorage.getItem(key)]).filter(([, value]) => value !== null)
      );
      return { format: 1, values: exported };
    },
    async restore(id) {
      await replace("/__preferences/restore", { id });
    },
    async importDocument(document) {
      if (!document || document.format !== 1 || !document.values || Array.isArray(document.values)
          || typeof document.values !== "object") throw new Error("请选择有效的配置导出文件。");
      await replace("/__preferences", { values: document.values });
    }
  };
})();
const bookmarkStorage = bookmarkPreferences.storage;
