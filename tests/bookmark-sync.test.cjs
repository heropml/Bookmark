const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/js/bookmark-sync.js'), 'utf8');
const response = (result, ok = true) => ({ ok, json: async () => result });
function fixture({ navigator = { userAgent: 'Chrome/140.0 Safari/537.36' }, location = {}, route } = {}) {
  const listeners = new Map(), elements = new Map(), requests = [];
  const storage = new Map([['bm-folder', '旧分类'], ['bm-skin', 'celadon']]);
  let reloads = 0;
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      id, disabled: false, open: false, textContent: '', dataset: {},
      addEventListener(type, callback) { listeners.set(id + ':' + type, callback); },
      focus() {}, showModal() { this.open = true; },
      close() { this.open = false; listeners.get(id + ':close')?.(); }
    });
    return elements.get(id);
  }
  const radios = ['chrome', 'edge', 'safari'].map(value => ({
    value, checked: false, disabled: false, label: { hidden: false },
    closest() { return this.label; }
  }));
  element('bookmarkSyncBrowsers').querySelectorAll = () => radios;
  const context = vm.createContext({
    navigator, document: { getElementById: element },
    localStorage: { setItem(key, value) { storage.set(key, value); } },
    location: { protocol: 'http:', hostname: '127.0.0.1', reload() { reloads++; }, ...location },
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (route) return route(url, options);
      return response(options.method === 'POST' ? { ok: true, count: 3 } : { browsers: ['chrome', 'edge'] });
    }
  });
  vm.runInContext(source, context);
  vm.runInContext('initBookmarkSync()', context);
  const fire = (id, type = 'click') => listeners.get(id + ':' + type)?.({ preventDefault() {} });
  return {
    context, elements, radios, requests, fire, storage,
    open: () => fire('bookmarkSyncBtn'),
    submit: () => fire('bookmarkSyncForm', 'submit'),
    cancel: () => fire('bookmarkSyncCancel'),
    select(value) { radios.forEach(r => { r.checked = r.value === value; }); fire('bookmarkSyncBrowsers', 'change'); },
    get reloads() { return reloads; }
  };
}

test('打开同步窗口只查询支持情况，自动选择 Chrome，不读取或写入书签', async () => {
  const app = fixture();
  await app.open();
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0].options.method, undefined);
  assert.equal(app.radios.find(r => r.checked).value, 'chrome');
  assert.equal(app.radios.find(r => r.value === 'safari').label.hidden, true);
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, false);
});

test('识别 Edge 优先于 Chrome，并支持 Safari；不把 Firefox、Opera 当作 Chrome', () => {
  const samples = [
    ['Chrome/140.0 Safari/537.36 Edg/140.0', 'edge'],
    ['Version/18.0 Safari/605.1', 'safari'],
    ['Firefox/140', ''], ['Chrome/140 OPR/90', ''],
    ['CriOS/123 Mobile/15 Safari/604.1', ''],
  ];
  for (const [userAgent, expected] of samples) {
    const app = fixture({ navigator: { userAgent } });
    assert.equal(vm.runInContext('currentBookmarkBrowser()', app.context), expected);
  }
  const app = fixture({ navigator: { userAgent: 'Chromium', userAgentData: { brands: [{ brand: 'Microsoft Edge' }] } } });
  assert.equal(vm.runInContext('currentBookmarkBrowser()', app.context), 'edge');
});

test('未知浏览器不会擅自选来源，手动选择后才能确认', async () => {
  const app = fixture({ navigator: { userAgent: 'Firefox/140' } });
  await app.open();
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, true);
  await app.submit();
  assert.equal(app.requests.length, 1);
  app.select('edge');
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, false);
});

test('取消同步不提交数据、不刷新主页', async () => {
  const app = fixture();
  await app.open();
  app.cancel();
  assert.equal(app.requests.length, 1);
  assert.equal(app.reloads, 0);
  assert.equal(app.storage.get('bm-folder'), '旧分类');
  assert.equal(app.elements.get('bookmarkSyncDialog').open, false);
});

test('确认后只同步选定浏览器，携带确认字段，成功刷新一次', async () => {
  const app = fixture();
  await app.open();
  app.select('edge');
  await app.submit();
  const request = app.requests[1];
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['X-Bookmark-Sync'], '1');
  assert.deepEqual(JSON.parse(request.options.body), { browser: 'edge', confirmed: true });
  assert.equal(app.reloads, 1);
  assert.equal(app.storage.get('bm-folder'), '');
  assert.equal(app.storage.get('bm-skin'), 'celadon');
});

test('同步中禁用重复确认和关闭，避免重入', async () => {
  let done;
  const pending = new Promise(resolve => { done = resolve; });
  const app = fixture({ route: (_, options) => options.method === 'POST' ? pending : response({ browsers: ['chrome', 'edge'] }) });
  await app.open();
  const submit = app.submit();
  await app.submit();
  app.cancel();
  assert.equal(app.elements.get('bookmarkSyncDialog').open, true);
  assert.equal(app.requests.filter(r => r.options.method === 'POST').length, 1);
  assert.equal(app.elements.get('bookmarkSyncClose').disabled, true);
  done(response({ ok: true, count: 0 }));
  await submit;
  assert.equal(app.reloads, 1);
});

test('读取失败保留页面并显示原因，可以取消，不自动重试', async () => {
  const app = fixture({ route: (_, options) => response(options.method === 'POST' ? { ok: false, message: '浏览器书签不可用' } : { browsers: ['chrome'] }, options.method !== 'POST') });
  await app.open();
  await app.submit();
  assert.equal(app.reloads, 0);
  assert.equal(app.elements.get('bookmarkSyncStatus').textContent, '浏览器书签不可用');
  assert.equal(app.storage.get('bm-folder'), '旧分类');
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, false);
  assert.equal(app.requests.length, 2);
  app.cancel();
  assert.equal(app.elements.get('bookmarkSyncDialog').open, false);
});

test('直接打开 HTML 或托管网站时不请求本地同步', async () => {
  for (const location of [{ protocol: 'file:', hostname: '' }, { protocol: 'https:', hostname: 'example.com' }]) {
    const app = fixture({ location });
    await app.open();
    assert.equal(app.requests.length, 0);
    assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, true);
    assert.match(app.elements.get('bookmarkSyncStatus').textContent, /快捷方式/);
  }
});

test('旧后台不支持接口时给出说明，不允许提交同步', async () => {
  const app = fixture({ route: () => response({}, false) });
  await app.open();
  await app.submit();
  assert.equal(app.requests.length, 1);
  assert.match(app.elements.get('bookmarkSyncStatus').textContent, /新版程序/);
});

test('关闭并重新打开窗口后，旧响应不能覆盖新的浏览器选择', async () => {
  let finish;
  let reads = 0;
  const app = fixture({ route: () => ++reads === 1 ? new Promise(resolve => { finish = resolve; }) : response({ browsers: ['chrome', 'edge'] }) });
  const first = app.open();
  app.cancel();
  await app.open();
  app.select('edge');
  finish(response({ browsers: ['chrome'] }));
  await first;
  assert.equal(app.radios.find(r => r.checked).value, 'edge');
});
