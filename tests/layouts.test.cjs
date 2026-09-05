const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture({ layout = 'board', folder = '', items } = {}) {
  const books = items || [
    ...Array.from({ length: 45 }, (_, i) => ({ title: '工具 ' + i, href: 'https://example.com/tool/' + i, host: 'example.com', path: '工具/开发/前端', group: '工具' })),
    ...Array.from({ length: 10 }, (_, i) => ({ title: '办公 ' + i, href: 'https://example.org/office/' + i, host: 'example.org', path: '公司/办公', group: '公司' }))
  ];
  const storage = new Map([['bm-folder', folder]]);
  const handlers = new Map();
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', hidden: false,
      addEventListener: (name, handler) => handlers.set(id + ':' + name, handler) });
    return elements.get(id);
  };
  const context = vm.createContext({
    window: { BOOKMARKS: books },
    document: { documentElement: { dataset: { layout, fx: 'off' } },
      body: { classList: { toggle() {} } }, getElementById: element, querySelectorAll: () => [] },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    matchMedia: () => ({ matches: false }), setTimeout: callback => { callback(); return 1; }, clearTimeout() {}
  });
  for (const file of ['config.js', 'bookmarks.js', 'bookmark-layouts.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/js', file), 'utf8'), context, { filename: file });
  }
  const run = code => vm.runInContext(code, context);
  run('initBookmarks(); render()');
  return { run, context, elements, storage, handlers, html: () => element('main').innerHTML,
    choose(value) {
      const btn = { getAttribute: () => value };
      context.event = { target: { closest: selector => selector === '[data-folder]' ? btn : null } };
      run('pickFolder(event)');
    },
    more(name) {
      context.event = { target: { closest: selector => selector === '[data-board-more]' ? { dataset: { boardMore: name } } : null } };
      run('pickFolder(event)');
    },
    search(value) { handlers.get('q:input')({ target: { value } }); }
  };
}
const cardCount = html => (html.match(/<a class="card"/g) || []).length;

test('九种布局选项保留已有布局并追加分类折叠', () => {
  const app = fixture();
  assert.equal(app.run('LAYOUTS.map(x => x.id).join(",")'), 'classic,compact,list,icons,board,tree,tabs,start,accordion');
});

test('看板在全部分类中展示实际书签，每组独立限制，不受全局 36 条截断', () => {
  const app = fixture();
  assert.equal(cardCount(app.html()), 16);
  assert.match(app.html(), /data-board="公司"/);
  assert.match(app.html(), /data-board="工具"/);
  assert.doesNotMatch(app.html(), /id="moreBtn"/);
  assert.equal(app.elements.get('stats').textContent, '55 / 55');
});

test('看板加载更多只展开目标分类，最后一页按钮消失', () => {
  const app = fixture();
  app.more('工具');
  assert.equal(cardCount(app.html()), 24);
  assert.match(app.html(), /data-board-more="公司"/);
  app.more('公司');
  assert.equal(cardCount(app.html()), 26);
  assert.doesNotMatch(app.html(), /data-board-more="公司"/);
  assert.match(app.html(), /data-board-more="工具"/);
});

test('分类及搜索变化会重置看板展开数，保留原有过滤含义', () => {
  const app = fixture();
  app.more('工具');
  app.choose('工具');
  assert.equal(app.storage.get('bm-folder'), '工具');
  assert.equal(cardCount(app.html()), 8);
  assert.match(app.html(), /data-board="工具\/开发"/);
  app.more('工具/开发');
  assert.equal(cardCount(app.html()), 16);
  app.search('工具 4');
  assert.equal(cardCount(app.html()), 6);
  app.search('');
  assert.equal(cardCount(app.html()), 8);
  app.search('不存在的书签');
  assert.match(app.html(), /没有找到匹配的书签/);
});

test('切换布局不改变分类、查询和原有全局分页数量', () => {
  const app = fixture({ folder: '工具' });
  app.run('state.shown = 72; state.q = "工具"; document.documentElement.dataset.layout = "tree"; render()');
  assert.equal(cardCount(app.html()), 45);
  assert.equal(app.run('state.folder + ":" + state.q + ":" + state.shown'), '工具:工具:72');
  app.run('document.documentElement.dataset.layout = "board"; render()');
  assert.equal(cardCount(app.html()), 8);
  app.run('document.documentElement.dataset.layout = "classic"; render()');
  assert.equal(cardCount(app.html()), 45);
  assert.doesNotMatch(app.elements.get('nav').innerHTML, /tree-nav/);
});

