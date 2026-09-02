const clockEl = document.getElementById("clock");
clockEl.innerHTML = "--:--:--".split("").map((c, i) => '<span' + (i >= 5 ? ' class="clock-seconds"' : '') + '>' + c + '</span>').join("");
const LUNAR_DAYS = [
  "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
  "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
  "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"
];
function lunarDateText(date) {
  const parts = new Intl.DateTimeFormat("zh-CN-u-ca-chinese", {
    year: "numeric", month: "long", day: "numeric"
  }).formatToParts(date);
  const fields = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return fields.yearName + "年" + fields.month + LUNAR_DAYS[Number(fields.day) - 1];
}
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
  const ss = String(now.getSeconds()).padStart(2, "0");
  setClock(hh + ":" + mm + ":" + ss, roll);
  clockReady = true;
  const dateStr = now.toLocaleDateString("zh-CN", { year: "numeric", weekday: "long", month: "long", day: "numeric" });
  document.getElementById("bgTime").textContent = hh + ":" + mm;
  const h = now.getHours();
  const greet = h < 5 ? "夜深了" : h < 11 ? "早上好" : h < 14 ? "中午好" : h < 18 ? "下午好" : h < 22 ? "晚上好" : "夜深了";
  document.getElementById("greet").textContent = dateStr.replace(/星期/, " 星期");
  document.getElementById("lunarDate").textContent = lunarDateText(now) + " · " + greet;
  if (weatherScene.dataset.period !== weatherPeriod()) syncParticles();
}

function initClock() {
  tick();
  setInterval(tick, 1000);
  window.addEventListener("focus", () => tick(false));
  window.addEventListener("blur", () => tick(false));
  document.addEventListener("visibilitychange", () => tick(false));
}
