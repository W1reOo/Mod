ModHarbor 0.2.0 · Windows x64 便携版

使用方法：
1. 将下载包解压到普通文件夹。
2. 双击 ModHarbor.exe。无需安装 Python，无需命令行。
3. 在“我的游戏”中扫描本机游戏，或手动添加游戏目录。
4. 在“探索模组”点击“应用内打开 Nexus”浏览官网；也可粘贴 MOD 链接获取。
   API 查询需要在设置连接 API Key；网页登录与 API 连接独立。
   普通账户从官网 Manual / Slow Download 下载后，用“选择已下载的文件”加入下载管理。
   Premium 可直接请求 API 下载。Celeste 可查询与下载，尚不支持自动安装。
5. 确认游戏版本与作者说明，关闭游戏后启用 MOD。

运行条件：Windows 10/11 x64、.NET Framework 4.8、Microsoft Edge WebView2 Runtime。
WebView2 官方下载：https://developer.microsoft.com/microsoft-edge/webview2/

数据及备份：%LOCALAPPDATA%\ModHarbor
启动错误日志：%LOCALAPPDATA%\ModHarbor\desktop-error.log
模组启用期间请勿删除上述目录。

首版仅支持明确的 ZIP 部署规则。加载器需预装，不支持 FOMOD、7z/RAR、
交互式安装器、自动插件排序或 nxm 协议。Nexus 自动下载通常需要 Premium。

本版本未进行发行者代码签名。
本包由 Windows CPython/PyInstaller 构建，工作流执行核心安装与恢复自检。
真实 Nexus 网页登录、原生桌面窗口及游戏的最终效果需在 Windows 电脑上确认。
