const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'web/js/update.js'), 'utf8');
const response = (data, ok = true) => ({ ok, json: async () => data });

function streamResponse() {
  const chunks = [];
  let resume, released = false;
  const push = chunk => resume ? (resume(chunk), resume = null) : chunks.push(chunk);
  return {
    ok: true,
    headers: { get: () => 'application/x-ndjson; charset=utf-8' },
    body: { getReader: () => ({
      read: () => chunks.length ? Promise.resolve(chunks.shift()) : new Promise(resolve => { resume = resolve; }),
      releaseLock: () => { released = true; }
    }) },
    event: event => push({ value: Buffer.from(JSON.stringify(event) + '\n'), done: false }),
    bytes: value => push({ value, done: false }),
    end: () => push({ done: true }),
    released: () => released
  };
}

function fixture(routes, confirmed = true) {
  const handlers = new Map();
  const calls = [];
  const timers = [];
  const intervals = [];
  const confirmations = [];
  let reloads = 0;
  const elements = new Map([
    ['updateNotice', { hidden: true }],
    ['appVersion', { textContent: 'v1.0.4' }],
    ['updateBtn', {
      disabled: false, title: '', dataset: {}, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(type, handler) { handlers.set(type, handler); }
    }]
  ]);
  const element = () => ({
    hidden: true, dataset: {}, attributes: {}, textContent: '',
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(type, handler) { this[type] = handler; }
  });
  for (const suffix of ['', 'Title', 'Source', 'Message', 'Hint', 'Close', 'Steps']) {
    elements.set('updateProgress' + suffix, element());
  }
  elements.get('updateProgressSteps').children = Array.from({ length: 4 }, element);
  const fetchMock = async (url, options = {}) => {
    calls.push({ url, options });
    const result = routes.shift();
    if (result instanceof Error) throw result;
    return result;
  };
  const context = vm.createContext({
    TextDecoder,
    document: { getElementById: id => elements.get(id) },
    window: {
      confirm: message => { confirmations.push(message); return confirmed; },
      setTimeout: (callback, ms) => { timers.push({ callback, ms }); },
      setInterval: (callback, ms) => { intervals.push({ callback, ms }); },
      location: { reload: () => { reloads++; } }
    },
    fetch: fetchMock,
    fetchJson: async url => (await fetchMock(url)).json()
  });
  vm.runInContext(source, context, { filename: 'update.js' });
  vm.runInContext('initUpdate()', context);
  return {
    calls, elements, timers, intervals, confirmations,
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
  const app = fixture([response({ available: true, can_update: true, remote: 'abc1234', version: 'v1.0.4', source: 'Gitee' })]);
  await app.settled();
  assert.equal(app.elements.get('updateNotice').hidden, false);
  assert.match(app.elements.get('updateBtn').title, /abc1234/);
  assert.match(app.elements.get('updateBtn').title, /Gitee/);
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.4');
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
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.4');
  assert.equal(app.calls.length, 1);
});

test('后台版本落后时自动等待接管，不要求用户确认或执行 Git 更新', async () => {
  const app = fixture([
    response({ restarting: true, version: 'v1.0.1', instance: 'old' }),
    response({ instance: 'old' }),
    response({ instance: 'new' })
  ], false);
  await app.settled();
  assert.equal(app.elements.get('appVersion').textContent, 'v1.0.4');
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

test('证书失败显示具体提示，点击只重新检查，恢复后才允许确认升级', async () => {
  for (const error of ['certificate_error', 'tls_backend']) {
    const app = fixture([
      response({ error, reason: 'Gitee：证书验证失败' }, false),
      response({ available: true, can_update: true, remote: 'new1234', source: 'GitHub' }),
      response({ ok: true, updated: false })
    ]);
    await app.settled();
    assert.equal(app.elements.get('updateNotice').hidden, false);
    assert.equal(app.elements.get('updateBtn').dataset.state, 'error');
    assert.match(app.elements.get('updateBtn').title, /证书验证失败.*重新检查/);
    await app.click();
    assert.equal(app.calls[1].options.method, undefined, '错误点不能直接发起安装');
    assert.equal(app.elements.get('updateBtn').dataset.state, 'ready');
    await app.click();
    assert.equal(app.calls[2].options.method, 'POST');
  }
});

test('普通网络故障仍静默，证书恢复且无更新时清除错误提示', async () => {
  const quiet = fixture([response({ error: 'sources_unavailable', reason: '网络不可用' }, false)]);
  await quiet.settled();
  assert.equal(quiet.elements.get('updateNotice').hidden, true);
  const app = fixture([
    response({ error: 'certificate_error', reason: '证书验证失败' }, false),
    response({ available: false, can_update: true })
  ]);
  await app.settled();
  await app.intervals[0].callback();
  assert.equal(app.elements.get('updateNotice').hidden, true);
});

test('旧检查的证书错误不能覆盖正在安装的状态', async () => {
  let finish;
  const app = fixture([
    response({ available: true, can_update: true, remote: 'new1234' }),
    new Promise(resolve => { finish = resolve; }),
    response({ ok: true, updated: false })
  ]);
  await app.settled();
  const checking = app.intervals[0].callback();
  await app.click();
  finish(response({ error: 'certificate_error', reason: '旧检查错误' }, false));
  await checking;
  assert.equal(app.elements.get('updateNotice').hidden, true);
  assert.notEqual(app.elements.get('updateBtn').dataset.action, 'check');
});

test('页面全天无操作也每小时检查版本，不自动安装或重载网页', async () => {
  const app = fixture([
    response({ available: false, can_update: true }),
    ...Array.from({ length: 24 }, () => response({ available: true, can_update: true, remote: 'new1234', source: 'Gitee' }))
  ]);
  await app.settled();
  assert.equal(app.calls.length, 1, '打开页面立即检查');
  assert.equal(app.intervals.length, 1);
  assert.equal(app.intervals[0].ms, 3600000);
  for (let cycle = 0; cycle < 24; cycle++) await app.intervals[0].callback();
  assert.equal(app.calls.length, 25);
  assert.ok(app.calls.every(call => call.url === '/__update' && !call.options.method));
  assert.equal(app.elements.get('updateNotice').hidden, false);
  assert.equal(app.reloads(), 0);
});

test('上一次检查未完成时跳过周期触发，完成后正常检查', async () => {
  let finish;
  const app = fixture([
    new Promise(resolve => { finish = resolve; }),
    response({ available: false, can_update: true })
  ]);
  await app.intervals[0].callback();
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 1);
  finish(response({ available: false, can_update: true }));
  await app.settled();
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 2);
});

