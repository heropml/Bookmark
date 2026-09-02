const WMO = {
  0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
  45: "雾", 48: "雾凇",
  51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
  56: "冻毛毛雨", 57: "冻毛毛雨",
  61: "小雨", 63: "中雨", 65: "大雨",
  66: "冻雨", 67: "冻雨",
  71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
  80: "小阵雨", 81: "阵雨", 82: "强阵雨",
  85: "小阵雪", 86: "阵雪",
  95: "雷雨", 96: "雷雨冰雹", 99: "强雷雨冰雹"
};

async function locateCity() {
  const saved = readJson("bm-city");
  if (saved && Number.isFinite(saved.lat) && Number.isFinite(saved.lon)) return saved;
  if (saved && typeof saved.name === "string" && saved.name.trim()) return saved;
  try {
    const city = await Promise.any([
      fetchJson("https://get.geojs.io/v1/ip/geo.json", 4000).then((ip) => {
        if (ip.latitude == null || ip.longitude == null) throw new Error("geojs");
        return { name: ip.city || ip.region || ip.country || "未知", lat: +ip.latitude, lon: +ip.longitude };
      }),
      fetchJson("https://ipwho.is/", 4000).then((ip) => {
        if (!ip.success || ip.latitude == null || ip.longitude == null) throw new Error("ipwho");
        return { name: ip.city || ip.region || "未知", lat: ip.latitude, lon: ip.longitude };
      })
    ]);
    // 定位期间可能已经手动选了城市，用户的选择优先。
    const selected = readJson("bm-city");
    if (selected && typeof selected.name === "string" && selected.name.trim()) return selected;
    writeJson("bm-city", city);
    return city;
  } catch (e) {
    return { name: "北京", lat: 39.9, lon: 116.4 };
  }
}
async function searchCity(name) {
  const encoded = encodeURIComponent(name);
  const geo = fetch(
    "https://geocoding-api.open-meteo.com/v1/search?name=" + encoded + "&count=1&language=zh"
  ).then((response) => {
    if (!response.ok) throw new Error("city HTTP " + response.status);
    return response.json();
  }).then((data) => {
    const hit = data.results && data.results[0];
    if (!hit) throw new Error("city not found");
    return { name: hit.name, lat: hit.latitude, lon: hit.longitude };
  });
  // 备用天气源可校验城市名；没有经纬度时会直接使用该天气源刷新。
  const fallback = fetchJson(localWeatherUrl({ name }), WEATHER_FALLBACK_TIMEOUT_MS)
    .then(() => ({ name }));
  return Promise.any([geo, fallback]);
}
const W_ICONS = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5V5M12 19v2.5M2.5 12H5M19 12h2.5M4.8 4.8l1.7 1.7M17.5 17.5l1.7 1.7M19.2 4.8l-1.7 1.7M6.5 17.5l-1.7 1.7"/>',
  moon: '<path d="M20.2 13.6A8.2 8.2 0 0 1 10.4 3.8a8.2 8.2 0 1 0 9.8 9.8Z"/>',
  cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
  cloudsun: '<circle cx="6.5" cy="6" r="2.4"/><path d="M6.5 1.6v1.3M1.7 6h1.3M3.1 2.6l.9.9"/><path d="M17.5 20H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
  cloudmoon: '<path d="M7.4 6.4A3.4 3.4 0 0 1 3 2a3.4 3.4 0 1 0 4.4 4.4Z"/><path d="M17.5 20H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
  rain: '<path d="M4 14.9A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.24"/><path d="M16 14v5M8 14v5M12 16v5"/>',
  snow: '<path d="M4 14.9A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.24"/><path d="M8 15h.01M8 19h.01M12 17h.01M12 21h.01M16 15h.01M16 19h.01"/>',
  bolt: '<path d="M6 16.3A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.97"/><path d="m13 12-3 5h4l-3 5"/>',
  fog: '<path d="M17.5 16H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/><path d="M5 20h14M8 23h8"/>',
  pin: '<path d="M12 21s-6.5-5.4-6.5-10.2a6.5 6.5 0 1 1 13 0C18.5 15.6 12 21 12 21Z"/><circle cx="12" cy="10.5" r="2.3"/>'
};
function weatherIcon(code) {
  const h = new Date().getHours();
  const night = h >= 19 || h < 6;
  let k = "pin";
  if (code != null) {
    if (code === 0) k = night ? "moon" : "sun";
    else if (code === 1 || code === 2) k = night ? "cloudmoon" : "cloudsun";
    else if (code === 3) k = "cloud";
    else if (code === 45 || code === 48) k = "fog";
    else if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) k = "rain";
    else if ((code >= 71 && code <= 77) || code === 85 || code === 86) k = "snow";
    else if (code >= 95) k = "bolt";
  }
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + W_ICONS[k] + "</svg>";
}
function setWeatherUI(text, code) {
  document.getElementById("weatherIco").innerHTML = weatherIcon(code);
  document.getElementById("weatherTxt").textContent = text;
}
const WEATHER_REFRESH_MS = 10 * 60 * 1000;
const WEATHER_PRIMARY_TIMEOUT_MS = 4000;
const WEATHER_FALLBACK_TIMEOUT_MS = 7000;
const WEATHER_RETRY_COUNT = 3;
const WEATHER_RETRY_DELAY_MS = 1000;
let weatherRequest = null;
let cityLookup = 0;

