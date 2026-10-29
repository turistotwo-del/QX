"""E2E backup recovery UI with a local TestClient bridge; no network needed."""
from __future__ import annotations
import base64
from io import BytesIO
import os
os.environ['QX_OFFLINE_MODE'] = '1'
from pathlib import Path
import tempfile

os.environ['QX_DATA_DIR'] = tempfile.mkdtemp(prefix='qx_ui_restore_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import tender_store as t

root=Path(__file__).resolve().parents[1]
client=TestClient(app)

def qxapi(req):
    path=str(req.get('url','')).replace('/api/','/',1)
    binary=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode('utf-8')
    response=client.request(req.get('method','GET'),'/api'+path,content=binary,headers=req.get('headers') or {})
    return {'status':response.status_code,'body':response.text,'type':response.headers.get('content-type','application/json')}

html=(root/'modern/web/index.html').read_text(encoding='utf8')
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(root/'modern/web/style.css').read_text(encoding='utf8')+'</style>')
bridge='''<script>window.fetch=async(url,options={})=>{let binary=null;if(options.body instanceof Blob){let d=new Uint8Array(await options.body.arrayBuffer()),x='';for(let i=0;i<d.length;i+=15000)x+=String.fromCharCode(...d.slice(i,i+15000));binary=btoa(x)}const r=await QXTESTAPI({url:String(url),method:options.method||'GET',body:binary?'':options.body||'',binary,headers:options.headers||{}});return new Response(r.body,{status:r.status,headers:{'content-type':r.type}})}</script>'''
html=html.replace('<script type="module" src="/app.js"></script>', bridge+'<script>'+(root/'modern/web/app.js').read_text(encoding='utf8')+'</script>')

row=t.create({'title':'Вернуть эту закупку','number':'0322100002526000466','status':'Просчёт'})
t.add_comment(row['id'],'Сохранённая заметка')
t.add_document(row['id'],'условия.txt',b'BIOS reestr, 30 days')
archive=t.backup_archive()
t.update(row['id'],{'title':'Испорченные данные'})

with sync_playwright() as p:
    browser=launch_chromium(p)
    page=browser.new_page(viewport={'width':1400,'height':900})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.expose_function('QXTESTAPI',qxapi)
    page.set_content(html,wait_until='domcontentloaded')
    page.wait_for_selector('.sidebar')
    page.locator('.sidebar [data-action="tender-nav"][data-view="registry"]').click()
    page.wait_for_selector('[data-tender-row]')
    assert page.locator('text=Испорченные данные').count()>0
    page.locator('[data-action="tender-restore"]').click()
    page.locator('#file-tender-backup').set_input_files({'name':'QX_Tenders_Backup.zip','mimeType':'application/zip','buffer':archive})
    page.wait_for_selector('.qx-restore-modal')
    assert page.locator('.qx-restore-modal').inner_text().count('1')>=1
    assert 'Закупок в архиве' in page.locator('.qx-restore-modal').inner_text()
    assert 'Версия структуры архива' in page.locator('.qx-restore-modal').inner_text()
    if os.environ.get('QX_RESTORE_SCREENSHOT'):
        page.screenshot(path=os.environ['QX_RESTORE_SCREENSHOT'],full_page=False)
    page.locator('[data-action="tender-restore-confirm"]').click()
    page.wait_for_selector('text=Вернуть эту закупку',timeout=10000)
    assert t.get(row['id'])['title']=='Вернуть эту закупку'
    assert len(list((t.APP_DATA/'restore_snapshots').glob('*.zip')))==1
    assert not errors,errors
    browser.close()
print('Restore browser E2E OK')

client.close()
