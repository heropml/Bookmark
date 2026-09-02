const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const city = { name: '杭州', lat: 30.27, lon: 120.15 };
const hit = name => ({ results: [{ name, latitude: 29.87, longitude: 121.55 }] });
const response = data => ({ ok: true, status: 200, json: async () => data });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

function fixture({ savedCity = city, route } = {}) {
  const storage = new Map();
  if (savedCity) storage.set('bm-city', JSON.stringify(savedCity));
  const elements = new Map();
  const handlers = new Map();
  const prompts = [];
  const requests = [];
  const intervals = [];
  const context = vm.createContext({
    AbortController, Date, setTimeout, clearTimeout,
    setInterval: (callback, ms) => { intervals.push({ callback, ms }); return intervals.length; },
    localStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key)
    },
    window: { prompt: () => prompts.shift() ?? null },
    document: { getElementById: id => {
      if (!elements.has(id)) elements.set(id, {
        textContent: '', innerHTML: '', disabled: false, title: '', attributes: {},
        setAttribute(name, value) { this.attributes[name] = value; },
        addEventListener(name, callback) { handlers.set(id + ':' + name, callback); }
      });
      return elements.get(id);
    } },
    currentWeatherCode: null,
    syncParticles() {},
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (options.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      if (route) {
        const result = route(url, options);
        if (result !== undefined) return result;
      }
      if (url.startsWith('https://api.open-meteo.com/')) return response({ current: { weather_code: 61, temperature_2m: 22 } });
      if (url.startsWith('https://geocoding-api.open-meteo.com/')) return response(hit(new URL(url).searchParams.get('name')));
      throw Error('Unexpected request: ' + url);
    }
  });
  for (const file of ['utils.js', 'weather.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'web/js', file), 'utf8'), context, { filename: file });
  }
  vm.runInContext('initWeatherControls()', context);
  return {
    context, requests, storage, elements, intervals,
    run: code => vm.runInContext(code, context),
    async click(name) { prompts.push(name); await handlers.get('weather:click')(); },
    async settled() {
      for (let i = 0; i < 100; i++) {
        await new Promise(resolve => setImmediate(resolve));
        if (vm.runInContext('weatherRequest === null', context)) return;
      }
      throw Error('Weather request did not settle');
    },
    saved: key => JSON.parse(storage.get(key) || 'null')
  };
}

test('取消、空输入及纯空格不查询城市或刷新天气', async () => {
  const app = fixture();
  for (const name of [null, '', '   ']) { await app.click(name); await app.settled(); }
  assert.equal(app.requests.length, 0);
  assert.equal(app.saved('bm-city').name, '杭州');
});

test('零经度或零纬度的已保存城市不会触发 IP 定位', async () => {
  for (const coordinates of [{ lat: 0, lon: 120 }, { lat: 30, lon: 0 }]) {
    const app = fixture({ savedCity: { name: '测试城市', ...coordinates } });
    const located = await app.run('locateCity()');
    assert.equal(located.lat, coordinates.lat);
    assert.equal(located.lon, coordinates.lon);
    assert.equal(app.requests.length, 0);
  }
});

test('较慢的旧城市查询不能覆盖最后一次有效选择', async () => {
  const old = deferred();
  const app = fixture({ route: url => url.includes('name=' + encodeURIComponent('旧城市')) ? old.promise : undefined });
  const pending = app.click('旧城市');
  await app.click('宁波');
  await app.settled();
  old.resolve(response(hit('旧城市')));
  await pending;
  await app.settled();
  assert.equal(app.saved('bm-city').name, '宁波');
  assert.match(app.elements.get('weatherTxt').textContent, /宁波$/);
  assert.equal(app.requests.filter(r => r.url.startsWith('https://api.open-meteo.com/')).length, 1);
});

test('旧城市查询失败也不能覆盖新城市天气', async () => {
  const old = deferred();
  const app = fixture({ route: url => url.includes('name=' + encodeURIComponent('旧城市')) ? old.promise : undefined });
  const pending = app.click('旧城市');
  await app.click('宁波');
  await app.settled();
  old.reject(Error('network unavailable'));
  await pending;
  assert.match(app.elements.get('weatherTxt').textContent, /宁波$/);
});

test('自动定位较晚返回时，不覆盖用户手动选择的城市', async () => {
  const geo = deferred();
  const ip = deferred();
  const app = fixture({ savedCity: null, route: url => {
    if (url.startsWith('https://get.geojs.io/')) return geo.promise;
    if (url.startsWith('https://ipwho.is/')) return ip.promise;
  } });
  const pending = app.run('loadWeather(true, true)');
  await app.click('宁波');
  await app.settled();
  geo.resolve(response({ city: 'IP城市', latitude: '39.9', longitude: '116.4' }));
  ip.resolve(response({ success: true, city: 'IP城市', latitude: 39.9, longitude: 116.4 }));
  await pending;
  assert.equal(app.saved('bm-city').name, '宁波');
  assert.match(app.elements.get('weatherTxt').textContent, /宁波$/);
});

test('打开、手动刷新和 10 分钟周期仍绕过新鲜缓存', async () => {
  const app = fixture();
  app.storage.set('bm-weather', JSON.stringify({ text: '旧缓存', code: 0, at: Date.now() }));
  app.run('initWeatherRefresh()');
  await app.settled();
  assert.equal(app.intervals.length, 1);
  assert.equal(app.intervals[0].ms, 600000);
  await app.run('loadWeather(false, true)');
  await app.intervals[0].callback();
  assert.equal(app.requests.length, 3);
  assert.match(app.elements.get('weatherTxt').textContent, /22° · 杭州/);
});

test('天气刷新失败保留原数据并恢复按钮', async () => {
  const app = fixture({ route: () => ({ ok: false, status: 503, json: async () => ({}) }) });
  const cached = JSON.stringify({ text: '晴 20° · 杭州', code: 0, at: Date.now() });
  app.storage.set('bm-weather', cached);
  await app.run('loadWeather(false, true)');
  assert.equal(app.storage.get('bm-weather'), cached);
  assert.equal(app.elements.get('weatherTxt').textContent, '晴 20° · 杭州');
  assert.equal(app.elements.get('weatherRefresh').disabled, false);
  assert.match(app.elements.get('weatherRefresh').title, /失败/);
});
