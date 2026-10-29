"""Real Chromium QX AI offline-search E2E: no model service, actual stored attachment."""
from __future__ import annotations
import os
os.environ['QX_OFFLINE_MODE'] = '1'
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ['QX_DATA_DIR'] = tempfile.mkdtemp(prefix='qx_browser_ai_offline_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import local_ai

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def bridge(payload):
    url=str(payload.get('url','')).replace('/api/','/',1)
    body=payload.get('body') or ''
    resp=client.request(payload.get('method') or 'GET', '/api'+url,
                        content=body.encode('utf-8') if isinstance(body,str) else body,
                        headers=payload.get('headers') or {})
    return {'status':resp.status_code,'body':resp.text,
            'type':resp.headers.get('content-type','application/json')}


def test_browser():
    create=client.post('/api/tenders',json={'number':'0322100002526000466','title':'Тест локального поиска'})
    assert create.status_code==200, create.text
    id=create.json()['tender']['id']
    response=client.post(f'/api/tenders/{id}/documents',
                         content='Требуется реестровый BIOS. Поставить в течение 30 календарных дней.'.encode(),
                         headers={'X-File-Name':'contract.txt','Content-Type':'application/octet-stream'})
    assert response.status_code==200,response.text
    assets=ROOT/'modern'/'web'
    html=(assets/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">',
                      '<style>'+(assets/'style.css').read_text(encoding='utf-8')+'</style>')
    snippet='''<script>window.fetch=async(url, options={})=>{
      const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:options.body||'',headers:options.headers||{}});
      return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
    };</script>'''
    html=html.replace('<script type="module" src="/app.js"></script>',
                      snippet+'<script>'+(assets/'app.js').read_text(encoding='utf-8')+'</script>')
    path=shutil.which('chromium') or shutil.which('chrome')
    with patch.object(local_ai,'urlopen',side_effect=OSError('Ollama unavailable')), \
         patch.object(local_ai,'gguf_runtime_available',return_value=False), \
         sync_playwright() as p:
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1450,'height':900})
        page.set_default_timeout(8000)
        problems=[]
        page.on('pageerror',lambda exc:problems.append(str(exc)))
        page.expose_function('QXTESTAPI',bridge)
        page.set_content(html,wait_until='domcontentloaded')
        if page.locator('#tender-nav-toggle').get_attribute('aria-expanded') != 'true':
            page.locator('#tender-nav-toggle').click()
        page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
        page.locator('[data-action="tender-open"]').first.click()
        page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
        page.wait_for_selector('#tender-llm-model')
        assert page.locator('#tender-llm-model').input_value() == 'offline-search'
        page.locator('#tender-llm-question').fill('Нужен ли реестровый BIOS?')
        page.locator('[data-action="tender-local-ai"]').click()
        answer=page.locator('.readonly:has-text("Реестровый BIOS")')
        answer.wait_for()
        assert 'contract.txt' in answer.inner_text()
        assert page.locator('[data-action="tender-ai-model-download"]').is_disabled()
        assert not problems,problems
        browser.close()
    print('Chromium QX AI offline citations & GGUF-disabled UX: OK')


if __name__ == '__main__':
    try: test_browser()
    finally: client.close()
