import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from modmanager.__main__ import main, packaged_self_test
from modmanager.server import make_server


class DesktopTests(unittest.TestCase):
    def test_frozen_exe_opens_desktop_with_automatic_port(self):
        desktop = SimpleNamespace(create_window=Mock(), start=Mock())
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
