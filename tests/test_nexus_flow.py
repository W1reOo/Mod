import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from modmanager.engine import Engine
from modmanager.server import App
from modmanager.nexus import parse_mod_url, website_url


class NexusFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = App(self.root / 'state')
        self.game_dir = self.root / 'Celeste'
        self.game_dir.mkdir()
        self.game = self.app.engine.add_game({'path':str(self.game_dir), 'name':'Celeste'})

    def tearDown(self):
        self.app.engine.db.close()
        self.temp.cleanup()

    def call(self, route, **data):
        return self.app.api('POST', '/api/' + route, data)

    def test_link_parser_and_query_sanitization(self):
        self.assertEqual(parse_mod_url('https://www.nexusmods.com/celeste/mods/7?tab=files'), ('celeste',7))
        self.assertEqual(parse_mod_url('https://www.nexusmods.com/games/celeste/mods/7'), ('celeste',7))
        self.assertEqual(website_url('https://www.nexusmods.com/celeste/mods/7?tab=files&apikey=private&file_id=10'),
                         'https://www.nexusmods.com/celeste/mods/7?tab=files&file_id=10')
        for url in ['http://www.nexusmods.com/celeste/mods/7', 'https://www.nexusmods.com.evil.test/celeste/mods/7',
                    'https://user@www.nexusmods.com/celeste/mods/7', 'https://www.nexusmods.com:443/celeste/mods/7',
                    'https://www.nexusmods.com/celeste/mods/../7','file:///C:/secret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_mod_url(url)

    def test_celeste_domain_is_available_without_install_recipe(self):
        self.assertEqual(self.game['domain'], 'celeste')
        self.assertFalse(self.game['supported'])
        with patch.object(self.app.nexus, 'mod', return_value={'mod_id':7,'name':'C. full cheat player'}) as request:
            result = self.call('nexus/resolve', game_id=self.game['id'], url='https://www.nexusmods.com/celeste/mods/7')
            self.assertEqual(result['mod']['mod_id'],7)
            request.assert_called_once_with('celeste',7)

    def test_old_celeste_record_migrates_without_changing_install_rule(self):
        old = dict(self.game, domain='', supported=False)
        with self.app.engine.db:
            self.app.engine.save('games', old)
        self.app.engine.db.close()
        self.app.engine = Engine(self.root / 'state')
        game = self.app.engine.game(old['id'])
        self.assertEqual(game['domain'], 'celeste')
        self.assertEqual(game['rule_id'], 'custom-directory')
        self.assertFalse(game['supported'])

    def test_user_selected_unknown_game_can_bind_after_api_success(self):
        path = self.root/'Unknown'
        path.mkdir()
        game = self.app.engine.add_game({'path':str(path),'name':'Unknown'})
        with patch.object(self.app.nexus, 'mod', side_effect=ValueError('Not found')):
            with self.assertRaises(ValueError):
                self.call('nexus/resolve', game_id=game['id'],url='https://www.nexusmods.com/example/mods/2')
        self.assertEqual(self.app.engine.game(game['id'])['domain'],'')
        with patch.object(self.app.nexus, 'mod', return_value={'mod_id':2}):
            self.call('nexus/resolve', game_id=game['id'],url='https://www.nexusmods.com/example/mods/2')
        self.assertEqual(self.app.engine.game(game['id'])['domain'],'example')

    def test_wrong_game_rejected_before_network(self):
        with patch.object(self.app.nexus, 'mod') as request, self.assertRaisesRegex(ValueError,'对应游戏'):
            self.call('nexus/resolve',game_id=self.game['id'],url='https://www.nexusmods.com/skyrimspecialedition/mods/7')
        request.assert_not_called()

    def test_browser_open_requires_no_api_key(self):
        self.app.browser = Mock()
        self.app.browser.open.return_value = {'embedded':True}
        result = self.call('nexus/open',game_id=self.game['id'])
        self.assertTrue(result['embedded'])
        self.app.browser.open.assert_called_once_with('https://www.nexusmods.com/celeste/mods')
        self.assertEqual(self.app.nexus.key,'')

    def test_current_native_page_can_be_resolved(self):
        self.app.browser = Mock()
        self.app.browser.current.return_value='https://www.nexusmods.com/celeste/mods/7'
        with patch.object(self.app.nexus,'mod',return_value={'mod_id':7}):
            result=self.call('nexus/resolve',game_id=self.game['id'],current=True)
        self.assertEqual(result['mod']['mod_id'],7)

    def test_download_only_keeps_file_for_unadapted_game(self):
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w') as z:
            z.writestr('save.celeste','save data')
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value=io.BytesIO(payload.getvalue())
        with patch.object(self.app.nexus,'mod',return_value={'name':'Save File'}), \
             patch.object(self.app.nexus,'files',return_value={'files':[{'file_id':10,'file_name':'save.zip','version':'1'}]}), \
             patch.object(self.app.nexus,'download_link',return_value='https://cf-files.nexusmods.com/save.zip'), \
             patch('modmanager.server.urllib.request.build_opener',return_value=opener):
            result=self.call('nexus/download',game_id=self.game['id'],mod_id=7,file_id=10,download_only=True)
        self.assertTrue(Path(result['download']['path']).is_file())
        self.assertEqual(self.app.engine.mods(),[])
        self.assertEqual(list(self.game_dir.iterdir()),[])
        self.assertEqual(self.app.engine.downloads()[0]['nexus_id'],7)
        with self.assertRaisesRegex(ValueError,'尚无匹配'):
            self.call('downloads/import',id=result['download']['id'],game_id=self.game['id'])

    def test_native_file_picker_registers_file_and_hash_detects_tamper(self):
        file=self.root/'manual.zip'
        with zipfile.ZipFile(file,'w') as z:
            z.writestr('test.txt','data')
        self.app.browser=Mock()
        self.app.browser.pick_archive.return_value=str(file)
        result=self.call('downloads/pick',game_id=self.game['id'])['download']
        file.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'变化'):
            self.call('downloads/import',id=result['id'],game_id=self.game['id'])

    def test_downloaded_zip_imports_into_supported_game(self):
        path=self.root/'Custom'
        path.mkdir()
        game=self.app.engine.add_game({'path':str(path),'name':'Custom'})
        archive=self.root/'manual.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('payload.txt','data')
        downloaded=self.app.engine.register_download(archive,game['id'])
        mod=self.call('downloads/import',id=downloaded['id'],game_id=game['id'],rule_id='custom-directory')
        self.assertFalse(mod['enabled'])
        self.assertTrue(self.app.engine.downloads()[0]['imported'])
        self.app.engine.toggle(mod['id'],True)
        self.assertEqual((path/'Mods/payload.txt').read_text(),'data')


if __name__ == '__main__':
    unittest.main()