test('原四种布局保留根目录卡片和 36 条分页行为', () => {
  for (const layout of ['classic', 'compact', 'list', 'icons']) {
    const app = fixture({ layout });
    assert.equal(cardCount(app.html()), 0);
    assert.equal((app.html().match(/data-key="folder:/g) || []).length, 2);
    app.choose('工具');
    assert.equal(cardCount(app.html()), 36);
    assert.match(app.html(), /id="moreBtn"/);
    app.context.event = { target: { closest: selector => selector === '#moreBtn' ? {} : null } };
    app.run('pickFolder(event)');
    assert.equal(cardCount(app.html()), 45);
    assert.doesNotMatch(app.html(), /id="moreBtn"/);
  }
});

test('分类名称包在独立元素中，以便仅超长名称自动横向滚动', () => {
  const app = fixture({ layout: 'classic', folder: '工具' });
  assert.match(app.elements.get('nav').innerHTML, /<b><span class="folder-name">开发<\/span><\/b>/);
});

test('分类名称按本列最长名称对齐，超长名称默认省略、悬停或聚焦时才滚动', () => {
  const app = fixture({ layout: 'classic', items: [
    { title: '甲', href: 'https://example.com/a', host: 'example.com', path: '甲', group: '甲' },
    { title: '四', href: 'https://example.com/b', host: 'example.com', path: '四字分类', group: '四字分类' },
    { title: '五', href: 'https://example.com/c', host: 'example.com', path: '五字分类名', group: '五字分类名' }
  ] });
  assert.equal(app.run("folderNameWidth([{ name: '甲' }, { name: '四字分类' }, { name: '五字分类名' }])"), 4);
  assert.match(app.elements.get('nav').innerHTML, /style="--folder-name-width:4em"/);
  assert.match(app.elements.get('nav').innerHTML, /data-full-name="五字分类名"/);
  assert.doesNotMatch(app.elements.get('nav').innerHTML, /title="五字分类名"/);

  const makeLabel = text => {
    const states = new Map();
    const values = new Map();
    return {
      clientWidth: 40,
      querySelector: () => ({ textContent: text, scrollWidth: 80 }),
      classList: { toggle: (name, value) => states.set(name, value) },
      style: { setProperty: (name, value) => values.set(name, value) },
      states,
      values
    };
  };
  const fourChars = makeLabel('四字分类');
  const fiveChars = makeLabel('五字分类名');
  app.context.document.querySelectorAll = () => [fourChars, fiveChars];
  app.run('updateFolderNameScroll()');
  assert.equal(fourChars.states.get('is-overflow'), false);
  assert.equal(fiveChars.states.get('is-overflow'), true);
  assert.equal(fiveChars.values.get('--folder-overflow'), '40px');
  const css = fs.readFileSync(path.join(__dirname, '../web/css/bookmarks.css'), 'utf8');
  assert.match(css, /\.folder b\.is-overflow \.folder-name \{[\s\S]*text-overflow: ellipsis/);
  assert.match(css, /\.folder:hover b\.is-overflow \.folder-name,[\s\S]*animation: folder-name-pan/);
  assert.match(css, /\.folder-name-tooltip \{[\s\S]*linear-gradient/);
  assert.match(fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8'), /id="folderNameTooltip"/);
  const themes = fs.readFileSync(path.join(__dirname, '../web/css/themes.css'), 'utf8');
  for (const id of app.run('SKINS.map(skin => skin.id)').filter(id => id !== 'auto')) {
    assert.match(themes, new RegExp(`html\\[data-skin="${id}"\\] \\{ --tooltip-start:`));
  }
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname, '../web/js/bookmarks.js'), 'utf8'), /--tooltip-h/);
});

test('同步数据的根分类和子分类顺序在所有导航布局中保持不变', () => {
  const items = [
    { title: '第一个', href: 'https://example.com/1', host: 'example.com', path: '第二分类/后置', group: '第二分类' },
    { title: '第二个', href: 'https://example.com/2', host: 'example.com', path: '第一分类/甲', group: '第一分类' },
    { title: '第三个', href: 'https://example.com/3', host: 'example.com', path: '第二分类/前置', group: '第二分类' },
    { title: '第四个', href: 'https://example.com/4', host: 'example.com', path: '第三分类/乙', group: '第三分类' }
  ];
  const app = fixture({ layout: 'classic', items });
  const root = app.elements.get('nav').innerHTML;
  const rootOrder = ['第二分类', '第一分类', '第三分类'].map(name => root.indexOf(`data-folder="${name}"`));
  assert.ok(rootOrder[0] < rootOrder[1] && rootOrder[1] < rootOrder[2]);

  app.choose('第二分类');
  const child = app.elements.get('nav').innerHTML;
  assert.ok(child.indexOf('data-folder="第二分类/后置"') < child.indexOf('data-folder="第二分类/前置"'));

  app.run('document.documentElement.dataset.layout = "tree"; render()');
  const tree = app.elements.get('nav').innerHTML;
  const treeOrder = ['第二分类', '第一分类', '第三分类'].map(name => tree.indexOf(`data-tree-toggle="${name}"`));
  assert.ok(treeOrder[0] < treeOrder[1] && treeOrder[1] < treeOrder[2]);
});

test('目录树展开当前分类祖先，点击箭头只改变展开状态、不切换分类或重绘卡片', () => {
  const app = fixture({ layout: 'tree', folder: '工具/开发/前端' });
  const nav = app.elements.get('nav').innerHTML;
  assert.match(nav, /data-tree-toggle="工具" aria-expanded="true"/);
  assert.match(nav, /data-tree-toggle="工具\/开发" aria-expanded="true"/);
  assert.match(nav, /data-tree-toggle="公司" aria-expanded="false"/);
  const before = app.html();
  const attributes = { 'aria-expanded': 'true', 'aria-controls': 'fixture-children' };
  app.context.event = { target: { closest: selector => selector === '[data-tree-toggle]' ? {
    dataset: { treeToggle: '工具' }, getAttribute: name => attributes[name], setAttribute: (name, value) => { attributes[name] = value; }
  } : null } };
  app.run('pickFolder(event)');
  assert.equal(attributes['aria-expanded'], 'false');
  assert.equal(app.elements.get('fixture-children').hidden, true);
  assert.equal(app.run('state.folder'), '工具/开发/前端');
  assert.equal(app.html(), before);
  app.run('render()');
  assert.match(app.elements.get('nav').innerHTML, /data-tree-toggle="工具" aria-expanded="false"/);
});

test('搜索会展开匹配的深层目录，空结果仍可返回全部', () => {
  const app = fixture({ layout: 'tree' });
  app.search('工具 4');
  assert.match(app.elements.get('nav').innerHTML, /data-tree-toggle="工具\/开发" aria-expanded="true"/);
  assert.equal(cardCount(app.html()), 6);
  app.search('无结果');
  assert.match(app.elements.get('nav').innerHTML, /data-folder=""/);
  assert.match(app.html(), /没有找到匹配的书签/);
});

test('新布局中的分类名称、标题和控件属性均转义', () => {
  const name = '引号" <测试>&';
  const items = [{ title: '<script>测试</script>', href: 'https://example.com/', host: 'example.com', path: name + '/子级', group: name }];
  const app = fixture({ items });
  assert.match(app.html(), /data-board="引号&quot; &lt;测试&gt;&amp;"/);
  assert.doesNotMatch(app.html(), /<script>/);
  app.run('document.documentElement.dataset.layout = "tree"; render()');
  assert.doesNotMatch(app.elements.get('nav').innerHTML, /<测试>/);
  assert.match(app.elements.get('nav').innerHTML, /aria-controls="tree-/);
});

for (const layout of ['tabs', 'start']) {
  test(layout + ' 横向导航支持深层分类、面包屑返回、搜索和分页', () => {
    const app = fixture({ layout });
    assert.match(app.elements.get('nav').innerHTML, /horizontal-tabs/);
    app.choose('工具/开发/前端');
    assert.match(app.elements.get('nav').innerHTML, /aria-label="当前位置"/);
    assert.match(app.elements.get('nav').innerHTML, /data-folder="工具\/开发"/);
    assert.equal(cardCount(app.html()), 36);
    app.context.event = { target: { closest: selector => selector === '#moreBtn' ? {} : null } };
    app.run('pickFolder(event)');
    assert.equal(cardCount(app.html()), 45);
    app.choose('工具');
    assert.match(app.elements.get('nav').innerHTML, /aria-label="下级分类"/);
    app.search('工具 4');
    assert.equal(cardCount(app.html()), 6);
    app.search('无匹配');
    assert.match(app.html(), /没有找到匹配的书签/);
    assert.match(app.elements.get('nav').innerHTML, /data-folder=""/);
    app.choose('');
    app.search('');
    assert.equal((app.html().match(/data-key="folder:/g) || []).length, 2);
  });
}


test('分类折叠独立收起，加载更多保持状态，搜索重新展开', () => {
  const app = fixture({ layout: 'accordion' });
  assert.equal(cardCount(app.html()), 16);
  const attributes = { 'aria-expanded': 'true', 'aria-controls': 'accordion-test' };
  app.context.event = { target: { closest: selector => selector === '[data-accordion-toggle]' ? {
    dataset: { accordionToggle: '公司' }, getAttribute: key => attributes[key],
    setAttribute: (key, value) => { attributes[key] = value; }
  } : null } };
  app.run('pickFolder(event)');
  assert.equal(attributes['aria-expanded'], 'false');
  assert.equal(app.elements.get('accordion-test').hidden, true);
  assert.equal(app.run('state.folder'), '');
  app.more('工具');
  assert.equal(cardCount(app.html()), 24);
  assert.match(app.html(), /data-accordion-toggle="公司" aria-expanded="false"/);
  assert.match(app.html(), /data-accordion-toggle="工具" aria-expanded="true"/);
  app.search('办公');
  assert.equal(cardCount(app.html()), 8);
  assert.match(app.html(), /data-accordion-toggle="公司" aria-expanded="true"/);
  app.choose('公司/办公');
  assert.equal(cardCount(app.html()), 8);
  app.search('无匹配');
  assert.match(app.html(), /没有找到匹配的书签/);
});
