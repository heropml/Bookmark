const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../web/js/preferences.js'), 'utf8');

function fixture({ snapshot, cache = {}, failure, local = true, storageDenied = false, responder } = {}) {
  const saved = new Map(Object.entries(cache));
  const calls = [];
  const timers = new Map();
  const handlers = {};
  let timer = 0;
  const context = vm.createContext({
    location: { protocol: local ? 'http:' : 'https:', hostname: local ? '127.0.0.1' : 'example.com' },
    window: { BOOKMARK_PREFERENCES: snapshot, dispatchEvent() {},
      addEventListener: (type, action) => { handlers[type] = action; } },
    document: { addEventListener() {} },
    Event: class {},
    AbortSignal: { timeout: () => undefined },
    setTimeout: callback => { timers.set(++timer, callback); return timer; },
    clearTimeout: id => timers.delete(id),
    localStorage: {
      get length() { if (storageDenied) throw Error('denied'); return saved.size; },
      key(index) { return [...saved.keys()][index] ?? null; },
      getItem(key) { if (storageDenied) throw Error('denied'); return saved.get(key) ?? null; },
      setItem(key, value) { if (storageDenied) throw Error('denied'); saved.set(key, value); },
      removeItem(key) { if (storageDenied) throw Error('denied'); saved.delete(key); }
    },
    fetch: async (url, options) => {
      const body = JSON.parse(options.body);
      calls.push({ url, body });
      if (failure) throw Error(failure);
      if (responder) return responder(body);
      return { ok: true, json: async () => ({ revision: `r${calls.length}`, values: body.values || {} }) };
    }
  });
  vm.runInContext(source, context);
  return { api: vm.runInContext('bookmarkPreferences', context), store: vm.runInContext('bookmarkStorage', context),
    saved, calls, handlers, timers };
}

test('首次迁移只发送已有设置，保留置顶顺序且不写入默认值', async () => {
  const values = { 'bm-pins': '["https://b/","https://a/"]', 'bm-skin': 'celadon' };
  const app = fixture({ snapshot: { exists: false, revision: null }, cache: values });
  assert.equal(await app.api.flush(), true);
  assert.deepEqual(app.calls[0].body, { changes: values, base: { 'bm-pins': null, 'bm-skin': null }, migration: true });
  assert.equal(await app.api.flush(), true);
  assert.equal(app.calls.length, 1);
});

test('已有磁盘配置优先于空缓存或其他端口的旧缓存，启动不反向覆盖', async () => {
  for (const cache of [{}, { 'bm-pins': '[]', 'bm-skin': 'snow' }]) {
    const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-pins': '["https://a/"]' } }, cache });
    assert.equal(app.store.getItem('bm-pins'), '["https://a/"]');
    assert.equal(app.store.getItem('bm-skin'), null);
    await app.api.flush();
    assert.equal(app.calls.length, 0);
  }
});

test('空浏览器首次打开不生成空文件；读取失败不生成部分迁移', async () => {
  for (const options of [{}, { storageDenied: true }]) {
    const app = fixture({ snapshot: { exists: false }, ...options });
    await app.api.flush();
    assert.equal(app.calls.length, 0);
  }
});

test('磁盘读取失败时禁止自动保存', async () => {
  for (const snapshot of [{ error: 'broken file' }]) {
    const app = fixture({ snapshot, cache: { 'bm-pins': '["https://a/"]' } });
    assert.equal(await app.api.flush(), false);
    assert.throws(() => app.store.setItem('bm-pins', '[]'));
    assert.equal(app.calls.length, 0);
    assert.equal(app.api.exportDocument().values['bm-pins'], '["https://a/"]');
  }
});

test('其他本地服务器未嵌入配置数据时继续浏览器存储，不请求配置接口', async () => {
  const app = fixture({ cache: { 'bm-skin': 'snow' } });
  assert.equal(app.api.status().local, false);
  assert.equal(app.store.getItem('bm-skin'), 'snow');
  app.store.setItem('bm-pins', '["https://a/"]');
  app.store.removeItem('bm-skin');
  assert.equal(await app.api.flush(), true);
  assert.equal(app.saved.get('bm-pins'), '["https://a/"]');
  assert.equal(app.calls.length, 0);
});

test('无效旧值不阻塞有效设置迁移，保留原值副本且后续修改仍正常保存', async () => {
  const app = fixture({ snapshot: { exists: false, installation: 'one' },
    cache: { 'bm-pins': '["https://a/"]', 'bm-skin': 'removed-theme' },
    responder: async body => ({ ok: true, json: async () => ({ rejected: body.migration ? ['bm-skin'] : [] }) }) });
  assert.equal(await app.api.flush(), true);
  assert.equal(app.api.status().blocked, false);
  assert.match(app.api.status().message, /1 项旧配置无效/);
  assert.equal(app.api.exportDocument(app.api.drafts()[0].id).values['bm-skin'], 'removed-theme');
  app.store.setItem('bm-layout', 'compact');
  await app.api.flush();
  assert.deepEqual(app.calls[1].body, { changes: { 'bm-layout': 'compact' }, base: { 'bm-layout': null } });
  const reloaded = fixture({ snapshot: { exists: true, installation: 'one', values: { 'bm-pins': '["https://a/"]' } },
    cache: Object.fromEntries(app.saved) });
  assert.equal(reloaded.api.exportDocument(reloaded.api.drafts()[0].id).values['bm-skin'], 'removed-theme');
  app.store.setItem('bm-skin', 'snow');
  await app.api.flush();
  assert.equal(app.calls[2].body.base['bm-skin'], null);
  assert.equal(app.api.drafts().length, 0);
});

