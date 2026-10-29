"""Chromium smoke: QX AI auto-fills safe missing values after uploading a DOCX."""
import base64
import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

os.environ['QX_OFFLINE_MODE']='1'
os.environ['QX_DATA_DIR']=tempfile.mkdtemp(prefix='qx_autofill_')
from docx import Document
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from chromium_launch import launch_chromium
from modern.server import app
from modern import local_ai, tz_ai

root=Path(__file__).resolve().parents[1]
assets=root/'modern'/'web'
client=TestClient(app)

def call_api(req):
    path=str(req.get('url','')).replace('/api/','/',1)
    content=base64.b64decode(req['binary']) if req.get('binary') else str(req.get('body') or '').encode('utf-8')
    r=client.request(req.get('method') or 'GET','/api'+path,content=content,headers=req.get('headers') or {})
    return {'status':r.status_code,'body':r.text,'type':r.headers.get('content-type','application/json')}

html=(assets/'index.html').read_text('utf-8')
html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+(assets/'style.css').read_text('utf-8')+'</style>')
html=html.replace('<script type="module" src="/app.js"></script>', '''<script>
window.fetch=async(url,options={})=>{
 let binary=null;
 if(options.body instanceof Blob){const a=new Uint8Array(await options.body.arrayBuffer());let x='';for(let i=0;i<a.length;i+=13000)x+=String.fromCharCode(...a.slice(i,i+13000));binary=btoa(x);}
 const r=await QXAPI({url:String(url),method:options.method||'GET',body:binary?'':options.body||'',binary,headers:options.headers||{}});
 return new Response(r.body,{status:r.status,headers:{'content-type':r.type}});
};
</script><script>'''+(assets/'app.js').read_text('utf-8')+'</script>''')

doc=Document();doc.add_paragraph('Системный блок. Оперативная память от 24 ГБ.');b=BytesIO();doc.save(b)

def ai_answer(source, req, model):
    assert 'оперативная память от 24 гб' in source.lower()
    assert model=='mock-local:1'
    return {'model':model,'proposals':[{'field':'ram_gb_min','value':24,'previous':req.get('ram_gb_min'),
           'quote':'Оперативная память от 24 ГБ','auto_safe':True}], 'rejected':0}

with patch.object(local_ai,'available_models',return_value={'models':['mock-local:1'],'available':True,'message':'Mock AI local'}), \
     patch.object(tz_ai,'analyze_tz',side_effect=ai_answer):
  with sync_playwright() as p:
    browser=launch_chromium(p)
    page=browser.new_page(viewport={'width':1370,'height':840});page.set_default_timeout(18000)
    errors=[];page.on('pageerror', lambda e: errors.append(str(e)))
    page.expose_function('QXAPI',call_api)
    page.set_content(html,wait_until='domcontentloaded')
    page.locator('[data-action="tab"][data-tab="tz"]').click()
    page.evaluate("state.tzAiModel='mock-local:1';state.tzAiAuto=true;state.tzAiFill=true")
    page.locator('#file-tz').set_input_files({'name':'autofill.docx','mimeType':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','buffer':b.getvalue()})
    page.wait_for_function("state.reqs.length===1 && state.reqs[0].ram_gb_min===24",timeout=18000)
    assert 'заполнено 1' in page.evaluate('state.tzAiMessage')
    assert page.evaluate('state.reqs[0].ram_gb_min')==24
    assert not errors,errors
    browser.close()
    print('Browser TZ AI safe auto-fill: OK')
