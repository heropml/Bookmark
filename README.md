# 书签主页

一个本地运行的书签导航页。页面由项目自带的便携 Python 在 `127.0.0.1:8765` 提供服务，支持分类浏览、搜索、主题切换以及快捷方式图标联动。

## 外观与布局

- 15 套页面主题：极光、赛博、余烬、深海、星海、幻彩、墨金、宣纸、雪、樱、瓷、水墨、黛青、朱砂、夜墨，另支持跟随系统深浅色的“自动”模式。
- 6 种页面布局：标准、紧凑、列表、宫格、分组看板、目录树。
- 8 种网站图标风格，以及悬浮、呼吸、流光、摇摆、弹跳、旋转、涟漪、静止 8 种图标动效。
- 7 种鼠标拖尾效果，并支持单独关闭和大小调节。
- 所有选择都会保存在浏览器本地；关闭“动态效果”后会同时停用背景和图标动画。

在“外观 → 页面布局”切换：**分组看板**将分类并排展示，各组可独立加载更多，选择“全部”可总览所有分类；**目录树**将多级分类收进一个可展开、收起的侧栏。切换布局保留当前分类与搜索，继续使用原主题、图标和天气效果。

## 快速使用

### Windows

- 项目已包含 64 位便携 Python 3.13.13，不需要在电脑上另行安装 Python。
- 首次使用或移动项目后，双击 `launchers/windows/shortcut.bat` 生成根目录和桌面的“书签”快捷方式。
- 双击根目录的 `书签.lnk`：隐藏启动本地服务并打开页面，不会自动同步浏览器书签，也不会弹出控制台。
- 双击 `launchers/windows/sync-chrome.bat`：手动把当前 Chrome 活动账号的书签同步到页面。
- 双击 `launchers/windows/sync-edge.bat`：手动把当前 Edge 活动账号的收藏夹同步到页面。
- 双击 `launchers/windows/replace.bat`：选择一个 Chrome 导出的 HTML 文件并替换书签源数据。
- `launchers/windows/start.bat`：用于排查启动问题，会保留控制台窗口并显示错误。

### macOS

- 双击 `launchers/macos/open.command` 或 `launchers/macos/Bookmark.app` 打开页面。
- 双击 `launchers/macos/sync-chrome.command`：手动把当前 Google Chrome 账号的书签同步到页面。
- 双击 `launchers/macos/sync-safari.command`：手动把 Safari 书签同步到页面。
- `launchers/macos/replace.command` 用于导入书签 HTML。

## 目录结构

```text
Bookmark/
├─ 书签.lnk                 Windows 日常入口
├─ README.md                项目说明
├─ web/                     网页文件
│  ├─ index.html            页面结构和资源入口
│  ├─ README.md             前端模块与加载顺序说明
│  ├─ css/                  主题、布局、动效等分类样式
│  ├─ js/                   书签、天气、时钟、外观等功能脚本
│  ├─ themes/               主题预览图案
│  ├─ weather/              天气背景素材
│  ├─ data.example.js       公开的示例书签数据
│  └─ data.js               本地生成的私人书签数据（Git 忽略）
├─ data/                    书签源数据
│  ├─ bookmarks.example.html 公开的示例书签
│  └─ bookmarks.html        本地私人书签（Git 忽略）
├─ assets/
│  └─ icons/                快捷方式和应用图标
├─ runtime/
│  └─ python/               Windows 便携 Python 运行时
├─ scripts/                 Python 管理脚本
│  ├─ manage.py             构建数据、同步 Chrome/Edge/Safari、启动服务
│  ├─ shortcut.py           创建快捷方式并更新图标
│  └─ _make_icons.py        生成图标资源
└─ launchers/
   ├─ windows/              Windows 启动、同步和导入脚本
   └─ macos/                macOS 启动器和应用包
```

## 天气刷新

- 天气数据来自 Open-Meteo，打开或刷新网页时立即获取，之后每 10 分钟自动更新一次。
- 点击天气旁的刷新按钮可立即更新；点击天气文字可设置或切换城市。
- 最近 10 分钟的本地缓存用于快速显示，不阻止打开网页、定时或手动刷新；网络失败时保留已有天气，刷新按钮提示重试。
- 浏览器休眠或冻结后台页面时，定时任务可能延后；刷新网页或手动点击可立即重新获取。

## 双源在线升级

