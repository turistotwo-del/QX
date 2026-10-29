"""Regression: quick-note deadlines share calendar with tenders, quotations never trigger auction."""
from datetime import date
import pytest
from fastapi.testclient import TestClient
from modern import tender_store as store, quick_notes, reminders
from modern.server import app

@pytest.fixture
def isolated_data(monkeypatch, tmp_path):
    monkeypatch.setattr(store, 'APP_DATA', tmp_path)
    monkeypatch.setattr(store, 'DB_FILE', tmp_path/'tenders.sqlite3')
    monkeypatch.setattr(store, 'DOCUMENTS', tmp_path/'documents')
    monkeypatch.setattr(store, '_INITIALIZED', False)
    monkeypatch.setattr(quick_notes, 'APP_DATA', tmp_path)
    monkeypatch.setattr(quick_notes, 'DB_FILE', tmp_path/'notes.sqlite3')
    store.initialize()
    yield tmp_path


def test_note_deadline_calendar_and_completion(isolated_data):
    with TestClient(app) as client:
        note=client.post('/api/notes',json={'title':'Купить Key E адаптеры','body':'200 шт.','due_on':'2026-10-27'}).json()['note']
        fetched=client.get('/api/calendar/notes').json()['items']
        assert len(fetched)==1 and fetched[0]['id']==note['id']
        assert any(item['type']=='note' and item['note_id']==note['id'] for item in reminders.reminders(date(2026,10,23)))
        assert client.patch('/api/notes/'+note['id'],json={'fields':{'completed':True},'revision':1}).status_code==200
        assert client.get('/api/calendar/notes').json()['items'][0]['completed'] is True
        assert not any(item['type']=='note' for item in reminders.reminders(date(2026,10,23)))
        assert client.delete('/api/notes/'+note['id']).status_code==200
        assert client.get('/api/calendar/notes').json()['items']==[]


def test_quotation_results_without_auction_notifications(isolated_data):
    quote=store.create({'number':'0322100002526000466','title':'Моноблоки','status':'Подготовка заявки',
        'is_quotation':True,'application_due_on':'2026-10-25','auction_on':'2026-10-27','auction_time':'12:00',
        'results_on':'2026-10-29','results_time':'14:00'})
    ev=[x for x in reminders.reminders(date(2026,10,23)) if x['tender_id']==quote['id']]
    assert {'application','results'}==set(x['type'] for x in ev)
    assert all(x['type']!='auction' for x in ev)
    assert any(x['due_time']=='14:00' for x in ev if x['type']=='results')
    store.update(quote['id'],{'is_quotation':False})
    ev=[x for x in reminders.reminders(date(2026,10,23)) if x['tender_id']==quote['id']]
    assert 'auction' in [x['type'] for x in ev]
    assert 'results' not in [x['type'] for x in ev]
    with pytest.raises(ValueError): store.update(quote['id'],{'is_quotation':'yes'})
    with pytest.raises(ValueError): store.update(quote['id'],{'results_time':'99:99'})


def test_quotation_fields_persist_after_reinitialize(isolated_data):
    quote=store.create({'title':'Запрос котировок','is_quotation':True,'results_on':'2026-11-06'})
    store._INITIALIZED=False
    store.initialize()
    assert store.get(quote['id'])['is_quotation']==1
    assert store.get(quote['id'])['results_on']=='2026-11-06'
    with store.connection() as c:
        assert c.execute('select version from schema_version').fetchone()[0]==store.SCHEMA_VERSION


def test_http_quotation_toggle_and_due_date(isolated_data):
    with TestClient(app) as client:
        r=client.post('/api/tenders',json={'title':'Принтеры','status':'Черновик','is_quotation':True})
        assert r.status_code==200, r.text
        tid=r.json()['tender']['id']
        r=client.patch('/api/tenders/'+tid,json={'results_on':'2026-11-09','results_time':'10:45'})
        assert r.status_code==200,r.text
        t=client.get('/api/tenders/'+tid).json()['tender']
        assert t['results_time']=='10:45' and t['is_quotation']==1
