"""Browser regression for direct QX project attachment, time and signed contracts view."""
import base64, os, tempfile
from io import BytesIO
from pathlib import Path
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx4036_browser_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import tender_store
from core.project_io import dump_project

root=Path(__file__).resolve().parents[1]; web=root/'modern/web'; client=TestClient(app)
def api_forward(req):
    path=str(req['url']).replace('/api/','/',1)
    content=base64.b64decode(req['binary']) if req.get('binary') else (req.get('body') or '').encode()
    result=client.request(req.get('method') or 'GET', '/api'+path,content=content,headers=req.get('headers') or {})
    return {'status':result.status_code,'body':result.text,'type':result.headers.get('content-type','application/json')}
html=(web/'index.html').read_text('utf8').replace('<link rel="icon" href="/assets/qx_icon.png">','')
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(web/'style.css').read_text('utf8')+'</style>')
html=html.replace('<script type="module" src="/app.js"></script>', '''<script>window.fetch=async(url,opts={})=>{
 let binary=null; if(opts.body instanceof Blob){let b=new Uint8Array(await opts.body.arrayBuffer());let x='';for(let i=0;i<b.length;i+=14000)x+=String.fromCharCode(...b.slice(i,i+14000));binary=btoa(x);}
 const r=await QXAPI({url:String(url),method:opts.method||'GET',body:binary?'':opts.body||'',binary,headers:opts.headers||{}});
 return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
};</script><script>'''+(web/'app.js').read_text('utf8')+'</script>''')

if __name__=='__main__':
    lost=tender_store.create({'number':'0322100002526000401','title':'Проигранная закупка','status':'Проиграли','application_due_on':'2026-10-21'})
    win=tender_store.create({'number':'0322100002526000402','title':'Выигранная закупка','status':'Выиграли','auction_on':'2026-10-29','auction_time':'12:30'})
    with sync_playwright() as playwright:
        browser=launch_chromium(playwright)
        page=browser.new_page(viewport={'width':1470,'height':960});page.set_default_timeout(14000)
        errs=[]; page.on('pageerror',lambda e:errs.append(str(e)))
        page.expose_function('QXAPI',api_forward)
        page.set_content(html,wait_until='domcontentloaded');page.wait_for_selector('.sidebar')
        page.locator('[data-action="tender-nav"][data-view="contracts"]').click()
        page.wait_for_selector('.qx-tender-ident')
        assert page.locator('.qx-tender-ident').count()==1,page.locator('.qx-tender-ident').all_inner_texts()
        assert 'Выигранная' in page.locator('.qx-tender-ident').first.inner_text()
        page.locator('[data-action="tender-open"]').first.click()
        page.locator('[data-action="tender-detail-tab"][data-view="projects"]').click()
        assert page.locator('[data-action="tender-import-project"]').is_visible()
        raw=dump_project(reqs=[{'quantity':2,'item_name':'Моноблок'}],plans=[{'req':{'quantity':2,'item_name':'Моноблок'},'rows':[{'qty':1,'price':50000}]}],project_meta={'name':'Подбор 2 шт'})
        page.locator('#file-tender-project').set_input_files({'name':'calc.qxproj','mimeType':'application/octet-stream','buffer':raw})
        page.wait_for_function('state.tenders.current?.projects?.length === 1',timeout=18000)
        assert tender_store.get(win['id'])['purchase_cost']==100000
        assert page.locator('[data-tender-panel="projects"] .activity-item').count()>=1
        page.locator('[data-action="tender-detail-tab"][data-view="overview"]').click()
        assert page.locator('[data-tender-field="auction_time"]').first.input_value()=='12:30'
        page.locator('[data-action="tender-back"]').click()
        page.locator('[data-action="tender-nav"][data-view="calendar"]').click()
        page.evaluate('state.tenders.monthDelta=0;state.tenders.calendarFocus="2026-10-29";render()')
        assert '12:30' in page.locator('.qx-calendar-agenda').inner_text()
        assert not errs,errs
        browser.close()
    print('BROWSER_CONTRACTS_4036_OK')
