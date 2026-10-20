const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture({ local = true, flush = async () => true, drafts = [], fetch = async () => ({ ok: true, json: async () => ({ backups: [] }) }) } = {}) {
  const elements = new Map(), imports = [], exports = [];
  let reloads = 0;
  class Element {
    constructor() { this.listeners = {}; this.children = []; this.dataset = {}; this.files = []; }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    fire(type = 'click') { return this.listeners[type]?.({ preventDefault() {} }); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    showModal() { this.open = true; }
    close() { this.open = false; this.fire('close'); }
    click() { this.fire(); }
  }
  const element = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const context = vm.createContext({
    bookmarkPreferences: {
      status: () => ({ local }), drafts: () => drafts, flush,
      exportDocument: id => { exports.push(id); return { format: 1, values: {} }; },
      importDocument: async document => { imports.push(document); }
    },
    window: { addEventListener() {}, document: { getElementById: element } },
    document: { getElementById: element, createElement: () => new Element() },
    location: { reload() { reloads++; } }, fetch,
    URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} }, Blob: class {},
    setTimeout() {}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/js/preferences-ui.js'), 'utf8'), context);
  vm.runInContext('initPreferences()', context);
  return { element, imports, exports, get reloads() { return reloads; },
    open: () => element('preferencesOpen').fire(),
    choose: file => { element('preferencesFile').files = [file]; return element('preferencesFile').fire('change'); } };
}

test('保存失败时仍展示可导出的未保存副本', async () => {
  const app = fixture({ flush: async () => false, drafts: [{ id: 'draft', created: 1 }] });
  await app.open();
  const rows = app.element('preferencesDrafts').children;
  assert.equal(rows.length, 1);
  rows[0].children[1].click();
  assert.deepEqual(app.exports, ['draft']);
});

test('静态服务器明确提示浏览器存储限制，不读取本机备份', async () => {
  const app = fixture({ local: false, fetch: () => { throw Error('unexpected request'); } });
  await app.open();
  assert.match(app.element('preferencesDescription').textContent, /清理浏览器数据前请先导出/);
  assert.equal(app.element('preferencesFile').disabled, true);
});

test('关闭再打开时旧备份查询不会重复填入列表，坏备份不能恢复', async () => {
  let resolveOld;
  let requests = 0;
  const app = fixture({ fetch: async () => {
    if (++requests === 1) await new Promise(resolve => { resolveOld = resolve; });
    return { ok: true, json: async () => ({ backups: [{ id: 'backup', created: 1, error: '备份无法读取' }] }) };
  } });
  const first = app.open();
  await new Promise(resolve => setImmediate(resolve));
  app.element('preferencesClose').click();
  await app.open();
  resolveOld();
  await first;
  const rows = app.element('preferencesBackups').children;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].children[1].disabled, true);
});

test('导入允许配置大小上限之外的导出包装，确认后才替换', async () => {
  const app = fixture();
  await app.open();
  await app.choose({ name: 'full.json', size: 512 * 1024 + 100,
    text: async () => JSON.stringify({ format: 1, values: { 'bm-pins': '[]' } }) });
  assert.equal(app.element('preferencesConfirmPanel').hidden, false);
  assert.equal(app.imports.length, 0);
  await app.element('preferencesConfirm').fire();
  assert.equal(app.imports.length, 1);
  assert.equal(app.reloads, 1);
});

test('较早的文件读取不能覆盖后来选中的配置，关闭后也不能出现确认', async () => {
  let release;
  const app = fixture();
  await app.open();
  const old = app.choose({ name: 'old.json', size: 20,
    text: () => new Promise(resolve => { release = resolve; }) });
  await app.choose({ name: 'new.json', size: 20,
    text: async () => '{"format":1,"values":{}}' });
  release('{"format":1,"values":{}}');
  await old;
  assert.match(app.element('preferencesConfirmText').textContent, /new.json/);
  const late = app.choose({ name: 'late.json', size: 20,
    text: () => new Promise(resolve => { release = resolve; }) });
  app.element('preferencesClose').click();
  release('{"format":1,"values":{}}');
  await late;
  assert.equal(app.element('preferencesConfirmPanel').hidden, true);
});
