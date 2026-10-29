"""QX Modern local API. Existing thoroughly-tested QX engine stays authoritative."""
from __future__ import annotations
import base64
import binascii
from zipfile import BadZipFile
from dataclasses import asdict
from datetime import date
from io import BytesIO
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import unquote
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from core import storage, user_catalog, autosave
from core.tz_parser import parse_tz, Requirements
from core.selector import build_plan
from core.project_io import dump_project, load_project
from core.tender_fill import extract_characteristics_docx, build_characteristic_rows, fill_docx_characteristics
from core.currency import get_usd_rate, parse_price_input, RateInfo
from core.exporter import export_xlsx
from core.commercial_offer import build_offer_items, build_commercial_offer
from core.project_calc import build_arsenal_text, arsenal_equipment_default, normalize_arsenal_os_name, exit_points, arsenal_position_summary
from core.price_import import parse_supplier_price_excel, save_supplier_price_list, list_supplier_price_lists, update_all_linked_profiles
from modern.release_info import RELEASE_LABEL
from modern.document_preview import build_document_preview
from modern import tender_store as tenders
from modern.tender_analysis import analyze_documents, document_segments

app = FastAPI(title='QX Modern', docs_url=None, redoc_url=None)
from modern.loopback_security import LocalBrowserProtection
app.add_middleware(LocalBrowserProtection)
STATIC = Path(__file__).resolve().parent / 'web'
SAFE_KINDS = {'case', 'aio', 'monitor', 'keyboard', 'mouse', 'equipment_profile', 'price_list', 'supplier_price', 'pc_case', 'aio_platform'}


@app.middleware('http')
async def fresh_workspace_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in ('/', '/index.html', '/app.js', '/style.css', '/api/boot'):
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    return response

def b64decode(value):
    return base64.b64decode(value) if value else b''

def fnum(value, default=0.):
    try: return float(value if value not in ('',None) else default)
    except (TypeError, ValueError): return float(default)

def req_instance(obj):
    valid = Requirements.__dataclass_fields__
    return Requirements(**{k:v for k,v in (obj or {}).items() if k in valid})

def previous_merge(rows, previous, hard):
    for row in rows:
        row['_engine_name'] = row.get('name')
    if hard or not previous: return rows
    old_by_key = {}
    for row in previous:
        if row.get('_manual'): continue
        key = (row.get('category'), row.get('_engine_name') or row.get('name'))
        old_by_key[key] = row
    for new in rows:
        key = (new.get('category'), new.get('name'))
        old = old_by_key.get(key)
        if old:
            for prop in ('name','qty','price','price_input','source','note','url'):
                if prop in old: new[prop] = old[prop]
            if old.get('_locked'): new['_locked'] = old['_locked']
        new['_engine_name'] = key[1]
    rows.extend([dict(row) for row in previous if row.get('_manual')])
    return rows

from modern.attachment_integrity import CorruptAttachment

@app.exception_handler(CorruptAttachment)
async def corrupted_attachment_handler(request, exc):
    return Response(json.dumps({'error': str(exc)}, ensure_ascii=False),
                    status_code=409, media_type='application/json')

