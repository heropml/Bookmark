const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture({ at = '2026-09-02T03:04:05', focused = false, hidden = false, motion = true } = {}) {
  let timestamp = new Date(at).getTime();
  const intervals = [], animations = [], elements = new Map(), listeners = new Map();
  const span = text => ({ textContent: text,
    getAnimations() { return animations.filter(a => a.target === this && !a.cancelled); },
    animate(frames, options) {
      const animation = { target: this, frames, options, onfinish: null, cancelled: false,
        cancel() { this.cancelled = true; } };
      animations.push(animation);
      return animation;
    }
  });
  const clock = { children: [], set innerHTML(value) { this.children = [...value.matchAll(/<span[^>]*>(.*?)<\/span>/g)].map(match => span(match[1])); } };
  elements.set('clock', clock);
  for (const id of ['greet', 'lunarDate', 'bgTime']) elements.set(id, { textContent: '' });
  const document = { hidden, hasFocus: () => focused, getElementById: id => elements.get(id),
    addEventListener: (type, handler) => listeners.set(type, handler) };
  const context = vm.createContext({
    Date: class extends Date {
      constructor(...args) { super(...(args.length ? args : [timestamp])); }
      static now() { return timestamp; }
    },
    Intl, document,
    window: { addEventListener: (type, handler) => listeners.set(type, handler) },
    setInterval: (callback, delay) => intervals.push({ callback, delay }),
    motionOk: () => motion,
    weatherScene: { dataset: { period: 'day' } }, weatherPeriod: () => 'day', syncParticles() {}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/js/clock.js'), 'utf8'), context);
  return { elements, intervals, animations, document, listeners,
    run: code => vm.runInContext(code, context),
    time: () => clock.children.map(el => el.textContent).join(''),
    setTime(value) { timestamp = new Date(value).getTime(); },
    setFocus(value) { focused = value; },
    emit(type) { listeners.get(type)(); }
  };
}

test('时钟初始化为八位并补齐时分秒，每秒读取当前时间', () => {
  const app = fixture();
  assert.equal(app.time(), '--:--:--');
  app.run('initClock()');
  assert.equal(app.time(), '03:04:05');
  assert.equal(app.intervals.length, 1);
  assert.equal(app.intervals[0].delay, 1000);
  app.setTime('2026-09-02T03:04:06');
  app.intervals[0].callback();
  assert.equal(app.time(), '03:04:06');
  app.setTime('2026-09-02T03:05:17');
  app.intervals[0].callback();
  assert.equal(app.time(), '03:05:17', '定时器延后时不能靠累加秒数计时');
});

test('公历包含年、月、日和星期，农历包含干支年月日和问候语', () => {
  const app = fixture();
  app.run('initClock()');
  assert.equal(app.elements.get('greet').textContent, '2026年9月2日 星期三');
  assert.equal(app.elements.get('lunarDate').textContent, '丙午年七月廿一 · 夜深了');
  assert.equal(app.elements.get('bgTime').textContent, '03:04');
});

// Dates checked against HKO's 2025/2026 Gregorian–lunar conversion tables.
test('跨春节午夜同步更新时间、公历和农历年份', () => {
  const app = fixture({ at: '2026-02-16T23:59:59' });
  app.run('initClock()');
  assert.match(app.elements.get('lunarDate').textContent, /乙巳年.*廿九/);
  app.setTime('2026-02-17T00:00:00');
  app.intervals[0].callback();
  assert.equal(app.time(), '00:00:00');
  assert.equal(app.elements.get('greet').textContent, '2026年2月17日 星期二');
  assert.equal(app.elements.get('lunarDate').textContent, '丙午年正月初一 · 夜深了');
});

test('农历保留闰月，正确显示初十、二十、三十', () => {
  const app = fixture();
  for (const [date, expected] of [
    ['2025-07-25T12:00:00', '乙巳年闰六月初一'],
    ['2025-08-23T12:00:00', '乙巳年七月初一'],
    ['2026-07-23T12:00:00', '丙午年六月初十'],
    ['2026-08-02T12:00:00', '丙午年六月二十'],
    ['2026-08-12T12:00:00', '丙午年六月三十']
  ]) assert.equal(app.run('lunarDateText(new Date(' + JSON.stringify(date) + '))'), expected);
});

test('页面失焦或隐藏时，秒钟直接更新，不依赖数字动画结束', () => {
  const app = fixture({ focused: true });
  app.run('initClock()');
  app.setFocus(false);
  app.setTime('2026-09-02T03:04:06');
  app.emit('blur');
  assert.equal(app.time(), '03:04:06');
  app.document.hidden = true;
  app.setTime('2026-09-02T03:04:07');
  app.emit('visibilitychange');
  assert.equal(app.time(), '03:04:07');
  assert.equal(app.animations.length, 0);
  app.document.hidden = false;
  app.setFocus(true);
  app.setTime('2026-09-02T03:06:00');
  app.emit('focus');
  assert.equal(app.time(), '03:06:00');
});

test('暂停的旧数字动画不能在恢复焦点时覆盖最新秒数', () => {
  const app = fixture({ focused: true });
  app.run('initClock()');
  app.setTime('2026-09-02T03:04:06');
  app.intervals[0].callback();
  assert.equal(app.animations.length, 1);
  assert.equal(typeof app.animations[0].onfinish, 'function');
  app.setFocus(false);
  app.setTime('2026-09-02T03:04:08');
  app.emit('blur');
  assert.equal(app.time(), '03:04:08');
  assert.equal(app.animations[0].cancelled, true);
  assert.equal(app.animations[0].onfinish, null);
});

test('关闭动效时不创建秒钟动画；启用时只滚动变化的数字', () => {
  const quiet = fixture({ focused: true, motion: false });
  quiet.run('initClock()');
  quiet.setTime('2026-09-02T03:04:06');
  quiet.intervals[0].callback();
  assert.equal(quiet.time(), '03:04:06');
  assert.equal(quiet.animations.length, 0);
  const active = fixture({ focused: true });
  active.run('initClock()');
  active.setTime('2026-09-02T03:04:06');
  active.intervals[0].callback();
  assert.equal(active.animations.length, 1);
  active.animations[0].onfinish();
  assert.equal(active.time(), '03:04:06');
});
