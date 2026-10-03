const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const books = (group, length, folder = group) => Array.from({ length }, (_, i) => ({
  title: group + ' ' + i, href: `https://example.com/${encodeURIComponent(folder)}/${i}`, host: 'example.com', path: folder, group
}));

function fixture({ layout = 'board', folder = '', items = [...books('A', 40), ...books('B', 3), ...books('C', 40)], preferences = {} } = {}) {
  const storage = new Map([['bm-folder', folder], ['bm-category-layout', typeof preferences === 'string' ? preferences : JSON.stringify(preferences)]]);
  const handlers = new Map();
  const elements = new Map();
  const resizeObservers = [];
  let nextElement = 0;
  const element = id => {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', hidden: false, dataset: {}, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; }, focus() {}, querySelectorAll: () => [], querySelector: () => null,
      addEventListener: (name, fn) => handlers.set(id + ':' + name, fn), appendChild(child) { this.child = child; }
    });
    return elements.get(id);
  };
  element('categoryArrangeBtn').parentElement = element('toolbar');
  const context = vm.createContext({ window: { BOOKMARKS: items },
    document: { documentElement: { dataset: { layout, fx: 'off' } }, body: { classList: { toggle() {} } },
      getElementById: element, querySelectorAll: () => [], createElement: () => element('created-' + nextElement++) },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    getComputedStyle: element => element.computedStyle,
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; }
      observe(target) { resizeObservers.push({ target, callback: this.callback }); }
    },
    matchMedia: () => ({ matches: false }), setTimeout: callback => { callback(); return 1; }, clearTimeout() {}
  });
  for (const file of ['config.js', 'bookmarks.js', 'bookmark-layouts.js', 'category-arrangement.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/js', file), 'utf8'), context, { filename: file });
  }
  const run = code => vm.runInContext(code, context);
  run('initBookmarks(); initCategoryArrangement(); render()');
  return { run, context, elements, handlers, storage, html: () => element('main').innerHTML,
    resize: () => resizeObservers.forEach(observer => observer.callback([{ target: observer.target }])),
    edit: () => handlers.get('categoryArrangeBtn:click')(),
    order: () => JSON.parse(run('JSON.stringify(orderedCategories(categoryOriginalOrder))')),
    choose(value) { context.nextFolder = value; run('state.folder = nextFolder; state.shown = PAGE; render()'); },
    search(value) { context.nextQuery = value; run('state.q = nextQuery; render()'); },
    saved: () => JSON.parse(storage.get('bm-category-layout'))
  };
}
const renderedKeys = html => [...html.matchAll(/data-key="([^"]+)"/g)].map(match => match[1]);
const renderedGroups = html => [...html.matchAll(/data-category-block="([^"]+)"/g)].map(match => match[1]);

function directionElements(app, computedStyle) {
  const parent = { computedStyle };
  const control = dataset => ({ dataset, attributes: {}, textContent: '', title: '',
    setAttribute(name, value) { this.attributes[name] = value; }, focus() {} });
  const blocks = app.order().map((name, index) => {
    const moves = [-1, 1].map(step => control({ categoryMove: name, categoryStep: String(step) }));
    const handle = control({ categoryDrag: name });
    const classes = new Set();
    const block = { dataset: { categoryBlock: name }, parentElement: parent, moves, handle, classes,
      classList: { add: value => classes.add(value), remove: (...values) => values.forEach(value => classes.delete(value)) },
      getBoundingClientRect: () => ({ left: 100 + index * 220, top: 100, width: 200, height: 100 }),
      querySelectorAll: selector => selector === '[data-category-move]' ? moves : [],
      querySelector: selector => selector === '[data-category-drag]' ? handle : null };
    handle.closest = selector => selector === '[data-category-block]' ? block : null;
    return block;
  });
  const hint = { textContent: '' };
  app.elements.get('toolbar').child.querySelector = selector => selector === '.category-arrange-hint' ? hint : null;
  app.context.document.querySelectorAll = selector => {
    if (selector === '#main [data-category-block]' || selector === '[data-category-block]') return blocks;
    if (selector === '[data-category-drag]') return blocks.map(block => block.handle);
    return [];
  };
  return { blocks, hint, parent };
}

