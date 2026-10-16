import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from modmanager.engine import Engine
from modmanager.scanner import scan_games, scan_other_launchers


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.gamepath = self.root / 'game'
        self.gamepath.mkdir()
        self.engine = Engine(self.root / 'state')
        self.game = self.engine.add_game({'path': str(self.gamepath), 'name': 'Test Game'})
        self.counter = 0

    def tearDown(self):
        self.engine.db.close()
        self.temp.cleanup()

    def bundle(self, files, metadata=None, game=None, rule=None):
        self.counter += 1
        archive = self.root / f'package{self.counter}.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for path, content in files.items():
                info = zipfile.ZipInfo('placeholder')
                info.filename = path
                info.orig_filename = path
                z.writestr(info, content)
        return self.engine.install((game or self.game)['id'], archive, metadata, rule)

    def test_complete_lifecycle_preserves_original(self):
        target = self.gamepath / 'Mods/config.ini'
        target.parent.mkdir()
        target.write_text('original')
        mod = self.bundle({'Mods/config.ini': 'modded', 'extra.txt': 'new'})
        self.assertEqual(target.read_text(), 'original')
        self.engine.toggle(mod['id'], True)
        self.assertEqual(target.read_text(), 'modded')
        self.assertEqual((self.gamepath / 'Mods/extra.txt').read_text(), 'new')
        self.engine.toggle(mod['id'], False)
        self.assertEqual(target.read_text(), 'original')
        self.assertFalse((self.gamepath / 'Mods/extra.txt').exists())
        self.engine.toggle(mod['id'], True)
        self.engine.remove(mod['id'])
        self.assertEqual(target.read_text(), 'original')
        self.assertEqual(self.engine.mods(), [])

    def test_file_conflict_rejected_without_mutating_game(self):
        first = self.bundle({'a.txt': 'one'})
        second = self.bundle({'A.txt': 'two'})
        self.engine.toggle(first['id'], True)
        with self.assertRaisesRegex(ValueError, '冲突'):
            self.engine.toggle(second['id'], True)
        self.assertEqual((self.gamepath / 'Mods/a.txt').read_text(), 'one')
        self.assertFalse(self.engine.mod(second['id'])['enabled'])

    def test_external_edit_is_not_overwritten(self):
        mod = self.bundle({'a.txt': 'modded'})
        self.engine.toggle(mod['id'], True)
        (self.gamepath / 'Mods/a.txt').write_text('user changes')
        with self.assertRaisesRegex(ValueError, '外部修改'):
            self.engine.toggle(mod['id'], False)
        self.assertEqual((self.gamepath / 'Mods/a.txt').read_text(), 'user changes')
        self.assertTrue(self.engine.mod(mod['id'])['enabled'])

    def test_dependencies_and_disable_order(self):
        base = self.bundle({'base.txt': 'base'}, {'name': 'Base'})
        dependent = self.bundle({'feature.txt': 'feature', 'modmanager.json': json.dumps({'dependencies': ['Base']})})
        with self.assertRaisesRegex(ValueError, '缺少'):
            self.engine.toggle(dependent['id'], True)
        self.engine.toggle(base['id'], True)
        self.engine.toggle(dependent['id'], True)
        with self.assertRaisesRegex(ValueError, '依赖'):
            self.engine.remove(base['id'])
        self.engine.toggle(dependent['id'], False)
        self.engine.toggle(base['id'], False)

    def test_declared_conflict(self):
        first = self.bundle({'a': 'one'}, {'name': 'Base'})
        second = self.bundle({'b': 'two', 'modmanager.json': '{"conflicts":["Base"]}'})
        self.engine.toggle(first['id'], True)
        with self.assertRaisesRegex(ValueError, '声明冲突'):
            self.engine.toggle(second['id'], True)

    def test_traversal_and_windows_paths_rejected(self):
        for path in ['../escape', '/absolute', 'C:/escape', 'a\\escape', 'a/../../escape', 'CON.txt', 'trailing.']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.bundle({path: 'evil'})
        self.assertEqual(self.engine.mods(), [])

    @unittest.skipIf(os.name == 'nt', 'symlink privilege varies on Windows')
    def test_symlink_destination_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.gamepath / 'Mods').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            self.bundle({'escape.txt': 'evil'})
        self.assertFalse((outside / 'escape.txt').exists())

    def test_archive_symlink_rejected(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            info = zipfile.ZipInfo('link')
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            z.writestr(info, '/etc/passwd')
        with self.assertRaisesRegex(ValueError, '符号链接'):
            self.engine.install(self.game['id'], archive)

    def test_partial_deploy_rolls_back(self):
        original = self.gamepath / 'Mods/a'
        original.parent.mkdir()
        original.write_text('original')
        mod = self.bundle({'a': 'new', 'b': 'new'})
        copy = self.engine._atomic_copy
        count = 0
        def fail_second(source, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('simulated disk failure')
            copy(source, target)
        with patch.object(self.engine, '_atomic_copy', side_effect=fail_second), self.assertRaises(OSError):
            self.engine.toggle(mod['id'], True)
        self.assertEqual(original.read_text(), 'original')
        self.assertFalse((self.gamepath / 'Mods/b').exists())
        self.assertFalse(self.engine.mod(mod['id'])['enabled'])
        self.assertFalse((self.engine.state / 'transaction').exists())

    def test_crash_recovery_restores_uncommitted_files(self):
        target = self.gamepath / 'Mods/a'
        target.parent.mkdir()
        target.write_text('before')
        mod = self.bundle({'a': 'after'})
        self.engine._snapshot(self.game, mod)
        target.write_text('after')
        self.engine.db.close()
        self.engine = Engine(self.root / 'state')
        self.assertEqual(target.read_text(), 'before')
        self.assertFalse(self.engine.mod(mod['id'])['enabled'])

    def test_recovery_refuses_unknown_external_edits(self):
        mod = self.bundle({'a': 'after'})
        self.engine._snapshot(self.game, mod)
        target = self.gamepath / 'Mods/a'
        target.parent.mkdir(parents=True)
        target.write_text('external changes after crash')
        with self.assertRaisesRegex(ValueError, '外部修改'):
            self.engine.recover()
        self.assertEqual(target.read_text(), 'external changes after crash')
        self.assertTrue((self.engine.state / 'transaction/journal.json').exists())

    def test_committed_journal_keeps_deployment(self):
        target = self.gamepath / 'Mods/a'
        mod = self.bundle({'a': 'after'})
        journal = self.engine._snapshot(self.game, mod)
        target.parent.mkdir(parents=True)
        target.write_text('after')
        with self.engine.db:
            self.engine.db.execute('INSERT INTO operations VALUES(?)', (journal['id'],))
        self.engine.recover()
        self.assertEqual(target.read_text(), 'after')

    def test_package_hash_checked(self):
        mod = self.bundle({'a': 'good'})
        (self.engine.state / 'packages' / mod['id'] / 'Mods/a').write_text('tampered')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            self.engine.toggle(mod['id'], True)

    def test_fomod_not_silently_deployed(self):
        with self.assertRaisesRegex(ValueError, 'FOMOD'):
            self.bundle({'fomod/ModuleConfig.xml': '<config/>'})

    def test_duplicate_archive_targets_rejected(self):
        with self.assertRaisesRegex(ValueError, '重复'):
            self.bundle({'Mods/a': 'one', 'a': 'two'})

    def test_smapi_dependencies_and_minimum_version(self):
        game_dir = self.root / 'stardew'
        game_dir.mkdir()
        (game_dir / 'StardewModdingAPI').write_text('loader')
        game = self.engine.add_game({'path': str(game_dir), 'rule_id': 'stardew-smapi'})
        base = self.bundle({'Base/manifest.json': json.dumps({'UniqueID':'Test.Base','Version':'1.2.0'})}, game=game)
        dependent = self.bundle({'Feature/manifest.json': json.dumps({'UniqueID':'Test.Feature','Version':'1.0',
            'Dependencies':[{'UniqueID':'Test.Base','MinimumVersion':'1.3.0'}]})}, game=game)
        self.engine.toggle(base['id'], True)
        with self.assertRaisesRegex(ValueError, '版本不足'):
            self.engine.toggle(dependent['id'], True)

    def test_multiple_rules_for_same_game_and_loader_required(self):
        other = self.root / 'cyberpunk'
        other.mkdir()
        game = self.engine.add_game({'path':str(other),'rule_id':'cyberpunk-archive'})
        mod = self.bundle({'hello.reds':'// script'}, game=game, rule='cyberpunk-redscript')
        with self.assertRaisesRegex(ValueError, '缺少加载器'):
            self.engine.toggle(mod['id'], True)
        loader = other / 'engine/tools/scc.exe'
        loader.parent.mkdir(parents=True)
        loader.write_text('loader')
        self.engine.toggle(mod['id'], True)
        self.assertEqual((other / 'r6/scripts/hello.reds').read_text(), '// script')

    def test_heroic_metadata_scan(self):
        config = self.root / '.config/legendary'
        config.mkdir(parents=True)
        (config / 'installed.json').write_text(json.dumps({'game': {
            'title':'Stardew Valley','install_path':str(self.gamepath),'version':'1.6.15'}}))
        with patch('modmanager.scanner.Path.home', return_value=self.root), \
             patch('modmanager.scanner.platform.system', return_value='Linux'), \
             patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root / 'none')}):
            games, warnings = scan_other_launchers()
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]['rule_id'], 'stardew-smapi')
        self.assertEqual(games[0]['version'], '1.6.15')
        self.assertEqual(warnings, [])

    def test_windows_epic_metadata_scan(self):
        import types
        manifest_dir = self.root / 'Epic/EpicGamesLauncher/Data/Manifests'
        manifest_dir.mkdir(parents=True)
        (manifest_dir / 'game.item').write_text(json.dumps({'DisplayName':'Cyberpunk 2077',
            'InstallLocation':str(self.gamepath),'AppVersionString':'2.21'}))
        registry = types.SimpleNamespace(KEY_WOW64_32KEY=1, KEY_WOW64_64KEY=2,
            KEY_READ=4, HKEY_LOCAL_MACHINE=0, OpenKey=lambda *args: (_ for _ in ()).throw(FileNotFoundError()))
        with patch('modmanager.scanner.Path.home', return_value=self.root), \
             patch('modmanager.scanner.platform.system', return_value='Windows'), \
             patch.dict(os.environ, {'PROGRAMDATA': str(self.root)}), \
             patch.dict('sys.modules', {'winreg':registry}):
            games, warnings = scan_other_launchers()
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]['source'], 'Epic')
        self.assertEqual(games[0]['version'], '2.21')
        self.assertEqual(warnings, [])

    def test_scanner_finds_external_library_and_buildid(self):
        steam = self.root / 'steam'
        extra = self.root / 'external'
        (steam / 'steamapps').mkdir(parents=True)
        installed = extra / 'steamapps/common/Stardew Valley'
        installed.mkdir(parents=True)
        (steam / 'steamapps/libraryfolders.vdf').write_text(f'"libraryfolders" {{ "1" {{ "path" "{extra.as_posix()}" }} }}')
        (extra / 'steamapps/appmanifest_413150.acf').write_text('"AppState" { "appid" "413150" "name" "Stardew Valley" "installdir" "Stardew Valley" "buildid" "7654321" }')
        with patch('modmanager.scanner.default_steam_roots', return_value=[steam]):
            games, warnings = scan_games()
        self.assertEqual(warnings, [])
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]['path'], str(installed))
        self.assertEqual(games[0]['version'], '7654321')
        self.assertEqual(games[0]['rule_id'], 'stardew-smapi')


if __name__ == '__main__':
    unittest.main()
