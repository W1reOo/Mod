"""Native Nexus browser. Remote pages never receive the local application's API bridge."""
import threading
import webbrowser
from pathlib import Path
from .nexus import website_url


class NexusBrowser:
    def __init__(self, webview=None, main_window=None):
        self.webview = webview
        self.main_window = main_window
        self.window = None
        self.lock = threading.RLock()

    @property
    def embedded(self):
        return self.webview is not None

    def open(self, url, external=False):
        url = website_url(url)
        if not self.embedded or external:
            if not webbrowser.open(url):
                raise ValueError('无法启动系统浏览器，请复制 Nexus 链接到浏览器打开。')
            return {'embedded': False, 'url': url}
        with self.lock:
            if self.window is None:
                window = self.webview.create_window('Nexus Mods · ModHarbor', url,
                    js_api=None, width=1200, height=850, min_size=(800, 600))
                self.window = window
                def closed():
                    # Never wait for an HTTP-thread lock from the native GUI thread.
                    if self.window is window:
                        self.window = None
                window.events.closed += closed
            else:
                self.window.load_url(url)
                self.window.restore()
        return {'embedded': True, 'url': url}

    def current(self):
        with self.lock:
            window = self.window
        if window is None:
            raise ValueError('请先在应用内打开 Nexus，并进入一个 MOD 的详情页。')
        # The caller validates the domain and MOD route before using it as API input.
        return window.get_current_url()

    def pick_archive(self):
        if not self.embedded or self.main_window is None:
            raise ValueError('浏览器模式请使用“导入 ZIP”填写路径；桌面 EXE 支持文件选择窗口。')
        directory = Path.home() / 'Downloads'
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') as key:
                directory = Path(winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')[0])
        except (ImportError, OSError):
            pass
        paths = self.main_window.create_file_dialog(self.webview.OPEN_DIALOG, allow_multiple=False, directory=str(directory if directory.is_dir() else Path.home()),
            file_types=('MOD archives (*.zip;*.7z;*.rar)', 'All files (*.*)'))
        return paths[0] if paths else None

    def close(self):
        with self.lock:
            window, self.window = self.window, None
        if window is not None:
            window.destroy()
