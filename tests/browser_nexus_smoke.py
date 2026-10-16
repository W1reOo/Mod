"""Real UI/HTTP flow with deterministic Nexus and native-window fixtures, not live Nexus."""
import os
import tempfile
import threading
import zipfile
from pathlib import Path
from unittest.mock import Mock
from playwright.sync_api import sync_playwright, expect
from modmanager.server import App, make_server


def main():
    with tempfile.TemporaryDirectory(prefix='modharbor-nexus-ui-') as temp:
        root=Path(temp)
        app=App(root/'state')
        celeste=root/'Celeste'
        celeste.mkdir()
        game=app.engine.add_game({'name':'Celeste','path':str(celeste)})
        custom=root/'Custom'
        custom.mkdir()
        other=app.engine.add_game({'name':'Custom Game','path':str(custom)})
        archive=root/'manual.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('payload.txt','payload')
        app.account={'name':'Standard User','premium':False}
        app.nexus.mod=Mock(return_value={'mod_id':7,'name':'Celeste Test Mod','summary':'Test fixture',
            'description':'Author instructions <img src=x onerror="alert(1)">','version':'1.0'})
        app.nexus.files=Mock(return_value={'files':[{'file_id':70,'file_name':'manual.zip','name':'Manual ZIP','version':'1'}]})
        app.browser=Mock(embedded=True)
        app.browser.open.return_value={'embedded':True}
        app.browser.current.return_value='https://www.nexusmods.com/celeste/mods/7'
        app.browser.pick_archive.return_value=str(archive)
        server=make_server(app)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                options={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):
                    options.update(executable_path=os.environ['CHROMIUM_PATH'],args=['--no-sandbox'])
                browser=p.chromium.launch(**options)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/#nexus')
                page.locator('.page-heading [data-action="open-nexus"]').click()
                expect(page.locator('#toast')).to_contain_text('应用内')
                app.browser.open.assert_called_with('https://www.nexusmods.com/celeste/mods')
                page.locator('#nexus-query').fill('https://www.nexusmods.com/celeste/mods/7')
                page.locator('[data-action="browse"]').click()
                expect(page.locator('.nexus-card h3')).to_have_text('Celeste Test Mod')
                app.nexus.mod.assert_called_with('celeste',7)
                page.locator('[data-action="nexus-detail"]').click()
                expect(page.locator('.mod-description')).to_contain_text('<img src=x')
                expect(page.locator('.mod-description img')).to_have_count(0)
                page.locator('.modal-head [data-action="close-modal"]').click()
                page.locator('[data-action="files"]').click()
                expect(page.locator('#modal-content')).to_contain_text('普通账户')
                expect(page.locator('#modal-content [data-action="download"]')).to_have_count(0)
                with page.expect_response('**/api/nexus/open'):
                    page.locator('[data-action="open-file"]').click()
                app.browser.open.assert_called_with('https://www.nexusmods.com/celeste/mods/7?tab=files&file_id=70')
                page.locator('.modal-head [data-action="close-modal"]').click()
                page.locator('[data-action="read-nexus"]').click()
                expect(page.locator('#toast')).to_contain_text('已读取')
                page.locator('[data-action="pick-download"]').click()
                expect(page).to_have_url(__import__('re').compile(r'.*#downloads$'))
                expect(page.locator('[data-action="import-download"]')).to_be_disabled()
                expect(page.locator('.mod-item')).to_contain_text('尚无安装适配')
                # Explicitly choose a supported generic test game, then select its own archive.
                page.locator('nav a[href="#nexus"]').click()
                page.locator('#nexus-game').select_option(other['id'])
                page.locator('[data-action="pick-download"]').click()
                expect(page.locator('[data-action="import-download"]')).to_be_enabled()
                page.locator('[data-action="import-download"]').click()
                page.locator('[data-action="confirm-download-import"]').click()
                expect(page.locator('.mod-content h3')).to_contain_text('manual')
                assert not (custom/'Mods/payload.txt').exists(), 'Import must not auto-enable'
                page.set_viewport_size({'width':390,'height':900})
                page.goto(f'http://127.0.0.1:{server.server_port}/#nexus')
                expect(page.locator('h1')).to_be_visible()
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                assert not errors,errors
                browser.close()
                print('PASS: Nexus link/current-page lookup, native browser requests, Standard download fallback, escaped description, file picker and download import')
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
            app.engine.db.close()


if __name__=='__main__':
    main()
