"""Chromium E2E: import tender documentation ZIP from normal file input."""
import base64
import io
import os
os.environ['QX_OFFLINE_MODE'] = '1'
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_browser_package_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from docx import Document
from modern.server import app

client=TestClient(app)
assets=Path(__file__).resolve().parents[1]/'modern'/'web'


def api_call(req):
    path=str(req.get('url','')).replace('/api/','/',1)
    method=req.get('method') or 'GET'
    data=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode('utf-8')
    resp=client.request(method,'/api'+path,content=data,headers=req.get('headers') or {})
    return {'status':resp.status_code,'body':resp.text,'type':resp.headers.get('content-type','application/json')}


def test_import_ui():
    html=(assets/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(assets/'style.css').read_text(encoding='utf-8')+'</style>')
    stub='''<script>
    window.fetch=async(url, options={})=>{
      let binary=null;
      if(options.body instanceof Blob){let a=new Uint8Array(await options.body.arrayBuffer());let x='';for(let i=0;i<a.length;i+=15000)x+=String.fromCharCode(...a.slice(i,i+15000));binary=btoa(x);}
      const r=await QXTESTAPI({url:String(url), method:options.method||'GET', body:binary?'':options.body||'', binary, headers:options.headers||{}});
      return new Response(r.body, {status:r.status, headers:{'content-type':r.type}});
    }
    </script>'''
    html=html.replace('<script type="module" src="/app.js"></script>',stub+'<script>'+(assets/'app.js').read_text(encoding='utf-8')+'</script>')
    with sync_playwright() as p:
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1450,'height':930})
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.expose_function('QXTESTAPI',api_call)
        page.set_content(html,wait_until='domcontentloaded')
        page.wait_for_selector('.sidebar')
        page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_selector('[data-action="tender-new"]')
        page.locator('[data-action="tender-new"]').last.click()
        page.wait_for_selector('.tender-detail-tabs')
        page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
        page.wait_for_selector('#file-tender-package')
        doc=Document();doc.add_paragraph('Реестровый BIOS требуется для комплекта компьютера.')
        buf=io.BytesIO();doc.save(buf)
        archive=io.BytesIO()
        with ZipFile(archive,'w',ZIP_DEFLATED) as z:
            z.writestr('package/Контракт.docx',buf.getvalue())
            z.writestr('package/Извещение.xml',b'<notice><number>0322100002526000466</number></notice>')
            z.writestr('package/setup.exe',b'exe not trusted')
        page.locator('#file-tender-package').set_input_files({'name':'Документация_ЕИС.zip','mimeType':'application/zip','buffer':archive.getvalue()})
        page.wait_for_function('document.querySelectorAll(".tender-doc-list .activity-item").length===2',timeout=20000)
        assert page.locator('.tender-doc-list .activity-item').count()==2
        assert page.locator('.tender-detail-tab[aria-selected="true"]').inner_text().startswith('Документы')
        if os.environ.get('QX_SCREENSHOT_DIR'):
            path=Path(os.environ['QX_SCREENSHOT_DIR']);path.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(path/'Tender_Zip_Imported.png'))
        page.locator('[data-action="tender-analyze"]').click()
        page.wait_for_selector('.tender-summary',timeout=20000)
        assert 'BIOS' in page.locator('.tender-summary').inner_text()
        assert not errors, errors
        print('BROWSER PACKAGE IMPORT OK, 2 documents, analysis, 0 JS errors')
        browser.close()

if __name__=='__main__':test_import_ui()

client.close()
