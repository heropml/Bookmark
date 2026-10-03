function readJson(key) {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
}
function writeJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}
function fetchJson(url, ms) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { signal: ctrl.signal }).then((r) => {
    // An error page is not a result, even when its body happens to be JSON.
    if (r.ok === false) throw new Error("HTTP " + r.status);
    return r.json();
  }).finally(() => clearTimeout(timer));
}
