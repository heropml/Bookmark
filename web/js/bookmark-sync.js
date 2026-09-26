function currentBookmarkBrowser(nav = navigator) {
  const brands = (nav.userAgentData?.brands || []).map(item => item.brand).join(' ');
  const ua = nav.userAgent || '';
  if (/Microsoft Edge/i.test(brands) || /Edg\//.test(ua)) return 'edge';
  if (/QQBrowser/i.test(ua)) return 'qq';
  if (/360EE|360SE|QihooBrowser/i.test(ua)) return '360';
  if (/MetaSr/i.test(ua)) return 'sogou';
  if (/Quark/i.test(ua)) return 'quark';
  if (/UCBrowser/i.test(ua)) return 'uc';
  if (nav.brave) return 'brave';
  if (/Vivaldi/i.test(ua)) return 'vivaldi';
  if (/OPR\/|Opera/i.test(ua)) return 'opera';
  if (/SamsungBrowser|Firefox|FxiOS|CriOS|EdgiOS|EdgA\//i.test(ua)) return '';
  if (/Google Chrome/i.test(brands) || /Chrome\//.test(ua)) return 'chrome';
  if (/Safari\//.test(ua) && /Version\//.test(ua) && !/Mobile\//.test(ua)) return 'safari';
  return '';
}

function initBookmarkSync() {
  const trigger = document.getElementById('bookmarkSyncBtn');
  const dialog = document.getElementById('bookmarkSyncDialog');
  const form = document.getElementById('bookmarkSyncForm');
  const choices = document.getElementById('bookmarkSyncBrowsers');
  const radios = [...choices.querySelectorAll('input')];
  const detected = document.getElementById('bookmarkSyncDetected');
  const status = document.getElementById('bookmarkSyncStatus');
  const confirm = document.getElementById('bookmarkSyncConfirm');
  const cancel = document.getElementById('bookmarkSyncCancel');
  const close = document.getElementById('bookmarkSyncClose');
  const help = document.getElementById('bookmarkSyncHelp');
  const steps = document.getElementById('bookmarkSyncSteps');
  const settings = document.getElementById('bookmarkSyncSettings');
  const restart = document.getElementById('bookmarkSyncRestart');
  const menuRestart = document.getElementById('serviceRestartBtn');
  const restartStatus = document.getElementById('serviceRestartStatus');
  const restartDialog = document.getElementById('serviceRestartDialog');
  const restartConfirm = document.getElementById('serviceRestartConfirm');
  const restartCancel = document.getElementById('serviceRestartCancel');
  const localService = location.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(location.hostname);
  const names = { chrome: 'Chrome', edge: 'Edge', safari: 'Safari', html: '其他浏览器 HTML 文件', brave: 'Brave', vivaldi: 'Vivaldi', opera: 'Opera', 'opera-gx': 'Opera GX', qq: 'QQ浏览器', '360': '360极速浏览器', '360-x': '360极速浏览器X', sogou: '搜狗高速浏览器', quark: '夸克浏览器', uc: 'UC浏览器' };
  let busy = false;
  let generation = 0;
  let supported = [];
  menuRestart.hidden = true;
  if (localService) {
    fetch('/__service', { cache: 'no-store' }).then(async response => {
      if (response.ok) menuRestart.hidden = (await response.json()).can_restart !== true;
    }).catch(() => {});
  }
  const selected = () => radios.find(input => input.checked && !input.disabled)?.value;
  // A failure shows one line, with fix steps and macOS permission/restart actions below it.
  const showHelp = (result = {}) => {
    const list = Array.isArray(result.steps) ? result.steps : [];
    steps.replaceChildren(...list.map(text => Object.assign(document.createElement('li'), { textContent: text })));
    settings.hidden = !result.settings;
    settings.disabled = false;
    settings.textContent = '打开系统设置';
    restart.hidden = !result.restart;
    restart.disabled = false;
    restart.textContent = '重启书签';
    help.hidden = !list.length && !result.settings && !result.restart;
  };
  const message = (text, state = '', result) => { status.textContent = text; status.dataset.state = state; showHelp(result); };
  settings.addEventListener('click', async () => {
    if (busy) return;
    settings.disabled = true;
    try {
      const response = await fetch('/__bookmarks/settings', { method: 'POST' });
      settings.textContent = response.ok ? '已打开系统设置' : '请手动打开系统设置';
    } catch (error) {
      settings.textContent = '请手动打开系统设置';
    }
    settings.disabled = busy;
  });
  const restartService = async () => {
    if (busy) return;
    busy = true;
    menuRestart.disabled = trigger.disabled = true;
    choices.disabled = confirm.disabled = cancel.disabled = close.disabled = settings.disabled = restart.disabled = true;
    restart.textContent = '正在重启…';
    const report = (text, state = '') => {
      status.textContent = restartStatus.textContent = text;
      status.dataset.state = restartStatus.dataset.state = state;
      restartStatus.hidden = dialog.open;
    };
    report('正在重启书签，请稍候…');
    try {
      const response = await fetch('/__bookmarks/restart', { method: 'POST', headers: { 'X-Bookmark-Sync': '1' } });
      const result = await response.json();
      if (!response.ok || !result.ok || !result.instance) throw new Error(result.message || '无法重启书签，请稍后重试。');
      await waitForRestart(result.instance, () => report('书签已重启，正在刷新页面。'));
    } catch (error) {
      report(error.message || '重启结果未确认，请刷新主页查看。', 'error');
      busy = false;
      menuRestart.disabled = trigger.disabled = false;
      choices.disabled = !supported.length;
      confirm.disabled = !supported.includes(selected());
      cancel.disabled = close.disabled = settings.disabled = restart.disabled = false;
      restart.textContent = '重启书签';
    }
  };
  const askRestart = source => {
    if (busy || source.hidden || restartDialog.open) return;
    if (source === menuRestart) setAppearanceOpen(false);
    restartDialog.showModal();
  };
  restart.addEventListener('click', () => askRestart(restart));
  menuRestart.addEventListener('click', () => askRestart(menuRestart));
  restartCancel.addEventListener('click', () => restartDialog.close());
  restartConfirm.addEventListener('click', () => {
    if (!restartDialog.open || busy) return;
    restartDialog.close();
    return restartService();
  });
  const dismiss = () => { if (!busy) dialog.close(); };
  cancel.addEventListener('click', dismiss);
  close.addEventListener('click', dismiss);
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { generation++; trigger.focus(); });
  choices.addEventListener('change', () => { confirm.disabled = busy || !supported.includes(selected()); });

  trigger.addEventListener('click', async () => {
    if (busy || dialog.open || restartDialog.open) return;
    const current = ++generation;
    supported = [];
    confirm.disabled = true;
    choices.disabled = true;
    for (const input of radios) { input.checked = false; input.disabled = true; input.closest('label').hidden = true; }
    detected.textContent = '正在识别当前浏览器…';
    message('');
    dialog.showModal();
    if (!localService) {
      detected.textContent = '当前不是本地服务页面';
      message('请通过书签快捷方式打开本地主页，再同步浏览器书签。', 'error');
      return;
    }
    try {
      const response = await fetch('/__bookmarks/sync', { cache: 'no-store' });
      if (!response.ok) throw new Error('当前后台不支持主页同步，请使用包含此功能的新版程序启动。');
      const result = await response.json();
      if (!dialog.open || current !== generation) return;
      supported = Array.isArray(result.browsers) ? result.browsers.filter(browser => names[browser]) : [];
      const browser = currentBookmarkBrowser();
      for (const input of radios) {
        input.disabled = !supported.includes(input.value);
        input.closest('label').hidden = input.disabled;
        input.checked = !input.disabled && input.value === browser;
      }
      choices.disabled = !supported.length;
      confirm.disabled = !supported.includes(selected());
      detected.textContent = supported.includes(browser)
        ? `已识别当前浏览器：${names[browser]}，也可手动选择。`
        : '未识别到支持的当前浏览器，请手动选择来源；其他浏览器请先导出 HTML 书签文件。';
      if (!supported.length) message('此系统暂不支持从主页同步，请使用 HTML 导入入口。', 'error');
    } catch (error) {
      if (dialog.open && current === generation) {
        detected.textContent = '未能获取支持的浏览器';
        message(error.message || '无法连接本地服务，请稍后重新打开同步窗口。', 'error');
      }
    }
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const browser = selected();
    if (busy || !supported.includes(browser)) return;
    busy = true;
    menuRestart.disabled = true;
    choices.disabled = confirm.disabled = cancel.disabled = close.disabled = true;
    confirm.textContent = '正在同步…';
    message(browser === 'html' ? '请选择浏览器导出的 HTML 书签文件…' : `正在读取 ${names[browser]} 书签，请稍候…`);
    try {
      const response = await fetch('/__bookmarks/sync', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Bookmark-Sync': '1' },
        body: JSON.stringify({ browser, confirmed: true })
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw Object.assign(new Error(result.message || '同步失败，请检查浏览器书签和目录写入权限。'), { result });
      message(`已同步 ${result.count} 个书签，正在刷新主页。`);
      // The previous category may not exist in the newly imported bookmarks.
      try { localStorage.setItem('bm-folder', ''); } catch (error) {}
      location.reload();
    } catch (error) {
      message(error.message || '同步结果未确认，请刷新主页查看后再决定是否重试。', 'error', error.result);
      busy = false;
      menuRestart.disabled = false;
      choices.disabled = confirm.disabled = cancel.disabled = close.disabled = false;
      confirm.textContent = '确认同步';
    }
  });
}
