"""Chromium QX Modern: WebView native save and unavailable-dialog fallback."""
import base64
import os
import tempfile
from pathlib import Path
os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_browser_save_')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app

root=Path(__file__).resolve().parents[1]
assets=root/'modern'/'web'
client=TestClient(app)

def call_api(req):
    url='/api/'+str(req.get('url','')).replace('/api/','',1)
    raw=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode()
    rsp=client.request(req.get('method') or 'GET',url,content=raw,headers=req.get('headers') or {})
    return {'status':rsp.status_code,'data':base64.b64encode(rsp.content).decode(), 'type':rsp.headers.get('content-type','application/json')}

html=(assets/'index.html').read_text('utf-8').replace('<link rel="stylesheet" href="/style.css">','<style>'+(assets/'style.css').read_text('utf-8')+'</style>')
script='''<script>
window.QXSaved=[]; window.QXSaveMode='native';
window.pywebview={api:{save_file:async(name,payload)=>{
    window.QXSaved.push({name,payload});
    if(window.QXSaveMode==='fallback')return {browser_fallback:true,message:'disabled'};
    if(window.QXSaveMode==='cancel')return {cancelled:true};
    return {name:'C:\\\\QX\\\\'+name};
}}};
window.fetch=async(url,opts={})=>{
 let binary=null;
 if(opts.body instanceof Blob){const a=new Uint8Array(await opts.body.arrayBuffer());let raw='';for(let i=0;i<a.length;i+=12000)raw+=String.fromCharCode(...a.slice(i,i+12000));binary=btoa(raw);}
 const r=await QXTESTAPI({url:String(url),method:opts.method||'GET',body:binary?'':opts.body||'',binary,headers:opts.headers||{}});
 const raw=atob(r.data);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
 return new Response(bytes,{status:r.status,headers:{'content-type':r.type}});
};
</script>'''
html=html.replace('<script type="module" src="/app.js"></script>',script+'<script>'+(assets/'app.js').read_text('utf-8')+'</script>')

with sync_playwright() as p:
    browser=launch_chromium(p)
    page=browser.new_page(accept_downloads=True)
    page.expose_function('QXTESTAPI',call_api)
    errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.set_content(html,wait_until='domcontentloaded')
    page.wait_for_selector('.sidebar')
    page.evaluate("async () => await download('project/save', dataPackage(), 'QX_Проект.qxproj')")
    entries=page.evaluate('QXSaved')
    assert len(entries)==1 and entries[0]['name']=='QX_Проект.qxproj'
    assert base64.b64decode(entries[0]['payload']).startswith(b'{')
    assert 'Сохранено' in page.locator('#toasts').inner_text()
    # Browser fallback must initiate an actual download, not claim native save.
    page.evaluate("QXSaveMode='fallback'")
    with page.expect_download(timeout=12000) as download_info:
        page.evaluate("async () => await download('project/save', dataPackage(), 'QX_Проект_2.qxproj')")
    assert download_info.value.suggested_filename=='QX_Проект_2.qxproj'
    page.evaluate("QXSaveMode='cancel'")
    page.evaluate("async () => await download('project/save', dataPackage(), 'QX_Отмена.qxproj')")
    assert not errors,errors
    browser.close()
    print('Browser export native save, download fallback, cancel: OK')
client.close()
