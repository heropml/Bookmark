const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/js/bookmark-sync.js'), 'utf8');
const updateSource = fs.readFileSync(path.join(__dirname, '../web/js/update.js'), 'utf8');
const response = (result, ok = true) => ({ ok, json: async () => result });
function fixture({ navigator = { userAgent: 'Chrome/140.0 Safari/537.36' }, location = {}, canRestart = false, serviceError = false, route } = {}) {
  const listeners = new Map(), elements = new Map(), requests = [], timers = [];
  const storage = new Map([['bm-folder', '旧分类'], ['bm-skin', 'celadon']]);
  let reloads = 0;
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      id, disabled: false, open: false, textContent: '', dataset: {},
      addEventListener(type, callback) { listeners.set(id + ':' + type, callback); },
      focus() {}, showModal() { this.open = true; },
      children: [], replaceChildren(...nodes) { this.children = nodes; },
      close() { this.open = false; listeners.get(id + ':close')?.(); }
    });
    return elements.get(id);
  }
  const radios = ['chrome', 'edge', 'safari', 'html', 'brave', 'vivaldi', 'opera', 'opera-gx', 'qq', '360', '360-x', 'sogou', 'quark', 'uc'].map(value => ({
    value, checked: false, disabled: false, label: { hidden: false },
    closest() { return this.label; }
  }));
  element('bookmarkSyncBrowsers').querySelectorAll = () => radios;
  const pageLocation = { protocol: 'http:', hostname: '127.0.0.1', reload() { reloads++; }, ...location };
  const fetchMock = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === '/__service' && options.cache === 'no-store') {
      if (serviceError) throw new Error('service unavailable');
      return response({ can_restart: canRestart });
    }
    if (route) return route(url, options);
    return response(options.method === 'POST' ? { ok: true, count: 3 } : { browsers: ['chrome', 'edge'] });
  };
  const context = vm.createContext({
    navigator, document: { getElementById: element, createElement: tag => ({ tag }) },
    setAppearanceOpen(open) { element('appearanceMenu').hidden = !open; },
    localStorage: { setItem(key, value) { storage.set(key, value); } },
    location: pageLocation,
    window: { location: pageLocation, setTimeout(callback) { timers.push(callback); } },
    fetch: fetchMock,
    fetchJson: async url => (await fetchMock(url)).json()
  });
  vm.runInContext(updateSource, context);
  vm.runInContext(source, context);
  vm.runInContext('initBookmarkSync()', context);
  const fire = (id, type = 'click') => listeners.get(id + ':' + type)?.({ preventDefault() {} });
  return {
    context, elements, radios, requests, fire, storage,
    open: () => fire('bookmarkSyncBtn'),
    submit: () => fire('bookmarkSyncForm', 'submit'),
    cancel: () => fire('bookmarkSyncCancel'),
    async settled() { await new Promise(resolve => setImmediate(resolve)); },
    async runTimer() { assert.ok(timers.length, '等待服务重新启动'); timers.shift()(); await this.settled(); },
    select(value) { radios.forEach(r => { r.checked = r.value === value; }); fire('bookmarkSyncBrowsers', 'change'); },
    get reloads() { return reloads; }
  };
}

test('打开同步窗口只查询支持情况，自动选择 Chrome，不读取或写入书签', async () => {
  const app = fixture();
  await app.open();
  assert.equal(app.requests.length, 2);
  assert.equal(app.requests[1].options.method, undefined);
  assert.equal(app.radios.find(r => r.checked).value, 'chrome');
  assert.equal(app.radios.find(r => r.value === 'safari').label.hidden, true);
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, false);
});

test('识别 Edge、Safari 和常见 Chromium 浏览器，不把 Firefox 当作 Chrome', () => {
  const samples = [
    ['Chrome/140.0 Safari/537.36 Edg/140.0', 'edge'],
    ['Version/18.0 Safari/605.1', 'safari'],
    ['Firefox/140', ''], ['Chrome/140 OPR/90', 'opera'], ['Vivaldi/7.5 Chrome/140', 'vivaldi'],
    ['QQBrowser/14.0 Chrome/140', 'qq'], ['360SE', '360'], ['MetaSr 1.0', 'sogou'],
    ['Quark/6.0 Chrome/140', 'quark'], ['UCBrowser/16.0 Chrome/140', 'uc'],
    ['CriOS/123 Mobile/15 Safari/604.1', ''],
  ];
  for (const [userAgent, expected] of samples) {
    const app = fixture({ navigator: { userAgent } });
    assert.equal(vm.runInContext('currentBookmarkBrowser()', app.context), expected);
  }
  const app = fixture({ navigator: { userAgent: 'Chromium', userAgentData: { brands: [{ brand: 'Microsoft Edge' }] } } });
  assert.equal(vm.runInContext('currentBookmarkBrowser()', app.context), 'edge');
  const brave = fixture({ navigator: { userAgent: 'Chrome/140', brave: {} } });
  assert.equal(vm.runInContext('currentBookmarkBrowser()', brave.context), 'brave');
});

