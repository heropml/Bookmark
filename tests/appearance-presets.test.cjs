const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(stored = {}) {
  const storage = new Map(Object.entries(stored));
  let storageFails = false;
  let renderCount = 0;
  let populationCount = 0;
  let activeElement = null;
  const events = [];
  const elements = new Map();
  const summaries = new Map();
  const media = new Map();
  class Element {
    constructor(tag = 'div') {
      this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {};
      this.attributes = {}; this.dataset = {}; this.textContent = ''; this.value = '';
      this.className = ''; this.hidden = true; this.classList = { toggle() {} };
      this.style = { setProperty() {} }; this._html = ''; this.queries = {};
    }
    set innerHTML(html) {
      this._html = html;
      if (this.className.includes('appearance-presets-section')) {
        for (const selector of ['form', 'input', 'ul', '.sync-status']) this.queries[selector] = new Element(selector);
        this.queries.form.queries.button = new Element('button');
      } else {
        this.children = [...html.matchAll(/data-value="([^"]+)"/g)].map(match => {
          const choice = new Element('button'); choice.dataset.value = match[1]; return choice;
        });
      }
    }
    get innerHTML() { return this._html; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(key, value) { this.attributes[key] = value; }
    getAttribute(key) { return this.attributes[key] ?? null; }
    querySelector(selector) {
      const setting = selector.match(/^\[data-setting(-panel)?="([^"]+)"\]$/);
      if (setting) return this.querySelectorAll(setting[1] ? '[data-setting-panel]' : '[data-setting]').find(child => child.dataset[setting[1] ? 'settingPanel' : 'setting'] === setting[2]) || null;
      return this.queries[selector] || this.querySelectorAll(selector)[0] || null;
    }
    querySelectorAll(selector) {
      if (selector === '.choice') return this.children;
      return this.children.flatMap(child => [...(child.tagName.toLowerCase() === selector || (selector === '[data-setting]' && child.dataset.setting) || (selector === '[data-setting-panel]' && child.dataset.settingPanel) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    closest(selector) { return selector === '[data-setting]' && this.dataset.setting ? this : null; }
    contains(child) { return child === this || this.children.some(item => item.contains(child)); }
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
    fire(type, event = {}) { for (const listener of this.listeners[type] || []) listener({ preventDefault() {}, ...event }); }
    focus() { activeElement = this; }
    click() { this.fire('click'); }
  }
  const element = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const root = new Element();
  root.dataset = { skin: 'aurora', icon: 'logo', layout: 'classic', motion: 'float', trail: 'stardust', sky: 'auto', fx: 'on', focus: 'off' };
  const body = new Element('body');
  const appearanceBody = new Element();
  element('appearancePanel').append(appearanceBody);
  element('appearancePanel').queries['.appearance-body'] = appearanceBody;
  const localStorage = {
    getItem: key => { if (storageFails) throw new Error('unavailable'); return storage.get(key) ?? null; },
    setItem: (key, value) => { if (storageFails) throw new Error('quota'); storage.set(key, String(value)); },
    removeItem: key => { if (storageFails) throw new Error('unavailable'); storage.delete(key); }
  };
  const context = vm.createContext({
    console, Event: class { constructor(type) { this.type = type; } },
    localStorage,
    fetch: () => Promise.resolve(),
    window: { dispatchEvent: event => events.push(event.type) },
    document: {
      documentElement: root, body, getElementById: element, createElement: tag => new Element(tag), addEventListener() {},
      querySelector: selector => {
        if (!summaries.has(selector)) summaries.set(selector, new Element());
        return summaries.get(selector);
      }
    },
    matchMedia: query => {
      if (!media.has(query)) media.set(query, { matches: false, listeners: [], addEventListener(type, listener) { this.listeners.push(listener); } });
      return media.get(query);
    },
    render: () => renderCount++, skyPopulate: () => populationCount++
  });
  const run = code => vm.runInContext(code, context);
  for (const file of ['config.js', 'appearance.js', 'appearance-presets.js']) run(fs.readFileSync(path.join(__dirname, '../web/js', file), 'utf8'));
  run(`let trailScale = 1, skyScale = 1, skyCount = 1;
    function setTrailSize(value) { trailScale = value; }
    function setSkySize(value) { skyScale = value; }
    function setSkyCount(value) { skyCount = value; }
    initAppearance(); initLayoutDensity(); initAppearancePresets();`);
  element('focusPreset').addEventListener('click', () => {
    root.dataset.focus = root.dataset.focus === 'on' ? 'off' : 'on';
    element('focusPreset').setAttribute('aria-pressed', String(root.dataset.focus === 'on'));
    try { localStorage.setItem('bm-focus', root.dataset.focus); } catch {}
  });
  const section = appearanceBody.children[0];
  const input = section.querySelector('input');
  const form = section.querySelector('form');
  const list = section.querySelector('ul');
  const status = section.querySelector('.sync-status');
  const trigger = element('appearanceCategories').children.at(-1);
  const open = () => {
    run('setAppearanceOpen(true)');
    trigger.click();
    element('appearanceCategories').fire('click', { target: trigger });
  };
  const save = name => { input.value = name; form.fire('submit'); };
  return {
    run, root, storage, events, elements, section, trigger, list, input, form, status, open, save,
    snapshot: () => JSON.parse(run('JSON.stringify(captureAppearanceSnapshot())')),
    setSnapshot: value => { context.nextSnapshot = value; return run('applyAppearanceSnapshot(nextSnapshot)'); },
    action: (row, index) => list.children[row].children[1].children[index].click(),
    failStorage: () => { storageFails = true; },
    activeElement: () => activeElement,
    setMedia: (query, matches) => { const mq = media.get(query); mq.matches = matches; mq.listeners.forEach(listener => listener({ matches })); },
    renderCount: () => renderCount, populationCount: () => populationCount
  };
}

test('外观方案复用设置面板，悬停不抢焦点，点击聚焦输入，关闭返回入口', () => {
  const app = fixture();
  const panel = app.elements.get('appearancePanel');
  const categories = app.elements.get('appearanceCategories');
  app.run('setAppearanceOpen(true)');
  const focusBeforeHover = app.activeElement();
  const event = { target: app.trigger, pointerType: 'mouse', relatedTarget: null };
  app.trigger.fire('pointerover', event);
  categories.fire('pointerover', event);
  assert.equal(panel.hidden, false);
  assert.equal(app.section.hidden, false);
  assert.equal(app.section.tagName, 'SECTION');
  assert.equal(app.trigger.getAttribute('aria-controls'), 'appearancePanel');
  assert.equal(app.trigger.getAttribute('aria-expanded'), 'true');
  assert.equal(app.elements.get('appearanceTitle').textContent, '外观方案');
  assert.equal(app.activeElement(), focusBeforeHover);
  app.trigger.click();
  categories.fire('click', { target: app.trigger });
  assert.equal(app.activeElement(), app.input);
  app.elements.get('appearanceClose').click();
  assert.equal(panel.hidden, true);
  assert.equal(app.section.hidden, true);
  assert.equal(app.trigger.getAttribute('aria-expanded'), 'false');
  assert.equal(app.elements.get('appearanceMenu').hidden, false);
  assert.equal(app.activeElement(), app.trigger);
  app.open();
  app.run('setAppearanceOpen(false)');
  assert.equal(panel.hidden, true);
  assert.equal(app.elements.get('appearanceMenu').hidden, true);
});

test('外观方案保存自动主题原值并保留系统动态效果偏好，仅读取外观字段', () => {
  const app = fixture({ 'bm-skin': 'auto', 'bm-pins': '["private"]', 'bm-folder': '私人分类' });
  const snapshot = app.snapshot();
  assert.equal(snapshot.skin, 'auto');
  assert.equal(snapshot.fxFollowsSystem, true);
  assert.deepEqual(Object.keys(snapshot).sort(), ['skin', 'icon', 'layout', 'motion', 'trail', 'sky', 'fx', 'fxFollowsSystem', 'density', 'focus', 'trailSize', 'skySize', 'skyCount'].sort());
  app.open(); app.save('常用');
  const saved = JSON.parse(app.storage.get('bm-appearance-presets'));
  assert.deepEqual(saved, [{ name: '常用', settings: snapshot }]);
  assert.equal(app.storage.get('bm-pins'), '["private"]');
  assert.equal(app.storage.get('bm-folder'), '私人分类');
});

test('应用方案同步控制器、密度、特效参数和专注按钮，并重新绘制布局', () => {
  const app = fixture();
  const expected = { ...app.snapshot(), skin: 'celadon', layout: 'table', icon: 'letter', density: 70, trailSize: 1.8, skySize: 2, skyCount: 1.25, focus: 'on', fx: 'off', fxFollowsSystem: false };
  assert.equal(app.setSnapshot(expected), true);
  assert.deepEqual(app.snapshot(), expected);
  assert.equal(app.elements.get('focusPreset').attributes['aria-pressed'], 'true');
  assert.equal(app.elements.get('layoutDensityReset').textContent, '70%');
  const tableChoice = app.elements.get('layoutChoices').children.find(button => button.dataset.value === 'table');
  assert.equal(tableChoice.attributes['aria-pressed'], 'true');
  assert.equal(app.storage.get('bm-card-density'), '70');
  assert.equal(app.storage.get('bm-sky-count'), '1.25');
  assert.equal(app.renderCount(), 1);
  assert.ok(app.populationCount() > 0);
  assert.equal(app.events.at(-1), 'bm-fx');
  app.elements.get('layoutDensityIn').click();
  assert.equal(app.snapshot().density, 80, '应用后现有加减按钮继续使用新值');
});

test('方案可以恢复自动配色和系统动态效果跟随，之后手动选择仍优先', () => {
  const app = fixture({ 'bm-fx': 'on', 'bm-skin': 'snow' });
  app.setMedia('(prefers-reduced-motion: reduce)', true);
  app.setSnapshot({ ...app.snapshot(), skin: 'auto', fxFollowsSystem: true });
  assert.equal(app.root.dataset.fx, 'off');
  assert.equal(app.storage.has('bm-fx'), false);
  app.setMedia('(prefers-color-scheme: light)', true);
  assert.equal(app.root.dataset.skin, 'snow');
  assert.equal(app.snapshot().skin, 'auto');
  app.setMedia('(prefers-reduced-motion: reduce)', false);
  assert.equal(app.root.dataset.fx, 'on');
  app.elements.get('fxChoices').fire('click', { target: { closest: () => ({ dataset: { value: 'off' } }) } });
  app.setMedia('(prefers-reduced-motion: reduce)', false);
  assert.equal(app.root.dataset.fx, 'off');
  assert.equal(app.snapshot().fxFollowsSystem, false);
});

test('打开和取消不改变外观，名称始终作为纯文本，同名保存不覆盖方案', () => {
  const app = fixture();
  const original = app.snapshot();
  app.open(); app.input.value = '未保存'; app.elements.get('appearanceClose').click();
  assert.deepEqual(app.snapshot(), original);
  assert.equal(app.storage.has('bm-appearance-presets'), false);
  app.open(); app.save('<img src=x onerror=alert(1)>');
  const title = app.list.children[0].children[0].children[0];
  assert.equal(title.textContent, '<img src=x onerror=alert(1)>');
  assert.equal(title.innerHTML, '');
  const saved = app.storage.get('bm-appearance-presets');
  app.save('<img src=x onerror=alert(1)>');
  assert.match(app.status.textContent, /名称已存在/);
  assert.equal(app.storage.get('bm-appearance-presets'), saved);
});

test('更新采用当前外观，应用恢复保存值，删除只移除所选方案', () => {
  const app = fixture();
  app.open(); app.save('一'); app.save('二');
  app.setSnapshot({ ...app.snapshot(), layout: 'board', density: 80 });
  app.action(0, 1);
  app.setSnapshot({ ...app.snapshot(), layout: 'classic', density: 100 });
  app.action(0, 0);
  assert.equal(app.snapshot().layout, 'board');
  assert.equal(app.snapshot().density, 80);
  app.action(0, 2);
  assert.deepEqual(JSON.parse(app.storage.get('bm-appearance-presets')).map(item => item.name), ['二']);
});

test('存储失败时不更新方案列表，并明确区分页面应用与持久保存失败', () => {
  const app = fixture();
  app.open(); app.save('已有');
  const saved = app.storage.get('bm-appearance-presets');
  app.failStorage();
  app.save('新方案');
  assert.match(app.status.textContent, /无法保存.*方案未更改/);
  assert.equal(app.storage.get('bm-appearance-presets'), saved);
  assert.equal(app.list.children.length, 1);
  app.action(0, 2);
  assert.equal(app.list.children.length, 1);
  app.action(0, 0);
  assert.match(app.status.textContent, /当前页面应用.*无法保存/);
});

test('更新后焦点留在方案，删除后移至相邻方案，删除最后一项返回名称输入框', () => {
  const app = fixture();
  app.open(); app.save('一'); app.save('二'); app.save('三');
  app.action(1, 1);
  assert.equal(app.activeElement(), app.list.children[1].children[1].children[1]);
  app.action(1, 2);
  assert.equal(app.activeElement().getAttribute('aria-label'), '删除方案：三');
  app.action(1, 2);
  assert.equal(app.activeElement().getAttribute('aria-label'), '删除方案：一');
  app.action(0, 2);
  assert.equal(app.activeElement(), app.input);
});

test('无效持久数据不被覆盖，无效设置不产生页面副作用', () => {
  const app = fixture({ 'bm-appearance-presets': '{broken' });
  const original = app.snapshot();
  app.open(); app.save('不能覆盖');
  assert.equal(app.storage.get('bm-appearance-presets'), '{broken');
  assert.equal(app.form.querySelector('button').disabled, true);
  for (const invalid of [{ layout: 'missing' }, { density: 75 }, { skyCount: 0 }, { trailSize: 1.15 }, { focus: 'invalid' }, { fxFollowsSystem: 'false' }]) {
    assert.throws(() => app.setSnapshot({ ...original, ...invalid }), /无效/);
    assert.deepEqual(app.snapshot(), original);
  }
  assert.equal(app.renderCount(), 0);
});