test('默认页面没有分类编辑控件；编辑时拖拽与键盘按钮可用，完成后恢复', () => {
  const app = fixture();
  assert.doesNotMatch(app.html(), /data-category-drag=/);
  app.edit();
  assert.match(app.html(), /draggable="true" data-category-drag="A"/);
  assert.match(app.html(), /aria-label="上移 A" title="上移" disabled/);
  assert.match(app.html(), /aria-label="下移 C" title="下移" disabled/);
  app.context.moveEvent = { target: { closest: selector => selector === '[data-category-move]' ? { dataset: { categoryMove: 'C', categoryStep: '-1' } } : null } };
  app.run('pickFolder(moveEvent)');
  assert.deepEqual(app.order(), ['A', 'C', 'B']);
  assert.equal(app.run('reorderCategory("C", "A", false)'), true);
  assert.deepEqual(app.saved()[''].order, ['C', 'A', 'B']);
  app.edit();
  assert.doesNotMatch(app.html(), /data-category-drag=/);
  assert.deepEqual(renderedGroups(app.html()), ['C', 'A', 'B']);
  assert.equal(app.run('moveCategory("C", 1)'), false, '浏览模式不允许写入排列');
});

test('当前分类分别保存，刷新沿用顺序，源数据和置顶顺序不变', () => {
  const items = [...books('工作', 2, '工作/开发'), ...books('工作', 2, '工作/设计'), ...books('生活', 1)];
  const app = fixture({ items });
  app.run('pinnedUrls = [ITEMS[3].href, ITEMS[0].href]');
  const initialItems = app.run('JSON.stringify(ITEMS)');
  const initialPins = app.run('JSON.stringify(pinnedUrls)');
  app.edit();
  app.run('moveCategory("生活", -1)');
  app.choose('工作');
  assert.equal(app.run('categoryArrangementActive'), false);
  app.edit();
  app.run('moveCategory("工作/设计", -1)');
  assert.deepEqual(app.saved()[''].order, ['生活', '工作']);
  assert.deepEqual(app.saved()['工作'].order, ['工作/设计', '工作/开发']);
  const refreshed = fixture({ items, folder: '工作', preferences: app.saved() });
  assert.deepEqual(refreshed.order(), ['工作/设计', '工作/开发']);
  refreshed.choose('');
  assert.deepEqual(refreshed.order(), ['生活', '工作']);
  assert.equal(app.run('JSON.stringify(ITEMS)'), initialItems);
  assert.equal(app.run('JSON.stringify(pinnedUrls)'), initialPins);
});

test('旧分类消失后忽略，新分类按导入顺序追加；只读取时不会覆盖旧保存记录', () => {
  const saved = { '': { order: ['C', 'missing', 'C', 'A'] } };
  const app = fixture({ preferences: saved, items: [...books('A', 2), ...books('B', 2), ...books('C', 2), ...books('D', 2)] });
  assert.deepEqual(app.order(), ['C', 'A', 'B', 'D']);
  assert.deepEqual(app.saved(), saved);
  app.edit();
  app.run('moveCategory("D", -1)');
  assert.deepEqual(app.saved()[''].order, ['C', 'A', 'D', 'B']);
});

test('完整分类先排序再分页，大分类之后的书签仍能全部显示', () => {
  const app = fixture({ layout: 'tiles', preferences: { '': { order: ['C', 'B', 'A'] } } });
  assert.equal(renderedKeys(app.html()).length, 36);
  assert.deepEqual(renderedGroups(app.html()), ['C']);
  assert.ok(renderedKeys(app.html()).every(key => key.startsWith('https://example.com/C/')));
  app.run('state.shown += PAGE; render()');
  assert.equal(renderedKeys(app.html()).length, 72);
  assert.deepEqual(renderedGroups(app.html()), ['C', 'B', 'A']);
  app.run('state.shown += PAGE; render()');
  assert.equal(new Set(renderedKeys(app.html())).size, 83);
  assert.doesNotMatch(app.html(), /id="moreBtn"/);
});

test('分页只显示首组时，整理模式仍能排列末尾分类，退出保留原分页大小', () => {
  const app = fixture({ layout: 'tiles' });
  assert.deepEqual(renderedGroups(app.html()), ['A']);
  app.edit();
  assert.deepEqual(renderedGroups(app.html()), ['A', 'B', 'C']);
  assert.equal(renderedKeys(app.html()).length, 19, '编辑时每组最多先显示八项');
  app.run('moveCategory("C", -1)');
  assert.deepEqual(app.saved()[''].order, ['A', 'C', 'B']);
  app.edit();
  assert.equal(app.run('state.shown'), 36);
  assert.equal(renderedKeys(app.html()).length, 36);
});

