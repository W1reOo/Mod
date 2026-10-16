import os
import platform
import re
from pathlib import Path
from .rules import RULES


def vdf_pairs(text):
    return dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]*)"', text))


def default_steam_roots():
    home = Path.home()
    roots = [home / '.steam/steam', home / '.local/share/Steam', home / 'Library/Application Support/Steam']
    if platform.system() == 'Windows':
        roots += [Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Steam']
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
                roots.append(Path(winreg.QueryValueEx(key, 'SteamPath')[0]))
        except OSError:
            pass
    return roots


def scan_games(extra_roots=()):
    """Discover Steam manifests, including configured external libraries; no full disk scan."""
    roots = default_steam_roots() + [Path(p).expanduser() for p in extra_roots]
    libraries = set()
    warnings = []
    for root in roots:
        root = root.resolve()
        libraries.add(root if root.name != 'steamapps' else root.parent)
        config = root / 'steamapps/libraryfolders.vdf'
        if config.is_file():
            try:
                for path in re.findall(r'"path"\s+"([^"]+)"', config.read_text(errors='replace')):
                    libraries.add(Path(path.replace('\\\\', '\\')).resolve())
            except OSError as exc:
                warnings.append(f'{config}: {exc}')
    games = {}
    for library in sorted(libraries):
        try:
            manifests = list((library / 'steamapps').glob('appmanifest_*.acf'))
            for manifest in manifests:
                data = vdf_pairs(manifest.read_text(errors='replace'))
                appid = data.get('appid', '')
                install = data.get('installdir', '')
                base = (library / 'steamapps/common').resolve()
                path = (base / install).resolve()
                if not install or not path.is_relative_to(base) or not path.is_dir():
                    continue
                rules = [r['id'] for r in RULES.values() if r['steam_id'] == appid]
                games[str(path)] = dict(name=data.get('name', path.name), path=str(path),
                    version=data.get('buildid', '未知'), version_source='Steam Build ID',
                    steam_id=appid, source='Steam', rule_id=rules[0] if rules else 'custom-directory', supported=bool(rules))
        except OSError as exc:
            warnings.append(f'{library}: {exc}')
    others, launcher_warnings = scan_other_launchers()
    for game in others:
        games.setdefault(game['path'], game)
    return list(games.values()), warnings + launcher_warnings


def match_rule(name):
    normalized = name.casefold().replace('®', '').replace('™', '')
    return next((r['id'] for r in RULES.values() if r['steam_id'] and r['game'].casefold() in normalized), 'custom-directory')


def scan_other_launchers():
    """Read launcher-owned metadata; no credentials, recursive disk crawl or executables."""
    import json
    home = Path.home()
    games, warnings = [], []

    def add(name, raw_path, version, source):
        if not raw_path:
            return
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            return
        rule_id = match_rule(name)
        games.append(dict(name=name or path.name, path=str(path), version=version or '未知',
            version_source=f'{source} 安装元数据', rule_id=rule_id, source=source, supported=rule_id!='custom-directory'))

    if platform.system() == 'Windows':
        manifest_dir = Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Epic/EpicGamesLauncher/Data/Manifests'
        for file in manifest_dir.glob('*.item'):
            try:
                data = json.loads(file.read_text(encoding='utf-8-sig'))
                if not data.get('bIsIncompleteInstall') and data.get('InstallLocation'):
                    add(data.get('DisplayName', ''), data['InstallLocation'], data.get('AppVersionString'), 'Epic')
            except (OSError, ValueError) as exc:
                warnings.append(f'Epic 安装清单无法读取：{file.name} ({type(exc).__name__})')
        import winreg
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\GOG.com\Games', 0, winreg.KEY_READ | view) as root:
                    for i in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                                def value(name, default=''):
                                    try:
                                        return winreg.QueryValueEx(key, name)[0]
                                    except OSError:
                                        return default
                                add(value('gameName'), value('path'), value('buildId', value('version')), 'GOG')
                        except OSError:
                            warnings.append('部分 GOG 注册表记录无法读取。')
            except FileNotFoundError:
                pass
            except OSError:
                warnings.append('GOG 安装注册表无法访问。')
    legendary_files = [home / '.config/legendary/installed.json',
        home / '.config/heroic/legendaryConfig/legendary/installed.json',
        home / 'Library/Application Support/heroic/legendaryConfig/legendary/installed.json']
    config = os.environ.get('XDG_CONFIG_HOME')
    if config:
        legendary_files += [Path(config) / 'legendary/installed.json', Path(config) / 'heroic/legendaryConfig/legendary/installed.json']
    for file in dict.fromkeys(legendary_files):
        if not file.is_file():
            continue
        try:
            installed = json.loads(file.read_text(encoding='utf-8'))
            for item in installed.values():
                add(item.get('title', ''), item.get('install_path'), item.get('version'), 'Heroic / Legendary')
        except (OSError, ValueError, AttributeError, TypeError):
            warnings.append(f'Heroic / Legendary 安装清单无法读取：{file}')
    return games, warnings
