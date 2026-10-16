import hmac
import json
import mimetypes
import os
import re
import secrets
import tempfile
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .engine import Engine, MAX_ARCHIVE
from .nexus import Nexus, parse_mod_url, website_url
from .desktop import NexusBrowser
from .rules import RULES
from .scanner import scan_games


def valid_download(url):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or not any(
        host == domain or host.endswith('.' + domain) for domain in ('nexusmods.com', 'nexus-cdn.com')
    ):
        raise ValueError('下载地址不是受支持的 Nexus HTTPS CDN。请从 Nexus 网站下载后导入 ZIP。')
    return url


class DownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        valid_download(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class App:
    def __init__(self, state):
        self.engine = Engine(state)
        self.nexus = Nexus()
        self.account = None
        self.browser = NexusBrowser()
        self.token = secrets.token_urlsafe(32)
        self.web = Path(__file__).parent / 'web'

    def api(self, method, path, data):
        e = self.engine
        if method == 'GET' and path == '/api/state':
            return dict(games=e.games(), mods=e.mods(), rules=list(RULES.values()), account=self.account,
                        platform=os.name, logs=e.logs(), data_path=str(e.state),
                        embedded_browser=self.browser.embedded, downloads=e.downloads())
        if method == 'POST' and path == '/api/scan':
            roots = data.get('roots', [])
            if not isinstance(roots, list) or not all(isinstance(p, str) for p in roots):
                raise ValueError('扫描路径应为数组。')
            games, warnings = scan_games(roots)
            for game in games:
                e.add_game(game)
            e.log(f'扫描完成：发现 {len(games)} 个已安装游戏')
            for warning in warnings:
                e.log(warning, 'warning')
            return {'found': len(games), 'warnings': warnings}
        if method == 'POST' and path == '/api/games':
            return e.add_game(data)
        if method == 'POST' and path == '/api/install':
            return e.install(data['game_id'], data['path'], rule_id=data.get('rule_id'))
        if method == 'POST' and path == '/api/toggle':
            if not isinstance(data.get('enabled'), bool):
                raise ValueError('enabled 必须为布尔值。')
            return e.toggle(data['id'], data['enabled'])
        if method == 'POST' and path == '/api/remove':
            e.remove(data['id'])
            return {'ok': True}
        if method == 'POST' and path == '/api/nexus/connect':
            key = data.get('key', '').strip()
            if not key or len(key) > 512 or '\n' in key or '\r' in key:
                raise ValueError('请输入有效的 Nexus API Key。')
            self.nexus.key = key
            try:
                self.account = self.nexus.validate()
            except Exception:
                self.nexus.key = ''
                self.account = None
                raise
            e.log('已连接 Nexus Mods（密钥仅保存在当前进程内存）')
            return self.account
        if method == 'POST' and path == '/api/nexus/disconnect':
            self.nexus.key = ''
            self.account = None
            return {'ok': True}
        if method == 'POST' and path == '/api/nexus/open':
            url = data.get('url')
            if not url:
                game = e.game(data['game_id']) if data.get('game_id') else None
                url = f'https://www.nexusmods.com/{game["domain"]}/mods' if game and game.get('domain') else 'https://www.nexusmods.com/'
            if data.get('external') is True:
                return self.browser.open(website_url(url), external=True)
            return self.browser.open(website_url(url))
        if method == 'POST' and path == '/api/nexus/resolve':
            url = self.browser.current() if data.get('current') else data.get('url', '')
            domain, mod_id = parse_mod_url(url)
            game = e.game(data['game_id'])
            if game.get('domain') and game['domain'] != domain:
                raise ValueError(f'此链接属于 {domain}，请先选择对应游戏。')
            details = self.nexus.mod(domain, mod_id)
            # Only persist a user-selected unknown mapping after the API confirms the MOD.
            game = e.bind_domain(game['id'], domain)
            return {'game': game, 'mod': details, 'url': f'https://www.nexusmods.com/{domain}/mods/{mod_id}'}
        if method == 'POST' and path == '/api/downloads/pick':
            selected = self.browser.pick_archive()
            return {'download': e.register_download(selected, data.get('game_id')) if selected else None}
        if method == 'POST' and path == '/api/downloads/import':
            entry = next((d for d in e.downloads() if d['id'] == data['id']), None)
            if entry is None or not entry['exists']:
                raise ValueError('下载文件已不存在，请重新选择。')
            game = e.game(data['game_id'])
            if entry.get('domain') and entry['domain'] != game['domain']:
                raise ValueError('此下载文件属于另一款游戏，请选择原游戏。')
            from .engine import digest
            if digest(entry['path']) != entry['sha256']:
                raise ValueError('下载文件已发生变化，请重新选择并校验。')
            return e.install(data['game_id'], entry['path'],
                dict({k: entry[k] for k in ('nexus_id', 'file_id', 'version') if entry.get(k) is not None}, name=entry.get('title')), rule_id=data.get('rule_id'))
        if method == 'POST' and path == '/api/nexus/browse':
            game = e.game(data['game_id'])
            return self.nexus.browse(game['domain'], data.get('query', ''), data.get('category', 'trending'))
        if method == 'POST' and path == '/api/nexus/files':
            game = e.game(data['game_id'])
            return self.nexus.files(game['domain'], int(data['mod_id']))
        if method == 'POST' and path == '/api/nexus/download':
            game = e.game(data['game_id'])
            mod_id, file_id = int(data['mod_id']), int(data['file_id'])
            details = self.nexus.mod(game['domain'], mod_id)
            files = self.nexus.files(game['domain'], mod_id).get('files', [])
            selected = next((f for f in files if f['file_id'] == file_id), None)
            if not selected:
                raise ValueError('该文件已被移除，请刷新文件列表。')
            download_only = data.get('download_only', False)
            if not isinstance(download_only, bool):
                raise ValueError('download_only 必须是布尔值。')
            if not download_only and not selected.get('file_name', '').lower().endswith('.zip'):
                raise ValueError('当前仅支持 ZIP 自动部署；7z/RAR 请在本机解压并重新打包为 ZIP。')
            if not download_only:
                rule = RULES.get(data.get('rule_id') or game['rule_id'])
                if not rule or rule['domain'] != game['domain']:
                    raise ValueError('此游戏尚无安装适配，请选择“仅下载”或在 Nexus 官网下载。')
            filename = re.sub(r'[^A-Za-z0-9._-]', '_', selected.get('file_name', 'mod.zip'))[-150:]
            if Path(filename).suffix.lower() not in ('.zip', '.7z', '.rar'):
                raise ValueError('当前下载管理仅支持 ZIP、7z 或 RAR 压缩包。')
            folder = e.state / 'downloads'
            folder.mkdir(exist_ok=True)
            final = folder / f'{game["domain"]}-{mod_id}-{file_id}-{filename}'
            url = valid_download(self.nexus.download_link(game['domain'], mod_id, file_id))
            opener = urllib.request.build_opener(DownloadRedirect())
            with tempfile.NamedTemporaryFile(suffix='.part', dir=folder, delete=False) as out:
                temp = Path(out.name)
                try:
                    with opener.open(url, timeout=60) as response:
                        total = 0
                        while chunk := response.read(1024 * 1024):
                            total += len(chunk)
                            if total > MAX_ARCHIVE:
                                raise ValueError('下载超过 512 MiB 上限。')
                            out.write(chunk)
                    out.close()
                    os.replace(temp, final)
                    info = dict(title=details['name'], version=selected.get('version', ''), nexus_id=mod_id, file_id=file_id,
                        domain=game['domain'], source_url=f'https://www.nexusmods.com/{game["domain"]}/mods/{mod_id}')
                    downloaded = e.register_download(final, game['id'], info)
                    if download_only:
                        return {'download': downloaded}
                    return e.install(game['id'], final, dict(name=details['name'], version=selected.get('version', ''),
                                                        nexus_id=mod_id, file_id=file_id), rule_id=data.get('rule_id'))
                finally:
                    out.close()
                    temp.unlink(missing_ok=True)
        if method == 'POST' and path == '/api/nexus/updates':
            results = []
            for mod in e.mods():
                if not mod.get('nexus_id'):
                    continue
                files = self.nexus.files(mod['domain'], mod['nexus_id']).get('files', [])
                main = [f for f in files if f.get('category_id') == 1]
                latest = max(main, key=lambda f: f.get('uploaded_timestamp', 0), default=None)
                if latest and latest['file_id'] != mod.get('file_id') and latest.get('version') != mod['version']:
                    results.append(dict(id=mod['id'], name=mod['name'], game_id=mod['game_id'],
                                        nexus_id=mod['nexus_id'], current=mod['version'], latest=latest.get('version'), file=latest))
            e.log(f'更新检查完成：{len(results)} 个 MOD 有可用的不同版本主文件')
            return results
        raise ValueError('未知操作。')


def make_server(app, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log API credentials, signed URLs, or request bodies.

        def respond(self, status, body, kind='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host:
                self.respond(403, b'{"error":"Invalid host"}')
                return
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith('/api/'):
                if not hmac.compare_digest(self.headers.get('X-ModHarbor-Token', ''), app.token):
                    self.respond(403, b'{"error":"Unauthorized local request"}')
                    return
                origin = self.headers.get('Origin')
                if origin and origin != f'http://{host}':
                    self.respond(403, b'{"error":"Invalid origin"}')
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length < 0 or length > 65536:
                        raise ValueError('请求体过大。')
                    data = json.loads(self.rfile.read(length)) if length else {}
                    if not isinstance(data, dict):
                        raise ValueError('请求体必须为对象。')
                    result = app.api(self.command, path, data)
                    self.respond(200, json.dumps(result, ensure_ascii=False).encode())
                except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
                    # Network errors may contain a signed download URL: don't expose raw exceptions.
                    message = str(exc) if isinstance(exc, ValueError) else '操作失败：文件不可用、权限不足或压缩包损坏。请检查路径、网络与文件格式。'
                    app.engine.log(message, 'error')
                    self.respond(400, json.dumps({'error': message}, ensure_ascii=False).encode())
                except Exception:
                    app.engine.log('内部操作失败，已尝试回滚；请检查磁盘空间、权限与事务恢复状态。', 'error')
                    self.respond(500, json.dumps({'error': '内部操作失败，请查看日志并重启以恢复未完成事务。'}, ensure_ascii=False).encode())
                return
            if self.command != 'GET' or path not in ('/', '/index.html', '/app.js', '/style.css'):
                self.respond(404, b'Not found', 'text/plain')
                return
            file = app.web / ('index.html' if path == '/' else path.lstrip('/'))
            body = file.read_bytes()
            if file.suffix == '.html':
                body = body.replace(b'__TOKEN__', app.token.encode())
            self.respond(200, body, (mimetypes.guess_type(str(file))[0] or 'text/plain') + '; charset=utf-8')

        do_GET = handle_request
        do_POST = handle_request
    import zipfile
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = False
    return server
