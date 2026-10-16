import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from modmanager.__main__ import main, packaged_self_test
from modmanager.server import make_server
from modmanager.desktop import NexusBrowser


class Event:
    def __init__(self):
        self.handlers = []
    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self



class DesktopTests(unittest.TestCase):
    def test_frozen_exe_opens_desktop_with_automatic_port(self):
        window = Mock()
        window.events = SimpleNamespace(closed=Event())
        desktop = SimpleNamespace(create_window=Mock(return_value=window), start=Mock(), settings={})
        with tempfile.TemporaryDirectory() as data, \
             patch.object(sys, 'argv', ['ModHarbor.exe', '--data-dir', data]), \
             patch.object(sys, 'frozen', True, create=True), \
             patch.dict(sys.modules, {'webview': desktop}), \
             patch('modmanager.__main__.make_server', wraps=make_server) as server, \
             patch('modmanager.__main__.webbrowser.open') as browser:
            main()
            self.assertEqual(server.call_args.args[1], 0)
            desktop.create_window.assert_called_once()
            desktop.start.assert_called_once()
            browser.assert_not_called()

    def test_native_browser_reuses_window_without_privileged_bridge(self):
        window = Mock()
        window.events = SimpleNamespace(closed=Event())
        desktop = SimpleNamespace(create_window=Mock(return_value=window))
        browser = NexusBrowser(desktop)
        result = browser.open('https://www.nexusmods.com/celeste/mods/7')
        self.assertTrue(result['embedded'])
        self.assertIsNone(desktop.create_window.call_args.kwargs['js_api'])
        browser.open('https://www.nexusmods.com/celeste/mods/8')
        desktop.create_window.assert_called_once()
        window.load_url.assert_called_once_with('https://www.nexusmods.com/celeste/mods/8')
        browser.close()
        window.destroy.assert_called_once()
        self.assertIsNone(browser.window)

    def test_native_browser_rejects_foreign_origins(self):
        browser = NexusBrowser(SimpleNamespace(create_window=Mock()))
        for value in ['https://evil.test/celeste/mods/7', 'file:///C:/Windows/win.ini', 'http://www.nexusmods.com/']:
            with self.subTest(url=value), self.assertRaises(ValueError):
                browser.open(value)
        browser.webview.create_window.assert_not_called()

    def test_packaged_core_self_test_writes_machine_readable_result(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(sys.modules, {'webview': SimpleNamespace()}):
            report = Path(folder) / 'result.json'
            packaged_self_test(report, core_only=True)
            result = json.loads(report.read_text())
            self.assertTrue(result['ok'])
            self.assertTrue(result['web_assets'])
            self.assertTrue(result['mod_lifecycle'])
            self.assertEqual(result['desktop_backend'], 'not-tested')


if __name__ == '__main__':
    unittest.main()
