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
  const ctx = {
    setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {},
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
  return { run: code => vm.runInContext(code, context), root };
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
