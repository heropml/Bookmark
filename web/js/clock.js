const clockEl = document.getElementById("clock");
clockEl.innerHTML = "--:--".split("").map((c) => "<span>" + c + "</span>").join("");
let clockReady = false;
function rollDigit(span, ch) {
  const out = span.animate(
    [{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(-58%)", opacity: 0 }],
    { duration: 105, easing: "ease-in", fill: "forwards" }
  );
  out.onfinish = () => {
    span.textContent = ch;
    span.animate(
      [{ transform: "translateY(58%)", opacity: 0 }, { transform: "translateY(0)", opacity: 1 }],
      { duration: 170, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)", fill: "forwards" }
    );
  };
}
function setClock(str, roll) {
  const animate = roll && motionOk() && !document.hidden && document.hasFocus();
  for (let i = 0; i < str.length; i++) {
    const span = clockEl.children[i];
    if (!span) continue;
    // A suspended digit animation must not overwrite a newer time on resume.
    for (const animation of span.getAnimations()) {
      animation.onfinish = null;
      animation.cancel();
    }
    if (span.textContent === str[i]) continue;
    if (animate) rollDigit(span, str[i]);
    else span.textContent = str[i];
  }
}
function tick(roll = clockReady) {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  setClock(hh + ":" + mm, roll);
  clockReady = true;
  const dateStr = now.toLocaleDateString("zh-CN", { weekday: "long", month: "long", day: "numeric" });
  document.getElementById("bgTime").textContent = hh + ":" + mm;
  document.getElementById("bgDate").textContent = dateStr;
  const h = now.getHours();
  const greet = h < 5 ? "夜深了" : h < 11 ? "早上好" : h < 14 ? "中午好" : h < 18 ? "下午好" : h < 22 ? "晚上好" : "夜深了";
  document.getElementById("greet").textContent = dateStr + " · " + greet;
  if (weatherScene.dataset.period !== weatherPeriod()) syncParticles();
}

function initClock() {
  tick();
  setInterval(tick, 10000);
  window.addEventListener("focus", () => tick(false));
  window.addEventListener("blur", () => tick(false));
  document.addEventListener("visibilitychange", () => tick(false));
}
