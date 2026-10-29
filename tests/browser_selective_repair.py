"""Chromium E2E: Settings recovery repairs one corrupt document without DB rollback."""
from __future__ import annotations
import base64
import os
import tempfile
from pathlib import Path
from hashlib import sha256
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_browser_repair_')
os.environ['QX_CATALOG_DIR']=os.path.join(os.environ['QX_DATA_DIR'],'catalog')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import tender_store as store

ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'modern/web/index.html').read_text(encoding='utf-8')
html=html.replace('<link rel="stylesheet" href="/style.css">',
                  '<style>'+(ROOT/'modern/web/style.css').read_text(encoding='utf-8')+'</style>')
shim='''<script>window.fetch=async(url,options={})=>{
let binary=null;if(options.body instanceof Blob){let d=new Uint8Array(await options.body.arrayBuffer()),x='';for(let i=0;i<d.length;i+=15000)x+=String.fromCharCode(...d.slice(i,i+15000));binary=btoa(x)}
const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:binary?'':options.body||'',binary,headers:options.headers||{}});
return new Response(r.body,{status:r.status,headers:{'content-type':r.type}})}</script>'''
html=html.replace('<script type="module" src="/app.js"></script>',shim+'<script>'+(ROOT/'modern/web/app.js').read_text(encoding='utf-8')+'</script>')

row=store.create({'title':'Исходная закупка'})
original=b'Integrity verified contract BIOS is required'
did=store.add_document(row['id'],'contract.txt',original)
backup=store.backup_archive()
store.update(row['id'],{'title':'Новая редакция закупки'})
store.add_comment(row['id'],'Новое согласование после резервной копии')
path=store.DOCUMENTS/(sha256(original).hexdigest()+'.txt')
path.write_bytes(b'broken document')

with TestClient(app) as client, sync_playwright() as p:
    def bridge(req):
        binary=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode('utf8')
        response=client.request(req.get('method','GET'),str(req.get('url','/')),content=binary,headers=req.get('headers') or {})
        return {'status':response.status_code,'body':response.text,'type':response.headers.get('content-type','application/json')}
    browser=launch_chromium(p)
    page=browser.new_page(viewport={'width':1500,'height':930})
    page.set_default_timeout(9000)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.expose_function('QXTESTAPI',bridge)
    page.set_content(html,wait_until='domcontentloaded')
    page.locator('[data-action="tab"][data-tab="settings"]').click()
    panel=page.locator('#qx-diag-panel')
    panel.locator('[data-action="diagnostics-run"]').click()
    panel.locator('[data-action="audit-attachments"]').click()
    page.wait_for_selector('#qx-attachment-audit')
    assert 'изменены: 1' in panel.inner_text(),panel.inner_text()
    panel.locator('[data-action="repair-attachments-choose"]').click()
    page.locator('#file-tender-repair').set_input_files({'name':'QX_Tenders_Backup.zip','mimeType':'application/zip','buffer':backup})
    page.wait_for_selector('[aria-label="Восстановление только документов"]')
    modal=page.locator('[aria-label="Восстановление только документов"]')
    assert 'Можно восстановить' in modal.inner_text()
    assert path.read_bytes()==b'broken document','Preview must not modify files'
    if os.environ.get('QX_REPAIR_SCREENSHOT'):
        page.screenshot(path=os.environ['QX_REPAIR_SCREENSHOT'],full_page=False)
    modal.locator('[data-action="repair-attachments-confirm"]').click()
    page.wait_for_function("document.querySelector('#qx-attachment-audit')?.innerText.includes('изменены: 0')")
    assert path.read_bytes()==original
    assert store.get(row['id'])['title']=='Новая редакция закупки'
    assert 'Новое согласование после резервной копии' in [c['body'] for c in store.detail(row['id'])['comments']]
    assert not errors,errors
    browser.close()
print('Chromium selective attachment repair: OK')
