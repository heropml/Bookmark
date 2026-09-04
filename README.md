# Bookmark · 本地书签主页

一个本地运行的书签导航页。页面由项目自带的便携 Python 在 `127.0.0.1:8765` 提供服务，支持分类浏览、搜索、主题切换以及快捷方式图标联动。

Chrome / Edge / Safari 书签同步 · 多主题与六种布局 · 动态天气 · Windows 安装向导 · Gitee / GitHub 双源升级。

私人书签保存在本机，不上传到仓库。普通 Windows 用户使用 `.exe` 安装包即可，不需要安装 Python 或 Git；仓库的“克隆/下载 ZIP”是源码压缩包，不是安装程序。

仓库与发行版：[Gitee（国内优先）](https://gitee.com/heropml/Bookmark) · [GitHub](https://github.com/heropml/Bookmark) · [Gitee 发行版](https://gitee.com/heropml/Bookmark/releases) · [GitHub 发行版](https://github.com/heropml/Bookmark/releases)。安装包通过发行版附件提供；若发行版列表为空，表示尚未正式上传，并非安装失败。

## 外观与布局

- 15 套页面主题：极光、赛博、余烬、深海、星海、幻彩、墨金、宣纸、雪、樱、瓷、水墨、黛青、朱砂、夜墨，另支持跟随系统深浅色的“自动”模式。
- 6 种页面布局：标准、紧凑、列表、宫格、分组看板、目录树。
- 8 种网站图标风格，以及包含悬浮、翻转、聚焦、漂移和心跳在内的 16 项图标动效。
- 鼠标拖尾与背景特效各提供 16 项选择，并支持单独关闭、大小和数量调节。
- 所有选择都会保存在浏览器本地；关闭“动态效果”后会同时停用背景和图标动画。

在“外观 → 页面布局”切换：**分组看板**将分类并排展示，各组可独立加载更多，选择“全部”可总览所有分类；**目录树**将多级分类收进一个可展开、收起的侧栏。切换布局保留当前分类与搜索，继续使用原主题、图标和天气效果。

## 快速使用

### Windows

- 安装包用户：运行 `Bookmark_Setup_v1.0.6.exe`，按向导选择目录和桌面快捷方式，安装后从桌面或开始菜单打开；不需要另装 Python 或 Git。默认安装到 `%LOCALAPPDATA%\Programs\Bookmark`，建议使用当前用户有写权限的目录，以便在线升级。
- 安装包只附带公开示例书签；在开始菜单中选择“同步 Chrome 书签”“同步 Edge 收藏夹”或“导入书签 HTML”导入自己的数据。覆盖安装不覆盖私人书签和生成数据；卸载只移除安装记录中的程序文件，保留私人数据和在线更新备份，浏览器外观设置也不会被清除。
- 项目已包含 64 位便携 Python 3.13.13，不需要在电脑上另行安装 Python。
- 首次使用或移动项目后，双击 `launchers/windows/shortcut.bat` 生成根目录和桌面的“书签”快捷方式。
- 双击根目录的 `书签.lnk`：隐藏启动本地服务并打开页面，不会自动同步浏览器书签，也不会弹出控制台。
- 双击 `launchers/windows/sync-chrome.bat`：手动把当前 Chrome 活动账号的书签同步到页面。
- 双击 `launchers/windows/sync-edge.bat`：手动把当前 Edge 活动账号的收藏夹同步到页面。
- 双击 `launchers/windows/replace.bat`：选择一个 Chrome 导出的 HTML 文件并替换书签源数据。
- `launchers/windows/start.bat`：用于排查启动问题，会保留控制台窗口并显示错误。

### 从主页同步书签

点击右上角“同步书签”，选择浏览器，再点击“确认同步”。Windows 支持 Chrome、Edge；macOS 支持 Chrome、Safari。默认识别当前浏览器类型，不支持或无法识别时需要手动选择，不会擅自切换同步来源。

同步会替换**当前运行目录**内主页的书签和分类，不修改浏览器里的收藏夹；完成后刷新主页并回到“全部”，避免旧分类筛选隐藏新书签，其他外观设置保持不变。多账号按浏览器最近使用的配置读取，网页无法识别当前标签页所属账号。取消不执行同步，同步过程中禁止重复提交；文件模式和远程托管演示页不支持此入口，请通过本地快捷方式打开。

### 安装版与源码版同时使用

启动器仅复用属于同一目录的后台。安装版和 Git 源码版可以同时运行：如果 8765 被其他目录或旧版服务占用，会从 8766–8784 选择空闲端口，不强制关闭别的服务；再次打开会查找并复用本目录已运行的服务，即使更小的端口后来空闲，也不会另开一个实例。

旧服务未提供目录标识时不会被当成当前目录服务复用。不同端口的浏览器主题设置独立保存；此修改不迁移旧端口设置或其他目录的私人书签。

### 构建 Windows 安装包（维护者）

使用与 SerialTool 相同的 [Inno Setup 6](https://jrsoftware.org/isinfo.php)，支持 Windows 10/11 的 x64 环境，沿用项目便携 Python，不另做冻结打包。

1. 安装 Inno Setup 6，并将[简体中文语言文件](https://jrsoftware.org/files/istrans/)放入其 `Languages/ChineseSimplified.isl`（与 SerialTool 安装包共用）。
2. 在 Git 工程中执行 `runtime\python\python.exe -B -X utf8 scripts/build_installer.py`，也可双击 `launchers/windows/build-installer.bat`。非标准位置通过 `--iscc "路径\ISCC.exe"` 指定编译器。
3. 输出在 `installer/`：安装程序、SHA-256 校验文件及逐文件打包清单。构建时自动读取 `scripts/manage.py` 的版本，并核对网页版本；发布前需同步版本号。

构建只选择 Git 已跟踪的公开程序目录及必需模块，使用当前工作区内容；不包含 `.git`、私人书签、`web/data.js`、窗口状态、更新备份、缓存或本机快捷方式。Git 仅是维护者的构建依赖，安装包用户走免 Git 升级通道。安装包自身不进行代码签名，Windows 可能提示未知发布者。

便携 Python 按当前提交的原始字节打包，消除 Windows 检出时的换行符差异，确保在线升级校验一致；运行时的其他本地修改必须先提交再打包。

覆盖安装时，安装向导会检测本安装目录内占用的程序文件，提示关闭相应后台进程；确认卸载后只关闭本安装目录的 `manage.py --serve` 后台，不会按进程名批量结束其他 Python 程序。不要把安装包装进 Git 工程目录（安装器会拒绝）；安装包不会自动迁移其他目录的私人数据。

安装器回归验证：`runtime\python\python.exe -B -X utf8 tests/installer_smoke.py`。此测试使用独立产品标识、测试开始菜单和 `installer/verify-*/` 目录，验证真实安装、后台运行时覆盖安装、私人数据保留与卸载；会创建后删除测试卸载注册项，保留验证日志，不打开浏览器或操作日常 8765 服务。

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
│  ├─ archive_update.py     ZIP 安装的免 Git 双源更新与文件校验
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

- 打开或刷新本地服务页面时立即检查更新，页面停留期间每 1 小时再检查一次，无需操作鼠标；发现新版后点击左下角升级提示点，确认后更新程序，不会定时重载网页或自动安装远端更新。
- 正在检查、安装或等待后台重启时，不重复发起定时检查。浏览器休眠或冻结页面时，定时检查可能延后。
- 确认升级后，左下角显示实时阶段进度：检查、同步、应用、重启，并显示当前更新源及切换情况；失败会保留具体原因。进度按实际阶段推进，不显示估算百分比；新服务就绪后自动刷新页面，兼容旧服务的 JSON 升级响应。
- 参考 SerialTool 的顺序回退规则：优先使用 [Gitee](https://gitee.com/heropml/Bookmark)，连接或拉取失败时切换 [GitHub](https://github.com/heropml/Bookmark)。第一个成功的源为准，不会每次同时请求两边；Gitee 拉取不使用全局 HTTP 代理。
- Git 安装检查 `main` 的 Git 提交，不比较 Release 或标签。每条 Git 命令最多等待 15 秒；检查失败不影响书签使用。
- Git 通道在 Windows 上使用 Schannel 读取系统证书，避免 Git 自带 CA 包与系统证书不一致造成“网页能打开但无法升级”。仅对更新请求生效，不修改全局 Git 配置；macOS/Linux 保留原有 TLS 后端。ZIP 通道使用 Python 的默认系统证书信任配置。所有平台更新请求均保持证书校验。
- 两个源都不可用且检测到证书问题或不支持 Schannel 时，左下角显示错误状态点，悬停查看原因，点击只重新检查，不直接安装。不会通过关闭证书校验绕过错误；普通网络失败仍保持静默。
- Git 克隆安装需要电脑上安装 Git；无论从哪边克隆，都不需要手动配置第二个 remote。保留本地修改保护：不在 `main`、已跟踪代码有未提交修改、本地领先或与所选源分叉时，不执行升级；只允许快进合并。
- ZIP 解压安装也支持在线升级，无需安装 Git 或登录代码托管账号。没有 `.git` 标记时启用此通道；损坏的 Git 目录、分离 HEAD 或其他分支不会被当成 ZIP 安装来覆盖。
- ZIP 通道从公开 API 读取 `main` 对应的 `APP_VERSION`，仅安装更高的三段版本号，不自动降级。发布 ZIP 更新时必须提高 `scripts/manage.py` 与 `web/index.html` 的版本号；同版本号的代码修改只会被 Git 通道检测到。
- Gitee 的 ZIP 下载 API 需要授权，因此免 Git 升级使用公开文件清单和原始文件接口，按固定提交下载有变化的程序文件；每个文件都校验大小和 Git blob 哈希，Gitee 下载失败时只切到 GitHub 的同一提交，不混装不同版本。请求保持 HTTPS 证书校验，不使用浏览器登录状态。
- ZIP 通道仅更新 `web/`、`scripts/`、`assets/`、`launchers/`、公开示例书签及说明文件。`web/data.js`、私人书签、窗口状态、快捷方式及更新清单之外的额外文件不会被覆盖或删除；浏览器外观设置保持原地址、原端口存储。
- 替换前先完整下载校验，并将旧程序文件备份到 `data/.update-backups/`。替换失败时恢复已替换文件并保留备份；下载期间本地程序文件被修改则取消升级。ZIP 安装无法像 Git 一样判断原有代码修改，确认升级时会提示自改程序文件将被替换并备份。
- Windows 正在使用的便携 Python 不做在线替换：若新版要求不同的运行时文件，会在替换程序前停止并提示下载完整安装包；macOS/Linux 保持系统 Python 不变。
- 在线升级必须通过本地服务打开页面，直接双击 HTML 不支持。旧 ZIP 若尚未包含免 Git 升级模块，需要先换用包含该功能的新安装包。
- 多页面检查和升级串行执行，Git 通道合并、ZIP 通道下载均固定为本次检查得到的完整提交号；升级完成后沿用原端口自动重启及页面就绪检测。
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
- `data/.update-backups/` 为 ZIP 升级的本地程序备份，不会被提交或由升级自动删除。
- 普通打开“书签”快捷方式或 `Bookmark.app` 不会同步浏览器；在主页确认同步或执行对应的手动同步脚本、命令时才会更新。
- `Bookmark.app` 每次打开都会使用当前的 UI 和 `web/data.js`；如果书签源文件更新较晚，会先重新生成页面数据。
- 手动同步只读取浏览器本机缓存，不会修改浏览器内的书签；同步结果会覆盖 `data/bookmarks.html` 并保留为下次打开时的本地快照。
- 页面默认端口是 `8765`。
- Windows 启动脚本统一使用 `runtime/python/python.exe`，隐藏启动使用同目录的 `pythonw.exe`。
- 便携运行时适用于 64 位 Windows，并包含项目所需的 Pillow；macOS 仍使用系统的 `python3`。
