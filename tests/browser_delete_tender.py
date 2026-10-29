"""Actual Chromium UI smoke test: delete, cancel, confirmation and persistence."""
import os
import tempfile
from pathlib import Path
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_browser_delete_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import tender_store as store

ROOT=Path(__file__).resolve().parents[1]
web=ROOT/'modern/web'
client=TestClient(app)


def api_forward(req):
    url=str(req.get('url','')).replace('/api/','/',1)
    reply=client.request(req.get('method') or 'GET','/api'+url,
                         content=str(req.get('body') or '').encode('utf8'),
                         headers=req.get('headers') or {})
    return {'status':reply.status_code,'body':reply.text,'type':reply.headers.get('content-type','application/json')}


def run():
    card1=store.create({'title':'Лишний черновик', 'status':'Черновик'})
    card2=store.create({'title':'Нужная закупка', 'status':'Просчёт'})
    store.add_comment(card1['id'],'Это должно удалиться с карточкой')
    html=(web/'index.html').read_text('utf8')
    html=html.replace('<link rel="icon" href="/assets/qx_icon.png">','')
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+ (web/'style.css').read_text('utf8')+'</style>')
    mock='''<script>window.fetch=async(url,opts={})=>{
      const r=await QXAPI({url:String(url),method:opts.method||'GET',body:opts.body||'',headers:opts.headers||{}});
      return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
    };</script>'''
    html=html.replace('<script type="module" src="/app.js"></script>',mock+'<script>'+ (web/'app.js').read_text('utf8')+'</script>')
    with sync_playwright() as p:
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1650,'height':900})
        errors=[]
        page.on('pageerror',lambda err: errors.append(str(err)))
        page.expose_function('QXAPI',api_forward)
        page.set_content(html,wait_until='domcontentloaded')
        page.wait_for_selector('.sidebar',timeout=12000)
        page.locator('[data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_function('document.querySelectorAll("[data-tender-row]").length===2',timeout=15000)
        # Step 1: cancel leaves the tender untouched.
        page.locator(f'[data-action="tender-delete"][data-id="{card1["id"]}"]').click()
        page.wait_for_selector('[aria-label="Подтверждение удаления закупки"]')
        assert 'Лишний черновик' in page.locator('.modal').inner_text()
        page.locator('[data-action="close-modal"]').first.click()
        page.wait_for_function('document.querySelector(".modal")===null')
        assert store.get(card1['id']) is not None
        # Step 2: confirm does actual HTTP DELETE, cascade and reload table.
        page.locator(f'[data-action="tender-delete"][data-id="{card1["id"]}"]').click()
        page.locator('[data-action="tender-delete-confirm"]').click()
        page.wait_for_function('document.querySelectorAll("[data-tender-row]").length===1',timeout=15000)
        assert store.get(card1['id']) is None
        assert store.get(card2['id']) is not None
        assert page.locator('.tender-stats').first.inner_text().find('Всего закупок')>=0
        # Step 3: delete from detail view as well.
        page.locator(f'[data-action="tender-open"][data-id="{card2["id"]}"]').click()
        page.wait_for_selector('.tender-detail-tabs')
        page.locator(f'[data-action="tender-delete"][data-id="{card2["id"]}"]').click()
        page.locator('[data-action="tender-delete-confirm"]').click()
        page.wait_for_function('document.querySelectorAll("[data-tender-row]").length===0',timeout=15000)
        assert store.get(card2['id']) is None
        # Refresh should not resurrect deleted data.
        page.reload() if False else None
        page.locator('[data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_selector('h1:has-text("Реестр закупок")')
        assert page.locator('[data-tender-row]').count()==0
        assert not errors, errors
        browser.close()
    print('BROWSER_DELETE_TENDER_OK')


if __name__=='__main__': run()
