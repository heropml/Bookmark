const clockEl = document.getElementById("clock");
clockEl.innerHTML = "--:--:--".split("").map((c, i) => '<span' + (i >= 5 ? ' class="clock-seconds"' : '') + '>' + c + '</span>').join("");
const LUNAR_DAYS = [
  "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
  "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
  "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"
];
// Built once: creating a Chinese-calendar formatter every second costs more than formatting.
const LUNAR_FORMAT = new Intl.DateTimeFormat("zh-CN-u-ca-chinese", { year: "numeric", month: "long", day: "numeric" });
const SOLAR_FORMAT = new Intl.DateTimeFormat("zh-CN", { year: "numeric", weekday: "long", month: "long", day: "numeric" });
let clockDateShown = "";
let clockMinuteShown = "";
function lunarDateText(date) {
  const parts = LUNAR_FORMAT.formatToParts(date);
  const fields = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return fields.yearName + "年" + fields.month + LUNAR_DAYS[Number(fields.day) - 1];
}
function setClock(str) {
  // Keep gradient digits painted normally: retained animations can leave them blank.
  for (let i = 0; i < str.length; i++) {
    const span = clockEl.children[i];
    if (span && span.textContent !== str[i]) span.textContent = str[i];
  }
}
function tick() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  setClock(hh + ":" + mm + ":" + ss);
  // The seconds change every tick; the dates and greeting only when the minute does.
  if (clockMinuteShown !== hh + ":" + mm) {
    clockMinuteShown = hh + ":" + mm;
    document.getElementById("bgTime").textContent = clockMinuteShown;
    const h = now.getHours();
    const greet = h < 5 ? "夜深了" : h < 11 ? "早上好" : h < 14 ? "中午好" : h < 18 ? "下午好" : h < 22 ? "晚上好" : "夜深了";
    const dates = SOLAR_FORMAT.format(now).replace(/星期/, " 星期") + "\n" + lunarDateText(now) + " · " + greet;
    if (dates !== clockDateShown) {
      clockDateShown = dates;
      const [solar, lunar] = dates.split("\n");
      document.getElementById("greet").textContent = solar;
      document.getElementById("lunarDate").textContent = lunar;
    }
  }
  if (weatherScene.dataset.period !== weatherPeriod()) syncParticles();
}

function initClock() {
  tick();
  setInterval(tick, 1000);
  window.addEventListener("focus", () => tick());
  window.addEventListener("blur", () => tick());
  document.addEventListener("visibilitychange", () => tick());
}
