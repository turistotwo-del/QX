"""Real HTTP/Chromium EIS job lifecycle regression; only source network is mocked.

Run from repository root: PYTHONPATH=. python tests/browser_eis_jobs_4040.py
The source gates stay blocked while the browser navigates/reloads, proving that
card creation and progress do not await a website response. No live EIS is used.
"""
from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.error import URLError

os.environ['QX_OFFLINE_MODE'] = '1'
_DATA = tempfile.TemporaryDirectory(prefix='qx_eis_jobs_browser_')
os.environ['QX_DATA_DIR'] = _DATA.name

import httpx
import uvicorn
from docx import Document
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern.eis_public import parse_notice_metadata

ROOT = Path(__file__).resolve().parents[1]
NUMBER = '0325100013726000029'  # User's number; every remote response remains a fixture.
FAILED_NUMBER = '0373100104826000011'
PARTIAL_NUMBER = '0373100104826000012'
FILE_URL = 'https://zakupki.gov.ru/documents/workspace-4040.docx'
BAD_URL = 'https://zakupki.gov.ru/documents/unavailable-4040.pdf'
TERMINAL = {'succeeded', 'partial', 'failed'}


def document_bytes():
    document = Document()
    document.add_paragraph('Техническое задание. Поставка компьютеров: количество 10 штук.')
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def metadata(number):
    xml = (f'<epNotice><purchaseNumber>{number}</purchaseNumber>'
           '<purchaseName>Закупка — браузерная проверка 4.0.40</purchaseName>'
           '<customer><fullName>Заказчик из проверенного извещения</fullName></customer>'
           '<maxPrice>1250000.50</maxPrice><endDate>2026-12-12T12:30:00</endDate></epNotice>').encode()
    return {'available': True, 'notice': parse_notice_metadata(xml, number),
            'source_url': 'https://zakupki.gov.ru/epz/order/notice/printForm/viewXml.html?regNumber=' + number,
            'search_url': 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=' + number,
            'message': 'Поля получены из тестового XML ЕИС.'}


@contextmanager
def local_server():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical'))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started, 'Local QX HTTP server failed to start'
    try:
        yield 'http://127.0.0.1:' + str(port)
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive(), 'Local QX HTTP server did not stop'


def job(api, job_id):
    response = api.get('/api/eis/jobs/' + job_id)
    response.raise_for_status()
    return response.json()['job']


def wait_job(api, job_id):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        state = job(api, job_id)
        if state['status'] in TERMINAL:
            return state
        time.sleep(.05)
    raise AssertionError(('EIS job did not finish', job(api, job_id)))


