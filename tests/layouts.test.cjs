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
  // folder: null means nothing was saved yet, so the page starts from its default category.
  const storage = new Map(folder === null ? [] : [['bm-folder', folder]]);
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

const work = (title, href, host, extra = {}) => ({ title, href, host, path: '工作', group: '工作', ...extra });

test('首次打开没有“常用”分类时显示全部书签，而不是空页面', () => {
  const app = fixture({ layout: 'classic', folder: null, items: [work('A', 'https://a.example/', 'a.example')] });
  assert.equal(app.run('state.folder'), '');
  assert.equal(app.elements.get('stats').textContent, '1 / 1');
  assert.doesNotMatch(app.html(), /没有找到匹配的书签/);
  const example = fixture({ layout: 'classic', folder: null, items: [{ ...work('G', 'https://g.example/', 'g.example'), path: '常用', group: '常用' }] });
  assert.equal(example.run('state.folder'), '常用', '示例数据仍默认打开“常用”');
});

test('同步后已不存在的旧分类回到全部，仍存在的分类保持不变', () => {
  const items = [work('A', 'https://a.example/', 'a.example')];
  const stale = fixture({ layout: 'classic', folder: '已删除', items });
  assert.equal(stale.run('state.folder'), '');
  assert.equal(stale.storage.get('bm-folder'), '');
  assert.equal(stale.elements.get('stats').textContent, '1 / 1');
  const kept = fixture({ layout: 'classic', folder: '工作', items });
  assert.equal(kept.run('state.folder'), '工作');
  assert.equal(kept.storage.get('bm-folder'), '工作');
});

test('书签地址转义后才写入页面，脚本地址保持不可点击', () => {
  const app = fixture({ layout: 'classic', folder: '工作', items: [
    work('Quote', 'https://x.example/?q="a" onmouseover="alert(1)', 'x.example'),
    work('Script', ' java\tscript:alert(1)', ''),
    work('Data', 'DATA:text/html,<script>alert(1)</script>', ''),
    work('Tool', 'obsidian://open?vault=notes', '')
  ] });
  const html = app.html();
  assert.doesNotMatch(html, /onmouseover="/, "引号不能提前结束 href 并注入事件属性");
  assert.match(html, /href="https:\/\/x\.example\/\?q=&quot;a&quot; onmouseover=&quot;alert\(1\)"/);
  assert.doesNotMatch(html, /href="[^"]*(java\s*script|data):/i);
  assert.equal((html.match(/aria-disabled="true"/g) || []).length, 2);
  assert.match(html, /href="obsidian:\/\/open\?vault=notes"/, '其他应用的链接保留可点击');
});

test('网站图标不含内联脚本和账号密码，失败时先换备用源再保留首字母', () => {
  const app = fixture({ layout: 'classic', folder: '工作', items: [
    work('Router', 'http://admin:secret@192.168.1.1/', "admin:secret@192.168.1.1"),
    work('Quote', "https://q.example/", "x'-alert(1)-'.example")
  ] });
  const html = app.html();
  assert.doesNotMatch(html, /onerror=/);
  assert.doesNotMatch(html, /<img[^>]*secret/);
  assert.match(html, /<p>192\.168\.1\.1<\/p>/);
  assert.match(html, /data-fallback="https:\/\/icons\.duckduckgo\.com\/ip3\/192\.168\.1\.1\.ico"/);
  let removed = false;
  const img = { tagName: 'IMG', src: 'primary', dataset: { fallback: 'backup' }, remove() { removed = true; } };
  app.handlers.get('main:error')({ target: img });
  assert.equal(img.src, 'backup');
  assert.equal(removed, false);
  app.handlers.get('main:error')({ target: img });
  assert.equal(removed, true);
});

test('区块标题用面包屑，卡片标签只显示区块以下的路径', () => {
  const items = [
    { title: 'React', href: 'https://react.dev/', host: 'react.dev', path: '开发/前端/框架', group: '开发' },
    { title: 'MDN', href: 'https://developer.mozilla.org/', host: 'developer.mozilla.org', path: '开发/前端', group: '开发' }
  ];
  const app = fixture({ layout: 'classic', folder: '开发', items });
  const html = app.html();
  assert.match(html, /<span class="section-parent">开发 ›<\/span>前端/);
  assert.doesNotMatch(html, /开发\/前端</, '标题不再显示原始斜杠路径');
  const tags = [...html.matchAll(/<span class="tag">([^<]*)<\/span>/g)].map(match => match[1]);
  assert.deepEqual(tags, ['框架'], '只显示比区块更深的一级，与标题重复的部分不再出现');
  const all = fixture({ layout: 'classic', folder: '', items });
  all.search('mdn');
  assert.match(all.html(), /<span class="tag">前端<\/span>/, '搜索时区块是一级分类，标签显示其下的路径');
  all.search('react');
  assert.match(all.html(), /<span class="tag">前端\/框架<\/span>/);
});

