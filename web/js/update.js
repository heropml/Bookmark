const updateNotice = document.getElementById("updateNotice");
const updateBtn = document.getElementById("updateBtn");
const updateProgress = document.getElementById("updateProgress");
const UPDATE_STAGES = ["checking", "fetching", "applying", "restarting"];
const UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000;
let updateChecking = false;
let updateInstalling = false;
let updateGeneration = 0;
let updateMode = "git";

function showUpdateProgress(stage, message, source = "") {
  const finished = stage === "done" || stage === "current" || stage === "error";
  if (!UPDATE_STAGES.includes(stage) && stage !== "waiting" && !finished) return;
  updateProgress.hidden = false;
  updateProgress.dataset.stage = stage;
  document.getElementById("updateProgressTitle").textContent = stage === "error" ? "升级未完成" : stage === "current" ? "已是最新版本" : stage === "done" ? "升级完成" : "正在升级书签";
  document.getElementById("updateProgressMessage").textContent = message;
  if (source) document.getElementById("updateProgressSource").textContent = "更新源 · " + source;
  else if (stage === "waiting") document.getElementById("updateProgressSource").textContent = "本地服务";
  document.getElementById("updateProgressClose").hidden = !finished;
  document.getElementById("updateProgressHint").textContent = stage === "error"
    ? "可关闭此提示，查看左下角更新状态后重试。"
    : finished ? "书签数据已保留。" : "升级过程中仍可浏览书签，请勿退出本地服务。";
  if (stage !== "error") {
    const current = stage === "waiting" ? 0 : stage === "done" ? 4 : stage === "current" ? 2 : UPDATE_STAGES.indexOf(stage);
    Array.from(document.getElementById("updateProgressSteps").children).forEach((step, index) => {
      step.dataset.state = index < current ? "done" : index === current && !finished ? "active" : "pending";
      if (index === current && !finished) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");
    });
  }
}

async function readUpdateResult(response) {
  // A page updated before its backend can still receive the legacy JSON reply.
  if (!response.headers?.get("Content-Type")?.includes("application/x-ndjson")) return response.json();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", result;
  const accept = line => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "progress") showUpdateProgress(event.stage, event.message, event.source);
    else if (event.type === "error") throw new Error(event.message || "升级失败");
    else if (event.type === "result") result = event;
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        accept(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (done) break;
    }
    accept(buffer);
  } finally {
    reader.releaseLock();
  }
  if (!result) throw new Error("升级连接中断，未收到完成结果，请稍后检查更新状态");
  return result;
}

async function waitForRestart(instance) {
  for (let attempt = 0; attempt < 20; attempt++) {
    await new Promise(resolve => window.setTimeout(resolve, 500));
    try {
      const service = await fetchJson("/__service", 1000);
      if (service.instance && service.instance !== instance) {
        showUpdateProgress("done", "新服务已就绪，正在刷新页面");
        window.location.reload();
        return;
      }
    } catch (error) {
      // The old listener is closed while its replacement starts.
    }
  }
  throw new Error("后台重启未完成，请稍后刷新页面");
}

function showUpdateNotice(status) {
  updateMode = status.mode || "git";
  updateBtn.disabled = false;
  updateBtn.dataset.state = "ready";
  updateBtn.dataset.action = "install";
  updateBtn.title = "发现新版本 " + status.remote + (status.source ? "（" + status.source + "）" : "") + "，点击升级";
  updateBtn.setAttribute("aria-label", updateBtn.title);
  updateNotice.hidden = false;
}

async function checkForUpdate() {
  if (updateChecking || updateInstalling) return;
  updateChecking = true;
  const generation = updateGeneration;
  try {
    const response = await fetch("/__update", { cache: "no-store" });
    const status = await response.json();
    // A check started before an installation must not overwrite its UI later.
    if (generation !== updateGeneration) return;
    if (!response.ok) {
      if (status.error === "certificate_error" || status.error === "tls_backend") {
        updateBtn.disabled = false;
        updateBtn.dataset.state = "error";
        updateBtn.dataset.action = "check";
        updateBtn.title = (status.reason || "更新源证书验证失败") + "；点击重新检查";
        updateBtn.setAttribute("aria-label", updateBtn.title);
        updateNotice.hidden = false;
      }
      return;
    }
    if (status.restarting) {
      updateNotice.hidden = false;
      updateBtn.disabled = true;
      updateBtn.dataset.state = "loading";
      updateBtn.title = "后台已更新，正在自动重启…";
      updateBtn.setAttribute("aria-label", updateBtn.title);
      showUpdateProgress("restarting", "后台已更新，等待新服务接管");
      try {
        await waitForRestart(status.instance);
      } catch (error) {
        updateBtn.title = error.message;
        updateBtn.setAttribute("aria-label", error.message);
        showUpdateProgress("error", error.message);
      }
      return;
    }
    if (status.available && status.can_update) showUpdateNotice(status);
    else updateNotice.hidden = true;
  } catch (error) {
    // 更新检查不可用时保持静默，不影响书签页面使用。
  } finally {
    updateChecking = false;
  }
}

async function installUpdate() {
  if (updateInstalling) return;
  const confirmation = updateMode === "archive"
    ? "将下载并校验新版程序文件，备份后替换并重启本地服务。优先使用 Gitee，不可用时切换 GitHub，无需安装 Git。私人书签和外观设置会保留；自行修改的程序文件会被替换并备份。是否继续？"
    : "将更新 main 分支的完整代码库并重启本地服务：优先使用 Gitee，不可用时切换 GitHub。存在未提交的本地代码修改时会取消升级。是否继续？";
  if (!window.confirm(confirmation)) return;
  updateInstalling = true;
  updateGeneration++;
  updateBtn.disabled = true;
  updateBtn.dataset.state = "loading";
  updateBtn.title = "正在升级…";
  showUpdateProgress("waiting", "正在请求升级，请稍候");
  try {
    const response = await fetch("/__update", { method: "POST", cache: "no-store", headers: { Accept: "application/x-ndjson" } });
    const result = await readUpdateResult(response);
    if (!response.ok || !result.ok) throw new Error(result.message || "升级失败，请稍后重试");
    if (!result.updated) {
      updateNotice.hidden = true;
      showUpdateProgress("current", "当前已是最新代码，无需应用更新或重启", result.source);
      return;
    }
    updateBtn.title = "升级完成，正在重启…";
    showUpdateProgress("restarting", "代码已更新，等待后台重启", result.source);
    await waitForRestart(result.instance);
  } catch (error) {
    updateBtn.disabled = false;
    updateBtn.dataset.state = "error";
    updateBtn.setAttribute("aria-label", error.message || "升级失败，点击重试");
    updateBtn.title = error.message || "升级失败，点击重试";
    updateNotice.hidden = false;
    showUpdateProgress("error", error.message || "升级失败，请稍后重试");
  } finally {
    updateInstalling = false;
  }
}

function initUpdate() {
  document.getElementById("updateProgressClose").addEventListener("click", () => { updateProgress.hidden = true; });
  updateBtn.addEventListener("click", () => updateBtn.dataset.action === "check" ? checkForUpdate() : installUpdate());
  checkForUpdate();
  window.setInterval(checkForUpdate, UPDATE_CHECK_INTERVAL_MS);
}