- 打开或刷新本地服务页面时立即检查更新，页面停留期间每 1 小时再检查一次，无需操作鼠标；发现新版后点击左下角升级提示点，确认后更新完整代码库，不会定时重载网页或自动安装远端更新。
- 正在检查、安装或等待后台重启时，不重复发起定时检查。浏览器休眠或冻结页面时，定时检查可能延后。
- 确认升级后，左下角显示实时阶段进度：检查、同步、应用、重启，并显示当前更新源及切换情况；失败会保留具体原因。进度按实际阶段推进，不显示估算百分比；新服务就绪后自动刷新页面，兼容旧服务的 JSON 升级响应。
- 参考 SerialTool 的顺序回退规则：优先使用 [Gitee](https://gitee.com/heropml/Bookmark)，连接或拉取失败时切换 [GitHub](https://github.com/heropml/Bookmark)。第一个成功的源为准，不会每次同时请求两边；Gitee 拉取不使用全局 HTTP 代理。
- 两个源都检查 `main` 的 Git 提交，不比较 Release 或标签。每条 Git 命令最多等待 15 秒；检查失败不影响书签使用。
- Windows 更新请求使用 Schannel 读取系统证书，避免 Git 自带 CA 包与系统证书不一致造成“网页能打开但无法升级”。仅对更新请求生效，不修改全局 Git 配置；macOS/Linux 保留原有 TLS 后端。所有平台更新请求均保持证书校验。
- 两个源都不可用且检测到证书问题或不支持 Schannel 时，左下角显示错误状态点，悬停查看原因，点击只重新检查，不直接安装。不会通过关闭证书校验绕过错误；普通网络失败仍保持静默。
- 需要安装 Git，并通过 Git 克隆项目；无论从哪边克隆，都不需要手动配置第二个 remote。直接下载 ZIP 或双击 HTML 不支持在线升级。
- 保留本地修改保护：不在 `main`、已跟踪代码有未提交修改、本地领先或与所选源分叉时，不执行升级；只允许快进合并。私人书签仍由 Git 忽略。
- 多页面检查和升级串行执行，合并的是本次检查得到的完整提交号；升级完成后沿用原端口自动重启及页面就绪检测。
- 发布时必须将同一个提交推送到 GitHub、Gitee 的 `main`。如果 Gitee 可达但尚未同步，按优先源规则不会继续查询 GitHub。

维护者在配置好 `origin`（GitHub）和 `gitee` 两个 remote 后，分别执行：

```powershell
git push origin main
git push gitee main
```

## 数据流程

本地书签数据：

```text
data/bookmarks.html → scripts/manage.py → web/data.js → web/index.html
```

如果本地不存在 `data/bookmarks.html`，构建脚本会读取公开的 `data/bookmarks.example.html`。页面始终先加载 `web/data.example.js`，存在本地生成的 `web/data.js` 时再用它覆盖示例数据。

Chrome 手动同步：

```text
Chrome 当前活动 Profile 的 AccountBookmarks/Bookmarks
    → scripts/manage.py --sync-chrome
    → data/bookmarks.html
    → web/data.js
```

Chrome 新版本登录账号后的书签通常保存在 `AccountBookmarks`，旧版本或本地书签保存在 `Bookmarks`。脚本会优先读取当前活动 Profile 的 `AccountBookmarks`。

Edge 手动同步使用相同流程，从当前活动 Profile 的 `AccountBookmarks/Bookmarks` 读取收藏夹，并通过 `scripts/manage.py --sync-edge` 更新本地页面。

macOS 上 Chrome 同步会读取 `~/Library/Application Support/Google/Chrome` 中的当前 Profile；Safari 同步会读取 `~/Library/Safari/Bookmarks.plist`。Safari 数据受 macOS 隐私保护，首次同步时可能需要在系统设置中允许 Terminal 访问。

## 常用命令

在项目根目录运行：

```powershell
# 从 data/bookmarks.html 重新生成页面数据
runtime\python\python.exe -X utf8 scripts/manage.py --build

# 手动同步当前 Chrome 活动账号的书签
runtime\python\python.exe -X utf8 scripts/manage.py --sync-chrome --build

# 手动同步当前 Edge 活动账号的收藏夹
runtime\python\python.exe -X utf8 scripts/manage.py --sync-edge --build

# 创建或修复 Windows 快捷方式
runtime\python\python.exe -X utf8 scripts/shortcut.py

# 启动本地服务并打开页面
runtime\python\python.exe -X utf8 scripts/manage.py
```

## 注意事项

- 可以同时打开多个书签窗口或标签页，同一地址共用一个后台服务。
- 本地服务运行此版自动重启逻辑后，打开或刷新页面时发现磁盘上的后台版本已更新，会自动关闭旧监听并在原端口启动新服务；页面等新服务就绪后再刷新，无需手动结束进程。
- 左下角版本号以当前网页文件为准，不会再被尚未重启的旧后台版本覆盖。页面内升级也会等待新服务实际启动完成。

- `data/bookmarks.html` 和 `web/data.js` 包含私人书签，已被 Git 忽略，不能使用 `git add -f` 强制提交。
- `web/data.js` 是本地生成文件，不建议手工编辑；公开示例位于 `data/bookmarks.example.html` 和 `web/data.example.js`。
- 普通打开“书签”快捷方式或 `Bookmark.app` 不会同步浏览器；只有执行对应的手动同步脚本或命令时才会更新。
- `Bookmark.app` 每次打开都会使用当前的 UI 和 `web/data.js`；如果书签源文件更新较晚，会先重新生成页面数据。
- 手动同步只读取浏览器本机缓存，不会修改浏览器内的书签；同步结果会覆盖 `data/bookmarks.html` 并保留为下次打开时的本地快照。
- 页面默认端口是 `8765`。
- Windows 启动脚本统一使用 `runtime/python/python.exe`，隐藏启动使用同目录的 `pythonw.exe`。
- 便携运行时适用于 64 位 Windows，并包含项目所需的 Pillow；macOS 仍使用系统的 `python3`。