test('总览分类卡带前几个网站的图标，完整名称放在悬停提示中', () => {
  const items = ['a', 'b', 'c', 'd', 'e'].map(name => ({ title: name, href: `https://${name}.example/`, host: `${name}.example`, path: '很长的分类名称用于测试', group: '很长的分类名称用于测试' }));
  items.push({ title: 'script', href: 'javascript:void 0', host: '', path: '很长的分类名称用于测试', group: '很长的分类名称用于测试' });
  const app = fixture({ layout: 'classic', folder: '', items });
  const html = app.html();
  assert.match(html, /<button type="button" class="card"[^>]*title="很长的分类名称用于测试"/);
  const peek = html.match(/<span class="card-peek" aria-hidden="true">([\s\S]*?)<\/span>/);
  assert.ok(peek, '分类卡应有网站图标预览');
  assert.equal((peek[1].match(/<img /g) || []).length, 4, '最多四个，且跳过没有域名的书签');
});

test('没有域名的书签保留首字母，不发起注定失败的图标请求；普通卡片有完整标题提示', () => {
  const app = fixture({ layout: 'classic', folder: '工作', items: [
    { title: '本地文件', href: 'file:///C:/notes.txt', host: '', path: '工作', group: '工作' },
    { title: '一个很长很长的网站标题', href: 'https://long.example/', host: 'long.example', path: '工作', group: '工作' }
  ] });
  const cards = app.html().split('<a class="card"').slice(1);
  assert.doesNotMatch(cards[0], /<img/);
  assert.match(cards[0], /<span>本<\/span>/);
  assert.match(cards[1], /title="一个很长很长的网站标题"/);
});

test('目录树标题栏显示当前分类，可收起展开，选择分类后自动收起', () => {
  const app = fixture({ layout: 'tree', folder: '工具/开发' });
  const nav = () => app.elements.get('nav').innerHTML;
  assert.match(nav(), /<div class="tree-caption tree-caption-static">书签目录<span>工具 › 开发<\/span><\/div>/);
  assert.match(nav(), /<button type="button" class="tree-caption tree-caption-toggle" data-tree-menu aria-expanded="false">书签目录<span>工具 › 开发<\/span><\/button>/);
  assert.match(nav(), /<nav class="nav-col tree-nav" /, '默认收起');
  const toggled = { expanded: null, open: null };
  const menu = { setAttribute: (name, value) => { toggled.expanded = value; }, closest: () => ({ classList: { toggle: (name, on) => { toggled.open = on; } } }) };
  app.context.event = { target: { closest: selector => selector === '[data-tree-menu]' ? menu : null } };
  app.run('pickFolder(event)');
  assert.deepEqual(toggled, { expanded: 'true', open: true });
  app.run('render()');
  assert.match(nav(), /tree-nav is-open/, '展开状态在重新渲染后保留');
  app.choose('公司');
  assert.match(nav(), /<nav class="nav-col tree-nav" /, '选择分类后收起，把书签留在首屏');
  assert.match(nav(), /<span>公司<\/span><\/button>/);
});

test('目录树选择分类后，手机聚焦可见标题按钮，桌面仍聚焦所选分类；调整宽度后使用当前布局', () => {
  const app = fixture({ layout: 'tree', folder: '工具/开发' });
  const focused = [];
  const tree = { scrollTop: 48 };
  const menu = { focus: () => focused.push('menu'), closest: () => tree };
  const labels = ['工具', '公司'].map(folder => ({
    dataset: { folder }, focus: () => focused.push(folder), closest: () => tree
  }));
  let mobile = true;
  app.context.matchMedia = query => ({ matches: mobile && query === '(max-width: 600px)' });
  app.context.document.querySelector = selector => selector === '[data-tree-menu]' ? menu : null;
  app.context.document.querySelectorAll = selector => selector === '.tree-label' ? labels : [];
  app.elements.get('nav').firstElementChild = tree;

  app.run('treeMenuOpen = true');
  app.choose('公司');
  assert.deepEqual(focused, ['menu'], '收起目录后不能把焦点放在隐藏的分类按钮上');
  assert.equal(app.run('treeMenuOpen'), false);
  assert.equal(tree.scrollTop, 48);

  mobile = false;
  app.choose('工具');
  assert.deepEqual(focused, ['menu', '工具'], '切回桌面后聚焦仍可见的分类');
  assert.equal(tree.scrollTop, 48);

  mobile = true;
  app.choose('公司');
  assert.deepEqual(focused, ['menu', '工具', 'menu']);
});

test('看板只有嵌套分类才显示路径行，一级分类不重复名称', () => {
  const app = fixture({ layout: 'board', folder: '' });
  assert.doesNotMatch(app.html(), /class="board-path"/);
  app.choose('工具');
  assert.match(app.html(), /<p class="board-path" title="工具\/开发">工具\/开发<\/p>/);
});
