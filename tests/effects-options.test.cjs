const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const NEW_MOTIONS = ['flip', 'shake', 'zoom', 'slide', 'twist', 'blink', 'drift', 'heartbeat'];
const NEW_TRAILS = ['sparks', 'ribbon', 'notes', 'pixels', 'crystal', 'ink', 'hearts', 'smoke'];
const NEW_SKYS = ['aurora', 'bubbles', 'fireworks', 'matrix', 'nebula', 'ripples', 'beams', 'confetti'];

function effectsFixture({ reduceMotion = false } = {}) {
  const gradient = { addColorStop() {} };
  let draws = 0;
  const ctx = {
    setTransform() {}, clearRect() { draws++; }, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {},
    arc() {}, ellipse() {}, save() {}, restore() {}, translate() {}, rotate() {}, scale() {}, fillRect() {},
    closePath() {}, quadraticCurveTo() {}, bezierCurveTo() {}, fillText() {},
    createLinearGradient: () => gradient, createRadialGradient: () => gradient
  };
  const root = { dataset: { fx: 'on', skin: 'aurora', trail: 'stardust', sky: 'none' } };
  const weatherScene = { hidden: true, dataset: {} };
  const elements = new Map([
    ['fx-canvas', { width: 0, height: 0, getContext: () => ctx }],
    ['weatherScene', weatherScene]
  ]);
  const element = id => elements.get(id) || { value: '', textContent: '', addEventListener() {} };
  const context = vm.createContext({
    console,
    document: { documentElement: root, getElementById: element },
    window: { devicePixelRatio: 1, addEventListener() {}, dispatchEvent() {} },
    localStorage: { getItem: () => null, setItem() {} },
    matchMedia: query => ({ matches: query.includes('prefers-reduced-motion') && reduceMotion, addEventListener() {} }),
    innerWidth: 960, innerHeight: 640,
    requestAnimationFrame: () => 1, cancelAnimationFrame() {},
    setTimeout: callback => { callback(); return 1; }, clearTimeout() {},
    Date
  });
  const js = file => fs.readFileSync(path.join(__dirname, '../web/js', file), 'utf8');
  vm.runInContext(js('config.js'), context, { filename: 'config.js' });
  vm.runInContext(js('effects.js'), context, { filename: 'effects.js' });
  return { run: code => vm.runInContext(code, context), root, draws: () => draws, context };
}

test('三类特效各新增八项并保留关闭选项', () => {
  const app = effectsFixture();
  assert.deepEqual(Array.from(app.run('MOTIONS.map(x => x.id)')).slice(-9), [...NEW_MOTIONS, 'still']);
  assert.deepEqual(Array.from(app.run('TRAILS.map(x => x.id)')).slice(-9), [...NEW_TRAILS, 'none']);
  assert.deepEqual(Array.from(app.run('SKYS.map(x => x.id)')).slice(-9), [...NEW_SKYS, 'none']);
  assert.equal(app.run('MOTIONS.length + TRAILS.length + SKYS.length'), 48);
});

test('页面开关开启时所有动画不再被系统减少动态效果拆分门控', () => {
  const app = effectsFixture({ reduceMotion: true });
  assert.equal(app.run('motionOk()'), true);
  app.root.dataset.fx = 'off';
  assert.equal(app.run('motionOk()'), false);
});

test('八种新鼠标拖尾都能生成并完成首帧绘制', () => {
  const hostRandom = Math.random;
  const app = effectsFixture();
  app.run('Math.random = () => 0.1');
  assert.equal(Math.random, hostRandom);
  for (const id of NEW_TRAILS) {
    app.root.dataset.trail = id;
    assert.equal(app.run('starTrail.length = 0; spawnTrail(120, 90); starTrail[0] && starTrail[0].kind'), id);
    assert.doesNotThrow(() => app.run('skyType = null; skyRunning = true; skyLast = 0; skyFrame(16.7)'));
  }
});

test('未知拖尾类型不会静默降级成星尘', () => {
  const app = effectsFixture();
  app.root.dataset.trail = 'unknown';
  assert.equal(app.run('spawnTrail(120, 90)'), false);
  assert.equal(app.run('starTrail.length'), 0);
});

test('八种新背景都能创建粒子并完成首帧绘制', () => {
  const app = effectsFixture();
  for (const id of NEW_SKYS) {
    app.root.dataset.sky = id;
    assert.doesNotThrow(() => app.run(`skyType = ${JSON.stringify(id)}; skyPopulate(); skyRunning = true; skyLast = 0; skyFrame(16.7)`));
    assert.ok(app.run('skyDrops.length') > 0, id + ' should create particles');
  }
});

