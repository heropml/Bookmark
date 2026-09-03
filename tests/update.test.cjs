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
    ['appVersion', { textContent: 'v1.0.3' }],
    ['updateBtn', {
      disabled: false, title: '', dataset: {}, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(type, handler) { handlers.set(type, handler); }
    }]
  ]);
  const fetchMock = async (url, options = {}) => {
    calls.push({ url, options });
    const result = routes.shift();
    if (result instanceof Error) throw result;
    return result;
  };
  const context = vm.createContext({
    document: { getElementById: id => elements.get(id) },
    window: {
      confirm: () => confirmed,
      setTimeout: (callback, ms) => { timers.push({ callback, ms }); },
      location: { reload: () => { reloads++; } }
    },
    fetch: fetchMock,
    fetchJson: async url => (await fetchMock(url)).json()
  });
  vm.runInContext(source, context, { filename: 'update.js' });
  vm.runInContext('initUpdate()', context);
  return {
    calls, elements, timers,
    async settled() { await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve)); },
    async click() { await handlers.get('click')(); },
    async runTimer() {
      const timer = timers.shift();
      assert.ok(timer, '应存在等待服务启动的定时器');
      timer.callback();
      await this.settled();
    },
    reloads: () => reloads
  };
}

test('发现新版时在版本号后显示可点击的升级状态点', async () => {
  const app = fixture([response({ available: true, can_update: true, remote: 'abc1234', version: 'v1.0.3' })]);
  await app.settled();
  assert.equal(app.elements.get('updateNotice').hidden, false);
  assert.match(app.elements.get('updateBtn').title, /abc1234/);
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.3');
});

test('确认升级后请求完整仓库更新并在服务重启后刷新页面', async () => {
  const app = fixture([
    response({ available: true, can_update: true, remote: 'abc1234' }),
    response({ ok: true, updated: true, current: 'abc1234', instance: 'old' }),
    response({ instance: 'old' }),
    new Error('connection refused'),
    response({ instance: 'new' })
  ]);
  await app.settled();
  const installation = app.click();
  await app.settled();
  assert.equal(app.calls[1].url, '/__update');
  assert.equal(app.calls[1].options.method, 'POST');
  assert.equal(app.elements.get('updateBtn').title, '升级完成，正在重启…');
  assert.equal(app.timers[0].ms, 500);
  await app.runTimer();
  assert.equal(app.reloads(), 0, '旧服务还在线不能当作重启完成');
  await app.runTimer();
  assert.equal(app.reloads(), 0, '服务尚未监听时不能刷新成连接失败页面');
  await app.runTimer();
  await installation;
  assert.equal(app.reloads(), 1);
});

test('旧后台版本不会覆盖页面实际版本', async () => {
  const app = fixture([response({ available: false, version: 'v1.0.1' })]);
  await app.settled();
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.3');
  assert.equal(app.calls.length, 1);
});

test('后台版本落后时自动等待接管，不要求用户确认或执行 Git 更新', async () => {
  const app = fixture([
    response({ restarting: true, version: 'v1.0.1', instance: 'old' }),
    response({ instance: 'old' }),
    response({ instance: 'new' })
  ], false);
  await app.settled();
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.3');
  assert.equal(app.elements.get('updateBtn').disabled, true);
  assert.match(app.elements.get('updateBtn').title, /自动重启/);
  await app.runTimer();
  assert.equal(app.reloads(), 0);
  await app.runTimer();
  assert.equal(app.reloads(), 1);
  assert.ok(app.calls.every(call => !call.options.method), '自动接管不触发远端代码拉取');
});

test('重启失败有等待上限和明确提示，不循环刷新页面', async () => {
  const app = fixture([
    response({ restarting: true, instance: 'old' }),
    ...Array.from({ length: 20 }, () => response({ instance: 'old' }))
  ]);
  await app.settled();
  for (let attempt = 0; attempt < 20; attempt++) await app.runTimer();
  assert.equal(app.reloads(), 0);
  assert.equal(app.timers.length, 0);
  assert.match(app.elements.get('updateBtn').title, /重启未完成/);
});

test('检查不到新版时不显示任何提示', async () => {
  const app = fixture([response({ available: false, can_update: true })]);
  await app.settled();
  assert.equal(app.elements.get('updateNotice').hidden, true);
});
