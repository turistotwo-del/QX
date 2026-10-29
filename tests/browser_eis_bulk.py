"""Chromium UI: paste two EIS document links -> two files -> source-backed analysis."""
import os
os.environ['QX_OFFLINE_MODE']='1'
import tempfile
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_eis_bulk_browser_')
from fastapi.testclient import TestClient
from docx import Document
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app

ROOT=Path(__file__).resolve().parents[1]
CLIENT=TestClient(app)
EIS_A='https://zakupki.gov.ru/documents/contract.docx'
EIS_B='https://zakupki.gov.ru/documents/tech.docx'

def word(content):
    d=Document();d.add_paragraph(content);b=BytesIO();d.save(b);return b.getvalue()

def call_api(req):
    url=str(req.get('url','')).replace('/api/','/',1)
    r=CLIENT.request(req.get('method') or 'GET','/api'+url,
                     content=str(req.get('body') or '').encode(),headers=req.get('headers') or {})
    return {'status':r.status_code,'body':r.text,'type':r.headers.get('content-type','application/json')}

def main():
    assert CLIENT.post('/api/tenders',json={'number':'0322100002526000466','title':'Пакет документов ЕИС'}).status_code==200
    assets=ROOT/'modern/web'
    html=(assets/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(assets/'style.css').read_text(encoding='utf-8')+'</style>')
    html=html.replace('<script type="module" src="/app.js"></script>',
      '<script>window.fetch=async(url,options={})=>{const r=await QXTESTAPI({url:String(url),method:options.method||"GET",body:options.body||"",headers:options.headers||{}});return new Response(r.body,{status:r.status,headers:{"content-type":r.type}});};</script>'
      '<script>'+(assets/'app.js').read_text(encoding='utf-8')+'</script>')
    docs={EIS_A:('contract.docx',word('Срок поставки 30 календарных дней с даты заключения контракта')),
          EIS_B:('tech.docx',word('Реестровый BIOS является обязательным требованием закупки'))}
    def fake_fetch(url, *, opener=None):return docs[url]
    with sync_playwright() as pw:
        browser=launch_chromium(pw)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.expose_function('QXTESTAPI',call_api)
        page.set_content(html,wait_until='domcontentloaded')
        if page.locator('#tender-nav-toggle').get_attribute('aria-expanded') != 'true':
            page.locator('#tender-nav-toggle').click()
        page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_selector('[data-tender-row]')
        page.locator('[data-action="tender-open"]').first.click()
        page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
        page.locator('#tender-eis-doc-url').fill(EIS_A+'\n'+EIS_B)
        with patch('modern.eis_document_download.fetch_official_document',side_effect=fake_fetch) as dl:
            page.locator('[data-action="tender-eis-document-url"]').click()
            page.wait_for_function("document.querySelectorAll('.tender-doc-list .activity-item').length===2",timeout=20000)
            assert dl.call_count==2, dl.call_count
            page.screenshot(path=str(ROOT/'preview'/'EIS_Bulk_Import_4_0_23.png'),full_page=True)
        cards=CLIENT.get('/api/tenders').json()['items']
        detail=CLIENT.get('/api/tenders/'+cards[0]['id']).json()['tender']
        assert len(detail['documents'])==2,detail['documents']
        assert detail['status']=='Черновик',detail['status']
        assert not errors,errors
        browser.close()
    print('Browser EIS bulk docs: OK')

if __name__=='__main__':
    try: main()
    finally: CLIENT.close()