test('新图标动效同时具有列表预览与书签卡片动画规则', () => {
  const appearanceJs = fs.readFileSync(path.join(__dirname, '../web/js/appearance.js'), 'utf8');
  const appearanceCss = fs.readFileSync(path.join(__dirname, '../web/css/appearance.css'), 'utf8');
  const motionCss = fs.readFileSync(path.join(__dirname, '../web/css/motion.css'), 'utf8');
  for (const id of NEW_MOTIONS) {
    assert.match(appearanceJs, new RegExp('\\n  ' + id + ': `'));
    assert.match(motionCss, new RegExp('data-motion="' + id + '"'));
  }
  for (const preview of ['flip', 'jitter', 'focus', 'glide', 'twist', 'flash', 'drift', 'heart']) {
    assert.match(appearanceCss, new RegExp('motion-' + preview));
  }
});

const script = file => fs.readFileSync(path.join(__dirname, '../web/js', file), 'utf8');

function bootstrapFx({ reduceMotion, stored }) {
  const storage = new Map(stored ? [['bm-fx', stored]] : []);
  const root = { dataset: { fx: 'on' } };
  const context = vm.createContext({
    URL, location: { href: 'http://127.0.0.1:8765/index.html' }, history: { replaceState() {} },
    localStorage: { getItem: key => storage.get(key) ?? null },
    matchMedia: query => ({ matches: query.includes('prefers-reduced-motion') && reduceMotion }),
    document: { documentElement: root, createElement: () => ({}), head: { appendChild() {} } }
  });
  vm.runInContext(script('bootstrap.js'), context, { filename: 'bootstrap.js' });
  return root.dataset.fx;
}

test('系统要求减少动态效果且未手动选择时默认关闭，手动选择始终优先', () => {
  assert.equal(bootstrapFx({ reduceMotion: true }), 'off');
  assert.equal(bootstrapFx({ reduceMotion: false }), 'on');
  assert.equal(bootstrapFx({ reduceMotion: true, stored: 'on' }), 'on');
  assert.equal(bootstrapFx({ reduceMotion: false, stored: 'off' }), 'off');
});

function fxChoice({ stored, fx = 'on' } = {}) {
  const storage = new Map(stored ? [['bm-fx', stored]] : []);
  const handlers = new Map();
  let mediaChange;
  const root = { dataset: { fx } };
  const context = vm.createContext({
    Event: class { constructor(type) { this.type = type; } },
    window: { dispatchEvent() {} },
    document: {
      documentElement: root, querySelector: () => null,
      getElementById: id => ({ innerHTML: '', querySelectorAll: () => [], addEventListener: (type, callback) => handlers.set(id + ':' + type, callback) })
    },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    matchMedia: () => ({ matches: false, addEventListener: (type, callback) => { mediaChange = callback; } })
  });
  for (const file of ['config.js', 'appearance.js']) vm.runInContext(script(file), context, { filename: file });
  vm.runInContext('setupChoice(FX, "fx", "fxChoices")', context);
  return {
    storage, root,
    choose: value => handlers.get('fxChoices:click')({ target: { closest: () => ({ dataset: { value } }) } }),
    setReducedMotion: matches => mediaChange({ matches })
  };
}

test('加载时不把默认值写入本地存储，系统设置变化后仍能跟随；点击选择才保存', () => {
  const app = fxChoice({ fx: 'off' });
  assert.equal(app.root.dataset.fx, 'off');
  assert.equal(app.storage.has('bm-fx'), false);
  app.setReducedMotion(false);
  assert.equal(app.root.dataset.fx, 'on');
  app.setReducedMotion(true);
  assert.equal(app.root.dataset.fx, 'off');
  assert.equal(app.storage.has('bm-fx'), false);
  app.choose('on');
  assert.equal(app.root.dataset.fx, 'on');
  assert.equal(app.storage.get('bm-fx'), 'on');
  app.setReducedMotion(true);
  assert.equal(app.root.dataset.fx, 'on', '手动选择后不再受系统设置变化影响');
  assert.equal(fxChoice({ stored: 'broken' }).storage.get('bm-fx'), 'on', '无效的保存值会被纠正');
});

test('高刷屏幕上背景最多每秒绘制 60 帧，慢速环境特效和后台窗口 30 帧', () => {
  const frames = (sky, focused, hz) => {
    const app = effectsFixture();
    app.context.document.hasFocus = () => focused;
    app.run(`skyType = ${JSON.stringify(sky)}; skyPopulate(); skyRunning = true; skyLast = 0`);
    for (let i = 1; i <= hz; i++) app.run(`skyFrame(${(i * 1000 / hz).toFixed(3)})`);
    return app.draws();
  };
  assert.ok(Math.abs(frames('rain', true, 144) - 60) <= 2, 'rain at 144 Hz: ' + frames('rain', true, 144));
  assert.ok(Math.abs(frames('rain', true, 60) - 60) <= 1, '60 Hz 屏幕不丢帧');
  assert.ok(Math.abs(frames('stars', true, 120) - 30) <= 2);
  assert.ok(Math.abs(frames('rain', false, 120) - 30) <= 2);
});