test('搜索自动退出整理且禁用写入；表格隐藏入口，不会保存部分分类列表', () => {
  const app = fixture({ preferences: { '': { order: ['C', 'A', 'B'] } } });
  app.edit();
  app.search('A');
  assert.equal(app.run('categoryArrangementActive'), false);
  assert.equal(app.elements.get('categoryArrangeBtn').disabled, true);
  assert.equal(app.run('moveCategory("A", 1)'), false);
  app.run('categoryArrangementActive = true');
  assert.equal(app.run('reorderCategory("A", "B", false)'), false, '即使旧事件迟到也不能保存搜索结果');
  assert.deepEqual(app.saved()[''].order, ['C', 'A', 'B']);
  app.search('');
  app.run('document.documentElement.dataset.layout = "table"; render()');
  assert.equal(app.elements.get('categoryArrangeBtn').hidden, true);
  assert.doesNotMatch(app.html(), /data-category-drag=/);
});

test('存储失败、无效目标和边界移动不会改变展示顺序或保存数据', () => {
  const app = fixture();
  app.edit();
  assert.equal(app.run('moveCategory("A", -1)'), false);
  assert.equal(app.run('moveCategory("C", 1)'), false);
  assert.equal(app.run('reorderCategory("missing", "A")'), false);
  assert.equal(app.run('reorderCategory("A", "A")'), false);
  assert.equal(app.run('reorderCategory("A", "B", false)'), false);
  app.context.localStorage.setItem = () => { throw new Error('denied'); };
  assert.equal(app.run('moveCategory("C", -1)'), false);
  assert.deepEqual(app.order(), ['A', 'B', 'C']);
  assert.deepEqual(app.saved(), {});
  assert.match(app.elements.get('libraryStatus').textContent, /无法保存分类排列/);
});

test('恢复默认只重置当前分类顺序，保留列宽和其他分类设置；失败时保持原顺序', () => {
  const preferences = { '': { order: ['C', 'B', 'A'], width: 'large' }, 'A': { order: ['A/x', 'A/y'] } };
  const app = fixture({ preferences });
  app.edit();
  assert.equal(app.run('resetCategoryOrder()'), true);
  assert.deepEqual(app.order(), ['A', 'B', 'C']);
  assert.deepEqual(app.saved(), { '': { width: 'large' }, 'A': preferences.A });
  const failed = fixture({ preferences });
  failed.edit();
  failed.context.localStorage.setItem = () => { throw new Error('denied'); };
  assert.equal(failed.run('resetCategoryOrder()'), false);
  assert.deepEqual(failed.order(), ['C', 'B', 'A']);
});

test('全部十五种非表格布局都使用相同分类顺序和编辑入口', () => {
  const layouts = ['classic', 'compact', 'list', 'icons', 'board', 'tree', 'tabs', 'start', 'accordion', 'waterfall', 'shelves', 'index', 'tiles', 'split', 'text'];
  for (const layout of layouts) {
    const app = fixture({ layout, preferences: { '': { order: ['C', 'B', 'A'] } } });
    app.edit();
    assert.deepEqual(renderedGroups(app.html()), ['C', 'B', 'A'], layout);
    assert.equal((app.html().match(/data-category-drag=/g) || []).length, 3, layout);
  }
});

test('无效本地数据降级默认顺序，分类名称在编辑按钮中转义', () => {
  for (const preferences of ['bad json', 'null', '[]', '{"":null}', '{"":{"order":"wrong","width":"wrong"}}']) {
    assert.deepEqual(fixture({ preferences }).order(), ['A', 'B', 'C']);
  }
  const name = '引号" <测试>&';
  const app = fixture({ items: [...books(name, 1), ...books('B', 1)] });
  app.edit();
  assert.match(app.html(), /data-category-drag="引号&quot; &lt;测试&gt;&amp;"/);
  assert.doesNotMatch(app.html(), /<测试>/);
});

