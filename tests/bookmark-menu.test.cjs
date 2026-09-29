const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture({ items, writeText } = {}) {
  const books = items || [{ title: 'Example', href: 'https://example.com/', path: '工具/开发', group: '工具', host: 'example.com' }];
  const listeners = new Map();
  const opened = [];
  const copied = [];
  const doc = { documentElement: { clientWidth: 390, clientHeight: 600 }, activeElement: null,
    addEventListener(type, fn) { const all = listeners.get(type) || []; all.push(fn); listeners.set(type, all); },
    getElementById: () => null };
  function event(type, target, extra = {}) {
    const ev = { type, target, clientX: 388, clientY: 595, prevented: false,
      preventDefault() { this.prevented = true; }, stopPropagation() {}, ...extra };
    for (const fn of listeners.get(type) || []) fn(ev);
    return ev;
  }
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.style = {}; this.handlers = new Map(); this.hidden = false; this.disabled = false; this.open = false; this.isConnected = true; this.textContent = ''; }
    setAttribute(name, value) { this.attributes[name] = String(value); if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value); }
    hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
    append(...els) { for (const el of els) { el.parent = this; this.children.push(el); } }
    set innerHTML(html) {
      this.children = [];
      const stack = [this];
      for (const token of html.matchAll(/<([^>]+)>|([^<]+)/g)) {
        if (!token[1]) { stack.at(-1).textContent += token[2]; continue; }
        if (token[1][0] === '/') { stack.pop(); continue; }
        const tag = /^\w+/.exec(token[1])[0];
        const el = new Element(tag);
        for (const attr of token[1].slice(tag.length).matchAll(/([\w-]+)(?:="([^"]*)")?/g)) el.setAttribute(attr[1], attr[2] ?? '');
        stack.at(-1).append(el);
        stack.push(el);
      }
    }
    matches(selector) {
      if (selector === 'button:not(:disabled)') return this.tagName === 'button' && !this.disabled;
      const attr = /\[([^=\]]+)(?:="([^"]*)")?\]/.exec(selector);
      const cls = /^\.([\w-]+)/.exec(selector);
      const tag = /^[a-z]+/.exec(selector);
      return (!attr || (this.hasAttribute(attr[1]) && (attr[2] === undefined || this.attributes[attr[1]] === attr[2]))) &&
        (!cls || (this.className || this.attributes.class || '').split(' ').includes(cls[1])) && (!tag || this.tagName === tag[0]);
    }
    querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector) || null; }
    contains(el) { return el === this || this.children.some(child => child.contains(el)); }
    addEventListener(type, fn) { this.handlers.set(type, fn); }
    dispatch(type, target = this, extra = {}) { this.handlers.get(type)?.({ target, ...extra }); }
    focus() { doc.activeElement = this; event('focusin', this); }
    select() { this.selected = true; }
    getBoundingClientRect() { return { left: 360, top: 560, right: 386, bottom: 584, width: 204, height: 150 }; }
    showModal() { this.open = true; }
    close() { this.open = false; this.dispatch('close'); }
  }
  doc.body = new Element('body');
  doc.createElement = tag => new Element(tag);
  const context = vm.createContext({ document: doc, window: { BOOKMARKS: books, open: (...args) => opened.push(args), addEventListener() {} },
    navigator: { clipboard: { writeText: writeText || (async text => { copied.push(text); }) } }, localStorage: { getItem: () => null } });
  for (const file of ['bookmarks.js', 'bookmark-menu.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/js', file), 'utf8'), context, { filename: file });
  vm.runInContext('initBookmarkMenu()', context);
  const cards = books.map(book => {
    const wrapper = new Element('div'); wrapper.className = 'bookmark-item';
    const card = new Element('a'); card.className = 'card'; card.setAttribute('data-key', book.href); card.setAttribute('href', book.href);
    const more = new Element('button'); more.className = 'bookmark-more'; more.setAttribute('data-bookmark-menu', book.href); more.setAttribute('data-bookmark-path', book.path || '');
    wrapper.append(card, more); doc.body.append(wrapper);
    return { card, more, wrapper };
  });
  const menu = doc.body.children.find(el => el.id === 'bookmarkContextMenu');
  const details = doc.body.children.find(el => el.id === 'bookmarkDetailsDialog');
  return { doc, menu, details, cards, opened, copied, context, listeners, event,
    open(index = 0) { return event('click', cards[index].more); },
    action(name) { menu.dispatch('click', menu.querySelector(`[data-bookmark-action="${name}"]`)); },
    press(key, extra = {}) { return event('keydown', doc.activeElement, { key, ...extra }); } };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('more and keyboard menus stay within the viewport; navigation skips disabled actions', () => {
  const app = fixture();
  app.open();
  assert.equal(app.menu.hidden, false);
  assert.equal(app.menu.style.left, '178px');
  assert.equal(app.menu.style.top, '442px');
  assert.equal(app.doc.activeElement.dataset.bookmarkAction, 'open');
  app.press('ArrowUp');
  assert.equal(app.doc.activeElement.dataset.bookmarkAction, 'details');
  app.press('Home');
  assert.equal(app.doc.activeElement.dataset.bookmarkAction, 'open');
  app.press('End');
  assert.equal(app.doc.activeElement.dataset.bookmarkAction, 'details');
  app.press('Escape');
  assert.equal(app.menu.hidden, true);
  assert.equal(app.doc.activeElement, app.cards[0].more);
  assert.equal(app.cards[0].more.attributes['aria-expanded'], 'false');
  app.cards[0].card.focus();
  assert.equal(app.press('F10', { shiftKey: true }).prevented, true);
  assert.equal(app.menu.hidden, false);
  app.press('Tab');
  assert.equal(app.menu.hidden, true);
  assert.equal(app.doc.activeElement, app.cards[0].card);
});

