"""Offline Chromium smoke for QX 4.0.38 UI, no live EIS requests."""
import base64, os, tempfile
from pathlib import Path
from unittest.mock import patch
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx4038_browser_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import tender_store

ROOT=Path(__file__).resolve().parents[1]
web=ROOT/'modern/web';client=TestClient(app)
def api_forward(req):
    path=str(req['url']).replace('/api/','/',1)
    content=base64.b64decode(req['binary']) if req.get('binary') else (req.get('body') or '').encode()
    result=client.request(req.get('method') or 'GET','/api'+path,content=content,headers=req.get('headers') or {})
    return {'status':result.status_code,'body':result.text,'type':result.headers.get('content-type','application/json')}
html=(web/'index.html').read_text('utf8').replace('<link rel="icon" href="/assets/qx_icon.png">','')
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(web/'style.css').read_text('utf8')+'</style>')
html=html.replace('<script type="module" src="/app.js"></script>', '''<script>window.fetch=async(url,opts={})=>{
 let binary=null;if(opts.body instanceof Blob){let b=new Uint8Array(await opts.body.arrayBuffer());let x='';for(let i=0;i<b.length;i+=14000)x+=String.fromCharCode(...b.slice(i,i+14000));binary=btoa(x);}
 const r=await QXAPI({url:String(url),method:opts.method||'GET',body:binary?'':opts.body||'',binary,headers:opts.headers||{}});
 return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
};</script><script>'''+(web/'app.js').read_text('utf8')+'</script>''')
if __name__=='__main__':
    t=tender_store.create({'title':'Контракт на тест','number':'0322100002526000466','status':'Выиграли'})
    with sync_playwright() as p:
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1550,'height':920})
        page.set_default_timeout(10000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.expose_function('QXAPI',api_forward)
        page.set_content(html,wait_until='domcontentloaded')
        page.wait_for_selector('.sidebar')
        # A new unsaved active calculation warns before replacement.
        # Calculation tools now live in an explicit disclosure group.
        page.locator('#workspace-nav-group > summary').click()
        page.locator('[data-action="tab"][data-tab="tz"]').click()
        page.locator('[data-action="new-position"]').first.click()
        page.locator('[data-action="new-position"]').first.click()
        page.locator('[data-action="new"]').first.click()
        assert page.get_by_text('Расчёт ещё не сохранён').is_visible()
        page.locator('[data-action="close-modal"]').first.click()
        assert len(page.evaluate('state.reqs'))==2
        page.locator('[data-action="new"]').first.click()
        page.locator('[data-action="new-discard"]').click()
        assert len(page.evaluate('state.reqs'))==1
        # Tender stage add and delete with confirm confirmation.
        if page.locator('#tender-nav-toggle').get_attribute('aria-expanded') != 'true':
            page.locator('#tender-nav-toggle').click()
        page.locator('[data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_selector('[data-action="tender-open"]')
        page.locator('[data-action="tender-open"]').first.click()
        page.locator('[data-action="tender-detail-tab"][data-view="shipments"]').click()
        assert page.get_by_text('План поставок').is_visible()
        page.locator('#ship-name').fill('Первая партия')
        page.locator('#ship-qty').fill('12')
        page.locator('#ship-due').fill('2026-11-06')
        page.locator('[data-action="tender-add-shipment"]').click()
        page.wait_for_selector('.qx-shipment-item')
        assert 'Первая партия' in page.locator('.qx-shipment-item').inner_text()
        assert len(tender_store.detail(t['id'])['shipments'])==1
        page.on('dialog',lambda dialog:dialog.accept())
        page.locator('[data-action="tender-delete-stage"]').click()
        page.wait_for_function('state.tenders.current.shipments.length===0')
        assert not tender_store.detail(t['id'])['shipments']
        # EIS discovery data rendered safely; manual EIS download remains available.
        page.locator('[data-action="tender-detail-tab"][data-view="docs"]').click()
        assert page.locator('[data-action="tender-eis-discover"]').count()==1
        with patch('modern.eis_discovery.discover_for_tender',return_value={'notice_number':t['number'], 'checked_pages':1, 'found':1, 'available':True, 'message':'Найдено','documents':[{'title':'Контракт.pdf','url':'https://zakupki.gov.ru/44fz/filestore/contract.pdf'}]}) as mocked:
            page.locator('[data-action="tender-eis-discover"]').click()
            page.wait_for_selector('.qx-eis-file')
        assert 'Контракт.pdf' in page.locator('.qx-eis-file').inner_text()
        assert not errors,errors
        (ROOT/'preview').mkdir(exist_ok=True)
        page.screenshot(path=str(ROOT/'preview/QX4038_UI_check.png'),full_page=True,animations='disabled')
        browser.close()
    print('BROWSER_4038_OK')