test('磁盘配置在浏览器存储不可用时仍可读取和保存，显式清空置顶正常写回', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-pins': '["https://a/"]' } }, storageDenied: true });
  assert.equal(app.store.getItem('bm-pins'), '["https://a/"]');
  app.store.setItem('bm-pins', '[]');
  await app.api.flush();
  assert.deepEqual(app.calls[0].body, { changes: { 'bm-pins': '[]' }, base: { 'bm-pins': '["https://a/"]' } });
});

test('应用方案的多字段修改合并提交；删除 fx 保持跟随系统语义', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-fx': 'on' } } });
  app.store.setItem('bm-skin', 'paper');
  app.store.setItem('bm-layout', 'compact');
  app.store.removeItem('bm-fx');
  await app.api.flush();
  assert.equal(app.calls.length, 1);
  assert.deepEqual(app.calls[0].body, {
    changes: { 'bm-skin': 'paper', 'bm-layout': 'compact', 'bm-fx': null },
    base: { 'bm-skin': null, 'bm-layout': null, 'bm-fx': 'on' }
  });
});

test('正在保存时发生的新修改随后只提交新改动的字段', async () => {
  let release;
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: {} },
    responder: async body => {
      if ('bm-skin' in body.changes) await new Promise(resolve => { release = resolve; });
      return { ok: true, json: async () => ({}) };
    } });
  app.store.setItem('bm-skin', 'snow');
  const saving = app.api.flush();
  app.store.setItem('bm-layout', 'compact');
  release();
  assert.equal(await saving, true);
  assert.equal(app.calls.length, 2);
  assert.deepEqual(app.calls[1].body, { changes: { 'bm-layout': 'compact' }, base: { 'bm-layout': null } });
});

test('同一字段再次修改以本页上次保存的值为基准；改回原值不提交', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-skin': 'snow', 'bm-pins': '[]' } } });
  app.store.setItem('bm-skin', 'paper');
  await app.api.flush();
  app.store.setItem('bm-skin', 'abyss');
  await app.api.flush();
  assert.deepEqual(app.calls[1].body, { changes: { 'bm-skin': 'abyss' }, base: { 'bm-skin': 'paper' } });
  app.store.setItem('bm-pins', '["https://a/"]');
  app.store.setItem('bm-pins', '[]');
  assert.equal(await app.api.flush(), true);
  assert.equal(app.calls.length, 2);
  assert.equal(app.api.status().pending, false);
});

test('其他页面修改了同一字段时停止保存并提示刷新', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-pins': '[]' } },
    responder: async () => ({ ok: false, json: async () => ({ message: '其他页面已修改置顶，请刷新后再修改；本次未覆盖本地配置。' }) }) });
  app.store.setItem('bm-pins', '["https://a/"]');
  assert.equal(await app.api.flush(), false);
  assert.match(app.api.status().message, /其他页面已修改置顶/);
  assert.equal(app.api.status().blocked, true);
  assert.throws(() => app.store.setItem('bm-skin', 'snow'));
});

test('保存失败保留可导出的待保存数据，阻止后续覆盖并提示离开风险', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: {} }, failure: 'network failed' });
  app.store.setItem('bm-pins', '["https://a/"]');
  assert.equal(await app.api.flush(), false);
  assert.equal(await app.api.flush(), false);
  assert.equal(app.calls.length, 1);
  assert.equal(app.api.status().error, true);
  assert.equal(app.api.exportDocument().values['bm-pins'], '["https://a/"]');
  let prevented = false;
  app.handlers.beforeunload({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
});

test('静态页面继续使用浏览器存储，不向远端提交私人配置', async () => {
  const app = fixture({ local: false });
  app.store.setItem('bm-pins', '[]');
  await app.api.flush();
  assert.equal(app.saved.get('bm-pins'), '[]');
  assert.equal(app.api.exportDocument().values['bm-pins'], '[]');
  assert.equal(app.calls.length, 0);
});

test('天气缓存仍留在浏览器，不进入本地配置或迁移', async () => {
  const app = fixture({ snapshot: { exists: false }, cache: { 'bm-weather': '{"stale":1}' } });
  app.store.setItem('bm-weather', '{"new":1}');
  await app.api.flush();
  assert.equal(app.store.getItem('bm-weather'), '{"new":1}');
  assert.equal(app.calls.length, 0);
  assert.equal(app.api.exportDocument().values['bm-weather'], undefined);
});

