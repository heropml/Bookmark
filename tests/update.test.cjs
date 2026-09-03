const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'web/js/update.js'), 'utf8');
const response = (data, ok = true) => ({ ok, json: async () => data });

function fixture(routes, confirmed = true) {
  const handlers = new Map();
  const calls = [];
  const timers = [];
  let reloads = 0;
  const elements = new Map([
    ['updateNotice', { hidden: true }],
    ['appVersion', { textContent: 'v1.0.1' }],
    ['updateBtn', {
      disabled: false, title: '', dataset: {}, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(type, handler) { handlers.set(type, handler); }
    }]
  ]);
  const context = vm.createContext({
    document: { getElementById: id => elements.get(id) },
    window: {
      confirm: () => confirmed,
      setTimeout: (callback, ms) => { timers.push({ callback, ms }); },
      location: { reload: () => { reloads++; } }
    },
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      return routes.shift();
    }
  });
  vm.runInContext(source, context, { filename: 'update.js' });
  vm.runInContext('initUpdate()', context);
  return {
    calls, elements, timers,
    async settled() { await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve)); },
    async click() { await handlers.get('click')(); },
    reloads: () => reloads
  };
}

test('发现新版时在版本号后显示可点击的升级状态点', async () => {
  const app = fixture([response({ available: true, can_update: true, remote: 'abc1234', version: 'v1.0.1' })]);
  await app.settled();
  assert.equal(app.elements.get('updateNotice').hidden, false);
  assert.match(app.elements.get('updateBtn').title, /abc1234/);
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.1');
});

test('确认升级后请求完整仓库更新并在服务重启后刷新页面', async () => {
  const app = fixture([
    response({ available: true, can_update: true, remote: 'abc1234' }),
    response({ ok: true, updated: true, current: 'abc1234' })
  ]);
  await app.settled();
  await app.click();
  assert.equal(app.calls[1].url, '/__update');
  assert.equal(app.calls[1].options.method, 'POST');
  assert.equal(app.elements.get('updateBtn').title, '升级完成，正在重启…');
  assert.equal(app.timers[0].ms, 1200);
  app.timers[0].callback();
  assert.equal(app.reloads(), 1);
});

test('检查不到新版时不显示任何提示', async () => {
  const app = fixture([response({ available: false, can_update: true })]);
  await app.settled();
  assert.equal(app.elements.get('updateNotice').hidden, true);
});