test('只显示后台检测到的本机浏览器，并保留 HTML 导入', async () => {
  const app = fixture({ navigator: { userAgent: 'Chrome/140', brave: {} }, route: (_, options) => response(options.method === 'POST' ? { ok: true, count: 3 } : { browsers: ['brave', 'html'] }) });
  await app.open();
  assert.equal(app.radios.find(r => r.value === 'brave').checked, true);
  assert.equal(app.radios.find(r => r.value === 'chrome').label.hidden, true);
  assert.equal(app.radios.find(r => r.value === 'html').label.hidden, false);
});

test('未知浏览器不会擅自选来源，手动选择后才能确认', async () => {
  const app = fixture({ navigator: { userAgent: 'Firefox/140' } });
  await app.open();
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, true);
  await app.submit();
  assert.equal(app.requests.length, 2);
  app.select('edge');
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, false);
});

test('取消同步不提交数据、不刷新主页', async () => {
  const app = fixture();
  await app.open();
  app.cancel();
  assert.equal(app.requests.length, 2);
  assert.equal(app.reloads, 0);
  assert.equal(app.storage.get('bm-folder'), '旧分类');
  assert.equal(app.elements.get('bookmarkSyncDialog').open, false);
});

test('确认后只同步选定浏览器，携带确认字段，成功刷新一次', async () => {
  const app = fixture();
  await app.open();
  app.select('edge');
  await app.submit();
  const request = app.requests[2];
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['X-Bookmark-Sync'], '1');
  assert.deepEqual(JSON.parse(request.options.body), { browser: 'edge', confirmed: true });
  assert.equal(app.reloads, 1);
  assert.equal(app.storage.get('bm-folder'), '');
  assert.equal(app.storage.get('bm-skin'), 'celadon');
});

test('其他浏览器可选择导出的 HTML 书签文件导入', async () => {
  const app = fixture({ route: (_, options) => response(options.method === 'POST' ? { ok: true, count: 3 } : { browsers: ['chrome', 'edge', 'html'] }) });
  await app.open();
  app.select('html');
  await app.submit();
  assert.deepEqual(JSON.parse(app.requests[2].options.body), { browser: 'html', confirmed: true });
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
  assert.equal(app.requests.length, 3);
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
  assert.equal(app.requests.length, 2);
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

test('失败只显示一句原因，解决步骤可展开，macOS 权限问题可一键打开系统设置', async () => {
  const failure = { ok: false, message: 'macOS 未允许“书签”读取 Chrome 数据。', steps: ['打开完全磁盘访问权限', '添加并启用 /Applications/Bookmark.app'], settings: true };
  const app = fixture({ route: (url, options) => {
    if (url === '/__bookmarks/settings') return { ok: true, status: 204 };
    return response(options.method === 'POST' ? failure : { browsers: ['chrome'] }, options.method !== 'POST');
  } });
  await app.open();
  assert.equal(app.elements.get('bookmarkSyncHelp').hidden, true, '打开窗口时不显示帮助区');
  await app.submit();
  assert.equal(app.elements.get('bookmarkSyncStatus').textContent, failure.message);
  assert.equal(app.elements.get('bookmarkSyncHelp').hidden, false);
  assert.deepEqual(app.elements.get('bookmarkSyncSteps').children.map(li => li.textContent), failure.steps);
  const settings = app.elements.get('bookmarkSyncSettings');
  assert.equal(settings.hidden, false);
  await app.fire('bookmarkSyncSettings');
  const request = app.requests.at(-1);
  assert.equal(request.url, '/__bookmarks/settings');
  assert.equal(request.options.method, 'POST');
  assert.equal(settings.textContent, '已打开系统设置');
});

test('没有解决步骤的失败不显示帮助区，重新打开窗口会清除上次的帮助', async () => {
  let failure = { ok: false, message: '无法读取或保存 Chrome 书签。', steps: ['确认浏览器已创建书签'] };
  const app = fixture({ route: (_, options) => response(options.method === 'POST' ? failure : { browsers: ['chrome'] }, options.method !== 'POST') });
  await app.open();
  await app.submit();
  assert.equal(app.elements.get('bookmarkSyncHelp').hidden, false);
  assert.equal(app.elements.get('bookmarkSyncSettings').hidden, true, '只有 macOS 权限问题提供系统设置入口');
  assert.equal(app.elements.get('bookmarkSyncRestart').hidden, true, '后台未声明重启能力时不显示入口');
  app.cancel();
  await app.open();
  assert.equal(app.elements.get('bookmarkSyncHelp').hidden, true);
  failure = { ok: false, message: '浏览器书签不可用' };
  await app.submit();
  assert.equal(app.elements.get('bookmarkSyncHelp').hidden, true);
});

test('重启书签等待新服务接管，期间不重复请求或同步，保留书签分类和外观', async () => {
  let probes = 0;
  const failure = { ok: false, message: '需要重新授权', settings: true, restart: true };
  const app = fixture({ route: (url, options) => {
    if (url === '/__bookmarks/restart') return response({ ok: true, instance: 'old' });
    if (url === '/__service') {
      probes++;
      if (probes === 2) throw new Error('listener is restarting');
      return response({ instance: probes < 3 ? 'old' : 'new' });
    }
    return response(options.method === 'POST' ? failure : { browsers: ['chrome'] }, options.method !== 'POST');
  } });
  await app.open();
  await app.submit();
  assert.equal(app.elements.get('bookmarkSyncRestart').hidden, false);
  await app.fire('bookmarkSyncRestart');
  const pending = app.fire('serviceRestartConfirm');
  await app.settled();
  await app.fire('bookmarkSyncRestart');
  await app.submit();
  app.cancel();
  assert.equal(app.elements.get('bookmarkSyncDialog').open, true);
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, true);
  assert.equal(app.elements.get('bookmarkSyncSettings').disabled, true);
  const request = app.requests.find(r => r.url === '/__bookmarks/restart');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['X-Bookmark-Sync'], '1');
  await app.runTimer();
  assert.equal(app.reloads, 0, '旧实例仍响应时不能刷新');
  await app.runTimer();
  assert.equal(app.reloads, 0, '端口关闭期间继续等待');
  await app.runTimer();
  await pending;
  assert.equal(app.reloads, 1);
  assert.equal(app.requests.filter(r => r.url === '/__bookmarks/restart').length, 1);
  assert.equal(app.requests.filter(r => r.url === '/__bookmarks/sync' && r.options.method === 'POST').length, 1);
  assert.equal(app.storage.get('bm-folder'), '旧分类');
  assert.equal(app.storage.get('bm-skin'), 'celadon');
  assert.match(app.elements.get('bookmarkSyncStatus').textContent, /已重启/);
  assert.equal(app.elements.has('updateProgressTitle'), false, '重启不显示升级进度面板');
});

