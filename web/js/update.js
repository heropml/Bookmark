const updateNotice = document.getElementById("updateNotice");
const updateBtn = document.getElementById("updateBtn");
const appVersion = document.getElementById("appVersion");

function showUpdateNotice(status) {
  updateBtn.disabled = false;
  updateBtn.dataset.state = "ready";
  updateBtn.setAttribute("aria-label", "发现新版本 " + status.remote + "，点击升级");
  updateBtn.title = "发现新版本 " + status.remote + "，点击升级";
  updateNotice.hidden = false;
}

async function checkForUpdate() {
  try {
    const response = await fetch("/__update", { cache: "no-store" });
    if (!response.ok) return;
    const status = await response.json();
    if (status.version) appVersion.textContent = status.version;
    if (status.available && status.can_update) showUpdateNotice(status);
  } catch (error) {
    // 更新检查不可用时保持静默，不影响书签页面使用。
  }
}

async function installUpdate() {
  if (!window.confirm("将拉取 origin/main 的完整代码库并重启本地服务。存在未提交的本地代码修改时会取消升级。是否继续？")) return;
  updateBtn.disabled = true;
  updateBtn.dataset.state = "loading";
  updateBtn.title = "正在升级…";
  try {
    const response = await fetch("/__update", { method: "POST", cache: "no-store" });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || "升级失败，请稍后重试");
    if (!result.updated) {
      updateNotice.hidden = true;
      return;
    }
    updateBtn.title = "升级完成，正在重启…";
    window.setTimeout(() => window.location.reload(), 1200);
  } catch (error) {
    updateBtn.disabled = false;
    updateBtn.dataset.state = "error";
    updateBtn.setAttribute("aria-label", error.message || "升级失败，点击重试");
    updateBtn.title = error.message || "升级失败，点击重试";
    updateNotice.hidden = false;
  }
}

function initUpdate() {
  updateBtn.addEventListener("click", installUpdate);
  checkForUpdate();
}
