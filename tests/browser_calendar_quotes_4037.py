"""Browser scenario for combined note/calendar workflow and quotation procedure."""
import base64, os, tempfile
from pathlib import Path
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx4037_browser_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import tender_store, quick_notes

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
    note=quick_notes.create({'title':'Заказать адаптеры Key E','source':'Поручение босса','due_on':'2026-10-27'})
    quote=tender_store.create({'title':'Закупка 200 моноблоков','number':'0322100002526000466','is_quotation':True,'application_due_on':'2026-10-25','auction_on':'2026-10-27','auction_time':'12:00','results_on':'2026-10-27','results_time':'15:00','status':'Подготовка заявки'})
    with sync_playwright() as playwright:
        browser=launch_chromium(playwright)
        page=browser.new_page(viewport={'width':1460,'height':900});page.set_default_timeout(12000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.expose_function('QXAPI',api_forward)
        page.set_content(html,wait_until='domcontentloaded');page.wait_for_selector('.sidebar')
        page.locator('[data-action="tender-nav"][data-view="calendar"]').click()
        page.wait_for_function('state.tenders.calendarNotes && state.tenders.calendarNotes.length>0')
        page.evaluate('''() => { const d=new Date(); state.tenders.monthDelta=(2026-d.getFullYear())*12+9-d.getMonth();state.tenders.calendarFocus='2026-10-27';render(); }''')
        assert page.locator('.qx-calendar-agenda .kind-note').count()==1, page.locator('.qx-calendar-agenda').inner_text()
        assert 'Заказать адаптеры Key E' in page.locator('.qx-calendar-agenda').inner_text()
        assert page.locator('.qx-calendar-agenda .kind-results').count()==1
        assert page.locator('.qx-calendar-agenda .kind-auction').count()==0
        page.locator('.qx-calendar-agenda .kind-note').click()
        page.wait_for_selector('[data-note-field="title"]')
        assert page.locator('[data-note-field="title"]').input_value()=='Заказать адаптеры Key E'
        page.locator('[data-action="notes-complete"]').click()
        page.wait_for_function('state.tab === "notes" && notesState.items.some(n=>n.completed)')
        page.locator('[data-action="tender-nav"][data-view="calendar"]').click()
        page.wait_for_function('state.tenders.calendarNotes && state.tenders.calendarNotes.some(n=>n.completed)')
        assert page.locator('.qx-calendar-agenda .kind-note.completed').count()==1
        page.locator('.qx-calendar-agenda .kind-results').click()
        page.wait_for_selector('[data-tender-field="is_quotation"]')
        assert page.locator('[data-tender-field="is_quotation"]').is_checked()
        assert page.locator('[data-tender-field="results_on"]').count()==2
        assert page.locator('[data-tender-field="auction_on"]').count()==0
        assert not errors, errors
        browser.close()
    print('BROWSER_CALENDAR_QUOTES_4037_OK')
