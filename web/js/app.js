// 模块已按依赖顺序加载；事件绑定和启动操作统一在这里执行。
initBookmarks();
initWindowState();
initPointerEffects();
initAppearance();
initSearchShortcuts();
initWeatherControls();
initUpdate();
initEffects();
initClock();
initWeatherRefresh();
if (!ITEMS.length) {
  document.getElementById("main").innerHTML = '<div class="empty">暂无书签数据</div>';
} else {
  render();
}
