"""Actual HTTP, parser, saved projects and sidebar regression for QX 4.0.41."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile

os.environ['QX_OFFLINE_MODE'] = '1'
_DATA = tempfile.TemporaryDirectory(prefix='qx_complexity_browser_')
os.environ['QX_DATA_DIR'] = _DATA.name
os.environ['QX_PORTABLE_DATA_DIR'] = _DATA.name + '/userdata'
os.environ['QX_CATALOG_DIR'] = _DATA.name + '/catalog'

import httpx
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern.start import _start_loopback_server
from test_tz_complexity import SIMPLE, MEDIUM, COMPLEX

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server():
    running, thread, listener, url = _start_loopback_server(app)
    try:
        yield url.rstrip('/')
    finally:
        running.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive()


def main():
    preview = ROOT/'preview'
    preview.mkdir(exist_ok=True)
    with server() as url, httpx.Client(base_url=url, trust_env=False) as api, sync_playwright() as pw:
        card = api.post('/api/tenders', json={'number':'0325100013726000029', 'title':'Контрольная закупка'}).json()['tender']
        browser = launch_chromium(pw)
        page = browser.new_page(viewport={'width':1440,'height':1050})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        toggle = page.locator('#tender-nav-toggle')
        toggle.wait_for()
        assert toggle.get_attribute('aria-expanded') == 'false'
        assert not page.locator('#tender-nav-submenu').is_visible()
        assert page.locator('#workspace-nav-group > summary .nav-text').inner_text() == 'РАСЧЁТ И ДОКУМЕНТЫ'
        assert page.locator('#workspace-nav-group > summary').evaluate('(e)=>getComputedStyle(e).color') == 'rgb(255, 255, 255)'
        assert toggle.evaluate('(e)=>getComputedStyle(e).color') == 'rgb(255, 255, 255)'
        calendar = page.locator('.sidebar .qx-calendar-nav')
        assert calendar.inner_text().strip().endswith('Календарь')
        assert page.locator('#tender-nav-submenu [data-view="calendar"]').count() == 0
        assert page.evaluate('Boolean(document.querySelector(".qx-calendar-nav").compareDocumentPosition(document.querySelector(".sidebar [data-tab=notes]")) & Node.DOCUMENT_POSITION_FOLLOWING)')
        calendar.click()
        page.locator('.tender-calendar-day').first.wait_for()
        assert toggle.get_attribute('aria-expanded') == 'false'
        assert not page.locator('.sidebar .tender-group').evaluate('(e)=>e.classList.contains("active")')
        page.locator('.sidebar [data-tab="home"]').click()
        page.locator(f'.qx-dashboard-tender[data-id="{card["id"]}"]').wait_for()
        page.locator(f'.qx-dashboard-tender[data-id="{card["id"]}"]').click()
        page.locator('[data-tender-panel="overview"]').first.wait_for()
        assert toggle.get_attribute('aria-expanded') == 'false'
        page.locator('.sidebar [data-tab="home"]').click()
        toggle.click()
        assert toggle.get_attribute('aria-expanded') == 'true'
        assert page.locator('#home-eis-number').is_visible(), 'Header click must only toggle, not navigate'
        toggle.press('Space')
        assert toggle.get_attribute('aria-expanded') == 'false'

        group = page.locator('#workspace-nav-group')
        if group.get_attribute('open') is None:
            group.locator('summary').click()
        page.locator('.sidebar [data-tab="tz"]').click()
        files = [
            {'name':'Простое.txt','mimeType':'text/plain','buffer':SIMPLE.encode()},
            {'name':'Среднее.txt','mimeType':'text/plain','buffer':MEDIUM.encode()},
            {'name':'Сложное.txt','mimeType':'text/plain','buffer':COMPLEX.encode()},
            {'name':'Без характеристик.txt','mimeType':'text/plain','buffer':'Договор поставки. Общие условия поставки и приёмки.'.encode()},
        ]
        page.locator('#file-tz').set_input_files(files)
        page.wait_for_function('document.querySelectorAll(".qx-doc-complexity [data-tz-complexity-badge]").length === 4')
        levels = page.locator('.qx-doc-complexity [data-tz-complexity-badge]').evaluate_all('(items)=>items.map(e=>e.dataset.level)')
        assert levels == ['simple','medium','complex','unknown'], levels
        panel = page.locator('[data-tz-complexity]')
        assert panel.get_attribute('data-level') == 'simple'
        page.locator('[data-action="tz-doc-view"]').nth(2).click()
        assert panel.get_attribute('data-level') == 'complex'
        assert 'позиций' in panel.locator('.qx-tz-complexity-reasons').inner_text().lower() or 'позиций' in panel.inner_text().lower()
        assert 'Оценка трудоёмкости' in panel.inner_text()
        assert page.locator('[data-tz-additional] [data-tz-condition=\"special_certification\"]').is_visible()
        assert 'ФСТЭК' not in panel.locator('.qx-tz-complexity-reasons').inner_text()
        assert 'ФСТЭК' in page.locator('[data-tz-additional]').inner_text()
        page.screenshot(path=str(preview/'TZ_Complexity_4_0_41.png'), full_page=False, animations='disabled')

        with page.expect_download() as download:
            page.locator('[data-action="project-save"]').first.click()
        saved_path = Path(download.value.path())
        saved = json.loads(saved_path.read_text())
        assert [d['complexity']['level'] for d in saved['tz_documents']] == levels
        page.reload()
        toggle.wait_for()
        assert toggle.get_attribute('aria-expanded') == 'false'
        page.locator('#file-project').set_input_files({'name':'saved.qxproj','mimeType':'application/octet-stream','buffer':saved_path.read_bytes()})
        page.wait_for_function('document.querySelector(".sidebar [data-tab=build]")?.classList.contains("active")')
        page.locator('.sidebar [data-tab="tz"]').click()
        assert page.locator('.qx-doc-complexity [data-tz-complexity-badge]').evaluate_all('(items)=>items.map(e=>e.dataset.level)') == levels
        assert toggle.get_attribute('aria-expanded') == 'false'
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(preview/'TZ_Complexity_4_0_41_Mobile.png'), full_page=True, animations='disabled')
        dimensions = page.evaluate('({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})')
        assert dimensions['scroll'] <= dimensions['width']+1, dimensions
        assert not errors, errors
        browser.close()
    print('TZ complexity 4.0.41 PASS: real parser, all categories, explanations, multiple documents, save/load, independent calendar, explicit white sidebar toggles, mobile')


if __name__ == '__main__':
    try:
        main()
    finally:
        _DATA.cleanup()
