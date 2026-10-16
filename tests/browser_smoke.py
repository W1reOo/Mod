"""Optional real-browser lifecycle test: pip install playwright; python tests/browser_smoke.py.
Uses Chromium from CHROMIUM_PATH or Playwright's installed browsers. All files are temporary.
"""
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory(prefix='modharbor-browser-') as temp:
        root = Path(temp)
        game = root / 'DemoGame'
        (game / 'Mods').mkdir(parents=True)
        (game / 'Mods/config.ini').write_text('original')
        archive = root / 'browser-mod.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('config.ini', 'modded')
            z.writestr('modmanager.json', '{"name":"Browser Smoke","version":"2.0"}')
        proc = subprocess.Popen([sys.executable, '-m', 'modmanager', '--data-dir', str(root / 'state'),
                                 '--port', '0', '--no-browser'], stdout=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline()
            assert 'http://' in line, line
            url = 'http://' + line.split('http://', 1)[1].strip()
            with sync_playwright() as p:
                options = {'headless':True}
                if os.environ.get('CHROMIUM_PATH'):
                    options['executable_path'] = os.environ['CHROMIUM_PATH']
                    options['args'] = ['--no-sandbox']
                browser = p.chromium.launch(**options)
                page = browser.new_page(viewport={'width':1440,'height':1000})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(url)
                expect(page.locator('.hero')).to_be_visible()
                page.locator('[data-action="add-game"]').click()
                page.locator('#game-name').fill('Browser Test Game')
                page.locator('#game-path').fill(str(game))
                page.locator('#game-rule').select_option('custom-directory')
                page.locator('[data-action="save-game"]').click()
                expect(page.locator('dialog')).not_to_be_visible()
                page.locator('nav a[href="#mods"]').click()
                page.locator('.page-heading [data-action="import"]').click()
                page.locator('#archive-path').fill(str(archive))
                page.locator('[data-action="save-import"]').click()
                expect(page.locator('.mod-content h3')).to_contain_text('Browser Smoke')
                assert (game / 'Mods/config.ini').read_text() == 'original'
                page.locator('.switch').click()
                page.locator('#enable-confirm').check()
                page.locator('[data-action="confirm-enable"]').click()
                expect(page.locator('.switch')).to_have_attribute('aria-checked','true')
                assert (game / 'Mods/config.ini').read_text() == 'modded'
                page.locator('.switch').click()
                expect(page.locator('.switch')).to_have_attribute('aria-checked','false')
                assert (game / 'Mods/config.ini').read_text() == 'original'
                page.locator('[data-action="remove"]').click()
                page.locator('[data-action="confirm-remove"]').click()
                expect(page.locator('.mod-item')).to_have_count(0)
                for width in (1440,390):
                    page.set_viewport_size({'width':width,'height':900})
                    for view in ['overview','games','mods','nexus','updates','logs','settings']:
                        page.goto(url+'/#'+view)
                        expect(page.locator('h1')).to_be_visible()
                        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), (width,view)
                assert not errors, errors
                browser.close()
                print('PASS: real-browser add / import / enable / disable / remove; 7 views at desktop and mobile; no JS errors')
        finally:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == '__main__':
    main()