function localWeatherUrl(city) {
  const params = new URLSearchParams({ city: city.name });
  if (Number.isFinite(city.lat) && Number.isFinite(city.lon)) {
    params.set("lat", city.lat);
    params.set("lon", city.lon);
  }
  return "/__weather?" + params;
}

async function fetchWeatherResponse(url, timeout, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timer = setTimeout(abort, timeout);
  signal.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) throw new Error("weather HTTP " + response.status);
    const data = await response.json();
    if (!data.current || !Number.isFinite(data.current.weather_code) ||
        !Number.isFinite(data.current.temperature_2m)) throw new Error("weather data");
    return data;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

async function fetchWeather(city, signal) {
  const fallback = localWeatherUrl(city);
  const sources = [fetchWeatherResponse(fallback, WEATHER_FALLBACK_TIMEOUT_MS, signal)];
  if (Number.isFinite(city.lat) && Number.isFinite(city.lon)) {
    const primary = "https://api.open-meteo.com/v1/forecast?latitude=" + city.lat +
      "&longitude=" + city.lon +
      "&current=temperature_2m,weather_code&timezone=auto";
    sources.unshift(fetchWeatherResponse(primary, WEATHER_PRIMARY_TIMEOUT_MS, signal));
  }
  return Promise.any(sources);
}

function waitForWeatherRetry(signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason || new Error("weather request aborted"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason || new Error("weather request aborted"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, WEATHER_RETRY_DELAY_MS);
    signal.addEventListener("abort", abort, { once: true });
  });
}

async function fetchWeatherWithRetry(city, signal) {
  for (let attempt = 0; attempt <= WEATHER_RETRY_COUNT; attempt++) {
    try {
      return await fetchWeather(city, signal);
    } catch (error) {
      if (signal.aborted || attempt === WEATHER_RETRY_COUNT) throw error;
      await waitForWeatherRetry(signal);
    }
  }
}

async function loadWeather(quiet, force = false) {
  const cache = readJson("bm-weather");
  if (cache && cache.text && Date.now() - cache.at < WEATHER_REFRESH_MS) {
    currentWeatherCode = cache.code;
    setWeatherUI(cache.text, cache.code);
    syncParticles();
    if (!force) return;
  }
  // 切换城市或主动刷新时，旧请求不能覆盖新结果。
  if (weatherRequest) weatherRequest.abort();
  const request = new AbortController();
  weatherRequest = request;
  const refresh = document.getElementById("weatherRefresh");
  refresh.disabled = true;
  refresh.setAttribute("aria-busy", "true");
  refresh.setAttribute("data-state", "loading");
  refresh.title = "正在刷新天气…";
  try {
    const city = await locateCity();
    const data = await fetchWeatherWithRetry(city, request.signal);
    if (weatherRequest !== request) return;
    const code = data.current.weather_code;
    const t = Math.round(data.current.temperature_2m);
    const desc = data.description || WMO[code] || "天气";
    const text = desc + " " + t + "° · " + city.name;
    currentWeatherCode = code;
    setWeatherUI(text, code);
    writeJson("bm-weather", { text, at: Date.now(), code });
    refresh.setAttribute("data-state", "ready");
    refresh.title = "刷新天气（每 10 分钟自动刷新）";
  } catch (e) {
    if (weatherRequest !== request) return;
    refresh.setAttribute("data-state", "error");
    refresh.title = "天气刷新失败，点击重试";
    if (!quiet && !cache) setWeatherUI("天气刷新失败，请重试", null);
  } finally {
    if (weatherRequest === request) {
      weatherRequest = null;
      refresh.disabled = false;
      refresh.setAttribute("aria-busy", "false");
      refresh.setAttribute("aria-label", refresh.title);
    }
  }
  syncParticles();
}

function initWeatherRefresh() {
  // 首次打开（含网页刷新）立即获取；缓存仅用于等待期间的显示。
  loadWeather(true, true);
  setInterval(() => loadWeather(true, true), WEATHER_REFRESH_MS);
}

function initWeatherControls() {
  document.getElementById("weatherRefresh").addEventListener("click", () => loadWeather(false, true));
  document.getElementById("weather").addEventListener("click", async () => {
    const cur = readJson("bm-city");
    const name = window.prompt("输入城市", cur && cur.name || "");
    if (!name || !name.trim()) return;
    const lookup = ++cityLookup;
    let city;
    try {
      city = await searchCity(name.trim());
    } catch (e) {
      if (lookup === cityLookup) setWeatherUI("城市查询失败，请重试", null);
      return;
    }
    // 只接受最后一次有效输入；旧查询的成功或失败都不更新页面。
    if (lookup !== cityLookup) return;
    if (!city) {
      setWeatherUI("没找到这个城市", null);
      return;
    }
    writeJson("bm-city", city);
    localStorage.removeItem("bm-weather");
    setWeatherUI("天气加载中…", null);
    loadWeather(false, true);
  });
}
