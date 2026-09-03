# 前端文件说明

这是原生 HTML / CSS / JavaScript 页面，不需要安装前端依赖或构建。`index.html` 只保留页面结构和资源引用；按功能修改对应文件即可。

## 样式

`css/` 按原页面的覆盖顺序加载，修改引用顺序可能改变外观：

1. `base.css`：基础变量、重置、底色。
2. `weather.css`：天空、云雾、日夜天气场景。
3. `shell.css`：页头、时钟、天气、搜索框、工具入口。
4. `appearance.css`：外观菜单、功能弹框和选项预览。
   随后加载 `bookmark-sync.css`：主页同步入口、浏览器选择和确认窗口。
5. `bookmarks.css`：分类导航与书签卡片。
6. `themes.css`：页面主题配色和表面样式。
7. `icons.css`：网站图标及相关主题覆盖。
8. `layouts.css`：紧凑、列表、宫格、分组看板、目录树等布局。
9. `motion.css`：图标动效、焦点、动态效果开关。
10. `responsive.css`：小屏和减少动态效果设置。

CSS 图片路径相对于 `css/`，例如 `../themes/shuimo.svg`。

## 脚本

脚本仍采用有序加载的普通脚本，共享原来的顶层变量与函数，不是 ES Modules，不要直接添加 `async` 或随意调整顺序。

| 文件 | 职责 |
| --- | --- |
| `js/bootstrap.js` | 在页面绘制前恢复主题、窗口状态及页面图标 |
| `js/data-loader.js` | 先加载公开示例，再加载可选的本地私人书签 |
| `js/config.js` | 设置选项、默认值和共享状态 |
| `js/utils.js` | 本地存储、请求等共用小工具 |
| `js/bookmarks.js` | 书签数据整理、分类、搜索、渲染和快捷键 |
| `js/bookmark-layouts.js` | 分组看板的独立分页、目录树导航与展开状态 |
| `js/weather.js` | 城市、天气 API、图标与刷新机制 |
| `js/clock.js` | 时钟、日期、问候语和焦点切换后的校时 |
| `js/appearance.js` | 外观选项、弹框、设置保存和主题切换 |
| `js/window-state.js` | 本地窗口尺寸记录 |
| `js/interactions.js` | 鼠标光效、拖尾和卡片倾斜交互 |
| `js/bookmark-sync.js` | 当前浏览器识别、来源选择、确认同步与结果处理 |
| `js/effects.js` | 背景天气、粒子、画布与动画调度 |
| `js/app.js` | 按顺序绑定事件、启动时钟天气并渲染书签 |

`bootstrap.js` 位于页头；`data-loader.js` 在页面底部同步加载数据，不能加 `defer`（内部使用 `document.write`）。其余脚本使用 `defer`，由最后的 `app.js` 统一启动。

## 天气行为

打开或刷新网页时，先显示有效缓存，同时请求最新天气；之后每 10 分钟请求一次。天气旁的刷新按钮可立即重新获取，天气文字用于切换城市。刷新失败不会写入新的缓存时间，已有天气会保留，按钮提示重试。后台休眠可能使定时执行延后。

定时周期集中在 `js/weather.js` 的 `WEATHER_REFRESH_MS`，当前为 10 分钟。天气更新会同步“跟随天气”的背景特效。

取消或输入空白不会请求天气；连续查询城市时以最后一次有效输入为准，自动 IP 定位不会覆盖期间手动选择的城市。

## 时间与日期

左上角以 24 小时制显示时、分、秒，每秒更新；公历（含年份、星期）和农历分行显示，保留问候语。农历通过浏览器的 `Intl.DateTimeFormat` 中国历法在本地转换，包含干支年份、闰月及中文日期，不请求网络。时间和日期都跟随设备本地时区；失焦直接更新时间，返回页面时立即校时。背景装饰时钟保留时、分。

## 回归检查

安装 Node.js 的开发环境可在项目根目录运行以下命令，无需安装 npm 依赖：

```powershell
node --test tests/weather.test.cjs
node --test tests/layouts.test.cjs
node --test tests/clock.test.cjs
node --test tests/bookmark-sync.test.cjs
```

测试使用模拟网络、存储和页面元素，验证城市切换竞争、取消输入、零坐标、10 分钟刷新及失败状态，不访问私人书签或快捷方式接口。

布局测试覆盖分类总览、看板独立分页与搜索重置、目录树展开/收起和原有布局的分类及分页行为。看板默认每组显示 8 个书签（`BOARD_PAGE`）；展开状态仅在本次页面内保留，不写入私人书签数据。
