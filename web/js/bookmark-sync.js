function currentBookmarkBrowser(nav = navigator) {
  const brands = (nav.userAgentData?.brands || []).map(item => item.brand).join(' ');
  const ua = nav.userAgent || '';
  if (/Microsoft Edge/i.test(brands) || /Edg\//.test(ua)) return 'edge';
  if (/OPR\/|Opera|Vivaldi|SamsungBrowser|Firefox|FxiOS|CriOS|EdgiOS|EdgA\//i.test(ua) || nav.brave) return '';
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
  const names = { chrome: 'Chrome', edge: 'Edge', safari: 'Safari' };
  let busy = false;
  let generation = 0;
  let supported = [];
  const selected = () => radios.find(input => input.checked && !input.disabled)?.value;
  const message = (text, state = '') => { status.textContent = text; status.dataset.state = state; };
  const dismiss = () => { if (!busy) dialog.close(); };
  cancel.addEventListener('click', dismiss);
  close.addEventListener('click', dismiss);
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { generation++; trigger.focus(); });
  choices.addEventListener('change', () => { confirm.disabled = busy || !supported.includes(selected()); });

  trigger.addEventListener('click', async () => {
    if (dialog.open) return;
    const current = ++generation;
    supported = [];
    confirm.disabled = true;
    choices.disabled = true;
    for (const input of radios) { input.checked = false; input.disabled = true; input.closest('label').hidden = true; }
    detected.textContent = '正在识别当前浏览器…';
    message('');
    dialog.showModal();
    if (location.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(location.hostname)) {
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
        : '未识别到支持的当前浏览器，请手动选择来源。';
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
    choices.disabled = confirm.disabled = cancel.disabled = close.disabled = true;
    confirm.textContent = '正在同步…';
    message(`正在读取 ${names[browser]} 书签，请稍候…`);
    try {
      const response = await fetch('/__bookmarks/sync', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Bookmark-Sync': '1' },
        body: JSON.stringify({ browser, confirmed: true })
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.message || '同步失败，请检查浏览器书签和目录写入权限。');
      message(`已同步 ${result.count} 个书签，正在刷新主页。`);
      // The previous category may not exist in the newly imported bookmarks.
      try { localStorage.setItem('bm-folder', ''); } catch (error) {}
      location.reload();
    } catch (error) {
      message(error.message || '同步结果未确认，请刷新主页查看后再决定是否重试。', 'error');
      busy = false;
      choices.disabled = confirm.disabled = cancel.disabled = close.disabled = false;
      confirm.textContent = '确认同步';
    }
  });
}
