
function initWindowState() {
  let windowSizeTimer = 0;
  function persistWindowSize() {
    const width = Math.round(window.outerWidth);
    const height = Math.round(window.outerHeight);
    if (width < 320 || height < 240) return;
    const maximized =
      Math.abs(width - screen.availWidth) <= 16 &&
      Math.abs(height - screen.availHeight) <= 16 &&
      Math.abs(window.screenX - screen.availLeft) <= 16 &&
      Math.abs(window.screenY - screen.availTop) <= 16;
    fetch("/__window_state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ width, height, maximized }),
      keepalive: true
    }).catch(() => {});
  }
  function saveWindowSize() {
    clearTimeout(windowSizeTimer);
    windowSizeTimer = setTimeout(persistWindowSize, 300);
  }
  window.addEventListener("resize", saveWindowSize);
  window.addEventListener("pagehide", () => {
    clearTimeout(windowSizeTimer);
    persistWindowSize();
  });
}
