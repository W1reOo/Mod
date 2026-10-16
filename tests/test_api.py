import json
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from modmanager.server import App, make_server, valid_download
from modmanager.nexus import Nexus


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name)
        self.server = make_server(self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.app.engine.db.close()
        self.temp.cleanup()

    def request(self, path, data=None, token=True, **headers):
        if token:
            headers['X-ModHarbor-Token'] = self.app.token
        req = urllib.request.Request(self.base+path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        return urllib.request.urlopen(req)

    def test_static_and_authenticated_state(self):
        with self.request('/') as res:
            html = res.read().decode()
            self.assertIn(self.app.token, html)
            self.assertNotIn('__TOKEN__', html)
            self.assertIn("frame-ancestors 'none'", res.headers['Content-Security-Policy'])
        with self.request('/api/state') as res:
            result = json.load(res)
            self.assertEqual(result['games'], [])
            self.assertEqual(len(result['rules']), 5)

    def test_missing_token_and_cross_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/state', token=False)
        self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/scan', {}, Origin='https://evil.example')
        self.assertEqual(caught.exception.code, 403)

    def test_error_is_reported_and_logged(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/games', {'path':'/nonexistent/modharbor-test'})
        self.assertEqual(caught.exception.code, 400)
        result = json.load(caught.exception)
        self.assertIn('路径', result['error'])
        self.assertEqual(self.app.engine.logs()[0]['level'], 'error')

    def test_api_key_not_returned_or_logged(self):
        with patch.object(self.app.nexus, 'validate', return_value={'name':'Tester','premium':True}):
            with self.request('/api/nexus/connect', {'key':'private-test-key'}) as response:
                self.assertEqual(json.load(response)['name'], 'Tester')
        with self.request('/api/state') as response:
            self.assertNotIn('private-test-key', response.read().decode())
        with self.request('/api/nexus/disconnect', {}) as response:
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(self.app.nexus.key, '')

    def test_nexus_download_imports_real_zip_and_updates_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self.app.engine.add_game({'path': folder, 'rule_id': 'cyberpunk-archive'})
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, 'w') as z:
                z.writestr('archive/pc/mod/test.archive', b'archive payload')
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = io.BytesIO(payload.getvalue())
            file_info = {'file_id':10,'file_name':'test.zip','version':'1.0','category_id':1}
            with patch.object(self.app.nexus, 'mod', return_value={'name':'Nexus Test'}), \
                 patch.object(self.app.nexus, 'files', return_value={'files':[file_info]}), \
                 patch.object(self.app.nexus, 'download_link', return_value='https://cf-files.nexusmods.com/test.zip'), \
                 patch('modmanager.server.urllib.request.build_opener', return_value=opener):
                with self.request('/api/nexus/download', {'game_id':game['id'],'mod_id':42,'file_id':10}) as response:
                    mod = json.load(response)
            self.assertEqual(mod['nexus_id'], 42)
            self.assertFalse(mod['enabled'])
            self.app.engine.toggle(mod['id'], True)
            self.assertEqual((Path(folder)/'archive/pc/mod/test.archive').read_bytes(), b'archive payload')
            with patch.object(self.app.nexus, 'files', return_value={'files':[
                {'file_id':20,'version':'2.0','category_id':1,'uploaded_timestamp':123}]}):
                with self.request('/api/nexus/updates', {}) as response:
                    updates = json.load(response)
            self.assertEqual(updates[0]['latest'], '2.0')
            self.assertEqual(updates[0]['current'], '1.0')
            self.app.engine.remove(mod['id'])
            self.assertFalse((Path(folder)/'archive/pc/mod/test.archive').exists())

    def test_download_url_policy(self):
        self.assertEqual(valid_download('https://cf-files.nexusmods.com/file.zip'), 'https://cf-files.nexusmods.com/file.zip')
        for url in ['http://cf-files.nexusmods.com/a','https://127.0.0.1/a','https://nexusmods.com.evil.test/a','file:///etc/passwd','https://user:pass@files.nexusmods.com/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                valid_download(url)

    def test_nexus_uses_supported_lists_and_exact_id(self):
        nexus = Nexus()
        with patch.object(nexus, 'request', return_value=[{'name':'Sky Test','summary':'weather'}]) as request:
            self.assertEqual(len(nexus.browse('skyrimspecialedition', 'sky', 'updated')), 1)
            request.assert_called_once_with('/games/skyrimspecialedition/mods/latest_updated.json')
        with patch.object(nexus, 'request', return_value={'mod_id':42}) as request:
            self.assertEqual(nexus.browse('stardewvalley', '42'), [{'mod_id':42}])
            request.assert_called_once_with('/games/stardewvalley/mods/42.json')


if __name__ == '__main__':
    unittest.main()
