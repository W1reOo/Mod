ModHarbor 0.1.0 · Windows x64 便携版

使用方法：
1. 将下载包解压到普通文件夹。
2. 双击 ModHarbor.exe。无需安装 Python，无需命令行。
3. 在“我的游戏”中扫描本机游戏，或手动添加游戏目录。
4. 在“设置”中连接你的 Nexus Mods API Key，或直接导入本地 ZIP。
5. 确认游戏版本与作者说明，关闭游戏后启用 MOD。

运行条件：Windows 10/11 x64、.NET Framework 4.8、Microsoft Edge WebView2 Runtime。
WebView2 官方下载：https://developer.microsoft.com/microsoft-edge/webview2/

数据及备份：%LOCALAPPDATA%\ModHarbor
启动错误日志：%LOCALAPPDATA%\ModHarbor\desktop-error.log
模组启用期间请勿删除上述目录。

首版仅支持明确的 ZIP 部署规则。加载器需预装，不支持 FOMOD、7z/RAR、
交互式安装器、自动插件排序或 nxm 协议。Nexus 自动下载通常需要 Premium。

本版本未进行发行者代码签名。
本包由 Windows CPython/PyInstaller 在 Wine 中构建；核心自检已运行，
原生 Windows 桌面窗口及真实游戏的最终效果仍需在 Windows 电脑上确认。