test('网络失败或 HTTP 错误后，下一个周期仍继续检查', async () => {
  for (const failure of [new Error('offline'), response({}, false)]) {
    const app = fixture([failure, response({ available: true, can_update: true, remote: 'new1234', source: 'GitHub' })]);
    await app.settled();
    await app.intervals[0].callback();
    assert.equal(app.calls.length, 2);
    assert.match(app.elements.get('updateBtn').title, /GitHub/);
  }
});

test('周期检查发现没有可安装更新时，清除上次的过期提示', async () => {
  const app = fixture([
    response({ available: true, can_update: true, remote: 'new1234' }),
    response({ available: false, can_update: true })
  ]);
  await app.settled();
  await app.intervals[0].callback();
  assert.equal(app.elements.get('updateNotice').hidden, true);
});

test('安装期间和等待新后台就绪期间，定时检查不会发送请求', async () => {
  let finish;
  const app = fixture([
    response({ available: true, can_update: true, remote: 'new1234' }),
    new Promise(resolve => { finish = resolve; }),
    response({ instance: 'new' })
  ]);
  await app.settled();
  const installation = app.click();
  await app.settled();
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 2);
  finish(response({ ok: true, updated: true, instance: 'old' }));
  await app.settled();
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 2);
  await app.runTimer();
  await installation;
  assert.equal(app.reloads(), 1);
});

test('安装前发出的周期检查晚到，不会覆盖安装结果', async () => {
  let finish;
  const app = fixture([
    response({ available: true, can_update: true, remote: 'new1234' }),
    new Promise(resolve => { finish = resolve; }),
    response({ ok: true, updated: false }),
    response({ available: false, can_update: true })
  ]);
  await app.settled();
  const checking = app.intervals[0].callback();
  await app.click();
  assert.equal(app.elements.get('updateNotice').hidden, true);
  finish(response({ available: true, can_update: true, remote: 'stale' }));
  await checking;
  assert.equal(app.elements.get('updateNotice').hidden, true);
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 4, '安装与旧检查结束后恢复定时检查');
});

test('安装失败后恢复定时检查，等待后台自动接管时不重复检查', async () => {
  const app = fixture([
    response({ available: true, can_update: true, remote: 'new1234' }),
    response({ ok: false, message: '升级失败' }, false),
    response({ restarting: true, instance: 'old' }),
    response({ instance: 'new' })
  ]);
  await app.settled();
  await app.click();
  const checking = app.intervals[0].callback();
  await app.settled();
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 3);
  assert.match(app.elements.get('updateBtn').title, /自动重启/);
  await app.runTimer();
  await checking;
  assert.equal(app.reloads(), 1);
});