def main():
    from modern import tender_store as store
    metadata_entered = threading.Event()
    metadata_release = threading.Event()
    document_entered = threading.Event()
    document_release = threading.Event()
    calls = []
    payload = document_bytes()
    errors = []

    def fetch_metadata(number, **kwargs):
        calls.append(('metadata', number))
        if number == NUMBER:
            metadata_entered.set()
            assert metadata_release.wait(20), 'Browser did not release the metadata gate'
        if number == FAILED_NUMBER:
            raise RuntimeError('Fixture unexpected provider failure')
        if number == PARTIAL_NUMBER:
            return {'available': False, 'notice': None, 'error_type': 'HTTPError',
                    'message': 'ЕИС не предоставила проверяемые сведения: HTTP 403.'}
        return metadata(number)

    def discover(tender_id, **kwargs):
        number = store.get(tender_id)['number']
        files = [FILE_URL, BAD_URL] if number == PARTIAL_NUMBER else [FILE_URL]
        return {'notice_number': number, 'available': True, 'complete': True,
                'documents': [{'url': url, 'title': 'Техническое задание'} for url in files],
                'found': len(files), 'checked_pages': 1, 'errors': [],
                'search_url': 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=' + number,
                'message': 'Найдены ссылки из тестовой страницы ЕИС.'}

    def download(url, **kwargs):
        calls.append(('document', url))
        if url == BAD_URL:
            raise URLError('Fixture HTTP 403 document is unavailable')
        if not document_release.is_set():
            document_entered.set()
            assert document_release.wait(20), 'Browser did not release the document gate'
        return 'Техническое задание 4040.docx', payload

    unavailable = {'available': False, 'notice': None, 'error_type': 'HTTPError',
                   'message': 'ЕИС не предоставила проверяемые сведения: HTTP 403.'}
    try:
        with patch('modern.eis_sync.fetch_notice_metadata', side_effect=fetch_metadata), \
             patch('modern.eis_sync.fetch_notice_html_metadata', return_value=unavailable), \
             patch('modern.eis_sync.lookup_secondary', return_value={**unavailable, 'documents': [], 'found': 0, 'source_name': 'Вторичный тестовый источник'}), \
             patch('modern.eis_discovery.discover_for_tender', side_effect=discover), \
             patch('modern.eis_document_download.fetch_official_document', side_effect=download), \
             local_server() as base_url, httpx.Client(base_url=base_url, timeout=3, trust_env=False) as api, \
             sync_playwright() as playwright:
            for asset in ('/', '/app.js', '/style.css'):
                asset_response = api.get(asset)
                assert asset_response.status_code == 200, (asset, asset_response.status_code)
                assert 'no-store' in asset_response.headers.get('cache-control', '').lower(), asset
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.set_default_timeout(6000)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base_url)
            page.locator('#home-eis-number').wait_for()
            pasted = 'https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=' + NUMBER
            page.locator('#home-eis-number').fill(pasted)
            started = time.monotonic()
            with page.expect_response(lambda response: response.url.endswith('/api/eis/jobs') and response.request.method == 'POST', timeout=3000) as response_info:
                page.locator('#home-eis-number').press('Enter')
            response = response_info.value
            assert response.status == 202, response.text()
            initial = response.json()
            active = initial['job']
            tender_id = initial['tender']['id']
            assert active['number'] == NUMBER, active
            assert active['tender_id'] == tender_id
            create_ms = round((time.monotonic() - started) * 1000)
            assert create_ms < 2000, ('Job creation waited for source network', create_ms)
            print('Job202 elapsed_ms:', create_ms, flush=True)
            assert metadata_entered.wait(2)
            assert not metadata_release.is_set()
            assert len(store.listing()) == 1
            page.locator('.qx-import-job progress').wait_for(timeout=2000)
            page.locator(f'[data-action="tender-open"][data-id="{tender_id}"]').first.wait_for(timeout=2000)

            # Server-side deduplication works even for a second independent caller.
            duplicate = api.post('/api/eis/jobs', json={'number': NUMBER, 'download_documents': True})
            assert duplicate.status_code == 202, duplicate.text
            assert duplicate.json()['job']['id'] == active['id'], duplicate.json()
            assert calls.count(('metadata', NUMBER)) == 1

            # Reload loses JS memory; the persisted job must remain discoverable.
            page.reload()
            page.locator('.qx-import-job progress').wait_for(timeout=2500)
            page.locator(f'[data-action="tender-open"][data-id="{tender_id}"]').first.wait_for(timeout=2500)
            page.locator(f'[data-action="tender-open"][data-id="{tender_id}"]').first.click()
            page.locator('[data-tender-field="number"]').wait_for()
            assert page.locator('[data-tender-field="number"]').input_value() == NUMBER
            assert job(api, active['id'])['status'] in {'queued', 'running'}
            page.locator('.qx-import-job progress').wait_for(timeout=2500)
            preview = ROOT / 'preview'
            preview.mkdir(exist_ok=True)
            page.screenshot(path=str(preview / 'Workspace_4_0_40_Import_Progress.png'), full_page=True, animations='disabled')
            metadata_release.set()
            assert document_entered.wait(3)
            progress = job(api, active['id'])
            assert progress['status'] == 'running', progress
            assert 0 < progress['progress'] < 100, progress
            assert store.get(tender_id)['customer'] == 'Заказчик из проверенного извещения'
            document_release.set()
            finished = wait_job(api, active['id'])
            assert finished['status'] == 'succeeded', finished
            assert finished['progress'] == 100
            assert len(store.detail(tender_id)['documents']) == 1
            page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
            page.locator('.tender-doc-list .activity-item').wait_for(timeout=4000)
            assert 'Техническое задание 4040.docx' in page.locator('.tender-doc-list').inner_text()
            page.locator('.sidebar [data-action="tab"][data-tab="home"]').click()
            page.locator('#home-eis-number').wait_for()

            # An unexpected source error leaves the created draft visible and usable.
            page.locator('#home-eis-number').fill(FAILED_NUMBER)
            with page.expect_response(lambda response: response.url.endswith('/api/eis/jobs') and response.request.method == 'POST') as response_info:
                page.locator('.qx-purchase-form [data-action="home-eis-import"]').click()
            failed_initial = response_info.value.json()
            failed = wait_job(api, failed_initial['job']['id'])
            assert failed['status'] == 'failed', failed
            failed_id = failed_initial['tender']['id']
            assert store.get(failed_id)['number'] == FAILED_NUMBER
            page.locator(f'[data-action="tender-open"][data-id="{failed_id}"]').first.wait_for(timeout=4000)
            page.wait_for_function('!document.querySelector("[data-action=home-eis-import]").disabled', timeout=4000)
            page.locator('.qx-import-feedback.error').wait_for(timeout=4000)
            assert page.locator('.qx-import-feedback.error').inner_text().strip()
            assert page.locator('.qx-import-feedback.error .qx-import-retry').is_visible()

            # Metadata denial and one failed file do not discard a successful download.
            page.locator('#home-eis-number').fill(PARTIAL_NUMBER)
            with page.expect_response(lambda response: response.url.endswith('/api/eis/jobs') and response.request.method == 'POST') as response_info:
                page.locator('.qx-purchase-form [data-action="home-eis-import"]').click()
            partial_initial = response_info.value.json()
            partial = wait_job(api, partial_initial['job']['id'])
            assert partial['status'] == 'partial', partial
            result = partial['result']
            assert result['partial'] is True
            assert result['metadata_available'] is False
            assert len(result['documents_result']['imported']) == 1, result
            assert result['documents_result']['failed_count'] == 1, result
            assert len(store.detail(partial_initial['tender']['id'])['documents']) == 1
            assert len(store.listing()) == 3
            page.wait_for_function('!document.querySelector("[data-action=home-eis-import]").disabled', timeout=4000)
            report = page.locator('.qx-import-feedback.partial')
            report.locator('.qx-import-details > summary').click()
            report.locator('.qx-import-sources').wait_for()
            assert report.locator('.qx-import-source').count() >= 2
            assert '403' in report.locator('.qx-import-sources').inner_text()
            assert 'ошибок файлов: 1' in report.inner_text()
            assert not errors, errors
            preview = ROOT / 'preview'
            preview.mkdir(exist_ok=True)
            page.screenshot(path=str(preview / 'Workspace_4_0_40_Partial_Import.png'), full_page=True, animations='disabled')
            browser.close()
        print('EIS jobs 4.0.40 Chromium PASS: immediate draft, source-delay progress, duplicate job, reload/navigation, failure draft, partial download retention')
    finally:
        metadata_release.set()
        document_release.set()


if __name__ == '__main__':
    try:
        main()
    finally:
        _DATA.cleanup()
