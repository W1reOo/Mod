# ModHarbor

一个本地优先的跨平台 MOD 管理器。中文界面，Python 3.11+，核心功能仅使用标准库，无需 Node.js、数据库服务或前端构建。可通过浏览器使用，也可选择 pywebview 原生窗口。

这是可运行的首版实现，不是所有游戏通用的自动安装器。对不支持的包格式、安装规则和依赖版本会明确报错。

## Windows EXE（直接双击）

构建产物为 `dist/ModHarbor.exe`：Windows 10/11 x64 便携版，自带 Python 与应用依赖，默认打开独立桌面窗口，不需要命令行或自行安装 Python。不要在压缩包内部直接运行，先解压至普通目录后双击。

系统需具备 .NET Framework 4.8 和 Microsoft Edge WebView2 Runtime，现代 Windows 通常已经安装。缺少 WebView2 时可从 [微软官网](https://developer.microsoft.com/microsoft-edge/webview2/) 安装。运行错误记录于 `%LOCALAPPDATA%/ModHarbor/desktop-error.log`。

本任务已在 Linux 上通过 Wine 使用 Windows CPython 与 Windows PyInstaller 生成真正的 PE x64 GUI 程序；Wine 的核心自检不代表原生 Windows/WebView2 窗口已经实机验证。EXE 尚未进行发行者代码签名。请以交付报告中的验证结果为准。

在 Windows 上复现构建（构建者需要 Python 3.11，最终用户不需要）：

```powershell
.\scripts\build-windows.ps1
```

也可以把代码推送到 GitHub 后，在 Actions 手动运行 **Build Windows EXE**，成功后从 **ModHarbor-Windows-x64** 下载构建附件。工作流会运行单元测试、生成单文件程序并执行打包程序自身的资源、HTTP 服务和 WinForms 后端导入检查；它不等同于真实交互式游戏验收。此任务没有推送代码或执行远程工作流。

## 从源码启动（开发者）

在运行游戏的电脑上，进入仓库目录：

```sh
python -m modmanager
```

应用仅监听 `127.0.0.1:8765`，自动打开本机浏览器。Windows 如果没有 `python` 命令，可用 `py -3 -m modmanager`。必须在安装了游戏的电脑上运行，云环境无法扫描另一台电脑的磁盘。

自定义端口与数据目录：

```sh
python -m modmanager --port 8766 --data-dir /path/to/modharbor-data
```

无图形环境调试：

```sh
python -m modmanager --no-browser --data-dir /tmp/modharbor-dev
```

可选安装为命令：`python -m pip install .`，然后运行 `modharbor`。

原生窗口模式：

```sh
python -m pip install '.[desktop]'
python -m modmanager --desktop
```

pywebview 需要平台 WebView 运行库：Windows 为 WebView2，macOS 为系统 WebKit，Linux 需要 GTK/WebKit 或 Qt。核心浏览器模式不依赖这些组件。当前已在 Linux/Chromium 验证；Windows/macOS 原生窗口及真实游戏的最终加载效果尚未实机验证。仓库提供三平台、三个 Python 版本的 CI 配置，但此任务没有执行远程 CI。

## 使用流程

1. **我的游戏 → 扫描游戏**：发现 Steam 的默认与附加库、Windows Epic 清单和 GOG 注册表、Linux/macOS Heroic/Legendary 元数据。其他游戏可手动登记。扫描仅读取启动器记录，不遍历整个磁盘。
2. 确认路径和安装规则。Steam 版本来自 `buildid`，并非游戏营销版本；其他来源读取启动器版本。手动登记支持填写版本。
3. **设置 → Nexus Mods**：到 [Nexus API Keys](https://www.nexusmods.com/users/myaccount?tab=api) 获取 Personal API Key，在应用中验证连接。密钥仅保存于进程内存，不写磁盘或浏览器存储。
4. **探索模组**：选择游戏，浏览热门、最新发布、最近更新。名称筛选作用于当前 API 列表；数字按 MOD ID 精确查询。公开 v1 API 没有通用名称搜索接口。
5. 打开作者页面核对版本与依赖，选择安装机制和 ZIP 文件。自动下载通常需要 Nexus Premium；普通用户可从官网手动下载，然后通过**导入 ZIP**填写本机完整路径。
6. 导入只写缓存。关闭游戏后点击启用，确认作者要求，管理器检查依赖和冲突、备份原文件，再部署。禁用会恢复原文件；原本不存在的文件会被移除。
7. **更新中心**检查 Nexus 主文件的不同版本，下载新版后先禁用旧版，再启用新版。不会自动覆盖配置；多分支和可选文件需核对作者页面。

## 安装规则

| 规则 | 部署位置 | 前置条件与边界 |
| --- | --- | --- |
| Cyberpunk Archive | `archive/pc/mod` | 接受 `.archive`、`.xl`；`.xl` 检查 ArchiveXL DLL。REDmod 包不支持 |
| Cyberpunk redscript | `r6/scripts` | 接受 `.reds`，检查 `engine/tools/scc.exe`，加载器需先安装 |
| Stardew Valley SMAPI | `Mods` | 检查 SMAPI，要求每个模组目录有 `manifest.json`；根级 manifest 会包装成独立目录 |
| Skyrim Special Edition Data | `Data` | 普通文件替换；不自动启用 ESP/ESM、排序或安装 SKSE |
| 通用目录 | `Mods` | 仅用于已确认会读取 Mods 的游戏，不会推断未知机制 |

同一游戏的每个 MOD 可选择不同的匹配规则，例如 Cyberpunk 的 archive 与 redscript。游戏目录不得重叠。规则是明确的目录部署配方，不会注入运行中的进程或执行包内安装器。DLL/脚本由游戏或已有加载器加载，管理器无法证明第三方代码安全。

包应直接包含有效负载或对应目标前缀。例如 Cyberpunk 接受 `example.archive` 或 `archive/pc/mod/example.archive`。不猜测任意套壳目录。FOMOD、7z/RAR、交互安装器、加载器自动安装、插件排序、虚拟文件系统、多配置档案和 nxm 协议注册暂未实现。

## 依赖、冲突与恢复

所有 MOD 检测大小写不敏感的文件目标冲突，采用拒绝覆盖另一启用 MOD 的策略。支持 ZIP 根目录中的 `modmanager.json`：

```json
{
  "name": "My Mod",
  "version": "1.2.0",
  "dependencies": ["Base Mod", "12345"],
  "conflicts": ["Incompatible Mod"]
}
```

依赖可以引用同一游戏的已启用 MOD 名称、本地 ID 或 Nexus MOD ID（字符串）。禁用或移除被依赖的 MOD 会被阻止。只有显式声明的依赖和文件冲突可自动处理，无法从自然语言说明或运行时行为判断所有语义冲突。

SMAPI 原生清单会读取 `UniqueID`、`Dependencies`、`IsRequired` 和 `MinimumVersion`。最低版本比较支持稳定数字版本（如 `1.2.3`），预发布版本会明确阻止自动比较。同包内依赖也会检查。Nexus 元数据不会自动提供全部依赖；必须阅读作者说明。

启用前 SHA-256 检查缓存；恢复时检查备份。部署过程使用临时文件替换、SQLite 提交与磁盘事务日志。中途失败会回滚；进程中断后，下次启动会恢复未提交事务。发现不属于原文件或部署文件的外部修改会停止恢复，保留事务和备份。这个机制不承诺断电后所有文件系统写入的持久性。

默认数据目录：

- Windows：`%LOCALAPPDATA%/ModHarbor`
- macOS：`~/Library/Application Support/ModHarbor`
- Linux：`$XDG_DATA_HOME/modharbor` 或 `~/.local/share/modharbor`

保留 `manager.sqlite3`、`packages/`、`backups/`；模组启用期间不要删除数据目录。单个数据目录只允许一个应用实例。事务恢复遇到外部修改时，应先完整复制数据目录及冲突文件，核对 `transaction/journal.json` 和备份后人工恢复；不要直接删除事务日志或强制覆盖。

限制：ZIP ≤ 512 MiB，解压后 ≤ 2 GiB，最多 20,000 条目。拒绝路径穿越、符号链接、加密包、重复目标和 Windows 保留文件名。下载仅允许 HTTPS Nexus CDN，并验证每次重定向；API Key 不发送给 CDN。

## 测试

核心测试不需要依赖、真实游戏或 Nexus Key：

```sh
python -m unittest discover -s tests -v
```

可选浏览器端到端测试（独立临时目录，验证实际文件变化）：

```sh
python -m pip install playwright
python -m playwright install chromium
python tests/browser_smoke.py
```

已有系统 Chromium 时可设置 `CHROMIUM_PATH`。测试覆盖添加游戏、导入、启用、禁用、移除，以及桌面/手机宽度下全部页面的 JavaScript 错误与布局溢出。

真实 Nexus API 和下载需要用户自己的有效密钥及账户权限，不纳入离线测试。跨平台 CI 与打包配置见 `.github/workflows/test.yml` 和 `pyproject.toml`。

## 代码结构

- `modmanager/scanner.py`：启动器发现与安装元数据。
- `modmanager/rules.py`：声明式安装配方。
- `modmanager/nexus.py`：Nexus v1 API、账户验证、列表、文件与下载链接。
- `modmanager/engine.py`：SQLite 状态、清单、依赖、备份与事务。
- `modmanager/server.py`：仅本机 HTTP 服务、会话令牌、同源与下载策略。
- `modmanager/web/`：响应式中文界面，无 CDN 依赖。

新增游戏时先扩展扫描映射与规则；涉及交互安装器或新加载机制时，为其单独实现可验证的安装策略及恢复测试，不应把它伪装成普通目录复制。
