try {
  const url = new URL(location.href);
  if (url.searchParams.get("window") === "maximized") {
    try {
      window.moveTo(screen.availLeft, screen.availTop);
      window.resizeTo(screen.availWidth, screen.availHeight);
    } finally {
      url.searchParams.delete("window");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }
} catch (e) {}
try {
  document.documentElement.dataset.focus = bookmarkStorage.getItem("bm-focus") === "on" ? "on" : "off";
  let s = bookmarkStorage.getItem("bm-skin");
  if (s === "auto") s = matchMedia("(prefers-color-scheme: light)").matches ? "snow" : "aurora";
  const i = bookmarkStorage.getItem("bm-icon");
  const l = bookmarkStorage.getItem("bm-layout");
  const m = bookmarkStorage.getItem("bm-motion");
  const f = bookmarkStorage.getItem("bm-fx");
  const t = bookmarkStorage.getItem("bm-trail");
  const k = bookmarkStorage.getItem("bm-sky");
  if (s) document.documentElement.dataset.skin = s;
  if (i) document.documentElement.dataset.icon = i;
  if (l) document.documentElement.dataset.layout = l;
  if (m) document.documentElement.dataset.motion = m;
  if (t) document.documentElement.dataset.trail = t;
  if (k) document.documentElement.dataset.sky = k;
  if (f === "on" || f === "off") document.documentElement.dataset.fx = f;
  // Until the user picks an option, follow the system's reduce-motion setting.
  else if (matchMedia("(prefers-reduced-motion: reduce)").matches) document.documentElement.dataset.fx = "off";
  const fav = document.createElement("link");
  fav.rel = "icon";
  fav.id = "fav";
  fav.href = "/__favicon?skin=" + encodeURIComponent(s || "aurora");
  document.head.appendChild(fav);
} catch (e) {}
