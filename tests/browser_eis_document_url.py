"""UI acceptance: manually supplied official EIS URL -> document -> analysis."""
import os
os.environ['QX_OFFLINE_MODE']='1'
import tempfile
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
import shutil

os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_eis_doc_browser_')
from fastapi.testclient import TestClient
from docx import Document
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app

ROOT=Path(__file__).resolve().parents[1]
CLIENT=TestClient(app)
EIS_URL='https://zakupki.gov.ru/44fz/filestore/public/contract.docx'

def get_doc():
    d=Document();d.add_paragraph('По контракту необходим реестровый BIOS в составе системного блока.')
    b=BytesIO();d.save(b);return b.getvalue()

def call_api(req):
    url=str(req.get('url','')).replace('/api/','/',1)
    r=CLIENT.request(req.get('method') or 'GET','/api'+url,
                     content=str(req.get('body') or '').encode(),headers=req.get('headers') or {})
    return {'status':r.status_code,'body':r.text,'type':r.headers.get('content-type','application/json')}

def main():
    assert CLIENT.post('/api/tenders',json={'number':'0322100002526000466','title':'Импорт документа ЕИС'}).status_code==200
    assets=ROOT/'modern/web'
    html=(assets/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(assets/'style.css').read_text(encoding='utf-8')+'</style>')
    html=html.replace('<script type="module" src="/app.js"></script>',
      '<script>window.fetch=async(url,options={})=>{const r=await QXTESTAPI({url:String(url),method:options.method||"GET",body:options.body||"",headers:options.headers||{}});return new Response(r.body,{status:r.status,headers:{"content-type":r.type}});};</script>'
      '<script>'+(assets/'app.js').read_text(encoding='utf-8')+'</script>')
    with sync_playwright() as pw:
        browser=launch_chromium(pw)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror', lambda e:errors.append(str(e)))
        page.expose_function('QXTESTAPI',call_api)
        page.set_content(html,wait_until='domcontentloaded')
        page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_selector('[data-tender-row]')
        page.locator('[data-action="tender-open"]').first.click()
        page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
        page.locator('#tender-eis-doc-url').fill(EIS_URL)
        with patch('modern.eis_document_download.fetch_official_document',return_value=('contract.docx',get_doc())) as download:
            page.locator('[data-action="tender-eis-document-url"]').click()
            page.wait_for_selector('.tender-summary',timeout=20000)
            assert page.locator('.tender-summary').count()==1
            assert 'BIOS' in page.locator('.tender-summary').inner_text()
            assert download.called
            preview=ROOT/'preview'
            preview.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(preview/'EIS_Document_Analysis.png'),full_page=True)
        detail=CLIENT.get('/api/tenders/'+CLIENT.get('/api/tenders').json()['items'][0]['id']).json()['tender']
        assert len(detail['documents'])==1
        assert detail['status']=='Черновик'
        assert not errors,errors
        browser.close()
    print('Browser EIS document link: OK')

if __name__=='__main__':main()
CLIENT.close()
