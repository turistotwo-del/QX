"""Offline Chromium E2E: quick note, navigation during debounce, reload, complete, delete."""
import os,tempfile,base64
from pathlib import Path
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx4035browser_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import quick_notes

root=Path(__file__).resolve().parents[1]
web=root/'modern/web'
client=TestClient(app)

def forward(req):
 path=str(req.get('url','')).replace('/api/','/',1)
 body=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode('utf8')
 resp=client.request(req.get('method') or 'GET','/api'+path,content=body,headers=req.get('headers') or {})
 return {'status':resp.status_code,'body':resp.text,'type':resp.headers.get('content-type','application/json')}

html=(web/'index.html').read_text('utf8').replace('<link rel="icon" href="/assets/qx_icon.png">','')
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(web/'style.css').read_text('utf8')+'</style>')
html=html.replace('<script type="module" src="/app.js"></script>', '''<script>window.fetch=async(url,opts={})=>{
 const r=await QXAPI({url:String(url),method:opts.method||'GET',body:opts.body||'',headers:opts.headers||{}});
 return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
};</script><script>'''+(web/'app.js').read_text('utf8')+'</script>')

def run():
 with sync_playwright() as pw:
  browser=launch_chromium(pw)
  page=browser.new_page(viewport={'width':1460,'height':900})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.expose_function('QXAPI',forward)
  page.set_content(html,wait_until='domcontentloaded');page.wait_for_selector('.sidebar')
  page.locator('[data-action="tab"][data-tab="notes"]').click()
  page.wait_for_selector('.qx-notes-layout')
  page.locator('[data-action="notes-new"]').last.click()
  page.wait_for_selector('[data-note-field="body"]')
  page.locator('[data-note-field="title"]').fill('Андрей: закупка 0322100002526000466')
  page.locator('[data-note-field="source"]').select_option('Поручение босса')
  page.locator('[data-note-field="body"]').fill('Согласовать 25 моноблоков. Позвонить на завод до вечера.')
  page.locator('[data-note-field="due_on"]').fill('2026-10-27')
  # Move away before normal debounce fires, then verify background save.
  page.locator('[data-action="tab"][data-tab="home"]').click()
  page.wait_for_timeout(1800)
  assert len(quick_notes.all_notes())==1, quick_notes.all_notes()
  item=quick_notes.all_notes()[0]
  assert item['title'].startswith('Андрей:') and item['body'].startswith('Согласовать')
  assert item['source']=='Поручение босса' and item['due_on']=='2026-10-27'
  page.locator('[data-action="tab"][data-tab="notes"]').click()
  page.wait_for_selector('.qx-notes-row') if False else page.wait_for_selector('.qx-note-row')
  assert 'Позвонить на завод' in page.locator('[data-note-field="body"]').input_value()
  page.locator('[data-action="notes-pin"]').click()
  page.wait_for_function('fetch("/api/notes").then(r=>r.json()).then(o=>o.items[0]?.pinned===true)',timeout=5000)
  # Restart the entire UI: saved notes must survive a fresh browser window.
  page.goto('about:blank')
  page.set_content(html,wait_until='domcontentloaded');page.wait_for_selector('.sidebar')
  page.locator('[data-action="tab"][data-tab="notes"]').click()
  page.wait_for_selector('.qx-note-row')
  assert page.locator('[data-note-field="body"]').input_value().startswith('Согласовать')
  page.locator('[data-notes-search]').fill('моноблоков')
  assert page.locator('.qx-note-row:visible').count()==1
  page.locator('[data-notes-search]').fill('')
  screenshot=os.environ.get('QX_SCREENSHOT_DIR')
  if screenshot:
   Path(screenshot).mkdir(parents=True,exist_ok=True)
   page.screenshot(path=str(Path(screenshot)/'QX_Notes_4035.png'),full_page=False)
  page.locator('[data-action="notes-complete"]').click()
  page.wait_for_function('fetch("/api/notes").then(r=>r.json()).then(o=>o.items[0]?.completed===true)',timeout=5000)
  assert page.locator('.qx-note-row:visible').count()==0
  page.locator('[data-notes-done]').check()
  assert page.locator('.qx-note-row:visible').count()==1
  page.locator('.qx-note-row').first.click()
  page.once('dialog',lambda d:d.accept())
  page.locator('[data-action="notes-delete"]').click()
  page.wait_for_function('fetch("/api/notes").then(r=>r.json()).then(o=>o.items.length===0)',timeout=8000)
  assert not errors, errors
  browser.close()
 print('BROWSER_QUICK_NOTES_4035_OK')
if __name__=='__main__':run()