@app.exception_handler(Exception)
async def error_handler(request, exc):
    # Consistent, user-readable error, without an internal traceback in the UI.
    if not isinstance(exc, HTTPException):
        try:
            import traceback
            from datetime import datetime
            tenders.APP_DATA.mkdir(parents=True,exist_ok=True)
            with (tenders.APP_DATA/'QX_MODERN_ERROR.log').open('a',encoding='utf-8') as stream:
                stream.write('\n--- '+datetime.now().isoformat()+' '+request.method+' '+str(request.url.path)+' ---\n')
                stream.write(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception: pass
    if isinstance(exc, HTTPException):
        return Response(json.dumps({'error': str(exc.detail)}, ensure_ascii=False), status_code=exc.status_code, media_type='application/json')
    return Response(json.dumps({'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False), status_code=500, media_type='application/json')

@app.get('/api/boot')
def boot():
    settings=storage.load_settings()
    return {'version':'QX Workspace ' + RELEASE_LABEL,'engine_version':'2.9.5', 'settings':settings, 'requirements_defaults':asdict(Requirements()),
            'prices':storage.load_prices(),
            'catalogs':{kind:user_catalog.list_items(kind) for kind in ('equipment_profile','case','aio','monitor','keyboard','mouse')},
            'autosave': autosave.autosave_info(), 'suppliers': list_supplier_price_lists()}

@app.get('/api/diagnostics')
def diagnostics():
    from modern.diagnostics import run_diagnostics
    return run_diagnostics()

@app.get('/api/diagnostics/attachments')
def diagnostics_attachments():
    from modern.attachment_integrity import audit_attachments
    return audit_attachments()

@app.post('/api/legacy/preview')
async def legacy_preview(request: Request):
    from modern.legacy_import import preview_legacy
    try:
        return preview_legacy(await request.body())
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post('/api/legacy/import')
async def legacy_import(request: Request):
    from modern.legacy_import import import_legacy
    if request.headers.get('x-qx-confirm-legacy') != 'IMPORT_LEGACY_SETTINGS_AND_PRICES':
        raise HTTPException(400, 'Для замены прайса и настроек нужно подтверждение')
    try:
        return import_legacy(await request.body())
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/rate')
def rate():
    settings = storage.load_settings()
    # Air-gapped tender offices and deterministic offline smoke tests must not
    # accidentally trigger an external DNS lookup. Use saved rate as clearly
    # stale information, never mark it as freshly fetched from the CBR.
    if os.environ.get('QX_OFFLINE_MODE') == '1' or settings.get('offline_mode') is True:
        return RateInfo(rate=fnum(settings.get('usd_rate_cached'),86.8872),
                        date=str(settings.get('usd_rate_date_cached') or ''), live=False,
                        error='Офлайн-режим QX: использован сохранённый курс.').to_dict()
    info=get_usd_rate(fnum(settings.get('usd_rate_cached'),86.8872),settings.get('usd_rate_date_cached',''),timeout=4)
    if info.live:
        settings['usd_rate_cached']=info.rate;settings['usd_rate_date_cached']=info.date
        storage.save_settings(settings)
    return info.to_dict()

@app.post('/api/parse')
async def parse(request: Request):
    data=await request.body(); filename=unquote(request.headers.get('x-file-name','ТЗ.docx'))
    if not filename.lower().endswith(('.docx','.pdf','.xlsx','.xlsm','.odt','.txt','.csv','.md')):
        raise HTTPException(400,'Поддерживаются DOCX, PDF, XLSX, XLSM, ODT, TXT, CSV, MD')
    if len(data)>30*1024*1024: raise HTTPException(413,'Файл ТЗ больше 30 МБ')
    try:
        from starlette.concurrency import run_in_threadpool
        reqs, text=await run_in_threadpool(parse_tz, filename+'.txt' if filename.lower().endswith('.md') else filename,data)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(422, 'Не удалось разобрать файл ТЗ: '+str(exc)) from exc
    if not text or not text.strip():
        raise HTTPException(422, 'В файле не найден текст. Если это скан PDF, сначала выполните OCR-распознавание.')
    char=[]
    if filename.lower().endswith('.docx'):
        char=await run_in_threadpool(extract_characteristics_docx,data)
    return {'reqs':[asdict(r) for r in reqs], 'source_text':text,
            'source_filename':filename, 'source_docx_base64':base64.b64encode(data).decode('ascii') if filename.lower().endswith('.docx') else '',
            'characteristics':char}


@app.get('/api/parse/ai/diagnostic')
async def qx_ai_inference_diagnostic():
    """Non-blocking actual one-word inference to diagnose slow/local models."""
    from starlette.concurrency import run_in_threadpool
    from modern.local_ai import lite_diagnostic
    return await run_in_threadpool(lite_diagnostic)

@app.post('/api/parse/ai')
async def tz_ai_suggestions(request: Request):
    """Actual on-device model inference; cannot silently change a QX project."""
    from starlette.concurrency import run_in_threadpool
    from modern.tz_ai import analyze_tz
    content_length = int(request.headers.get('content-length') or 0)
    if content_length > 5_000_000: raise HTTPException(413,'AI-запрос больше допустимого размера')
    body=await request.body()
    if len(body)>5_000_000: raise HTTPException(413,'AI-запрос больше допустимого размера')
    try:
        payload=json.loads(body)
        result=await run_in_threadpool(analyze_tz, payload.get('source_text') or '',
                                       payload.get('req') or {}, payload.get('model') or '')
        return result
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc

@app.post('/api/document/preview')
async def document_preview(request: Request):
    # The original DOCX (if saved) is the source of truth for table preview.
    # Text fallback supports previously saved projects and non-Word formats.
    body = await request.json()
    encoded = body.get('source_docx_base64') or ''
    if len(encoded) > 42 * 1024 * 1024:
        raise HTTPException(413, 'Слишком большой файл для просмотра')
    try:
        source = base64.b64decode(encoded, validate=True) if encoded else None
        return build_document_preview(
            body.get('source_filename') or 'Техническое задание',
            source, body.get('source_text') or '',
            body.get('characteristics') or [],
        )
    except (ValueError, OSError, KeyError, TypeError, binascii.Error, BadZipFile) as exc:
        raise HTTPException(422, 'Не удалось показать таблицу ТЗ: '+str(exc)) from exc

@app.post('/api/select')
async def select(request: Request):
    body=await request.json()
    prices=storage.normalize_prices(body.get('prices') or storage.load_prices())
    settings=body.get('settings') or storage.load_settings()
    before=body.get('previous') or []
    plans=[]
    from core import user_catalog as catalog
    for i,obj in enumerate(body.get('reqs') or []):
        req=req_instance(obj)
        profile=None
        if req.equipment_profile_name and req.product_type not in ('keyboard','mouse','monitor'):
            entry=catalog.get_item('equipment_profile',req.equipment_profile_name)
            profile=entry['data'] if entry else None
        peripherals={kind:catalog.list_items(kind) for kind in ('monitor','keyboard','mouse')}
        rows,registry,warnings,checks=build_plan(req,prices,settings,equipment_profile=profile,peripheral_catalogs=peripherals)
        prev=before[i] if i<len(before) else {}
        hard=(bool(body.get('hard')) or
              (prev.get('req',{}).get('platform')!=obj.get('platform')) or
              (prev.get('req',{}).get('equipment_profile_name')!=obj.get('equipment_profile_name')) or
              (prev.get('req',{}).get('product_type')!=obj.get('product_type')) or
              any(prev.get('req',{}).get(k)!=obj.get(k) for k in (
                  'keyboard_source_mode','mouse_source_mode',
                  'keyboard_catalog_item','mouse_catalog_item','monitor_catalog_item')))
        rows=previous_merge(rows, prev.get('rows') or [], hard)
        plans.append({'req':dict(obj),'rows':rows,'registry':registry,'warnings':warnings,
                      'checks':checks,'extras':dict(prev.get('extras') or {}),
                      'arsenal':dict(prev.get('arsenal') or {})})
    return {'plans':plans}

@app.post('/api/price')
async def price(request: Request):
    b=await request.json();price,currency,note=parse_price_input(b.get('value'),fnum(b.get('rate')),fnum(b.get('buffer'),5))
    return {'price':price,'currency':currency,'note':note}

@app.post('/api/settings')
async def save_settings(request: Request):
    b=await request.json(); current=storage.load_settings()
    current.update({k:v for k,v in b.items() if k in current})
    storage.save_settings(current)
    return {'settings':current}

@app.post('/api/prices')
async def save_prices(request: Request):
    b=await request.json()
    if not isinstance(b,dict): raise HTTPException(400,'Некорректный прайс')
    prices=storage.load_prices()
    for k,v in b.items():
        if k in prices and isinstance(v,dict):
            prices[k].update({t:v[t] for t in ('price','name') if t in v})
    storage.save_prices(prices)
    return {'prices':prices}

def project_dump(body):
    return dump_project(reqs=body.get('reqs'), plans=body.get('plans'),source_text=body.get('source_text',''),
        qx_prices=body.get('prices'),project_meta={'name':body.get('name','Новый проект'),'tender_project_key':body.get('tender_project_key',''),'tender_link_enabled':bool(body.get('tender_link_enabled')),'tender_notice_number':body.get('tender_notice_number','')},
        settings_snapshot=body.get('settings'),source_filename=body.get('source_filename',''),
        source_docx_bytes=b64decode(body.get('source_docx_base64')),
        tender_overrides=body.get('tender_overrides'),tender_characteristics=body.get('characteristics'),
        tz_documents=body.get('tz_documents'))

@app.post('/api/project/save')
async def save_project(request: Request):
    data=project_dump(await request.json())
    return Response(data,media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="qx_project.qxproj"'})

@app.post('/api/project/load')
async def open_project(request: Request):
    try:
        payload=load_project(await request.body())
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    payload.pop('source_docx_bytes',None)
    # Old projects may predate the QX Key E adapter price. Fill missing keys
    # while retaining the user's historical prices and component selections.
    payload['qx_prices'] = storage.normalize_prices(payload.get('qx_prices'))
    return payload

@app.post('/api/project/autosave')
async def save_auto(request: Request):
    b=await request.json()
    # Do not replace previous backup with empty data.
    if not (b.get('reqs') or b.get('plans')):return {'saved':False}
    return {'saved':autosave.save_autosave(project_dump(b))}

@app.get('/api/project/autosave')
def load_auto():
    data=autosave.load_autosave()
    if not data: return {'found':False}
    payload=load_project(data);payload.pop('source_docx_bytes',None)
    return {'found':True,'project':payload}

@app.post('/api/export/excel')
async def excel(request: Request):
    b=await request.json(); plan=b['plan'];req=plan['req']
    data=export_xlsx(b.get('name','Расчёт'),req,plan.get('rows',[]),plan.get('registry'),plan.get('extras') or {},plan.get('checks') or [])
    # export_xlsx returns bytes (legacy function)
    if hasattr(data,'getvalue'): data=data.getvalue()
    return Response(content=data, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition':'attachment; filename="QX_calculation.xlsx"'})

@app.post('/api/export/offer')
async def offer(request: Request):
    b=await request.json()
    if any(fnum((p.get('req') or {}).get('quantity')) <= 0 for p in b.get('plans') or []):
        raise HTTPException(400, 'Укажите количество для каждой позиции. Значение должно быть больше нуля.')
    items=build_offer_items(b.get('plans') or [], fnum(b.get('percent'),20),b.get('mode','markup'))
    data=build_commercial_offer(items,sequence=int(b.get('sequence') or 1),
        warranty_months=int(b.get('warranty') or 12),validity_days=int(b.get('validity') or 30))
    return Response(content=data,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition':'attachment; filename="QX_offer.docx"'})

@app.post('/api/characteristics')
async def characteristics(request: Request):
    b=await request.json();return {'rows':build_characteristic_rows(b.get('characteristics',[]),b.get('reqs',[]),b.get('plans',[]),b.get('overrides') or {})}

@app.post('/api/export/filled-tz')
async def filled_tz(request: Request):
    b=await request.json(); blob=b64decode(b.get('source_docx_base64'))
    if not blob: raise HTTPException(400,'Нужен исходный DOCX-файл ТЗ')
    chars=b.get('characteristics') or extract_characteristics_docx(blob)
    rows=build_characteristic_rows(chars,b.get('reqs',[]),b.get('plans',[]),b.get('overrides') or {})
    values={x['id']:x.get('value','') for x in rows if x.get('editable')}
    result=fill_docx_characteristics(blob,chars,values)
    return Response(content=result,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         headers={'Content-Disposition':'attachment; filename="QX_filled_tz.docx"'})

@app.post('/api/arsenal')
async def arsenal(request: Request):
    b=await request.json(); plans=b.get('plans') or []
    equipment=[arsenal_equipment_default(p) for p in plans]
    summary=arsenal_position_summary(plans)
    purchase=summary['purchase']
    # project_qty is legacy compatibility only; the set denominator is derived
    # from equal quantities per position, never their sum (e.g. 4*59 = 236).
    qty=summary['set_quantity'] or 1
    info=b.get('fields') or {};s=storage.load_settings()
    need_os=any((p.get('req') or {}).get('need_os') for p in plans)
    text=build_arsenal_text(purchase,qty,fnum(info.get('delivery')),fnum(info.get('bg')),
        fnum(info.get('go')),info.get('sender') or s.get('default_sender','ЗИОН'),equipment,
        info.get('country') or s.get('default_country','Россия'),normalize_arsenal_os_name(need_os,info.get('os')),
        info.get('trademark') or s.get('default_trademark','1093786'),position_summary=summary)
    return {'text':text,'purchase':purchase,'summary':summary,'exit_points':exit_points(purchase,fnum(info.get('delivery')),fnum(info.get('bg')),fnum(info.get('go')))}

@app.get('/api/catalog/{kind}')
def catalog_list(kind:str):
    if kind not in SAFE_KINDS:raise HTTPException(400,'Неизвестный тип базы')
    return {'items':user_catalog.list_items(kind)}

@app.post('/api/catalog/{kind}')
async def catalog_save(kind:str, request: Request):
    if kind not in SAFE_KINDS: raise HTTPException(400,'Неизвестный тип базы')
    b=await request.json()
    if not str(b.get('name') or '').strip():raise HTTPException(400,'Укажи название позиции')
    user_catalog.save_item(kind,b['name'],b.get('data') or {})
    return {'items':user_catalog.list_items(kind)}

@app.delete('/api/catalog/{kind}/{name}')
def catalog_delete(kind:str,name:str):
    if kind not in SAFE_KINDS:raise HTTPException(400,'Неизвестный тип базы')
    return {'deleted':user_catalog.delete_item(kind,name)}

@app.get('/api/catalog-export')
def catalog_export():
    return Response(user_catalog.export_catalog_bytes(), media_type='application/octet-stream',
                   headers={'Content-Disposition':'attachment; filename="QX_UserCatalog.qxdb"'})

@app.post('/api/catalog-import')
async def catalog_import(request:Request):
    b=await request.body()
    if len(b)>20*1024*1024: raise HTTPException(413,'База больше 20 МБ')
    return {'imported': user_catalog.import_catalog_bytes(b)}

@app.post('/api/supplier-price')
async def supplier_price(request: Request):
    b=await request.body()
    name=request.headers.get('x-supplier','ExeGate')
    mode=request.headers.get('x-price-mode','ОПТ')
    parsed=parse_supplier_price_excel(b,name,mode)
    save_supplier_price_list(name,parsed)
    return {'items':len(parsed.get('items',[])), 'supplier':name, 'updated':update_all_linked_profiles(name)}



# Standalone quick notes. Kept under QX user data and independent from .qxproj.
@app.get('/api/notes')
def notes_list():
    from modern import quick_notes
    return {'items':quick_notes.all_notes()}

@app.post('/api/notes')
async def notes_create(request: Request):
    from modern import quick_notes
    try:
        fields=await request.json()
        return {'note':quick_notes.create(fields)}
    except (ValueError,TypeError) as e:
        raise HTTPException(422,str(e)) from e

@app.patch('/api/notes/{note_id}')
async def notes_update(note_id: str,request: Request):
    from modern import quick_notes
    try:
        payload=await request.json()
        if not isinstance(payload,dict): raise ValueError('Неверный формат')
        return {'note':quick_notes.update(note_id,payload.get('fields') or {},payload.get('revision'))}
    except KeyError as e: raise HTTPException(404,str(e)) from e
    except (ValueError,TypeError) as e: raise HTTPException(422,str(e)) from e

@app.delete('/api/notes/{note_id}')
def notes_delete(note_id: str):
    from modern import quick_notes
    try: return quick_notes.delete(note_id)
    except KeyError as e: raise HTTPException(404,str(e)) from e

@app.get('/api/calendar/notes')
def calendar_notes():
    from modern import quick_notes
    return {'items':quick_notes.due_notes()}

@app.get('/api/notes-export')
def notes_export():
    from modern import quick_notes
    return Response(quick_notes.export_json(),media_type='application/json; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="QX_Quick_Notes.json"'})

@app.get('/api/health')
def health():return {'ok':True,'ui':'TypeScript','engine':'Python 2.9.5'}


# Tender operations (SQLite, user-controlled status, fully offline-capable).
@app.get('/api/tenders/backup')
def tender_backup():
    return Response(tenders.backup_archive(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename=QX_Tenders_Backup.zip'})

@app.post('/api/tenders/backup/preview')
async def tender_backup_preview(request: Request):
    from modern.tender_backup import preview_archive
    if int(request.headers.get('content-length') or 0) > 150*1024*1024:
        raise HTTPException(413, 'Архив больше 150 МБ')
    try:
        return {'preview':preview_archive(await request.body())}
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        raise HTTPException(400, str(exc)) from exc

@app.post('/api/tenders/backup/restore')
async def tender_backup_restore(request: Request):
    from modern.tender_backup import restore_archive
    if request.headers.get('x-qx-confirm-restore') != 'REPLACE_EXISTING_TENDERS':
        raise HTTPException(400, 'Для восстановления требуется подтверждение пользователя')
    if int(request.headers.get('content-length') or 0) > 150*1024*1024:
        raise HTTPException(413, 'Архив больше 150 МБ')
    try:
        return restore_archive(await request.body())
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        raise HTTPException(400, str(exc)) from exc

@app.post('/api/tenders/backup/repair-preview')
async def tender_repair_preview(request: Request):
    from modern.tender_backup import preview_document_repair, MAX_ARCHIVE
    if int(request.headers.get('content-length') or 0) > MAX_ARCHIVE:
        raise HTTPException(413, 'Архив больше 150 МБ')
    try:
        return {'preview':preview_document_repair(await request.body())}
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        raise HTTPException(400, str(exc)) from exc

@app.post('/api/tenders/backup/repair')
async def tender_repair(request: Request):
    from modern.tender_backup import repair_documents, MAX_ARCHIVE
    if request.headers.get('x-qx-confirm-repair') != 'REPAIR_DAMAGED_ATTACHMENTS_ONLY':
        raise HTTPException(400, 'Для восстановления документов требуется подтверждение')
    if int(request.headers.get('content-length') or 0) > MAX_ARCHIVE:
        raise HTTPException(413, 'Архив больше 150 МБ')
    try:
        return repair_documents(await request.body())
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/tenders/reminders')
def tender_reminders():
    from modern.reminders import reminders, preferences
    return {'items': reminders(), 'settings': preferences(),
            'note':'Даты ориентировочные. Проверьте договор, переносы рабочих дней, исполнение и оплату.'}

@app.post('/api/tenders/reminders/settings')
async def tender_reminder_settings(request: Request):
    from modern.reminders import set_preferences
    values=await request.json()
    try:
        return {'settings':set_preferences(enabled=values.get('enabled'),advance_days=values.get('advance_days'))}
    except (TypeError, ValueError) as exc:
        raise HTTPException(400,str(exc)) from exc

@app.post('/api/tenders/reminders/check')
def tender_reminder_check():
    from modern.reminders import dispatch
    return dispatch()

@app.get('/api/tenders')
def tender_list():
    return {'items':[{**t,'calculated_due_on':tenders.calculate_deadline(t)['due_on']} for t in tenders.listing()], 'summary':tenders.dashboard(), 'organizations':tenders.organizations(), 'statuses':tenders.STATUSES}

@app.post('/api/tenders')
async def tender_create(request: Request):
    try: return {'tender':tenders.create(await request.json())}
    except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc

@app.post('/api/tenders/organizations')
async def tender_org(request: Request):
    b=await request.json()
    try: return {'id':tenders.add_org(b.get('name'),b.get('inn'),b.get('details'))}
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc

@app.patch('/api/tenders/organizations/{org_id}')
async def tender_org_update(org_id: str, request: Request):
    b=await request.json()
    try: return {'organization':tenders.update_org(org_id,name=b.get('name'),inn=b.get('inn'),details=b.get('details'))}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc

@app.delete('/api/tenders/{tender_id}')
def tender_delete(tender_id: str):
    try:
        tenders.delete_tender(tender_id)
        return {'deleted': True, 'id': tender_id}
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/tenders/{tender_id}')
def tender_detail(tender_id:str):
    try:
        item=tenders.detail(tender_id)
        item['deadline']=tenders.calculate_deadline(item)
        return {'tender':item}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc

@app.patch('/api/tenders/{tender_id}')
async def tender_update(tender_id:str, request:Request):
    try: return {'tender':tenders.update(tender_id,await request.json())}
    except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc

@app.post('/api/tenders/{tender_id}/comments')
async def tender_add_comment(tender_id:str, request:Request):
    try:
        tenders.add_comment(tender_id,(await request.json()).get('body',''))
        return {'tender':tenders.detail(tender_id)}
    except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc

@app.patch('/api/tenders/{tender_id}/comments/{comment_id}')
async def tender_edit_comment(tender_id: str, comment_id: str, request: Request):
    try:
        tenders.edit_comment(tender_id, comment_id, (await request.json()).get('body'))
        return {'tender':tenders.detail(tender_id)}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc


@app.delete('/api/tenders/{tender_id}/comments/{comment_id}')
def tender_delete_comment(tender_id: str, comment_id: str):
    try:
        tenders.delete_comment(tender_id, comment_id)
        return {'tender':tenders.detail(tender_id)}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc


@app.delete('/api/tenders/{tender_id}/documents/{document_id}')
def tender_delete_doc(tender_id: str, document_id: str):
    try:
        tenders.remove_document(tender_id,document_id)
        return {'tender':tenders.detail(tender_id)}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc


@app.post('/api/tenders/{tender_id}/shipments')
async def tender_add_shipment(tender_id:str, request:Request):
    try:
        sid=tenders.add_shipment(tender_id,await request.json());return {'id':sid}
    except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc


@app.patch('/api/tenders/{tender_id}/shipments/{shipment_id}')
async def tender_edit_shipment(tender_id:str,shipment_id:str,request:Request):
    try: return {'tender':tenders.update_shipment(tender_id,shipment_id,await request.json())}
    except (ValueError,KeyError) as exc:raise HTTPException(400,str(exc)) from exc

@app.delete('/api/tenders/{tender_id}/shipments/{shipment_id}')
def tender_delete_shipment(tender_id: str, shipment_id: str):
    try:
        return {'tender':tenders.delete_shipment(tender_id,shipment_id)}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc


@app.post('/api/tenders/{tender_id}/documents')
async def tender_upload_doc(tender_id:str,request:Request):
    data=await request.body()
    filename=unquote(request.headers.get('x-file-name','document.docx'))
    try:
        from modern.attachment_formats import RAW_EXTENSIONS, RAW_WARNING, validate_raw_document
        raw = Path(filename).suffix.lower() in RAW_EXTENSIONS
        if raw:
            validate_raw_document(filename, data)
        fragments=[] if raw else document_segments(filename,data)
        snippet='\n'.join(x['text'] for x in fragments)[:30000]
        did=tenders.add_document(tender_id,filename,data,snippet)
        return {'document_id':did,'documents':tenders.detail(tender_id)['documents'],
                'warnings':[RAW_WARNING] if raw else []}
    except (ValueError,KeyError,TypeError,RuntimeError) as exc: raise HTTPException(400,str(exc)) from exc

@app.post('/api/tenders/{tender_id}/documents/import-package')
async def tender_import_package(tender_id: str, request: Request):
    """Import an offline ZIP bundle; no direct EIS HTTP access or auto field changes."""
    from modern.tender_package import import_package, MAX_ARCHIVE
    if request.headers.get('content-length'):
        try:
            if int(request.headers['content-length'])>MAX_ARCHIVE:
                raise HTTPException(413,'ZIP должен быть не больше 50 МБ')
        except ValueError:
            raise HTTPException(400,'Неверная длина данных')
    payload=bytearray()
    async for part in request.stream():
        payload.extend(part)
        if len(payload)>MAX_ARCHIVE:
            raise HTTPException(413,'ZIP должен быть не больше 50 МБ')
    try:
        return import_package(tender_id, bytes(payload))
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except (ValueError,TypeError) as exc: raise HTTPException(400,str(exc)) from exc

@app.get('/api/tenders/{tender_id}/documents/{document_id}')
def tender_download_doc(tender_id:str,document_id:str):
    try:
        name,data=tenders.document_bytes(tender_id,document_id)
        from urllib.parse import quote
        return Response(content=data,media_type='application/octet-stream',
            headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name)})
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except (OSError, ValueError) as exc: raise HTTPException(409,str(exc)) from exc

@app.post('/api/tenders/{tender_id}/analyze')
def tender_analyze(tender_id:str):
    try:
        item=tenders.detail(tender_id)
        docs=[tenders.document_bytes(tender_id,x['id']) for x in item['documents'] if not x.get('filename','').lower().endswith('.qxproj')]
        if not docs:return {'analysis':{'mode':'Локальное извлечение, без нейросети','summary':[],'bios':{'status':'Документы не загружены','evidence':[]},'errors':[],'disclaimer':'Добавьте проект контракта или ТЗ для анализа.'}}
        analysis=analyze_documents(docs)
        from modern.contract_autofill import extract
        contract=extract(docs,use_local_ai=False)
        candidates={x['field']:x for x in contract['verified']}
        labels={'due_days':'Срок поставки','due_on':'Срок поставки',
                'supply_address':'Место поставки','payment_terms':'Оплата','warranty':'Гарантия'}
        reverse={'Срок поставки':('due_on','due_days'),'Место поставки':('supply_address',),
                 'Оплата':('payment_terms',),'Гарантия':('warranty',)}
        if any('контракт' in n.lower() or 'договор' in n.lower() for n,_ in docs):
            for line in analysis['summary']:
                fields=reverse.get(line.get('label'))
                if not fields: continue
                found=next((candidates[k] for k in fields if k in candidates),None)
                conflict=any(k in contract['disputed'] for k in fields)
                if found:
                    line['value']=str(found['value']) + (' '+ ('рабочих' if candidates.get('due_unit',{}).get('value')=='work' else 'календарных')+' дней' if found['field']=='due_days' else '')
                    line['evidence']=[found['evidence']]
                else:
                    line['value']='Неоднозначно — проверьте документ' if conflict else 'Однозначное значение не найдено'
                    line['evidence']=[]
            proposals=[]
            for found in contract['verified']:
                proposals.append({'field':found['field'],'value':found['value'],
                                  'label':labels.get(found['field'],found['field']),
                                  'evidence':found['evidence']})
            analysis['suggested_fields']=proposals
            analysis['contract_disputes']=list(contract['disputed'])
        return {'analysis':analysis}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc

@app.get('/api/tenders/{tender_id}/report.docx')
def tender_word_report(tender_id: str):
    """Download an evidence-linked DOCX; read-only and fully local."""
    from modern.tender_report import build_tender_report
    from urllib.parse import quote
    try:
        item=tenders.detail(tender_id)
        readable=[]
        damaged=[]
        for document in item['documents']:
            if document['filename'].lower().endswith('.qxproj'): continue
            try:
                readable.append(tenders.document_bytes(tender_id,document['id']))
            except (OSError, ValueError) as exc:
                damaged.append({'file':document['filename'], 'error':'Файл повреждён или отсутствует; требуется восстановление'})
        if readable:
            results=analyze_documents(readable)
        else:
            results={'bios':{'status':'Документы недоступны или не загружены','evidence':[]},
                     'evidence':{},'suggested_fields':[],'errors':[],
                     'disclaimer':'Необходимо проверить исходные документы вручную.'}
        results['errors']=(results.get('errors') or [])+damaged
        if damaged:
            results['bios']['status']='Требуется уточнение: не все документы удалось проверить'
        payload=build_tender_report(item,results)
        number=''.join(ch for ch in str(item.get('number') or 'bez_nomera') if ch.isdigit())[:30] or 'bez_nomera'
        return Response(content=payload,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('QX_Otchet_'+number+'.docx'),
                     'Cache-Control':'no-store'})
    except KeyError as exc:
        raise HTTPException(404,'Закупка не найдена') from exc

@app.post('/api/tenders/{tender_id}/analyze-and-fill')
def tender_autofill_contract(tender_id: str):
    """One-click evidence-backed autofill, with optional local AI on missing clauses."""
    from modern.contract_autofill import extract, blank_fields
    try:
        item=tenders.detail(tender_id)
        docs=[tenders.document_bytes(tender_id, doc['id']) for doc in item['documents']
              if not doc['filename'].lower().endswith('.qxproj')]
        result=extract(docs,use_local_ai=True)
        updates=blank_fields(item,result['verified'])
        # Any unreadable attached document could hide a contradictory clause.
        # Return proposals but require manual verification in that case.
        if result['errors']:
            updates={}
        # If source docs contradict, don't fill those fields at all.
        for field in result['disputed']:
            updates.pop(field,None)
        if 'due_days' in result['disputed'] or 'due_unit' in result['disputed']:
            updates.pop('due_days',None)
            updates.pop('due_unit',None)
        if updates.get('due_on') and updates.get('due_days'):
            # Two different deadline forms in the same documents need review.
            updates.pop('due_days',None)
            updates.pop('due_unit',None)
        if updates:
            tenders.update(tender_id,updates,manual=False)
            with tenders.transaction() as con:
                for entry in result['verified']:
                    if entry['field'] in updates:
                        proof=entry['evidence']
                        con.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',(
                            tender_id,'Автозаполнение '+entry['field']+' из '+proof['file']+' ('+proof['location']+')',tenders.now()))
        return {'applied':list(updates),'proposals':result['verified'],
                'disputed':result['disputed'],'errors':result['errors'],
                'tender':tenders.detail(tender_id)}
    except KeyError as exc:raise HTTPException(404,str(exc)) from exc
    except (ValueError,OSError,TypeError) as exc:raise HTTPException(400,str(exc)) from exc

@app.post('/api/tenders/{tender_id}/apply-suggestions')
async def tender_apply_suggestions(tender_id:str,request:Request):
    # Every value is verified again against the stored documents. The user
    # explicitly selects the fields; existing values are never overwritten.
    try:
        item=tenders.detail(tender_id)
        docs=[tenders.document_bytes(tender_id,x['id']) for x in item['documents'] if not x.get('filename','').lower().endswith('.qxproj')]
        if any('контракт' in n.lower() or 'договор' in n.lower() for n,_ in docs):
            from modern.contract_autofill import extract
            suggested={x['field']:x['value'] for x in extract(docs)['verified']}
        else:
            suggested={x['field']:x['value'] for x in analyze_documents(docs)['suggested_fields']}
        selected=(await request.json()).get('fields') or []
        if not isinstance(selected,list) or len(selected)>20 or any(not isinstance(k,str) for k in selected):
            raise ValueError('Некорректный список полей')
        allowed={'due_on','due_days','due_unit','supply_address','payment_terms','warranty','security'}
        if any(x not in allowed or x not in suggested for x in selected):
            raise ValueError('Сведения не подтверждены загруженными документами')
        updates={}
        for field in selected:
            value=suggested[field]
            old=item.get(field)
            # Default due_unit='calendar' is not considered user input only if
            # corresponding due_days has not been supplied yet.
            is_blank=not old or (field=='due_unit' and not item.get('due_days'))
            if field=='due_days':is_blank=int(old or 0)==0
            if is_blank:updates[field]=value
        if updates:
            tenders.update(tender_id,updates,manual=True)
        return {'applied':list(updates),'skipped':[k for k in selected if k not in updates],
                'tender':tenders.get(tender_id)}
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except (ValueError,TypeError) as exc: raise HTTPException(400,str(exc)) from exc


@app.post('/api/tenders/{tender_id}/projects/import')
async def tender_import_qxproj(tender_id: str, request: Request):
    """Link a saved project directly to a card; never replace active workspace.

    Project is retained as an attachment. Cost is sourced exclusively from the
    uploaded price rows; an incomplete or zero-cost calculation is clearly shown.
    """
    import hashlib
    name=unquote(request.headers.get('x-file-name','calculation.qxproj'))
    if not name.lower().endswith('.qxproj'):
        raise HTTPException(400, 'Выберите файл с расширением .qxproj')
    raw=await request.body()
    if not raw or len(raw)>20*1024*1024:
        raise HTTPException(413, 'Файл проекта должен быть меньше 20 МБ')
    if not tenders.get(tender_id):
        raise HTTPException(404,'Закупка не найдена')
    try:
        project=load_project(raw)
        entries=project.get('plans') or []
        reqs=project.get('reqs') or []
        if len(entries)>300 or len(reqs)>300:
            raise ValueError('Слишком много позиций в проекте')
        positions=[]
        for i, plan in enumerate(entries):
            if not isinstance(plan,dict):
                raise ValueError('Неверная структура позиций')
            req=plan.get('req') or (reqs[i] if i<len(reqs) else {})
            qty=max(0,float(req.get('quantity') or 0))
            unit=0.0
            for row in plan.get('rows') or []:
                unit+=max(0,float(row.get('qty',1) or 0))*max(0,float(row.get('price') or 0))
            if not (0<=unit<1e11 and 0<=qty<1e7):
                raise ValueError('Некорректная стоимость в проекте')
            positions.append({'title':str(req.get('item_name') or req.get('title') or f'Позиция {i+1}')[:250],
                              'quantity':qty,'unit_cost':unit})
        if not positions:
            # An unfinished .qxproj is still a useful linked document.
            # Do not invent a price or discard the original file.
            positions=[{'title':'Проект без просчитанной комплектации','quantity':0,'unit_cost':0}]
        total=sum(x['quantity']*x['unit_cost'] for x in positions)
        if total>1e12: raise ValueError('Стоимость проекта превышает допустимую')
        key='import:'+tender_id+':'+hashlib.sha256(raw).hexdigest()
        title=str((project.get('project_meta') or {}).get('name') or name)[:250]
        before_cost=float(tenders.get(tender_id).get('purchase_cost') or 0)
        tenders.link_project(key,title,name,'',positions,total,tender_id=tender_id,manual=True)
        if total==0 and before_cost>0:
            # Importing a draft must not erase a manually recorded cost.
            tenders.update(tender_id,{'purchase_cost':before_cost},manual=True)
        doc_id=tenders.add_document(tender_id,name,raw,'Файл расчёта QX; не анализируется как контракт.')
        return {'project_name':title,'positions':len(positions),'purchase_cost':total,
                'document_id':doc_id,'tender':tenders.detail(tender_id)}
    except (ValueError,TypeError,OverflowError,UnicodeError) as exc:
        raise HTTPException(400,'Не удалось прочитать .qxproj: '+str(exc)[:250]) from exc

@app.post('/api/tenders/link-project')
async def tender_link_project(request:Request):
    body=await request.json()
    if len(json.dumps(body,ensure_ascii=False))>1_000_000: raise HTTPException(413,'Слишком много данных расчёта')
    positions=[]
    for p in (body.get('positions') or [])[:300]:
        positions.append({'title':str(p.get('title') or '')[:250], 'quantity':max(0,float(p.get('quantity') or 0)),
                          'unit_cost':max(0,float(p.get('unit_cost') or 0))})
    try:
        return tenders.link_project(body.get('project_key'),body.get('project_name'),body.get('source_name'),
                                    body.get('source_text',''),positions,body.get('cost',0),body.get('organization_id'),manual=body.get('manual') is True,notice_number_override=body.get('notice_number',''),tender_id=body.get('tender_id',''))
    except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc

class EisImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: StrictStr = Field(min_length=11, max_length=20)
    download_documents: StrictBool = True
    tender_id: StrictStr = Field(default='', max_length=100)


class EisJobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: StrictStr = Field(min_length=1, max_length=2048)
    download_documents: StrictBool = True
    tender_id: StrictStr = Field(default='', max_length=100)


@app.post('/api/eis/jobs', status_code=202)
def start_eis_job(body: EisJobRequest):
    from modern.eis_jobs import start_job, JobQueueFull
    try:
        return start_job(body.number, download_documents=body.download_documents, tender_id=body.tender_id)
    except JobQueueFull as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({'error': str(exc), 'tender': tenders.detail(exc.tender_id)}, status_code=429)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/eis/jobs')
def list_eis_jobs():
    from modern.eis_jobs import active_jobs
    return active_jobs()


@app.get('/api/eis/jobs/{job_id}')
def read_eis_job(job_id: str):
    from modern.eis_jobs import get_job
    try:
        return get_job(job_id)
    except KeyError as exc:
        raise HTTPException(404, 'Задача больше не выполняется. Карточка и скачанные файлы сохранены.') from exc


@app.post('/api/eis/import')
async def import_eis_notice(body: EisImportRequest):
    """Explicit lookup, safe fill and attachment download without blocking the UI."""
    from modern.eis_sync import sync_notice
    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(sync_notice, body.number,
                                      download_documents=body.download_documents,
                                      tender_id=body.tender_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/eis/notice/{number}')
async def public_eis_notice(number: str):
    """Best-effort, read-only public EIS XML preview. Never invent missing fields."""
    from modern.eis_public import fetch_notice_metadata
    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(fetch_notice_metadata, number)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.get('/api/tenders/{tender_id}/eis')
def tender_eis_link(tender_id:str):
    # The official EIS search interface is used rather than an invented API.
    item=tenders.get(tender_id)
    if not item:raise HTTPException(404,'Закупка не найдена')
    from urllib.parse import quote
    number=item.get('number') or ''
    # Link only, never claim a real-time lookup succeeded.
    return {'url':'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString='+quote(number),
            'source':'Официальный сайт ЕИС', 'verified':False,
            'message':'Откройте ЕИС и загрузите документацию в карточку. Автоматическая выгрузка не подключена.'}


@app.post('/api/tenders/{tender_id}/eis/lookup')
def tender_eis_lookup(tender_id:str):
    """Optional user-initiated public RSS request. No auto-write to contract."""
    from modern.eis_public import lookup_notice, validate_notice
    item=tenders.get(tender_id)
    if not item: raise HTTPException(404,'Закупка не найдена')
    try:
        number=validate_notice(item.get('number'))
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return lookup_notice(number)


@app.post('/api/tenders/{tender_id}/eis/discover')
async def tender_eis_discover(tender_id: str):
    """Find public EIS document links by this purchase number, without downloading."""
    from starlette.concurrency import run_in_threadpool
    from modern.eis_discovery import discover_for_tender
    try: return await run_in_threadpool(discover_for_tender, tender_id)
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@app.post('/api/tenders/{tender_id}/eis/discover-and-import')
async def tender_eis_discover_and_import(tender_id: str):
    """Explicit user action. Never changes contract terms from an unverified link."""
    from starlette.concurrency import run_in_threadpool
    from modern.eis_discovery import discover_and_import
    try: return await run_in_threadpool(discover_and_import, tender_id)
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@app.post('/api/tenders/{tender_id}/eis/document-from-url')
async def tender_eis_document_from_url(tender_id: str, request: Request):
    """Download an explicitly supplied official EIS document link, never scrape login pages."""
    from starlette.concurrency import run_in_threadpool
    from modern.eis_document_download import import_official_document
    body = await request.json()
    try:
        url = body.get('url') if isinstance(body, dict) else None
        # Real network I/O runs in a worker thread so the UI remains responsive.
        return await run_in_threadpool(import_official_document, tender_id, url)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post('/api/tenders/{tender_id}/eis/documents-from-urls')
async def tender_eis_documents_from_urls(tender_id: str, request: Request):
    """Import a pasted set of official document URLs without blocking the UI."""
    from starlette.concurrency import run_in_threadpool
    from modern.eis_document_download import import_official_documents
    body = await request.json()
    try:
        urls = body.get('urls') if isinstance(body, dict) else None
        return await run_in_threadpool(import_official_documents, tender_id, urls)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/local-ai/status')
async def local_ai_status():
    from modern.local_ai import available_models
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(available_models)


@app.get('/api/local-ai/model-install')
def model_install_get():
    from modern.model_install import model_install_status
    return model_install_status()


@app.post('/api/local-ai/model-install')
def model_install_start():
    from modern.model_install import start_model_install
    try:
        return start_model_install()
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post('/api/local-ai/model-install/cancel')
def model_install_cancel():
    from modern.model_install import cancel_model_install
    return cancel_model_install()


@app.post('/api/tenders/{tender_id}/local-ai')
async def tender_local_ai(tender_id:str, request:Request):
    from modern.local_ai import local_question
    try:
        b=await request.json()
        item=tenders.detail(tender_id)
        docs=[tenders.document_bytes(tender_id,x['id']) for x in item['documents'] if not x.get('filename','').lower().endswith('.qxproj')]
        # GGUF inference can take minutes and Ollama can wait on an HTTP timeout.
        # Never block the one event loop that serves the entire desktop UI.
        from starlette.concurrency import run_in_threadpool
        answer = await run_in_threadpool(local_question, docs,
                                         b.get('question') or '',
                                         b.get('model') or 'offline-search')
        return {'answer': answer}
    except (ValueError,RuntimeError) as exc: raise HTTPException(422,str(exc)) from exc
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc

app.mount('/', StaticFiles(directory=str(STATIC),html=True),name='web')