test('right click opens only bookmarks, and outside interaction closes without stealing focus', () => {
  const app = fixture();
  assert.equal(app.event('contextmenu', app.doc.body).prevented, false);
  assert.equal(app.event('contextmenu', app.cards[0].card).prevented, true);
  app.event('pointerdown', app.doc.body);
  assert.equal(app.menu.hidden, true);
  app.open();
  app.event('scroll', app.menu);
  assert.equal(app.menu.hidden, false);
  app.event('scroll', app.doc.body);
  assert.equal(app.menu.hidden, true);
  vm.runInContext('initBookmarkMenu()', app.context);
  assert.equal(app.listeners.get('contextmenu').length, 1);
});

test('dangerous URL schemes remain inert while details and copying remain available', async () => {
  for (const href of ['javascript:alert(1)', 'jAvA\nScRiPt:alert(1)', ' data:text/html,test', 'vbscript:msgbox(1)']) {
    const app = fixture({ items: [{ href, title: 'Unsafe', path: '测试' }] });
    app.open();
    assert.equal(app.menu.querySelector('[data-bookmark-action="open"]').disabled, true);
    assert.equal(app.doc.activeElement.dataset.bookmarkAction, 'copy');
    app.action('open');
    assert.equal(app.opened.length, 0);
    app.action('copy');
    await flush();
    assert.deepEqual(app.copied, [href]);
  }
  const app = fixture();
  app.open(); app.action('open');
  assert.deepEqual(app.opened, [['https://example.com/', '_blank', 'noopener,noreferrer']]);
});

test('details preserve full long strings as text and distinguish duplicate URLs in different folders', () => {
  const href = 'https://user:secret@example.com/' + 'a'.repeat(1000);
  const title = '<img src=x onerror=alert(1)>' + '全名'.repeat(300);
  const app = fixture({ items: [{ title: 'First', href, path: '第一类' }, { title, href, path: '第二类/<子类>' }] });
  app.open(1); app.action('details');
  assert.equal(app.details.open, true);
  assert.equal(app.details.querySelector('[data-bookmark-title]').textContent, title);
  assert.equal(app.details.querySelector('[data-bookmark-folder]').textContent, '第二类/<子类>');
  assert.equal(app.details.querySelector('textarea').value, href);
  assert.equal(app.details.querySelector('[data-bookmark-title]').children.length, 0);
  app.details.dispatch('click', app.details.querySelector('[data-bookmark-close]'));
  assert.equal(app.doc.activeElement, app.cards[1].more);
});

test('clipboard success is announced only after resolution; rejection gives selectable manual copy', async () => {
  const app = fixture({ writeText: async () => { throw new Error('denied'); } });
  app.open(); app.action('copy');
  await flush();
  assert.equal(app.details.open, true);
  assert.equal(app.details.querySelector('textarea').selected, true);
  assert.match(app.details.querySelector('[role="status"]').textContent, /无法写入剪贴板/);
  assert.doesNotMatch(app.menu.querySelector('[role="status"]').textContent, /已复制/);
  const success = fixture(); success.open(); success.action('copy');
  assert.match(success.menu.querySelector('[role="status"]').textContent, /正在复制/);
  await flush();
  assert.match(success.menu.querySelector('[role="status"]').textContent, /网址已复制/);
});

test('late clipboard rejection does not reopen a dismissed menu', async () => {
  let reject;
  const app = fixture({ writeText: () => new Promise((_, fail) => { reject = fail; }) });
  app.open(); app.action('copy'); app.press('Escape');
  reject(new Error('denied'));
  await flush();
  assert.equal(app.details.open, false);
  assert.equal(app.menu.hidden, true);
});

test('more button HTML escapes URL, title and category attributes', () => {
  const app = fixture();
  app.context.example = { href: 'https://example.com/?x="<', title: '"<坏标题>', path: '类"<别>' };
  const html = vm.runInContext('bookmarkMenuButtonHtml(example)', app.context);
  assert.match(html, /&quot;&lt;坏标题&gt;/);
  assert.doesNotMatch(html, /<坏标题>|类"<别>/);
});
