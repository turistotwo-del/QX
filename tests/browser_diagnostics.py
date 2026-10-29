"""Real Chromium: visible health report in Settings, no network required."""
from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_browser_diag_')
os.environ['QX_CATALOG_DIR']=os.path.join(os.environ['QX_DATA_DIR'],'catalog')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern.release_info import APP_VERSION
from modern import local_ai
from modern import tender_store as tenders
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    browser_path=shutil.which('chromium') or shutil.which('chrome')
    directory=ROOT/'modern/web'
    html=(directory/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">',
                      '<style>'+(directory/'style.css').read_text(encoding='utf-8')+'</style>')
    shim='''<script>window.fetch=async(url, options={})=>{
      const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:options.body||'',headers:options.headers||{}});
      return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
    };</script>'''
    html=html.replace('<script type="module" src="/app.js"></script>',shim+'<script>'+(directory/'app.js').read_text(encoding='utf-8')+'</script>')
    t=tenders.create({'title':'Browser audit fixture'})
    tenders.add_document(t['id'],'Browser contract.txt',b'BIOS in registry')
    with TestClient(app) as client, patch.object(local_ai,'gguf_runtime_available',return_value=False), sync_playwright() as p:
        def bridge(payload):
            url=str(payload.get('url',''))
            method=str(payload.get('method','GET'))
            body=payload.get('body') or ''
            response=client.request(method,url,
                                    content=body.encode() if isinstance(body,str) else body,
                                    headers=payload.get('headers') or {})
            return {'status':response.status_code,'body':response.text,'type':response.headers.get('content-type','application/json')}
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1450,'height':900})
        page.set_default_timeout(7500)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.expose_function('QXTESTAPI',bridge)
        page.set_content(html,wait_until='domcontentloaded')
        page.locator('[data-action="tab"][data-tab="settings"]').click()
        panel=page.locator('#qx-diag-panel')
        panel.locator('[data-action="diagnostics-run"]').click()
        page.wait_for_function("document.querySelector('#qx-diag-panel')?.innerText.includes('База закупок')")
        contents=panel.inner_text()
        assert APP_VERSION in contents,contents[:200]
        assert 'Папка данных' in contents, contents
        assert 'Локальный AI' in contents, contents
        panel.locator('[data-action="audit-attachments"]').click()
        page.wait_for_function("document.querySelector('#qx-attachment-audit')?.innerText.includes('проверено успешно: 1')")
        assert 'Отсутствуют: 0' in panel.inner_text()
        assert not errors,errors
        preview=ROOT/'preview/Diagnostics_Settings_Current.png'
        preview.parent.mkdir(parents=True,exist_ok=True)
        panel.screenshot(path=str(preview))
        browser.close()
    print('Chromium diagnostics / Settings: OK')

if __name__=='__main__':main()