test('后台拒绝重启时显示原因并恢复操作，不自动重试或刷新', async () => {
  const app = fixture({ route: (url, options) => {
    if (url === '/__bookmarks/restart') return response({ ok: false, message: '已有书签同步正在进行，请完成后再重启。' }, false);
    return response(options.method === 'POST' ? { ok: false, message: '需要授权', restart: true } : { browsers: ['chrome'] }, options.method !== 'POST');
  } });
  await app.open();
  await app.submit();
  await app.fire('bookmarkSyncRestart');
  await app.fire('serviceRestartConfirm');
  assert.match(app.elements.get('bookmarkSyncStatus').textContent, /同步正在进行/);
  assert.equal(app.elements.get('bookmarkSyncRestart').disabled, false);
  assert.equal(app.elements.get('bookmarkSyncConfirm').disabled, false);
  assert.equal(app.reloads, 0);
  assert.equal(app.requests.filter(r => r.url === '/__service').length, 1);
  app.cancel();
  assert.equal(app.elements.get('bookmarkSyncDialog').open, false);
});

test('重启服务一直未就绪时停止等待并恢复弹窗操作', async () => {
  const app = fixture({ route: (url, options) => {
    if (url === '/__bookmarks/restart') return response({ ok: true, instance: 'old' });
    if (url === '/__service') return response({ instance: 'old' });
    return response(options.method === 'POST' ? { ok: false, message: '需要授权', restart: true } : { browsers: ['chrome'] }, options.method !== 'POST');
  } });
  await app.open();
  await app.submit();
  await app.fire('bookmarkSyncRestart');
  const pending = app.fire('serviceRestartConfirm');
  await app.settled();
  for (let i = 0; i < 20; i++) await app.runTimer();
  await pending;
  assert.equal(app.reloads, 0);
  assert.equal(app.requests.filter(r => r.url === '/__service').length, 21);
  assert.match(app.elements.get('bookmarkSyncStatus').textContent, /重启未完成/);
  assert.equal(app.elements.get('bookmarkSyncRestart').disabled, false);
  app.cancel();
  assert.equal(app.elements.get('bookmarkSyncDialog').open, false);
});