test('当前分类只留在浏览器：切换分类不提交、不迁移，磁盘旧值不覆盖本页分类', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-folder': '磁盘旧分类' } },
    cache: { 'bm-folder': '本页分类' } });
  assert.equal(app.store.getItem('bm-folder'), '本页分类');
  app.store.setItem('bm-folder', '另一个分类');
  await app.api.flush();
  assert.equal(app.calls.length, 0);
  assert.equal(app.saved.get('bm-folder'), '另一个分类');
  assert.equal(app.api.status().pending, false);
  const migrating = fixture({ snapshot: { exists: false, revision: null }, cache: { 'bm-folder': '分类', 'bm-skin': 'snow' } });
  await migrating.api.flush();
  assert.deepEqual(migrating.calls[0].body.changes, { 'bm-skin': 'snow' });
});

test('导入配置整体替换，之后的修改以导入结果为基准', async () => {
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: { 'bm-skin': 'snow' } } });
  await app.api.importDocument({ format: 1, values: { 'bm-skin': 'paper' } });
  assert.deepEqual(app.calls[0].body, { values: { 'bm-skin': 'paper' } });
  app.store.setItem('bm-skin', 'abyss');
  await app.api.flush();
  assert.deepEqual(app.calls[1].body, { changes: { 'bm-skin': 'abyss' }, base: { 'bm-skin': 'paper' } });
});

test('失败后的刷新保留独立副本，磁盘配置照常加载且不同安装目录隔离', async () => {
  const snapshot = { exists: true, revision: 'old', installation: 'one', values: { 'bm-skin': 'snow' } };
  const app = fixture({ snapshot, failure: 'offline' });
  app.store.setItem('bm-skin', 'paper');
  await app.api.flush();
  const cache = Object.fromEntries(app.saved);
  const reloaded = fixture({ snapshot, cache });
  assert.equal(reloaded.store.getItem('bm-skin'), 'snow');
  assert.equal(reloaded.api.drafts().length, 1);
  assert.equal(reloaded.api.exportDocument(reloaded.api.drafts()[0].id).values['bm-skin'], 'paper');
  assert.equal(fixture({ snapshot: { ...snapshot, installation: 'two' }, cache }).api.drafts().length, 0);
  await reloaded.api.flush();
  assert.equal(reloaded.calls.length, 0);
});

test('成功保存只清除本页副本，旧页面未保存副本仍可导出', async () => {
  const id = 'bm-preferences-draft:one:previous';
  const app = fixture({ snapshot: { exists: true, installation: 'one', values: {} },
    cache: { [id]: JSON.stringify({ format: 1, values: { 'bm-skin': 'paper' }, created: 1 }) } });
  app.store.setItem('bm-skin', 'snow');
  assert.equal(app.api.drafts().length, 2);
  await app.api.flush();
  assert.equal(app.api.drafts().length, 1);
  assert.equal(app.api.drafts()[0].id, id);
});

test('排队保存第二次失败时仍保留包含全部修改的副本', async () => {
  let release;
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: {} },
    responder: async body => {
      if (!('bm-skin' in body.changes)) throw Error('offline');
      await new Promise(resolve => { release = resolve; });
      return { ok: true, json: async () => ({}) };
    } });
  app.store.setItem('bm-skin', 'paper');
  const saving = app.api.flush();
  app.store.setItem('bm-layout', 'compact');
  release();
  assert.equal(await saving, false);
  const exported = app.api.exportDocument(app.api.drafts()[0].id);
  assert.equal(exported.values['bm-skin'], 'paper');
  assert.equal(exported.values['bm-layout'], 'compact');
});

test('恢复前先保存本页改动，恢复期间阻止后台修改和重复导入', async () => {
  let release;
  const app = fixture({ snapshot: { exists: true, revision: 'old', values: {} },
    responder: async body => {
      if (body.id) await new Promise(resolve => { release = resolve; });
      return { ok: true, json: async () => ({ values: { 'bm-skin': 'paper' } }) };
    } });
  app.store.setItem('bm-skin', 'snow');
  const restoring = app.api.restore('backup');
  assert.throws(() => app.store.setItem('bm-city', '{"name":"Shanghai"}'), /正在恢复/);
  await assert.rejects(app.api.importDocument({ format: 1, values: {} }), /正在恢复/);
  for (let i = 0; i < 10 && !release; i++) await Promise.resolve();
  assert.deepEqual(app.calls[0].body.changes, { 'bm-skin': 'snow' });
  assert.deepEqual(app.calls[1].body, { id: 'backup' });
  assert.equal(app.api.status().pending, true);
  release();
  await restoring;
  assert.equal(app.api.status().pending, false);
  assert.equal(app.store.getItem('bm-skin'), 'paper');
  assert.equal(app.calls.length, 2);
});

test('副本存储不可用时明确提示先导出再关闭', async () => {
  const app = fixture({ snapshot: { exists: true, values: {} }, storageDenied: true, failure: 'offline' });
  app.store.setItem('bm-skin', 'snow');
  await app.api.flush();
  assert.match(app.api.status().message, /浏览器无法保留/);
});
