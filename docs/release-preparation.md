# 仓库展示与发行流程

仓库简介已同步至 GitHub 和 Gitee。各版本变更见 `releases/`，安装包通过对应发行版附件提供。

## Gitee 简介

本地浏览器书签导航页，支持 Chrome / Edge / Safari 同步、多主题布局、动态天气、Windows 安装包及 Gitee / GitHub 双源升级。私人书签保存在本机。

建议标签：`书签管理`、`导航页`、`Python`、`Windows`、`本地应用`。

简介区保持简短，完整使用说明放在 README；安装包放在“发行版”的附件中，不放进 Git 历史。源码 ZIP 和可安装 EXE 明确区分。

## v1.0.8 发行内容

- 16 套网站图标风格扩展（新增 `outline`、`halo`、`frame`、`badge`、`ink`、`grain`、`mirror`、`circuit`）并同步接入外观面板。
- 每套图标保持与当前皮肤的配色/发光/阴影策略一致，新增图标可独立预览与切换。
- 入口与升级链路维持既有行为：版本显示、双源升级和安装包发布逻辑一致。
- 继续包含 Apple Silicon macOS DMG 与 `v1.0.8` 同步发布内容。

## 发布检查清单

1. 确认正式版本号，并同步 Python、网页和版本测试。免 Git 更新仅识别更高版本，同号重新打包不会提示已安装用户升级。
2. 完成回归、安装覆盖与卸载验证，再构建安装包及 SHA-256 校验文件。macOS 在 Apple Silicon 主机运行 `bash scripts/build_macos.sh --dmg`，验证 `.app` 和 `.dmg` 后上传 DMG 与校验文件。
3. 用户确认提交推送后，将同一提交推送到 Gitee、GitHub。
4. 将上述简介和标签填写到 Gitee 仓库设置；两端创建对应发行版并上传相同 EXE 与校验文件。
5. 发行说明注明 Windows 10/11 x64、macOS Apple Silicon、安装包使用 ad-hoc 签名、仅含示例书签及首次导入方法；不要上传私人数据、测试安装器或验证目录。
