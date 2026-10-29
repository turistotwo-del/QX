import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from modern import quick_notes
from modern.server import app

@pytest.fixture
def scoped_notes(monkeypatch,tmp_path):
    monkeypatch.setattr(quick_notes,'APP_DATA',tmp_path)
    monkeypatch.setattr(quick_notes,'DB_FILE',tmp_path/'notes.sqlite3')
    yield tmp_path

def test_notes_persist_and_utf8(scoped_notes):
    row=quick_notes.create({'title':'Звонок от Андрея','body':'Позвонить заводу до обеда. Моноблоков 25 шт.','source':'Поручение босса','due_on':'2026-10-27'})
    assert len(quick_notes.all_notes())==1
    assert row['revision']==0 and row['completed'] is False
    saved=quick_notes.update(row['id'],{'body':'Отправить счёт № 12 \nСогласовать цену','pinned':True},1)
    assert saved['revision']==1 and saved['pinned'] is True
    assert 'Согласовать' in quick_notes.get(row['id'])['body']
    assert scoped_notes.joinpath('notes.sqlite3').exists()

def test_old_changes_cannot_overwrite_latest(scoped_notes):
    item=quick_notes.create({'title':'Черновик'})
    quick_notes.update(item['id'],{'body':'Новая важная запись'},3)
    stale=quick_notes.update(item['id'],{'body':'Опоздавший сетевой запрос'},2)
    assert stale['stale'] is True
    assert quick_notes.get(item['id'])['body']=='Новая важная запись'
    assert quick_notes.get(item['id'])['revision']==3

def test_validation_delete_export(scoped_notes):
    item=quick_notes.create({'body':'Привет'})
    with pytest.raises(ValueError):quick_notes.create({'body':'x'*30001})
    with pytest.raises(ValueError):quick_notes.update(item['id'],{'due_on':'2026-02-30'},1)
    with pytest.raises(ValueError):quick_notes.update(item['id'],{'pinned':'yes'},1)
    assert 'Привет' in quick_notes.export_json().decode('utf8')
    assert quick_notes.delete(item['id'])['deleted'] is True
    assert quick_notes.all_notes()==[]
    with pytest.raises(KeyError):quick_notes.delete(item['id'])

def test_http_crud(scoped_notes):
    with TestClient(app) as client:
        assert client.get('/api/notes').json()['items']==[]
        res=client.post('/api/notes',json={'title':'Завод','source':'Звонок'})
        assert res.status_code==200,res.text
        item=res.json()['note'];id=item['id']
        res=client.patch('/api/notes/'+id,json={'fields':{'body':'Поставка в среду','completed':True},'revision':1})
        assert res.status_code==200,res.text
        assert res.json()['note']['completed'] is True
        assert client.get('/api/notes').json()['items'][0]['body']=='Поставка в среду'
        exported=client.get('/api/notes-export')
        assert exported.status_code==200 and b'QX' not in exported.content[:20]
        assert client.delete('/api/notes/'+id).status_code==200
        assert client.delete('/api/notes/'+id).status_code==404
