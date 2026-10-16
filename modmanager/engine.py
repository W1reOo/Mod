import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from .rules import RULES, known_domain
from .nexus import Nexus


MAX_ARCHIVE = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_relative(name):
    if '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('压缩包包含不安全路径。')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('压缩包包含不安全路径。')
    if any(part.endswith((' ', '.')) or part.split('.')[0].upper() in
           {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
           for part in p.parts):
        raise ValueError('压缩包包含不兼容的跨平台文件名。')
    return p.as_posix()


def destination(root, relative):
    relative = safe_relative(relative)
    root = Path(root).resolve()
    raw = root / relative
    cursor = raw
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError(f'拒绝通过符号链接部署：{relative}')
        cursor = cursor.parent
    target = raw.resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError('目标路径超出游戏目录。')
    if target.exists() and not target.is_file():
        raise ValueError(f'目标不是普通文件：{relative}')
    return target


class Engine:
    def __init__(self, state):
        self.state = Path(state).expanduser().resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.state / 'manager.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS mods(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY, time REAL, level TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS downloads(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        ''')
        self.recover()
        # Repair existing Celeste records without changing deployment rules or mod files.
        with self.db:
            for game in self.games():
                domain = known_domain(game['name'], game.get('steam_id', ''))
                if not game.get('domain') and domain:
                    game['domain'] = domain
                    game['supported'] = False
                    self.save('games', game)

    def bind_domain(self, game_id, domain):
        domain = Nexus.domain(domain)
        with self.lock:
            game = self.game(game_id)
            if game.get('domain') and game['domain'] != domain:
                raise ValueError(f'此链接属于 {domain}，所选游戏是 {game["domain"]}；请先切换游戏。')
            if not game.get('domain'):
                game['domain'] = domain
                game['supported'] = any(r['domain'] == domain for r in RULES.values())
                with self.db:
                    self.save('games', game)
            return game

    def downloads(self):
        result = []
        for entry in self.records('downloads'):
            entry['exists'] = Path(entry['path']).is_file()
            entry['imported'] = any(m.get('source_archive') == entry['path'] for m in self.mods())
            result.append(entry)
        return sorted(result, key=lambda item: item['created'], reverse=True)

    def register_download(self, path, game_id=None, metadata=None):
        path = Path(path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in ('.zip', '.7z', '.rar'):
            raise ValueError('请选择已下载完成的 ZIP、7z 或 RAR 文件。')
        if path.stat().st_size > MAX_ARCHIVE:
            raise ValueError('文件超过 512 MiB 上限。')
        if game_id:
            self.game(game_id)
        with self.lock:
            entry = dict(metadata or {}, id=hashlib.sha256(str(path).encode()).hexdigest(),
                path=str(path), name=path.name, size=path.stat().st_size, game_id=game_id,
                created=time.time(), sha256=digest(path))
            with self.db:
                self.save('downloads', entry)
            self.log(f'文件已加入下载管理：{path.name}')
            return entry

    def log(self, message, level='info'):
        with self.lock, self.db:
            self.db.execute('INSERT INTO logs(time,level,message) VALUES(?,?,?)', (time.time(), level, message))

    def records(self, table):
        with self.lock:
            return [json.loads(r['data']) for r in self.db.execute(f'SELECT data FROM {table}')]

    def games(self):
        return self.records('games')

    def mods(self):
        return self.records('mods')

    def save(self, table, item):
        self.db.execute(f'INSERT OR REPLACE INTO {table}(id,data) VALUES(?,?)', (item['id'], json.dumps(item)))

    def game(self, game_id):
        return next((g for g in self.games() if g['id'] == game_id), None) or self.fail('未找到游戏。')

    def mod(self, mod_id):
        return next((m for m in self.mods() if m['id'] == mod_id), None) or self.fail('未找到 MOD。')

    @staticmethod
    def fail(message):
        raise ValueError(message)

    def add_game(self, data):
        with self.lock:
            path = Path(data.get('path', '')).expanduser().resolve()
            if not path.is_dir() or not str(data.get('path', '')).strip():
                raise ValueError('游戏路径必须是已存在的目录。')
            if path == Path(path.anchor) or self.state.is_relative_to(path) or path.is_relative_to(self.state):
                raise ValueError('请选择独立的游戏目录，不能是磁盘根目录或管理器数据目录。')
            rule_id = data.get('rule_id', 'custom-directory')
            if rule_id not in RULES:
                raise ValueError('未知安装规则。')
            for game in self.games():
                old = Path(game['path'])
                if old == path:
                    return game
                if old.is_relative_to(path) or path.is_relative_to(old):
                    raise ValueError('游戏目录不能互相嵌套。')
            rule = RULES[rule_id]
            game = dict(id=uuid.uuid4().hex, name=str(data.get('name') or path.name)[:200], path=str(path),
                        version=str(data.get('version') or '未知'), version_source=data.get('version_source', '手动登记'), steam_id=str(data.get('steam_id', '')),
                        rule_id=rule_id, domain=rule['domain'] or known_domain(str(data.get('name') or path.name), str(data.get('steam_id', ''))), source=data.get('source', '手动'), supported=data.get('supported', True))
            if game['domain'] and not any(r['domain'] == game['domain'] for r in RULES.values()):
                game['supported'] = False
            with self.db:
                self.save('games', game)
            self.log(f'登记游戏：{game["name"]} · {path}')
            return game

    def _check_loader(self, game, rule_id=None):
        rule = RULES[rule_id or game['rule_id']]
        for req in rule.get('requires', []):
            if not (Path(game['path']) / req).is_file():
                raise ValueError(f'缺少加载器组件：{req}。请先按作者说明安装。')
        any_of = rule.get('requires_any', [])
        if any_of and not any((Path(game['path']) / p).is_file() for p in any_of):
            raise ValueError('未检测到 SMAPI；请先安装对应平台的 SMAPI。')

    def install(self, game_id, archive, metadata=None, rule_id=None):
        with self.lock:
            game = self.game(game_id)
            rule_id = rule_id or game['rule_id']
            if rule_id not in RULES:
                raise ValueError('未知安装规则。')
            rule = RULES[rule_id]
            if rule['domain'] != game['domain']:
                raise ValueError('此游戏尚无匹配的安装规则。可以浏览和下载文件，但不能自动部署；请按作者说明安装。')
            archive = Path(archive).expanduser()
            if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
                raise ValueError('请选择不超过 512 MiB 的 ZIP 文件。')
            mod_id = uuid.uuid4().hex
            stage = self.state / 'packages' / mod_id
            stage.mkdir(parents=True)
            metadata = metadata or {}
            try:
                files, seen, manifest = [], set(), {}
                provides = []
                native_dependencies = []
                dependency_versions = {}
                provides_versions = {}
                with zipfile.ZipFile(archive) as bundle:
                    entries = bundle.infolist()
                    smapi_root = rule_id == 'stardew-smapi' and any(i.filename == 'manifest.json' for i in entries)
                    smapi_folder = ''.join(c for c in archive.stem if c.isalnum() or c in '-_') or 'ImportedMod'
                    if len(entries) > 20000 or sum(i.file_size for i in entries) > MAX_EXPANDED:
                        raise ValueError('压缩包文件过多或解压大小超过 2 GiB。')
                    for entry in entries:
                        name = safe_relative(entry.orig_filename.rstrip('/'))
                        mode = entry.external_attr >> 16
                        if stat.S_ISLNK(mode) or entry.flag_bits & 1:
                            raise ValueError('不支持符号链接或加密压缩包。')
                        if entry.is_dir():
                            continue
                        lower = name.casefold()
                        if lower.endswith(('.fomod',)) or 'fomod/' in lower:
                            raise ValueError('此包使用 FOMOD 交互式安装器，目前不支持自动安装。')
                        if name == 'modmanager.json':
                            if entry.file_size > 65536:
                                raise ValueError('MOD 清单过大。')
                            manifest = json.loads(bundle.read(entry))
                            if not isinstance(manifest, dict):
                                raise ValueError('MOD 清单必须为对象。')
                            continue
                        stripped = name
                        for prefix in rule['strip']:
                            if name.casefold().startswith(prefix.casefold() + '/'):
                                stripped = name[len(prefix) + 1:]
                                break
                        if rule['extensions'] and Path(stripped).suffix.lower() not in rule['extensions']:
                            if Path(stripped).suffix.lower() in {'.txt', '.md', '.png', '.jpg'}:
                                continue
                            raise ValueError(f'文件不符合所选规则：{name}。请确认下载的是正确的 MOD 类型。')
                        if smapi_root:
                            stripped = smapi_folder + '/' + stripped
                        rel = safe_relative(rule['target'] + '/' + stripped)
                        if rel.casefold() in seen:
                            raise ValueError(f'压缩包包含重复目标文件：{rel}')
                        seen.add(rel.casefold())
                        target = destination(game['path'], rel)
                        output = stage / rel
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.open(entry) as source, output.open('wb') as out:
                            shutil.copyfileobj(source, out)
                        files.append({'path': rel, 'sha256': digest(output)})
                if not files:
                    raise ValueError('压缩包中没有可安装文件。')
                if rule_id == 'stardew-smapi':
                    manifests = list((stage / 'Mods').glob('*/manifest.json'))
                    if not manifests:
                        raise ValueError('SMAPI 包中缺少独立模组目录及 manifest.json。')
                    for native in manifests:
                        if native.stat().st_size > 65536:
                            raise ValueError('SMAPI 清单过大。')
                        info = json.loads(native.read_text(encoding='utf-8-sig'))
                        if not isinstance(info.get('UniqueID'), str):
                            raise ValueError('SMAPI manifest.json 缺少 UniqueID。')
                        provides.append(info['UniqueID'])
                        provides_versions[info['UniqueID']] = str(info.get('Version', ''))
                        for dep in info.get('Dependencies', []):
                            if dep.get('IsRequired', True):
                                if dep.get('MinimumVersion'):
                                    dependency_versions[dep['UniqueID']] = str(dep['MinimumVersion'])
                                native_dependencies.append(dep['UniqueID'])
                dependencies = manifest.get('dependencies', [])
                conflicts = manifest.get('conflicts', [])
                if not isinstance(dependencies, list) or not isinstance(conflicts, list) or not all(isinstance(x, str) for x in dependencies + conflicts):
                    raise ValueError('dependencies 和 conflicts 必须为字符串数组。')
                dependencies = list(dict.fromkeys(dependencies + [d for d in native_dependencies if d not in provides]))
                mod = dict(id=mod_id, game_id=game_id, rule_id=rule_id, provides=provides, dependency_versions=dependency_versions, provides_versions=provides_versions, name=str(metadata.get('name') or manifest.get('name') or archive.stem)[:200],
                           version=str(metadata.get('version') or manifest.get('version') or '1.0'), enabled=False,
                           files=files, dependencies=dependencies, conflicts=conflicts,
                           nexus_id=metadata.get('nexus_id'), file_id=metadata.get('file_id'),
                           domain=game['domain'], created=time.time(), baseline={}, source_archive=str(archive.resolve()))
                with self.db:
                    self.save('mods', mod)
                self.log(f'导入 MOD：{mod["name"]}，{len(files)} 个文件（尚未启用）')
                return mod
            except Exception:
                shutil.rmtree(stage, ignore_errors=True)
                raise

    def _ids(self, mod):
        return {mod['id'], str(mod.get('nexus_id') or ''), mod['name'], *mod.get('provides', [])}

    def _validate_enable(self, mod, game):
        self._check_loader(game, mod.get('rule_id'))
        if mod.get('rule_id') == 'cyberpunk-archive' and any(f['path'].lower().endswith('.xl') for f in mod['files']):
            if not (Path(game['path']) / 'red4ext/plugins/ArchiveXL/ArchiveXL.dll').is_file():
                raise ValueError('此包包含 .xl 文件，需要先安装 RED4ext 与 ArchiveXL。')
        others = [m for m in self.mods() if m['game_id'] == mod['game_id'] and m['enabled'] and m['id'] != mod['id']]
        ids = set().union(*(self._ids(m) for m in others)) if others else set()
        missing = [dep for dep in mod['dependencies'] if dep not in ids]
        if missing:
            raise ValueError('缺少已启用的依赖：' + ', '.join(missing))
        for dependency, minimum in mod.get('dependency_versions', {}).items():
            candidates = [mod] + others
            provider = next((m for m in candidates if dependency in m.get('provides_versions', {})), None)
            version = provider['provides_versions'][dependency] if provider else ''
            def numeric(value):
                if not re.fullmatch(r'\d+(?:\.\d+){0,3}', value):
                    raise ValueError(f'无法自动比较依赖版本：{dependency} ({value})，仅支持稳定数字版本。')
                parts = tuple(int(v) for v in value.split('.'))
                return parts + (0,) * (4 - len(parts))
            if not provider or numeric(version) < numeric(minimum):
                raise ValueError(f'依赖版本不足：{dependency} 需要 >= {minimum}，当前 {version or "未安装"}')
        paths = {f['path'].casefold() for f in mod['files']}
        for other in others:
            if set(mod.get('provides', [])) & set(other.get('provides', [])):
                raise ValueError(f'与 {other["name"]} 提供了重复的 SMAPI UniqueID。')
            if set(mod['conflicts']) & self._ids(other) or set(other['conflicts']) & self._ids(mod):
                raise ValueError(f'与 {other["name"]} 存在声明冲突。')
            collision = paths & {f['path'].casefold() for f in other['files']}
            if collision:
                raise ValueError(f'与 {other["name"]} 文件冲突：{sorted(collision)[0]}')

    def _snapshot(self, game, mod):
        tx = self.state / 'transaction'
        if tx.exists():
            raise ValueError('存在待恢复事务，请重启管理器。')
        tx.mkdir()
        journal = {'id': uuid.uuid4().hex, 'root': game['path'], 'files': []}
        try:
            for i, f in enumerate(mod['files']):
                target = destination(game['path'], f['path'])
                exists = target.is_file()
                if exists:
                    shutil.copy2(target, tx / str(i))
                journal['files'].append({'path': f['path'], 'backup': str(i), 'exists': exists,
                    'before': digest(target) if exists else None, 'deployed': f['sha256'],
                    'original': mod.get('baseline', {}).get(f['path'])})
            # Journal is published only once the complete snapshot exists.
            temp = tx / 'journal.tmp'
            temp.write_text(json.dumps(journal), encoding='utf-8')
            os.replace(temp, tx / 'journal.json')
            return journal
        except Exception:
            shutil.rmtree(tx)
            raise

    def recover(self):
        tx = self.state / 'transaction'
        journal_path = tx / 'journal.json'
        if journal_path.exists():
            journal = json.loads(journal_path.read_text(encoding='utf-8'))
            committed = self.db.execute('SELECT 1 FROM operations WHERE id=?', (journal['id'],)).fetchone()
            if not committed:
                # Check every target before restoring any file. External edits after a crash
                # require manual intervention; never overwrite an unknown version.
                for f in journal['files']:
                    target = destination(journal['root'], f['path'])
                    if target.is_file() and digest(target) not in {f.get('before'), f.get('deployed'), f.get('original')}:
                        raise ValueError(f'事务恢复发现外部修改：{f["path"]}。已保留事务与备份，请先保存此文件并人工核对。')
                for f in reversed(journal['files']):
                    target = destination(journal['root'], f['path'])
                    if f['exists']:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(tx / f['backup'], target)
                    else:
                        target.unlink(missing_ok=True)
            shutil.rmtree(tx)
        elif tx.exists():
            shutil.rmtree(tx)  # No deployment starts before journal publication.

    @staticmethod
    def _atomic_copy(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.parent / ('.modharbor-' + uuid.uuid4().hex + '.tmp')
        try:
            shutil.copy2(source, temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def toggle(self, mod_id, enabled):
        with self.lock:
            mod = self.mod(mod_id)
            if mod['enabled'] == enabled:
                return mod
            game = self.game(mod['game_id'])
            if not Path(game['path']).is_dir():
                raise ValueError('游戏目录已不存在，请重新挂载磁盘。')
            if enabled:
                self._validate_enable(mod, game)
                for f in mod['files']:
                    source = self.state / 'packages' / mod_id / f['path']
                    if not source.is_file() or digest(source) != f['sha256']:
                        raise ValueError(f'MOD 缓存校验失败：{f["path"]}')
            else:
                for other in self.mods():
                    if other['enabled'] and other['game_id'] == mod['game_id'] and other['id'] != mod_id:
                        if set(other['dependencies']) & self._ids(mod):
                            raise ValueError(f'{other["name"]} 依赖此 MOD，请先禁用它。')
                for f in mod['files']:
                    target = destination(game['path'], f['path'])
                    if not target.is_file() or digest(target) != f['sha256']:
                        raise ValueError(f'文件已被外部修改，停止恢复以避免数据丢失：{f["path"]}')
            journal = self._snapshot(game, mod)
            try:
                baseline = self.state / 'backups' / mod_id
                if enabled:
                    baseline.mkdir(parents=True, exist_ok=True)
                    mod['baseline'] = {}
                    for f, saved in zip(mod['files'], journal['files']):
                        rel = f['path']
                        if saved['exists']:
                            backup = baseline / rel
                            backup.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(self.state / 'transaction' / saved['backup'], backup)
                            mod['baseline'][rel] = digest(backup)
                        else:
                            mod['baseline'][rel] = None
                        self._atomic_copy(self.state / 'packages' / mod_id / rel, destination(game['path'], rel))
                else:
                    for f in mod['files']:
                        rel = f['path']
                        target = destination(game['path'], rel)
                        original = mod['baseline'][rel]
                        if original is None:
                            target.unlink()
                        else:
                            backup = baseline / rel
                            if not backup.is_file() or digest(backup) != original:
                                raise ValueError(f'原文件备份校验失败：{rel}')
                            self._atomic_copy(backup, target)
                mod['enabled'] = enabled
                with self.db:
                    self.save('mods', mod)
                    self.db.execute('INSERT INTO operations(id) VALUES(?)', (journal['id'],))
            except Exception:
                self.db.rollback()
                self.recover()
                raise
            self.recover()
            self.log(f'{"启用" if enabled else "禁用"} MOD：{mod["name"]}')
            return mod

    def remove(self, mod_id):
        with self.lock:
            mod = self.mod(mod_id)
            if mod['enabled']:
                self.toggle(mod_id, False)
            with self.db:
                self.db.execute('DELETE FROM mods WHERE id=?', (mod_id,))
            shutil.rmtree(self.state / 'packages' / mod_id, ignore_errors=True)
            shutil.rmtree(self.state / 'backups' / mod_id, ignore_errors=True)
            self.log(f'移除 MOD：{mod["name"]}')

    def logs(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 200')]
