"""Fast, offline QX notes. Independent from tender project files and upgrades."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, date
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from modern.tender_store import APP_DATA

DB_FILE = APP_DATA / 'quick_notes.sqlite3'
_LOCK = threading.RLock()
MAX_TITLE = 200
MAX_BODY = 30000

@contextmanager
def _connect():
    APP_DATA.mkdir(parents=True,exist_ok=True)
    con = sqlite3.connect(str(DB_FILE),timeout=15)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA busy_timeout=15000')
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS notes(
          id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT 'Звонок', due_on TEXT NOT NULL DEFAULT '',
          pinned INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
          revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        con.execute('CREATE INDEX IF NOT EXISTS notes_order ON notes(completed,pinned,updated_at)')
        con.commit()
        yield con
    finally:
        con.close()

def _stamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def _clean_fields(fields):
    if not isinstance(fields,dict): raise ValueError('Неверный формат заметки')
    permitted={'title','body','source','due_on','pinned','completed'}
    if any(key not in permitted for key in fields): raise ValueError('Неизвестное поле заметки')
    result={}
    for key,value in fields.items():
        if key in ('pinned','completed'):
            if type(value) is not bool: raise ValueError('Ожидается Да/Нет')
            result[key]=int(value)
        else:
            if not isinstance(value,str): raise ValueError('Ожидается текст')
            if len(value)>({'title':MAX_TITLE,'body':MAX_BODY,'source':40,'due_on':10}[key]):
                raise ValueError('Слишком длинный текст заметки')
            if key=='due_on' and value: date.fromisoformat(value)
            result[key]=value
    return result

def _as_dict(row):
    if row is None: return None
    value=dict(row)
    value['completed']=bool(value['completed']);value['pinned']=bool(value['pinned'])
    return value

def all_notes():
    with _LOCK, _connect() as c:
        return [_as_dict(x) for x in c.execute('SELECT * FROM notes ORDER BY completed ASC, pinned DESC, updated_at DESC').fetchall()]

def due_notes(*, include_completed=True):
    """Stable local tasks for calendar, with no changes to notes themselves."""
    with _LOCK, _connect() as c:
        sql = "SELECT * FROM notes WHERE due_on <> ''"
        if not include_completed:
            sql += ' AND completed = 0'
        sql += ' ORDER BY due_on ASC, completed ASC, created_at ASC'
        return [_as_dict(row) for row in c.execute(sql).fetchall()]

def get(note_id):
    with _LOCK, _connect() as c:
        return _as_dict(c.execute('SELECT * FROM notes WHERE id=?',(note_id,)).fetchone())

def create(fields=None):
    fields=_clean_fields(fields or {})
    note_id=str(uuid.uuid4());timestamp=_stamp()
    with _LOCK, _connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("""INSERT INTO notes(id,title,body,source,due_on,pinned,completed,revision,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,0,?,?)""",(
            note_id,fields.get('title',''),fields.get('body',''),fields.get('source','Звонок'),
            fields.get('due_on',''),fields.get('pinned',0),fields.get('completed',0),timestamp,timestamp))
        c.commit()
    return get(note_id)

def update(note_id, fields, revision):
    fields=_clean_fields(fields)
    if type(revision) is not int or revision<1 or revision>2**53: raise ValueError('Неверная версия записи')
    with _LOCK, _connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT revision FROM notes WHERE id=?',(note_id,)).fetchone()
        if row is None: raise KeyError('Заметка не найдена')
        if revision <= row['revision']:
            result=_as_dict(c.execute('SELECT * FROM notes WHERE id=?',(note_id,)).fetchone())
            c.commit()
            return {**result,'stale':True}
        if fields:
            c.execute('UPDATE notes SET '+', '.join(k+'=?' for k in fields)+', revision=?, updated_at=? WHERE id=?',
                      (*fields.values(),revision,_stamp(),note_id))
        else:
            c.execute('UPDATE notes SET revision=?, updated_at=? WHERE id=?',(revision,_stamp(),note_id))
        result=_as_dict(c.execute('SELECT * FROM notes WHERE id=?',(note_id,)).fetchone())
        c.commit()
        return result

def delete(note_id):
    with _LOCK, _connect() as c:
        c.execute('BEGIN IMMEDIATE')
        count=c.execute('DELETE FROM notes WHERE id=?',(note_id,)).rowcount
        c.commit()
    if not count: raise KeyError('Заметка не найдена')
    return {'deleted':True}

def export_json():
    return json.dumps({'format':'qx-quick-notes-v1','exported_at':_stamp(),'items':all_notes()},
                      ensure_ascii=False,indent=2).encode('utf-8')
