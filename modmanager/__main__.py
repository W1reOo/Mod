import argparse
import os
import platform
import sys
import json
import tempfile
import urllib.request
import zipfile
import threading
import webbrowser
from pathlib import Path
from .server import App, make_server
from .desktop import NexusBrowser


def default_state():
    home = Path.home()
    system = platform.system()
    if system == 'Windows':
        return Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local')) / 'ModHarbor'
    if system == 'Darwin':
        return home / 'Library/Application Support/ModHarbor'
    return Path(os.environ.get('XDG_DATA_HOME', home / '.local/share')) / 'modharbor'


def packaged_self_test(report, core_only=False):
    """Headless check executed by the packaged Windows binary itself."""
    with tempfile.TemporaryDirectory(prefix='modharbor-selftest-') as directory:
        app = App(Path(directory) / 'state')
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import webview
            if not core_only:
                from webview.platforms import winforms
            # Importing the actual backend validates Python.NET and packaged DLLs.
            url = f'http://127.0.0.1:{server.server_port}'
            request = urllib.request.Request(url + '/api/state', headers={'X-ModHarbor-Token': app.token})
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)
            with urllib.request.urlopen(url, timeout=10) as response:
                html = response.read().decode('utf-8')
            for file in ['index.html', 'app.js', 'style.css']:
                if not (app.web / file).is_file():
                    raise RuntimeError(f'Missing packaged asset: {file}')
            if len(data['rules']) != 5 or '__TOKEN__' in html:
                raise RuntimeError('Packaged service did not return the expected state')
            game_dir = Path(directory) / 'game'
            target = game_dir / 'Mods' / 'test.txt'
            target.parent.mkdir(parents=True)
            target.write_text('original', encoding='utf-8')
            game = app.engine.add_game({'path': str(game_dir), 'name': 'Self-test'})
            archive = Path(directory) / 'test.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('test.txt', 'modified')
            mod = app.engine.install(game['id'], archive)
            app.engine.toggle(mod['id'], True)
            if target.read_text(encoding='utf-8') != 'modified':
                raise RuntimeError('Packaged MOD deployment failed')
            app.engine.toggle(mod['id'], False)
            if target.read_text(encoding='utf-8') != 'original':
                raise RuntimeError('Packaged original-file restoration failed')
            app.engine.remove(mod['id'])
            Path(report).write_text(json.dumps({'ok': True, 'rules': len(data['rules']),
                'desktop_backend': 'not-tested' if core_only else 'winforms', 'web_assets': True, 'mod_lifecycle': True, 'frozen': bool(getattr(sys, 'frozen', False))}), encoding='utf-8')
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
            app.engine.db.close()


def main():
    parser = argparse.ArgumentParser(description='ModHarbor · 跨平台 MOD 管理器')
    parser.add_argument('--data-dir', type=Path, default=default_state())
    parser.add_argument('--port', type=int, default=0 if getattr(sys, 'frozen', False) else 8765)
    parser.add_argument('--desktop', action='store_true', default=bool(getattr(sys, 'frozen', False)), help='通过可选 pywebview 启动原生窗口')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--self-test', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--self-test-core', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        packaged_self_test(args.self_test, args.self_test_core)
        return
    # An exclusive instance lock protects database/file transactions across processes.
    args.data_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (args.data_dir / 'instance.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            lock_file.seek(0)
            lock_file.write(b'0')
            lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if getattr(sys, 'frozen', False):
            raise RuntimeError('此数据目录已有一个 ModHarbor 实例正在运行。')
        parser.exit(1, '此数据目录已有一个 ModHarbor 实例正在运行。\n')
    app = App(args.data_dir)
    server = make_server(app, args.port)
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        if sys.stdout and not getattr(sys, 'frozen', False):
            try:
                print(f'ModHarbor 已启动 · {url}\n数据目录：{app.engine.state}', flush=True)
            except UnicodeEncodeError:
                print(f'ModHarbor: {url}', flush=True)
        if args.desktop:
            try:
                import webview
            except ImportError:
                parser.exit(1, '请先安装桌面依赖：pip install -e ".[desktop]"\n')
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                webview.settings['ALLOW_DOWNLOADS'] = True
                webview.settings['ALLOW_FILE_URLS'] = False
                app.browser = NexusBrowser(webview)
                main_window = webview.create_window('ModHarbor', url, width=1400, height=900, min_size=(960, 640))
                app.browser.main_window = main_window
                main_window.events.closed += app.browser.close
                webview.start(gui='edgechromium' if os.name == 'nt' else None)
            finally:
                server.shutdown()
        else:
            if not args.no_browser:
                webbrowser.open(url)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.engine.db.close()
        lock_file.close()


if __name__ == '__main__':
    main()
