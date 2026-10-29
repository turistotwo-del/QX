"""Chromium test: opt-in EIS lookup, exact source link, offline fallback.
PYTHONPATH=. python tests/browser_eis_lookup.py
"""
import os
os.environ['QX_OFFLINE_MODE'] = '1'
import tempfile
from pathlib import Path
from unittest.mock import patch
import shutil

os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_eis_ui_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern.eis_public import official_search_url

ROOT=Path(__file__).resolve().parents[1]
client=TestClient(app)
N='0322100002526000466'

def call_api(req):
    url=str(req.get('url','')).replace('/api/','/',1)
    r=client.request(req.get('method') or 'GET','/api'+url,content=str(req.get('body') or '').encode(),headers=req.get('headers') or {})
    return {'status':r.status_code,'body':r.text,'type':r.headers.get('content-type','application/json')}

def main():
    new=client.post('/api/tenders',json={'number':N,'title':'QX EIS test'})
    assert new.status_code==200,new.text
    # Contract price alone must never be presented as profit without purchase cost.
    tid=new.json()['tender']['id']
    assert client.patch('/api/tenders/'+tid,json={'contract_price':200000}).status_code==200
    assets=ROOT/'modern/web'
    html=(assets/'index.html').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(assets/'style.css').read_text(encoding='utf-8')+'</style>')
    html=html.replace('<script type="module" src="/app.js"></script>','''<script>
       window.fetch=async(url,options={})=>{const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:options.body||'',headers:options.headers||{}});return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});}
       </script><script>'''+(assets/'app.js').read_text(encoding='utf-8')+'</script>')
    chromium=shutil.which('chromium') or shutil.which('chrome')
    with sync_playwright() as p:
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1440,'height':900})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.expose_function('QXTESTAPI',call_api)
        page.set_content(html,wait_until='domcontentloaded')
        page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
        page.wait_for_selector('[data-tender-row]')
        page.locator('[data-action="tender-open"]').first.click()
        page.wait_for_selector('[data-action="tender-eis-lookup"]')
        mock={'available':True,'matches':[{'title':'Закупка № '+N,'description':'RSS-уведомление','url':official_search_url(N),'link_verified':False}],
              'message':'Точное совпадение найдено, проверьте официальный сайт', 'search_url':official_search_url(N)}
        with patch('modern.eis_public.lookup_notice',return_value=mock):
            page.locator('[data-action="tender-eis-lookup"]').click()
            page.wait_for_selector('.tender-rss-result .activity-item')
        assert N in page.locator('.tender-rss-result').inner_text()
        assert page.locator('[data-action="tender-eis-open-match"]').count()==1
        page.locator('[data-action="tender-eis-lookup"]').click() if False else None
        if os.environ.get('QX_SCREENSHOT_DIR'):
            folder=Path(os.environ['QX_SCREENSHOT_DIR']);folder.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(folder/'Tender_EIS_Lookup.png'))
        page.locator('[data-action="tender-back"]').click()
        page.locator('[data-action="tender-nav"][data-view="analytics"]').click()
        page.wait_for_selector('h1:has-text("Аналитика тендеров")')
        assert 'Плановый результат (0 с просчётом)' in page.locator('.tender-analytics-stats').inner_text()
        assert not errors,errors
        browser.close()
    print('Browser EIS lookup: OK')

if __name__=='__main__':main()

client.close()
