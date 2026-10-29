"""Chromium regression: GGUF is displayed as local model, no phantom AI button."""
from __future__ import annotations
import os
os.environ['QX_OFFLINE_MODE'] = '1'
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

os.environ['QX_DATA_DIR'] = tempfile.mkdtemp(prefix='qx_browser_gguf_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import local_ai

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def bridge(payload):
    url=str(payload.get('url','')).replace('/api/','/',1)
    rsp=client.request(payload.get('method') or 'GET','/api'+url,
                      content=str(payload.get('body') or '').encode(),
                      headers=payload.get('headers') or {})
    return {'status':rsp.status_code,'body':rsp.text,
            'type':rsp.headers.get('content-type','application/json')}


def test_browser():
    models=local_ai.gguf_model_dir()
    models.mkdir(parents=True,exist_ok=True)
    (models/'demo-qx.gguf').write_bytes(b'GGUF'+b'\x00'*128)
    new=client.post('/api/tenders',json={'number':'0322100002526000466','title':'GGUF demo'})
    assert new.status_code==200, new.text
    directory=ROOT/'modern/web'
    html=(directory/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">',
                      '<style>'+(directory/'style.css').read_text(encoding='utf-8')+'</style>')
    stub='''<script>window.fetch=async(url, options={})=>{
      const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:options.body||'',headers:options.headers||{}});
      return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
    };</script>'''
    html=html.replace('<script type="module" src="/app.js"></script>',
                      stub+'<script>'+(directory/'app.js').read_text(encoding='utf-8')+'</script>')
    browser_path=shutil.which('chromium') or shutil.which('chrome')
    with patch.object(local_ai,'gguf_runtime_available',return_value=True), \
         patch.object(local_ai,'urlopen',side_effect=OSError('Ollama stopped')), \
         sync_playwright() as p:
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1440,'height':900})
        page.set_default_timeout(4500)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.expose_function('QXTESTAPI',bridge)
        page.set_content(html,wait_until='domcontentloaded')
        page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
        page.locator('[data-action="tender-open"]').first.click()
        page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
        page.wait_for_selector('[data-action="tender-ai-model-folder"]')
        page.locator('[data-action="tender-ai-status"]').click()
        page.wait_for_selector('#tender-llm-model option[value="gguf:demo-qx.gguf"]',state='attached')
        assert str(models) in page.locator('.panel[data-tender-panel="docs"]').last.inner_text()
        assert not errors,errors
        browser.close()
    print('Chromium GGUF UI: OK')


if __name__=='__main__':
    try: test_browser()
    finally: client.close()
