const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture() {
  const opened = [];
  const renders = [];
  const documentHandlers = new Map();
  const elementHandlers = new Map();
  const reordered = [];
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      id, value: '', hidden: false, disabled: false, textContent: '', attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(type, handler) { elementHandlers.set(id + ':' + type, handler); }, focus() {}, dispatchEvent(event) { if (event.type === 'input') context.state.q = this.value; },
      querySelector: () => ({ textContent: '' }), querySelectorAll: () => [], replaceChildren() {}
    });
    return elements.get(id);
  };
  const search = element('q');
  const link = { getAttribute: () => 'https://first.example/', click: () => opened.push('https://first.example/'), focus() {} };
  const context = vm.createContext({
    Event: class { constructor(type) { this.type = type; } },
    state: { q: '', folder: '', searchLocal: false, shown: 36 },
    PAGE: 36,
    render: () => renders.push(true),
    pickFolder() {},
    handleIconLoad() {},
    handleIconError() {},
    reorderPinnedBookmark: (...args) => reordered.push(args),
    appearanceMenu: { hidden: true },
    localStorage: { getItem: () => null, setItem() {} },
    window: { dispatchEvent() {} },
    document: {
      documentElement: { dataset: {} },
      getElementById: element,
      querySelector: selector => selector === 'dialog[open]' ? null : selector === '#main a.card[href]' ? link : null,
      querySelectorAll: selector => selector === '#main a.card[href]' ? [link] : [],
      addEventListener: (type, handler) => documentHandlers.set(type, handler)
    }
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/js/library.js'), 'utf8'), context, { filename: 'library.js' });
  vm.runInContext('initLibrary()', context);
  const press = (key, extra = {}) => {
    const event = { key, target: search, prevented: false, preventDefault() { this.prevented = true; }, ...extra };
    documentHandlers.get('keydown')(event);
    return event;
  };
  return { context, search, opened, renders, press, elements, elementHandlers, reordered };
}

test('置顶图标沿用主页的加载成功与失败处理', () => {
  const app = fixture();
  assert.equal(app.elementHandlers.get('pinnedGrid:load'), app.context.handleIconLoad);
  assert.equal(app.elementHandlers.get('pinnedGrid:error'), app.context.handleIconError);
});

test('输入法选词时的回车和 Esc 交给输入法，不打开结果也不清空搜索', () => {
  const app = fixture();
  app.search.value = 'go';
  app.context.state.q = 'go';
  for (const extra of [{ isComposing: true }, { keyCode: 229 }]) {
    assert.equal(app.press('Enter', extra).prevented, false);
    app.press('Escape', extra);
  }
  assert.deepEqual(app.opened, []);
  assert.equal(app.search.value, 'go');
  assert.equal(app.context.state.q, 'go');
});

test('组字结束后回车打开第一个结果，Esc 清空搜索', () => {
  const app = fixture();
  app.search.value = 'go';
  app.context.state.q = 'go';
  assert.equal(app.press('Enter').prevented, true);
  assert.deepEqual(app.opened, ['https://first.example/']);
  app.press('Escape');
  assert.equal(app.search.value, '');
  assert.equal(app.context.state.q, '');
});

test('拖动只在放下时提交；取消和外部拖入不改变置顶', () => {
  const app = fixture();
  const card = url => {
    const classes = new Set();
    return { dataset: { pinnedUrl: url }, offsetWidth: 100, offsetHeight: 80, classes,
      classList: { add: value => classes.add(value), remove: (...values) => values.forEach(value => classes.delete(value)) },
      getBoundingClientRect: () => ({ left: 100, width: 100 }),
      closest(selector) { return selector === '[data-pinned-url]' ? this : null; }
    };
  };
  const source = card('source'), target = card('target');
  const fire = (type, node, x = 175) => app.elementHandlers.get('pinnedGrid:' + type)({
    target: node, clientX: x, preventDefault() {}, dataTransfer: { setData() {}, setDragImage() {} }
  });
  fire('dragover', target);
  fire('drop', target);
  assert.deepEqual(app.reordered, []);
  fire('dragstart', source);
  fire('dragover', target);
  assert.ok(target.classes.has('drop-after'));
  assert.deepEqual(app.reordered, []);
  fire('dragend', source);
  assert.equal(target.classes.size, 0);
  assert.equal(source.classes.size, 0);
  fire('dragstart', source);
  fire('dragover', target, 110);
  assert.ok(target.classes.has('drop-before'));
  fire('drop', target, 110);
  assert.deepEqual(app.reordered, [['source', 'target', false]]);
  assert.equal(source.classes.size, 0);
  assert.equal(target.classes.size, 0);
});

test('选中置顶卡片后 Alt+←/→ 移动一位并保持焦点；其他按键和边界不改变顺序', () => {
  const app = fixture();
  const focused = [];
  const pin = url => ({
    dataset: { pinnedUrl: url },
    closest(selector) { return selector === '[data-pinned-url]' ? this : null; },
    querySelector: selector => ({ focus: () => focused.push(url + ' ' + selector) })
  });
  const items = ['a', 'b', 'c'].map(pin);
  app.elements.get('pinnedGrid').querySelectorAll = () => items;
  const press = (item, key, extra = {}) => {
    const event = { key, altKey: true, target: item, prevented: false, preventDefault() { this.prevented = true; }, ...extra };
    app.elementHandlers.get('pinnedGrid:keydown')(event);
    return event;
  };
  assert.equal(press(items[0], 'ArrowRight').prevented, true);
  assert.deepEqual(app.reordered, [['a', 'b', true]]);
  assert.deepEqual(focused, ['a a.card'], '移动后焦点留在同一张卡片');
  press(items[2], 'ArrowLeft');
  assert.deepEqual(app.reordered.at(-1), ['c', 'b', false]);
  assert.equal(press(items[0], 'ArrowLeft').prevented, true, '已在最前时吞掉按键，避免触发浏览器后退');
  for (const extra of [{ altKey: false }, { ctrlKey: true }, { metaKey: true }, { shiftKey: true }]) {
    assert.equal(press(items[1], 'ArrowRight', extra).prevented, false);
  }
  assert.equal(press(items[1], 'ArrowUp').prevented, false);
  assert.equal(app.reordered.length, 2);
});

test('普通按键不扫描卡片列表，方向键仍在结果间移动', () => {
  const app = fixture();
  let scans = 0;
  const all = app.context.document.querySelectorAll;
  app.context.document.querySelectorAll = selector => { if (selector === '#main a.card[href]') scans++; return all(selector); };
  for (const key of ['a', 'b', 'Shift', 'Backspace']) app.press(key);
  assert.equal(scans, 0);
  assert.equal(app.press('ArrowDown').prevented, true);
  assert.equal(scans, 1);
});