test('拖拽只接受本次分类把手启动的拖动；放到目标后方与键盘上移都能保存', () => {
  const app = fixture();
  app.edit();
  const block = name => ({ dataset: { categoryBlock: name }, getBoundingClientRect: () => ({ top: 100, height: 100 }),
    classList: { add() {}, remove() {} } });
  const a = block('A');
  const c = block('C');
  const transfer = { setData() {} };
  let prevented = 0;
  const over = { target: { closest: selector => selector === '[data-category-block]' ? c : null },
    clientY: 175, dataTransfer: transfer, preventDefault() { prevented++; } };
  app.handlers.get('main:drop')(over);
  assert.deepEqual(app.saved(), {}, '外部拖进来的网址不能改变分类顺序');
  app.handlers.get('main:dragstart')({ target: { closest: selector => selector === '[data-category-drag]' ? {
    dataset: { categoryDrag: 'A' }, closest: () => a
  } : null }, dataTransfer: transfer });
  app.handlers.get('main:dragover')(over);
  assert.equal(transfer.dropEffect, 'move');
  app.handlers.get('main:drop')(over);
  assert.equal(prevented, 2);
  assert.deepEqual(app.saved()[''].order, ['B', 'C', 'A']);
  app.handlers.get('main:keydown')({ target: { closest: selector => selector === '[data-category-drag]' ? { dataset: { categoryDrag: 'A' } } : null },
    altKey: true, key: 'ArrowUp', preventDefault() {} });
  assert.deepEqual(app.saved()[''].order, ['B', 'A', 'C']);
});

test('看板列宽独立保存并跟随当前分类，设置失败不改变当前宽度', () => {
  const app = fixture();
  app.edit();
  const widthEvent = value => ({ target: { closest: selector => selector === '[data-category-width]' ? { dataset: { categoryWidth: value } } : null } });
  const panelClick = app.handlers.get('created-0:click');
  panelClick(widthEvent('small'));
  assert.equal(app.context.document.documentElement.dataset.categoryWidth, 'small');
  assert.deepEqual(app.saved()[''], { width: 'small' });
  assert.match(app.elements.get('toolbar').child.innerHTML, /data-category-width="small" aria-pressed="true"/);
  app.context.localStorage.setItem = () => { throw new Error('denied'); };
  panelClick(widthEvent('large'));
  assert.equal(app.context.document.documentElement.dataset.categoryWidth, 'small');
  app.choose('A');
  assert.equal(app.context.document.documentElement.dataset.categoryWidth, '');
  app.choose('');
  assert.equal(app.context.document.documentElement.dataset.categoryWidth, 'small');
});

test('横向分类同步左右按钮、标签、快捷键和提示，缩成单列时立即改为上下', () => {
  const app = fixture();
  const view = directionElements(app, { display: 'grid', gridTemplateColumns: '280px 280px 280px' });
  app.edit();
  assert.equal(app.context.document.documentElement.dataset.categoryAxis, 'horizontal');
  assert.deepEqual(view.blocks[0].moves.map(button => button.textContent), ['←', '→']);
  assert.deepEqual(view.blocks[0].moves.map(button => button.title), ['左移', '右移']);
  assert.equal(view.blocks[0].moves[1].attributes['aria-label'], '右移 A');
  assert.equal(view.blocks[0].handle.attributes['aria-keyshortcuts'], 'Alt+ArrowLeft Alt+ArrowRight');
  assert.match(view.hint.textContent, /左右箭头/);
  view.parent.computedStyle.gridTemplateColumns = '280px';
  app.resize();
  assert.equal(app.context.document.documentElement.dataset.categoryAxis, 'vertical');
  assert.deepEqual(view.blocks[0].moves.map(button => button.textContent), ['↑', '↓']);
  assert.equal(view.blocks[0].moves[1].attributes['aria-label'], '下移 A');
  assert.equal(view.blocks[0].handle.attributes['aria-keyshortcuts'], 'Alt+ArrowUp Alt+ArrowDown');
  assert.match(view.hint.textContent, /上下箭头/);
  view.parent.computedStyle.gridTemplateColumns = '280px 280px';
  app.resize();
  assert.equal(app.context.document.documentElement.dataset.categoryAxis, 'horizontal');
  assert.deepEqual(app.saved(), {}, '仅调整窗口尺寸不改变分类顺序');
});