test('实时显示同步与回退来源，未收到完成结果前不提前重启', async () => {
  const stream = streamResponse();
  const app = fixture([
    response({ available: true, can_update: true }), stream, response({ instance: 'new' })
  ]);
  await app.settled();
  const installation = app.click();
  await app.settled();
  assert.equal(app.calls[1].options.headers.Accept, 'application/x-ndjson');
  for (const event of [
    { stage: 'checking', message: '检查本地修改' },
    { stage: 'fetching', source: 'Gitee', message: '正在同步' },
    { stage: 'fetching', source: 'GitHub', message: '切换至 GitHub 同步代码' },
    { stage: 'applying', source: 'GitHub', message: '应用代码' }
  ]) {
    stream.event({ type: 'progress', ...event });
    await app.settled();
    assert.equal(app.elements.get('updateProgress').dataset.stage, event.stage);
    assert.equal(app.elements.get('updateProgressMessage').textContent, event.message);
    assert.equal(app.elements.get('updateProgressClose').hidden, true);
    assert.equal(app.reloads(), 0);
    assert.equal(app.timers.length, 0);
  }
  assert.equal(app.elements.get('updateProgressSource').textContent, '更新源 · GitHub');
  await app.intervals[0].callback();
  assert.equal(app.calls.length, 2, '读取进度期间不并发检查');
  stream.event({ type: 'result', ok: true, updated: true, instance: 'old', source: 'GitHub' });
  stream.end();
  await app.settled();
  assert.equal(app.elements.get('updateProgress').dataset.stage, 'restarting');
  await app.runTimer();
  await installation;
  assert.equal(app.reloads(), 1);
  assert.ok(stream.released());
  assert.ok(app.elements.get('updateProgressSteps').children.every(step => step.dataset.state === 'done'));
});

test('中文跨字节分块、多个帧与无末尾换行都正确解析', async () => {
  const stream = streamResponse();
  const app = fixture([response({ available: true, can_update: true }), stream]);
  await app.settled();
  const installation = app.click();
  const bytes = Buffer.from(JSON.stringify({ type: 'progress', stage: 'fetching', source: 'Gitee', message: '同步中文代码' }) + '\n');
  for (const byte of bytes) stream.bytes(Uint8Array.of(byte));
  await app.settled();
  assert.equal(app.elements.get('updateProgressMessage').textContent, '同步中文代码');
  stream.bytes(Buffer.from('\n' + JSON.stringify({ type: 'result', ok: true, updated: false })));
  stream.end();
  await installation;
  assert.equal(app.elements.get('updateProgress').dataset.stage, 'current');
  assert.deepEqual(app.elements.get('updateProgressSteps').children.map(step => step.dataset.state), ['done', 'done', 'pending', 'pending']);
  assert.ok(app.elements.get('updateProgressSteps').children.every(step => !step.attributes['aria-current']));
  assert.equal(app.reloads(), 0);
  assert.equal(app.elements.get('updateProgressClose').hidden, false);
  app.elements.get('updateProgressClose').click();
  assert.equal(app.elements.get('updateProgress').hidden, true);
});

test('服务错误、连接截断和损坏帧显示失败而不是虚假的完成', async () => {
  for (const failure of ['server', 'missing', 'malformed']) {
    const stream = streamResponse();
    const app = fixture([response({ available: true, can_update: true }), stream]);
    await app.settled();
    const installation = app.click();
    stream.event({ type: 'progress', stage: 'fetching', source: 'Gitee', message: '同步中' });
    stream.event({ type: 'progress', stage: 'unexpected', message: '不应显示' });
    await app.settled();
    assert.equal(app.elements.get('updateProgressMessage').textContent, '同步中');
    if (failure === 'server') stream.event({ type: 'error', message: '证书验证失败' });
    if (failure === 'malformed') stream.bytes(Buffer.from('{invalid\n'));
    stream.end();
    await installation;
    assert.equal(app.elements.get('updateProgress').dataset.stage, 'error');
    assert.equal(app.elements.get('updateProgressClose').hidden, false);
    assert.equal(app.elements.get('updateBtn').disabled, false);
    assert.equal(app.reloads(), 0);
    assert.equal(app.timers.length, 0);
    assert.ok(stream.released());
    if (failure === 'server') assert.equal(app.elements.get('updateProgressMessage').textContent, '证书验证失败');
    if (failure === 'missing') assert.match(app.elements.get('updateProgressMessage').textContent, /连接中断/);
  }
});

test('取消确认不请求升级、不打开进度浮层', async () => {
  const app = fixture([response({ available: true, can_update: true })], false);
  await app.settled();
  await app.click();
  assert.equal(app.calls.length, 1);
  assert.equal(app.elements.get('updateProgress').hidden, true);
});

test('ZIP 安装提示免 Git 更新及备份，Git 安装仍提示本地修改保护', async () => {
  for (const mode of ['archive', 'git']) {
    const app = fixture([response({ available: true, can_update: true, remote: 'v1.0.5', mode })], false);
    await app.settled();
    await app.click();
    if (mode === 'archive') {
      assert.match(app.confirmations[0], /无需安装 Git/);
      assert.match(app.confirmations[0], /私人书签和外观设置会保留/);
      assert.match(app.confirmations[0], /程序文件会被替换并备份/);
    } else {
      assert.match(app.confirmations[0], /存在未提交的本地代码修改时会取消升级/);
    }
    assert.equal(app.calls.length, 1);
  }
});