test('外观菜单只在本地后台支持重启时显示入口，旧后台或连接失败不显示', async () => {
  for (const options of [{}, { serviceError: true }, { location: { protocol: 'file:' } }, { location: { hostname: 'example.com' } }]) {
    const app = fixture(options);
    await app.settled();
    assert.equal(app.elements.get('serviceRestartBtn').hidden, true);
    await app.fire('serviceRestartBtn');
    assert.equal(app.requests.filter(r => r.options.method === 'POST').length, 0);
  }
  const app = fixture({ canRestart: true });
  await app.settled();
  assert.equal(app.elements.get('serviceRestartBtn').hidden, false);
  assert.deepEqual(app.requests.map(r => r.url), ['/__service']);
});

test('菜单确认重启，无需先同步；阻止重复操作，等新实例后刷新并保留分类与外观', async () => {
  let probes = 0;
  const app = fixture({ canRestart: true, route: url => {
    if (url === '/__bookmarks/restart') return response({ ok: true, instance: 'old' });
    if (url === '/__service') return response({ instance: ++probes > 1 ? 'new' : 'old' });
    throw new Error('不应访问同步接口');
  } });
  await app.settled();
  await app.fire('serviceRestartBtn');
  assert.equal(app.requests.filter(r => r.options.method === 'POST').length, 0);
  const pending = app.fire('serviceRestartConfirm');
  await app.settled();
  await app.fire('serviceRestartBtn');
  await app.open();
  assert.equal(app.elements.get('bookmarkSyncDialog').open, false);
  assert.equal(app.elements.get('serviceRestartBtn').disabled, true);
  assert.equal(app.elements.get('bookmarkSyncBtn').disabled, true);
  assert.equal(app.elements.get('serviceRestartStatus').hidden, false);
  assert.match(app.elements.get('serviceRestartStatus').textContent, /正在重启/);
  await app.runTimer();
  assert.equal(app.reloads, 0);
  await app.runTimer();
  await pending;
  assert.equal(app.reloads, 1);
  assert.equal(app.requests.filter(r => r.url === '/__bookmarks/restart').length, 1);
  assert.equal(app.requests.filter(r => r.url === '/__bookmarks/sync').length, 0);
  assert.equal(app.storage.get('bm-folder'), '旧分类');
  assert.equal(app.storage.get('bm-skin'), 'celadon');
});

test('菜单重启被拒绝会显示原因并恢复操作，不自动重试', async () => {
  const app = fixture({ canRestart: true, route: () => response({ ok: false, message: '已有书签同步正在进行，请完成后再重启。' }, false) });
  await app.settled();
  await app.fire('serviceRestartBtn');
  await app.fire('serviceRestartConfirm');
  assert.equal(app.elements.get('serviceRestartBtn').disabled, false);
  assert.equal(app.elements.get('bookmarkSyncBtn').disabled, false);
  assert.match(app.elements.get('serviceRestartStatus').textContent, /同步正在进行/);
  assert.equal(app.elements.get('serviceRestartStatus').dataset.state, 'error');
  assert.equal(app.reloads, 0);
  assert.equal(app.requests.filter(r => r.url === '/__bookmarks/restart').length, 1);
});


test('菜单重启必须确认，取消或关闭弹框不发送请求，也不刷新', async () => {
  const app = fixture({ canRestart: true });
  await app.settled();
  await app.fire('serviceRestartBtn');
  assert.equal(app.elements.get('serviceRestartDialog').open, true);
  assert.equal(app.requests.filter(r => r.options.method === 'POST').length, 0);
  await app.fire('serviceRestartCancel');
  assert.equal(app.elements.get('serviceRestartDialog').open, false);
  await app.fire('serviceRestartConfirm');
  assert.equal(app.requests.filter(r => r.options.method === 'POST').length, 0);
  await app.fire('serviceRestartBtn');
  app.elements.get('serviceRestartDialog').close();
  assert.equal(app.reloads, 0);
  assert.equal(app.storage.get('bm-folder'), '旧分类');
  assert.equal(app.storage.get('bm-skin'), 'celadon');
});

test('同步帮助的重启入口也须确认，取消后保留同步弹框和错误说明', async () => {
  const app = fixture({ route: (_, options) => response(options.method === 'POST' ? { ok: false, message: '需要重新授权', restart: true } : { browsers: ['chrome'] }, options.method !== 'POST') });
  await app.open();
  await app.submit();
  await app.fire('bookmarkSyncRestart');
  assert.equal(app.elements.get('serviceRestartDialog').open, true);
  await app.fire('serviceRestartCancel');
  assert.equal(app.elements.get('bookmarkSyncDialog').open, true);
  assert.equal(app.elements.get('bookmarkSyncStatus').textContent, '需要重新授权');
  assert.equal(app.requests.filter(r => r.url === '/__bookmarks/restart').length, 0);
  assert.equal(app.reloads, 0);
});