test('分类方向取决于容器排列：多列流和横向书架的分类保持上下，折叠轨道不算横列', () => {
  for (const layout of ['waterfall', 'text', 'shelves', 'accordion', 'tiles']) {
    const app = fixture({ layout });
    const view = directionElements(app, { display: 'block', gridTemplateColumns: 'none', columnCount: '3', columnWidth: '280px' });
    app.edit();
    assert.equal(app.context.document.documentElement.dataset.categoryAxis, 'vertical', layout);
    assert.equal(view.blocks[0].moves[1].title, '下移', layout);
  }
  const app = fixture({ layout: 'start' });
  const view = directionElements(app, { display: 'grid', gridTemplateColumns: '0px 180px 0px' });
  app.edit();
  assert.equal(app.context.document.documentElement.dataset.categoryAxis, 'vertical');
  view.parent.computedStyle.gridTemplateColumns = '180px 180px 0px';
  app.resize();
  assert.equal(app.context.document.documentElement.dataset.categoryAxis, 'horizontal');
});

test('分类把手只响应当前排列方向的 Alt 快捷键，缩成单列后改用上下', () => {
  const app = fixture();
  const view = directionElements(app, { display: 'grid', gridTemplateColumns: '280px 280px' });
  app.edit();
  let prevented = 0;
  const press = key => app.handlers.get('main:keydown')({
    target: { closest: selector => selector === '[data-category-drag]' ? view.blocks[2].handle : null },
    altKey: true, key, preventDefault() { prevented++; }
  });
  press('ArrowUp');
  assert.deepEqual(app.order(), ['A', 'B', 'C']);
  assert.equal(prevented, 0);
  press('ArrowLeft');
  assert.deepEqual(app.order(), ['A', 'C', 'B']);
  assert.equal(prevented, 1);
  view.parent.computedStyle.gridTemplateColumns = '280px';
  app.resize();
  press('ArrowRight');
  assert.deepEqual(app.order(), ['A', 'C', 'B']);
  assert.equal(prevented, 1);
  press('ArrowDown');
  assert.deepEqual(app.order(), ['A', 'B', 'C']);
  assert.equal(prevented, 2);
});

test('横向拖拽按左右半区插入，纵向按上下半区插入，另一轴位置不改变结果', () => {
  for (const horizontal of [true, false]) for (const after of [true, false]) {
    const app = fixture();
    const view = directionElements(app, { display: 'grid', gridTemplateColumns: horizontal ? '200px 200px 200px' : '640px' });
    app.edit();
    const source = view.blocks[after ? 0 : 2];
    const target = view.blocks[after ? 2 : 0];
    const rect = target.getBoundingClientRect();
    const transfer = { setData() {} };
    app.handlers.get('main:dragstart')({ target: { closest: selector => selector === '[data-category-drag]' ? source.handle : null }, dataTransfer: transfer });
    const event = { target: { closest: selector => selector === '[data-category-block]' ? target : null }, dataTransfer: transfer,
      clientX: rect.left + rect.width * ((horizontal ? after : !after) ? .75 : .25),
      clientY: rect.top + rect.height * ((horizontal ? !after : after) ? .75 : .25), preventDefault() {} };
    app.handlers.get('main:dragover')(event);
    assert.equal(target.classes.has(after ? 'category-drop-after' : 'category-drop-before'), true);
    app.handlers.get('main:drop')(event);
    assert.deepEqual(app.saved()[''].order, after ? ['B', 'C', 'A'] : ['C', 'A', 'B']);
  }
});

test('拖动过程中被拖分类保持半透明，放下后才恢复', () => {
  const app = fixture();
  const view = directionElements(app, { display: 'grid', gridTemplateColumns: '200px 200px 200px' });
  app.edit();
  const [source, , target] = view.blocks;
  const transfer = { setData() {} };
  app.handlers.get('main:dragstart')({ target: { closest: selector => selector === '[data-category-drag]' ? source.handle : null }, dataTransfer: transfer });
  assert.equal(source.classes.has('category-is-dragging'), true);
  const rect = target.getBoundingClientRect();
  const event = { target: { closest: selector => selector === '[data-category-block]' ? target : null }, dataTransfer: transfer,
    clientX: rect.left + rect.width * .75, clientY: rect.top + 10, preventDefault() {} };
  app.handlers.get('main:dragover')(event);
  app.handlers.get('main:dragover')(event);
  assert.equal(source.classes.has('category-is-dragging'), true, '经过其他分类时仍标记正在拖动');
  assert.equal(target.classes.has('category-drop-after'), true);
  app.handlers.get('main:dragend')();
  assert.equal(source.classes.has('category-is-dragging'), false);
  assert.equal(target.classes.has('category-drop-after'), false);
});
