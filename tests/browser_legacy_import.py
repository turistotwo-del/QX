"""Chromium: legacy QX 3.3.7 ZIP -> preview -> confirmed price/settings import."""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_browser_legacy_')
os.environ['QX_CATALOG_DIR']=os.path.join(os.environ['QX_DATA_DIR'],'catalog')
from core import storage
# The unfrozen app normally uses source data/; isolate this browser acceptance test.
storage.DATA_DIR=Path(os.environ['QX_DATA_DIR'])/'old-price-target'
storage.PRICES_FILE=storage.DATA_DIR/'qx_prices.json'
storage.SETTINGS_FILE=storage.DATA_DIR/'settings.json'
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app

key=next(iter(storage.DEFAULT_QX_PRICES))
prices={key:{'name':'Старый пользовательский прайс','price':28643.75}}
settings={'ui_theme':'light','sidebar_width':370,'offline_mode':True}
archive=BytesIO()
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('QX_Подборщик_3.3_MODERN/data/qx_prices.json',json.dumps(prices,ensure_ascii=False))
    z.writestr('QX_Подборщик_3.3_MODERN/data/settings.json',json.dumps(settings))

root=Path(__file__).resolve().parents[1]
web=root/'modern/web'
html=(web/'index.html').read_text(encoding='utf8')
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(web/'style.css').read_text(encoding='utf8')+'</style>')
shim='''<script>window.fetch=async(url,options={})=>{let binary=null;
 if(options.body instanceof Blob){let d=new Uint8Array(await options.body.arrayBuffer()),x='';for(let i=0;i<d.length;i+=15000)x+=String.fromCharCode(...d.slice(i,i+15000));binary=btoa(x)}
 const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:binary?'':options.body||'',binary,headers:options.headers||{}});
 return new Response(r.body,{status:r.status,headers:{'content-type':r.type}})}</script>'''
html=html.replace('<script type="module" src="/app.js"></script>',shim+'<script>'+(web/'app.js').read_text(encoding='utf8')+'</script>')

def main():
    with TestClient(app) as client, sync_playwright() as p:
        def api(req):
            payload=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode()
            resp=client.request(req.get('method','GET'),req.get('url'),content=payload,headers=req.get('headers') or {})
            return {'status':resp.status_code,'body':resp.text,'type':resp.headers.get('content-type','application/json')}
        browser=launch_chromium(p)
        page=browser.new_page(viewport={'width':1450,'height':930})
        page.set_default_timeout(10000)
        errors=[]
        page.on('pageerror',lambda err: errors.append(str(err)))
        page.expose_function('QXTESTAPI',api)
        page.set_content(html,wait_until='domcontentloaded')
        page.wait_for_selector('.sidebar')
        page.locator('[data-action="tab"][data-tab="settings"]').click()
        panel=page.locator('#qx-legacy-panel')
        before_preview=storage.PRICES_FILE.read_bytes()
        panel.locator('[data-action="legacy-import-choose"]').click()
        page.locator('#file-legacy').set_input_files({
            'name':'Мой_старый_QX.zip','mimeType':'application/zip','buffer':archive.getvalue()})
        panel.locator('[data-action="legacy-import-apply"]').wait_for()
        assert '1 позиций' in panel.inner_text()
        assert storage.PRICES_FILE.read_bytes()==before_preview, 'Preview must not alter prices'
        # A broken ZIP must clear the previous preview, not reuse its old confirmation.
        page.locator('#file-legacy').set_input_files({
            'name':'Повреждённый.zip','mimeType':'application/zip','buffer':b'broken'})
        page.wait_for_function("document.querySelectorAll('[data-action=legacy-import-apply]').length===0")
        assert storage.PRICES_FILE.read_bytes()==before_preview
        page.locator('#file-legacy').set_input_files({
            'name':'Мой_старый_QX.zip','mimeType':'application/zip','buffer':archive.getvalue()})
        panel.locator('[data-action="legacy-import-apply"]').wait_for()
        page.once('dialog',lambda dialog:dialog.accept())
        panel.locator('[data-action="legacy-import-apply"]').click()
        page.wait_for_function('document.querySelector("#qx-legacy-panel")?.innerText.includes("Импорт не начат")',timeout=20000)
        price=json.loads(storage.PRICES_FILE.read_text(encoding='utf8'))
        self_price=price[key]['price']
        assert self_price==28643.75,self_price
        assert json.loads(storage.SETTINGS_FILE.read_text('utf8'))['sidebar_width']==370
        backups=list((Path(os.environ['QX_DATA_DIR'])/'legacy_import_snapshots').iterdir())
        assert len(backups)==1
        assert not errors,errors
        browser.close()
    print('Browser legacy QX migration: preview, confirmation, prices, settings, snapshot OK')

if __name__=='__main__':main()
