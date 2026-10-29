"""QX Tender workspace: local SQLite, migrations, transactions and safe attachments.

No data lives in the installed application directory. Compatible with read-only exe.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
import threading
from datetime import timezone

APP_DATA = Path(os.environ.get('QX_DATA_DIR') or (Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'QXPodborshchik'))
DB_FILE = APP_DATA / 'tenders.sqlite3'
DOCUMENTS = APP_DATA / 'tender_documents'

STATUSES = ('Черновик', 'Просчёт', 'Подготовка заявки', 'Заявка подана', 'Ожидание результатов', 'Выиграли', 'Проиграли', 'Ожидание подписания', 'Контракт подписан', 'Заказ оборудования', 'Производство', 'Комплектация', 'Готово к отправке', 'Отгружено', 'Доставлено', 'Приёмка', 'Контракт исполнен', 'Отменено')
PROTECTED = {'Выиграли', 'Проиграли', 'Контракт подписан', 'Контракт исполнен'}
FIELDS = {'number', 'lot', 'title', 'customer', 'law', 'status', 'organization_id', 'nmck', 'bid_price', 'contract_price', 'purchase_cost', 'delivery_cost', 'extra_cost', 'paid_amount', 'payment_status', 'contract_number', 'signed_on', 'due_on', 'due_days', 'due_unit', 'deadline_basis', 'supply_address', 'payment_terms', 'warranty', 'security', 'notes', 'is_delivered','application_due_on','application_due_time','auction_on','auction_time','payment_due_on','is_quotation','results_on','results_time'}
TEXT_FIELDS = {'number','lot','title','customer','law','status','organization_id','payment_status','contract_number','signed_on','due_on','due_unit','deadline_basis','supply_address','payment_terms','warranty','security','notes','application_due_on','application_due_time','auction_on','auction_time','payment_due_on','results_on','results_time'}
MONEY_FIELDS = {'nmck','bid_price','contract_price','purchase_cost','delivery_cost','extra_cost','paid_amount'}
_INITIALIZED = False
_INIT_LOCK = threading.Lock()
NOTICE_RE = re.compile(r'(?<!\d)\d{19,20}(?!\d)')

def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def notice_number(text):
    return (NOTICE_RE.search(text or '') or [None])[0]

def _clean(value):
    return str(value or '').strip()

def _db():
    APP_DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_FILE), timeout=15)
    try:
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys = ON')
        c.execute('PRAGMA busy_timeout=15000')
        c.execute('PRAGMA journal_mode=WAL')
        return c
    except Exception:
        c.close()
        raise

@contextmanager
def connection():
    """Read connection: always close SQLite handle (important on Windows)."""
    con = _db()
    try: yield con
    finally: con.close()


@contextmanager
def transaction():
    con = _db()
    try:
        con.execute('BEGIN IMMEDIATE')
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

SCHEMA_VERSION = 7


def _read_schema_version(con):
    """Determine a database version without touching the user's tables."""
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
    if not exists:
        return 0
    cols = {r[1] for r in con.execute('PRAGMA table_info(schema_version)')}
    if 'version' not in cols:
        raise RuntimeError('Некорректная таблица версий SQLite — миграция остановлена')
    values = [r[0] for r in con.execute('SELECT version FROM schema_version')]
    if len(values) != 1 or not isinstance(values[0], int) or values[0] < 0:
        raise RuntimeError('Неверный номер схемы SQLite — миграция остановлена')
    return values[0]



def _needs_schema_repair(con):
    """Detect partially applied older upgrades even if version says current."""
    tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'schema_version','organizations','tenders','tender_projects',
              'tender_comments','tender_events','tender_documents',
              'tender_shipments','tender_notification_settings','tender_notified',
              'deleted_tender_project_keys'}
    if not required <= tables:
        return True
    cols={r[1] for r in con.execute('PRAGMA table_info(tenders)')}
    if not {'application_due_on','application_due_time','auction_on','auction_time','payment_due_on','is_quotation','results_on','results_time'} <= cols:
        return True
    indices={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    return 'tender_notice_unique' not in indices


def _write_migration_snapshot(source, old_version):
    """Consistent pre-update SQLite backup, including committed WAL rows."""
    folder = APP_DATA / 'migration_snapshots'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    path = folder / f'QX_Before_Schema_v{old_version}_to_v{SCHEMA_VERSION}_{stamp}_{uuid.uuid4().hex[:8]}.sqlite3'
    temp = path.with_suffix('.sqlite3.partial')
    try:
        with closing(sqlite3.connect(str(temp), timeout=15)) as target:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Резервная SQLite-копия повреждена')
        os.replace(temp, path)
        return path
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _apply_schema(c):
    """Apply DDL in caller's transaction.

    sqlite3.executescript commits an active transaction before execution,
    potentially leaving a partially migrated database if a statement fails.
    """
    create_sql = """CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS organizations (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, inn TEXT DEFAULT '', details TEXT DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tenders (
              id TEXT PRIMARY KEY, number TEXT DEFAULT '', lot TEXT DEFAULT '', title TEXT NOT NULL DEFAULT '',
              customer TEXT DEFAULT '', law TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Черновик',
              organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
              nmck REAL DEFAULT 0, bid_price REAL DEFAULT 0, contract_price REAL DEFAULT 0,
              purchase_cost REAL DEFAULT 0, delivery_cost REAL DEFAULT 0, extra_cost REAL DEFAULT 0, paid_amount REAL DEFAULT 0,
              payment_status TEXT DEFAULT '', contract_number TEXT DEFAULT '', signed_on TEXT DEFAULT '',
              due_on TEXT DEFAULT '', due_days INTEGER DEFAULT 0, due_unit TEXT DEFAULT 'calendar',
              deadline_basis TEXT DEFAULT '', supply_address TEXT DEFAULT '', payment_terms TEXT DEFAULT '',
              warranty TEXT DEFAULT '', security TEXT DEFAULT '', notes TEXT DEFAULT '',
              is_delivered INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS tender_notice_unique ON tenders(number, lot, COALESCE(organization_id, '')) WHERE number <> '';
            CREATE TABLE IF NOT EXISTS tender_projects (
              project_key TEXT PRIMARY KEY, tender_id TEXT NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
              project_name TEXT DEFAULT '', source_name TEXT DEFAULT '', positions_json TEXT NOT NULL DEFAULT '[]',
              cost REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tender_comments (
              id TEXT PRIMARY KEY, tender_id TEXT NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
              body TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tender_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, tender_id TEXT NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
              label TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tender_documents (
              id TEXT PRIMARY KEY, tender_id TEXT NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
              filename TEXT NOT NULL, sha256 TEXT NOT NULL, file_path TEXT NOT NULL,
              text_excerpt TEXT DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tender_shipments (
              id TEXT PRIMARY KEY, tender_id TEXT NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
              name TEXT DEFAULT '', quantity REAL DEFAULT 0, due_on TEXT DEFAULT '', sent_on TEXT DEFAULT '',
              delivered_on TEXT DEFAULT '', accepted_on TEXT DEFAULT '', note TEXT DEFAULT ''
            );"""
    for statement in create_sql.split(';'):
        if statement.strip():
            c.execute(statement)
    if not c.execute('SELECT count(*) FROM schema_version').fetchone()[0]:
        c.execute('INSERT INTO schema_version(version) VALUES (1)')
    cols = {r[1] for r in c.execute('PRAGMA table_info(tenders)').fetchall()}
    for col in ('application_due_on', 'application_due_time', 'auction_on', 'auction_time', 'payment_due_on'):
        if col not in cols:
            c.execute('ALTER TABLE tenders ADD COLUMN '+col+" TEXT DEFAULT ''")
    for col, column_type in [('is_quotation','INTEGER NOT NULL DEFAULT 0'),('results_on',"TEXT DEFAULT ''"),('results_time',"TEXT DEFAULT ''")]:
        if col not in cols:
            c.execute(f'ALTER TABLE tenders ADD COLUMN {col} {column_type}')
    c.execute("""CREATE TABLE IF NOT EXISTS tender_notification_settings(
         id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
         advance_days INTEGER NOT NULL DEFAULT 7)""")
    c.execute('INSERT OR IGNORE INTO tender_notification_settings(id,enabled,advance_days) VALUES(1,0,7)')
    c.execute("""CREATE TABLE IF NOT EXISTS tender_notified(
         event_key TEXT PRIMARY KEY, sent_on TEXT NOT NULL)""")
    # Persistent tombstones prevent a previously deleted procurement from being
    # silently re-created when an older calculated project is opened again.
    c.execute('CREATE TABLE IF NOT EXISTS deleted_tender_project_keys('
              'project_key TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)')
    c.execute('UPDATE schema_version SET version=? WHERE version<?',(SCHEMA_VERSION,SCHEMA_VERSION))


def initialize():
    """Create/migrate tenders transactionally, retaining an older copy."""
    global _INITIALIZED
    if _INITIALIZED:
        return True
    with _INIT_LOCK:
        if _INITIALIZED:
            return True
        had_existing_db = DB_FILE.exists()
        with connection() as reader:
            if reader.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('База закупок повреждена. Миграция не выполнялась.')
            old_version = _read_schema_version(reader)
            if old_version > SCHEMA_VERSION:
                raise RuntimeError('База закупок создана более новой версией QX. Откройте её в обновлённой программе.')
            if had_existing_db and (old_version < SCHEMA_VERSION or _needs_schema_repair(reader)):
                # A snapshot failure stops migration BEFORE updating any table.
                _write_migration_snapshot(reader, old_version)
        with transaction() as c:
            if _read_schema_version(c) > SCHEMA_VERSION:
                raise RuntimeError('Нельзя открыть более новую схему QX')
            _apply_schema(c)
            if c.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise RuntimeError('В базе закупок нарушены связи между записями')
        _INITIALIZED = True
    return True

def _dict(r):
    return dict(r) if r is not None else None

def _validate(fields):
    clean = {}
    for k, v in fields.items():
        if k not in FIELDS: continue
        if k in MONEY_FIELDS:
            v = float(v or 0)
            if not -1e12 < v < 1e12: raise ValueError('Недопустимая сумма')
        elif k == 'due_days':
            v = int(v or 0)
            if v < 0 or v > 36500: raise ValueError('Недопустимое число дней')
        elif k in ('is_delivered','is_quotation'):
            if type(v) is not bool: raise ValueError('Ожидается Да/Нет')
            v = 1 if v else 0
        elif k == 'organization_id': v = _clean(v) or None
        else: v = _clean(v)[:12000 if k == 'notes' else 1000]
        if k == 'status' and v not in STATUSES: raise ValueError('Неизвестный статус')
        if k == 'due_unit' and v not in ('calendar','work'): raise ValueError('Неизвестный тип дней')
        if k in ('signed_on', 'due_on','application_due_on','auction_on','payment_due_on','results_on') and v:
            date.fromisoformat(v)
        if k in ('application_due_time', 'auction_time','results_time') and v:
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', v):
                raise ValueError('Время события должно быть в формате ЧЧ:ММ')
        clean[k] = v
    return clean

def create(fields=None):
    initialize()
    values = _validate(fields or {})
    number, lot = values.get('number',''), values.get('lot','')
    if number:
        with transaction() as c:
            existing = c.execute('SELECT id FROM tenders WHERE number=? AND lot=? AND COALESCE(organization_id,\'\')=?', (number,lot,values.get('organization_id') or '')).fetchone()
            if existing: return _dict(c.execute('SELECT * FROM tenders WHERE id=?',(existing['id'],)).fetchone())
    obj_id = str(uuid.uuid4())
    with transaction() as c:
        keys = ['id','created_at','updated_at'] + list(values)
        params = [obj_id,now(),now()] + list(values.values())
        try:
            c.execute(f'INSERT INTO tenders({",".join(keys)}) VALUES({",".join("?" for _ in keys)})', params)
        except sqlite3.IntegrityError:
            if number:
                row=c.execute('SELECT id FROM tenders WHERE number=? AND lot=? AND COALESCE(organization_id,\'\')=?', (number,lot,values.get('organization_id') or '')).fetchone()
                if row: obj_id=row['id']
                else: raise
            else: raise
    return get(obj_id)

def get(tender_id):
    initialize()
    with connection() as c:
        return _dict(c.execute('SELECT * FROM tenders WHERE id=?',(tender_id,)).fetchone())

def listing():
    initialize()
    with connection() as c:
        return [_dict(r) for r in c.execute('SELECT t.*, o.name AS organization_name FROM tenders t LEFT JOIN organizations o ON o.id=t.organization_id ORDER BY t.updated_at DESC, t.created_at DESC').fetchall()]

def delete_tender(tender_id):
    """Permanently delete one tender and its dependent rows atomically.

    Equipment catalogs and standalone .qxproj project files are never modified.
    Document blobs are removed only if no other tender references that exact
    managed path; unmanaged files are never touched.
    """
    initialize()
    with transaction() as c:
        row = c.execute('SELECT id FROM tenders WHERE id=?', (tender_id,)).fetchone()
        if row is None:
            raise KeyError('Закупка не найдена')
        docs = [dict(r) for r in c.execute(
            'SELECT file_path, sha256 FROM tender_documents WHERE tender_id=?',
            (tender_id,)).fetchall()]
        c.execute('INSERT OR IGNORE INTO deleted_tender_project_keys(project_key,deleted_at) '
                  'SELECT project_key,? FROM tender_projects WHERE tender_id=?', (now(), tender_id))
        # The schema uses ON DELETE CASCADE for documents, comments, shipments,
        # events and tender/project links. The organization is independent.
        c.execute('DELETE FROM tenders WHERE id=?', (tender_id,))
    # Do not unlink files until the transaction has committed successfully.
    # Only remove content-addressed attachments that no surviving card uses.
    for doc in docs:
        path = Path(doc['file_path'])
        if path.parent.resolve() != DOCUMENTS.resolve():
            continue
        if not re.fullmatch(r'[0-9a-f]{64}\.(pdf|docx|xlsx|xlsm|txt|md|csv|xml|qxproj|doc|xls|rtf)', path.name):
            continue
        if not path.name.startswith(doc['sha256'] + '.'):
            continue
        with connection() as c:
            still_used = c.execute(
                'SELECT 1 FROM tender_documents WHERE file_path=? LIMIT 1',
                (str(path),)).fetchone()
        if still_used is None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # A locked blob can be cleaned later; the tender deletion
                # is already committed and must not be reported as failed.
                pass
    return True


def update(tender_id, fields, *, manual=True):
    values = _validate(fields)
    if not get(tender_id): raise KeyError('Закупка не найдена')
    if not values: return get(tender_id)
    with transaction() as c:
        old=_dict(c.execute('SELECT * FROM tenders WHERE id=?',(tender_id,)).fetchone())
        if not manual and ('status' in values and values['status'] in PROTECTED):
            raise ValueError('Ключевые статусы устанавливаются только после подтверждения пользователем')
        c.execute('UPDATE tenders SET '+', '.join(f'{k}=?' for k in values)+', updated_at=? WHERE id=?', [*values.values(), now(), tender_id])
        for k, v in values.items():
            if old.get(k) != v and k in ('status','due_on','contract_price','signed_on','is_delivered'):
                c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES (?,?,?)', (tender_id, f'{k}: {old.get(k) or "—"} → {v}', now()))
    return get(tender_id)

def add_org(name, inn='', details=''):
    if not _clean(name): raise ValueError('Введите название организации')
    initialize()
    oid=str(uuid.uuid4())
    with transaction() as c:
        c.execute('INSERT INTO organizations VALUES(?,?,?,?,?)', (oid,_clean(name),_clean(inn),_clean(details),now()))
    return oid

def update_org(org_id, *, name=None, inn=None, details=None):
    initialize()
    with transaction() as c:
        existing=c.execute('SELECT * FROM organizations WHERE id=?',(org_id,)).fetchone()
        if existing is None: raise KeyError('Организация не найдена')
        vals={}
        if name is not None:
            if not _clean(name): raise ValueError('Введите название организации')
            vals['name']=_clean(name)[:300]
        if inn is not None: vals['inn']=_clean(inn)[:20]
        if details is not None: vals['details']=_clean(details)[:3000]
        if vals:
            c.execute('UPDATE organizations SET '+','.join(k+'=?' for k in vals)+' WHERE id=?', [*vals.values(),org_id])
        return _dict(c.execute('SELECT * FROM organizations WHERE id=?',(org_id,)).fetchone())

def organizations():
    initialize()
    with connection() as c: return [_dict(r) for r in c.execute('SELECT * FROM organizations ORDER BY name')]

def add_comment(tid, body):
    if not get(tid): raise KeyError('Закупка не найдена')
    if not str(body or '').strip(): raise ValueError('Пустой комментарий')
    with transaction() as c:
        c.execute('INSERT INTO tender_comments VALUES(?,?,?,?)',(str(uuid.uuid4()),tid,str(body).strip()[:10000],now()))
        c.execute('UPDATE tenders SET updated_at=? WHERE id=?',(now(),tid))

def edit_comment(tid, comment_id, body):
    """Edit a comment with a timestamped audit record, without erasing history."""
    value=str(body or '').strip()
    if not value: raise ValueError('Комментарий не может быть пустым')
    if len(value)>10000: raise ValueError('Комментарий слишком длинный')
    with transaction() as c:
        row=c.execute('SELECT * FROM tender_comments WHERE tender_id=? AND id=?', (tid,comment_id)).fetchone()
        if row is None: raise KeyError('Комментарий не найден')
        if row['body']==value: return
        c.execute('UPDATE tender_comments SET body=? WHERE id=?',(value,comment_id))
        # An audit event preserves the previous comment (useful for contract management).
        c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                  (tid,'Редактирование комментария: '+row['body'][:300],now()))
        c.execute('UPDATE tenders SET updated_at=? WHERE id=?',(now(),tid))


def delete_comment(tid, comment_id):
    with transaction() as c:
        row=c.execute('SELECT * FROM tender_comments WHERE tender_id=? AND id=?',(tid,comment_id)).fetchone()
        if row is None: raise KeyError('Комментарий не найден')
        c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                  (tid,'Удалён комментарий: '+row['body'][:300],now()))
        c.execute('DELETE FROM tender_comments WHERE id=?',(comment_id,))
        c.execute('UPDATE tenders SET updated_at=? WHERE id=?',(now(),tid))


def remove_document(tid, doc_id):
    """Unlink a document; preserve shared content referenced by other cards."""
    with transaction() as c:
        row=c.execute('SELECT * FROM tender_documents WHERE tender_id=? AND id=?',(tid,doc_id)).fetchone()
        if row is None: raise KeyError('Документ не найден')
        c.execute('DELETE FROM tender_documents WHERE id=?',(doc_id,))
        c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                  (tid,'Удалён документ: '+row['filename']+' (sha256='+row['sha256']+')',now()))
        c.execute('UPDATE tenders SET updated_at=? WHERE id=?',(now(),tid))
        remaining=c.execute('SELECT count(*) FROM tender_documents WHERE sha256=?',(row['sha256'],)).fetchone()[0]
    if remaining==0:
        path=Path(row['file_path'])
        # Only delete content-addressed blobs in our managed directory.
        if path.parent.resolve()==DOCUMENTS.resolve() and path.name.startswith(row['sha256']):
            try: path.unlink(missing_ok=True)
            except OSError: pass


def record_official_document_source(tid: str, name: str, count: int):
    """Audit source without persisting a possibly token-bearing download URL."""
    if not get(tid):
        raise KeyError('Закупка не найдена')
    with transaction() as c:
        c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                  (tid, 'Документация: zakupki.gov.ru (ссылка пользователя); '+
                   str(name)[:140]+'; файлов: '+str(int(count)), now()))
        c.execute('UPDATE tenders SET updated_at=? WHERE id=?', (now(), tid))


def add_document(tid, filename, contents, text=''):
    if not get(tid): raise KeyError('Закупка не найдена')
    if len(contents)>30*1024*1024: raise ValueError('Документ больше 30 МБ')
    ext=Path(filename).suffix.lower()
    if ext not in ('.pdf','.docx','.xlsx','.xlsm','.txt','.md','.csv','.xml','.qxproj','.doc','.xls','.rtf'): raise ValueError('Неподдерживаемый документ')
    from modern.attachment_formats import RAW_EXTENSIONS, validate_raw_document
    if ext in RAW_EXTENSIONS: validate_raw_document(filename, contents)
    DOCUMENTS.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(contents).hexdigest()
    filename_clean=Path(str(filename).replace('\\','/')).name[:220]
    path=DOCUMENTS/(digest+ext)
    if path.exists():
        # An existing content-addressed blob may have been modified on disk.
        # Never silently link an altered contract to another tender.
        from modern.attachment_integrity import checked_attachment
        checked_attachment(path,digest,DOCUMENTS)
    else:
        temp=path.with_suffix(path.suffix+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_bytes(contents)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    with transaction() as c:
        current=c.execute('SELECT id FROM tender_documents WHERE tender_id=? AND sha256=?',(tid,digest)).fetchone()
        if current: return current['id']
        did=str(uuid.uuid4())
        c.execute('INSERT INTO tender_documents VALUES(?,?,?,?,?,?,?)',(did,tid,filename_clean,digest,str(path),text[:30000],now()))
        c.execute('UPDATE tenders SET updated_at=? WHERE id=?',(now(),tid))
    return did

def add_documents_batch(tid, entries):
    """Create links for multiple validated files in one SQLite transaction.

    Content-addressed blobs are saved before the transaction. A DB failure
    cannot create partially imported document rows. Existing attachments are
    never modified, and duplicates are reported rather than reinserted.
    """
    if not get(tid): raise KeyError('Закупка не найдена')
    if len(entries)>80: raise ValueError('Слишком много документов')
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    prepared=[]
    for filename, data, excerpt in entries:
        if not isinstance(data, bytes) or len(data)>30*1024*1024:
            raise ValueError('Некорректные данные документа')
        ext=Path(filename).suffix.lower()
        if ext not in ('.pdf','.docx','.xlsx','.xlsm','.txt','.md','.csv','.xml','.doc','.xls','.rtf'):
            raise ValueError('Недопустимый формат документа')
        from modern.attachment_formats import RAW_EXTENSIONS, validate_raw_document
        if ext in RAW_EXTENSIONS: validate_raw_document(filename, data)
        digest=hashlib.sha256(data).hexdigest()
        path=DOCUMENTS/(digest+ext)
        prepared.append((Path(str(filename).replace('\\','/')).name[:220],data,str(excerpt or '')[:30000],digest,path))
    imported=[]
    duplicates=[]
    newly_created=[]
    try:
        for name, data, excerpt, digest, path in prepared:
            if not path.exists():
                temp=path.with_suffix(path.suffix+'.'+str(uuid.uuid4())+'.tmp')
                try:
                    temp.write_bytes(data)
                    # A concurrent writer may create identical content first.
                    if not path.exists():
                        temp.replace(path)
                        newly_created.append(path)
                finally:
                    temp.unlink(missing_ok=True)
            else:
                from modern.attachment_integrity import checked_attachment
                checked_attachment(path,digest,DOCUMENTS)
        with transaction() as c:
            for name, data, excerpt, digest, path in prepared:
                existing=c.execute('SELECT id FROM tender_documents WHERE tender_id=? AND sha256=?',(tid,digest)).fetchone()
                if existing:
                    duplicates.append(name)
                    continue
                did=str(uuid.uuid4())
                c.execute('INSERT INTO tender_documents VALUES(?,?,?,?,?,?,?)',
                          (did,tid,name,digest,str(path),excerpt,now()))
                imported.append({'id':did,'filename':name})
            if imported:
                c.execute('UPDATE tenders SET updated_at=? WHERE id=?',(now(),tid))
                c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                          (tid,f'Импорт пакета документов: {len(imported)} файл(ов)',now()))
    except Exception:
        for path in newly_created:
            try:
                with connection() as c:
                    linked=c.execute('SELECT COUNT(*) FROM tender_documents WHERE file_path=?',(str(path),)).fetchone()[0]
                if not linked: path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return {'imported':imported,'duplicates':duplicates}

def document_bytes(tid, did):
    with connection() as c:
        row=c.execute('SELECT * FROM tender_documents WHERE id=? AND tender_id=?',(did,tid)).fetchone()
        if not row: raise KeyError('Документ не найден')
        from modern.attachment_integrity import checked_attachment
        return row['filename'], checked_attachment(Path(row['file_path']), row['sha256'], DOCUMENTS)

def detail(tid):
    tender=get(tid)
    if not tender: raise KeyError('Закупка не найдена')
    with connection() as c:
        tender['comments']=[_dict(r) for r in c.execute('SELECT * FROM tender_comments WHERE tender_id=? ORDER BY created_at DESC',(tid,))]
        tender['documents']=[{k:v for k,v in _dict(r).items() if k not in ('file_path',)} for r in c.execute('SELECT * FROM tender_documents WHERE tender_id=? ORDER BY created_at DESC',(tid,))]
        tender['events']=[_dict(r) for r in c.execute('SELECT * FROM tender_events WHERE tender_id=? ORDER BY id DESC LIMIT 120',(tid,))]
        tender['projects']=[_dict(r) for r in c.execute('SELECT * FROM tender_projects WHERE tender_id=? ORDER BY updated_at DESC',(tid,))]
        tender['shipments']=[_dict(r) for r in c.execute('SELECT * FROM tender_shipments WHERE tender_id=?',(tid,))]
    return tender

def link_project(project_key, project_name, source_name='', source_text='', positions=None, cost=0, org_id=None, *, manual=False, notice_number_override='', tender_id=''):
    """Idempotent upsert by persistent client-side project UUID, then by notice/lot/org."""
    if not project_key: raise ValueError('Нужен идентификатор проекта')
    initialize()
    with transaction() as c:
        removed = c.execute('SELECT 1 FROM deleted_tender_project_keys WHERE project_key=?',
                            (project_key,)).fetchone() is not None
        if removed and not manual:
            return {'tender_id': '', 'purchase_cost': 0, 'suppressed': True}
        if removed and manual:
            c.execute('DELETE FROM deleted_tender_project_keys WHERE project_key=?', (project_key,))
    with connection() as c:
        row=c.execute('SELECT tender_id FROM tender_projects WHERE project_key=?',(project_key,)).fetchone()
    # Explicit choice of notice always wins over an old implicit project link.
    # A changed number must not silently attach a new project to old card.
    chosen_number=_clean(notice_number_override)
    if chosen_number and not re.fullmatch(r'(?:\d{11}|\d{19,20})', chosen_number):
        raise ValueError('Номер ЕИС должен содержать 11, 19 или 20 цифр')
    existing = get(tender_id) if tender_id else None
    if chosen_number and existing and existing.get('number') != chosen_number:
        existing = None
    old_card = get(row['tender_id']) if row else None
    if chosen_number and old_card and old_card.get('number') != chosen_number:
        old_card = None
    if existing:
        tid=existing['id']
    elif old_card:
        tid=old_card['id']
    else:
        number=chosen_number or notice_number((source_name or '')+'\n'+(source_text or '')[:15000])
        t=create({'title':_clean(project_name) or _clean(source_name) or 'Закупка без номера','number':number or '', 'status':'Просчёт','organization_id':org_id or ''})
        tid=t['id']
    pos=positions or []
    total=float(cost or 0)
    with transaction() as c:
        c.execute('''INSERT INTO tender_projects(project_key,tender_id,project_name,source_name,positions_json,cost,updated_at) VALUES(?,?,?,?,?,?,?)
                     ON CONFLICT(project_key) DO UPDATE SET tender_id=excluded.tender_id,project_name=excluded.project_name,source_name=excluded.source_name,
                     positions_json=excluded.positions_json,cost=excluded.cost,updated_at=excluded.updated_at''',
                  (project_key,tid,_clean(project_name),_clean(source_name),json.dumps(pos,ensure_ascii=False),total,now()))
        total_all=c.execute('SELECT sum(cost) FROM tender_projects WHERE tender_id=?',(tid,)).fetchone()[0] or 0
        # Preserve manually edited tender statuses, contract price and comments.
        c.execute('UPDATE tenders SET purchase_cost=?,updated_at=? WHERE id=?',(total_all,now(),tid))
        # When a project is moved to another purchase, recalculate the OLD
        # card as well. Otherwise that purchase retains phantom expenses.
        if row and row['tender_id'] != tid:
            previous=row['tender_id']
            previous_total=c.execute('SELECT sum(cost) FROM tender_projects WHERE tender_id=?',(previous,)).fetchone()[0] or 0
            c.execute('UPDATE tenders SET purchase_cost=?,updated_at=? WHERE id=?', (previous_total,now(),previous))
    return {'tender_id':tid,'purchase_cost':total_all}

def add_shipment(tid, row):
    if not get(tid): raise KeyError('Закупка не найдена')
    due=_clean(row.get('due_on'))
    if due: date.fromisoformat(due)
    sid=str(uuid.uuid4())
    with transaction() as c:
        c.execute('INSERT INTO tender_shipments(id,tender_id,name,quantity,due_on,note) VALUES(?,?,?,?,?,?)',
            (sid,tid,_clean(row.get('name')),float(row.get('quantity') or 0),due,_clean(row.get('note'))))
    return sid

def update_shipment(tid, sid, fields):
    allowed={'sent_on','delivered_on','accepted_on','due_on','note','quantity','name'}
    clean={}
    for k,v in fields.items():
        if k not in allowed:continue
        if k in ('sent_on','delivered_on','accepted_on','due_on') and v:date.fromisoformat(str(v))
        clean[k]=float(v or 0) if k=='quantity' else str(v or '')[:1000]
    with transaction() as c:
        row=c.execute('SELECT * FROM tender_shipments WHERE id=? AND tender_id=?',(sid,tid)).fetchone()
        if not row:raise KeyError('Этап не найден')
        if clean:
            c.execute('UPDATE tender_shipments SET '+', '.join(k+'=?' for k in clean)+' WHERE id=? AND tender_id=?',(*clean.values(),sid,tid))
            c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',(tid,'Этап поставки «'+row['name']+'»: '+', '.join(clean.keys()),now()))
    return detail(tid)


def delete_shipment(tid: str, sid: str) -> dict:
    """Remove one delivery stage belonging to this tender; other stages survive."""
    with transaction() as c:
        exists=c.execute('SELECT name FROM tender_shipments WHERE id=? AND tender_id=?',(sid,tid)).fetchone()
        if not exists: raise KeyError('Этап поставки не найден')
        c.execute('DELETE FROM tender_shipments WHERE id=? AND tender_id=?',(sid,tid))
        c.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                  (tid,'Удалён этап поставки: '+str(exists['name'] or 'Без названия'),now()))
    return detail(tid)


def calculate_deadline(t, *, today=None, holidays=None):
    """Unambiguous dates only. Working-day holiday lists are supplied explicitly."""
    today=today or date.today()
    due=t.get('due_on') or ''
    if due:
        d=date.fromisoformat(due)
    elif t.get('signed_on') and int(t.get('due_days') or 0)>0:
        start=date.fromisoformat(t['signed_on'])
        days=int(t['due_days'])
        if t.get('due_unit')=='work':
            # Prefer sourced federal 2026–2027 calendar; never silently infer
            # future years or assert legal deadlines based on weekend-only math.
            from modern.ru_work_calendar import add_workdays
            if holidays is None:
                try:
                    d=add_workdays(start,days)
                except ValueError:
                    day=start
                    remaining=days
                    while remaining:
                        day+=timedelta(days=1)
                        if day.weekday()<5: remaining-=1
                    d=day
                    approximate=True
                else:
                    approximate=False
            else:
                day=start
                remaining=days
                excluded=set(holidays)
                while remaining:
                    day+=timedelta(days=1)
                    if day.weekday()<5 and day.isoformat() not in excluded:remaining-=1
                d=day
                approximate=True
        else: d=start+timedelta(days=days)
    else: return {'due_on':None,'remaining':None,'label':'Срок не установлен','caution':None}
    delta=(d-today).days
    done=bool(t.get('is_delivered') or t.get('status')=='Контракт исполнен')
    label=('Поставка подтверждена' if done else f'Осталось {delta} дн.' if delta>=0 else f'Возможная просрочка: {-delta} дн.')
    warning=None
    if t.get('due_unit')=='work' and not t.get('due_on'):
        warning=('Дата ОРИЕНТИРОВОЧНАЯ: год за пределами проверенного календаря 2026–2027; '
                 'учтены только выходные. Проверьте праздничные дни и контракт.' if approximate
                 else 'Учтены федеральные выходные и переносы по данным производственного календаря 2026–2027. '
                      'Региональные праздники, особые графики и условия контракта проверьте отдельно.')
    return {'due_on':d.isoformat(),'remaining':delta,'label':label,'caution':warning}

def dashboard():
    rows=listing()
    return {'total':len(rows),'calculating':sum(t['status'] in ('Просчёт','Черновик','Подготовка заявки') for t in rows),
            'submitted':sum(t['status']=='Заявка подана' for t in rows),'won':sum(t['status'] in ('Выиграли','Ожидание подписания','Контракт подписан','Заказ оборудования','Производство','Комплектация','Готово к отправке','Отгружено','Доставлено','Приёмка','Контракт исполнен') for t in rows),
            'active':sum(t['status'] in ('Контракт подписан','Заказ оборудования','Производство','Комплектация','Готово к отправке','Отгружено','Доставлено','Приёмка') for t in rows),
            'at_risk':sum((calculate_deadline(t)['remaining'] or 0)<0 and not t['is_delivered'] for t in rows)}

initialize()


def backup_archive() -> bytes:
    """Consistent DB snapshot + referenced document files. Never modifies live data."""
    import tempfile
    import zipfile
    from io import BytesIO
    initialize()
    result=BytesIO()
    with tempfile.TemporaryDirectory(prefix='qx_backup_') as temp:
        db=Path(temp)/'tenders.sqlite3'
        with connection() as con, closing(sqlite3.connect(str(db))) as dest:
            con.backup(dest)
            dest.commit()
        # Read references from the same SQLite snapshot being archived, not
        # the live database (which may change between the two operations).
        with closing(sqlite3.connect(str(db))) as snapshot:
            rows = snapshot.execute('SELECT DISTINCT sha256, file_path FROM tender_documents').fetchall()
        from modern.attachment_integrity import checked_attachment
        with zipfile.ZipFile(result,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            archive.write(db,'tenders.sqlite3')
            for digest, raw_path in rows:
                path=Path(raw_path)
                # In-memory verified bytes prevent the backup itself from
                # silently preserving a corrupted/altered contract.
                content=checked_attachment(path,digest,DOCUMENTS)
                archive.writestr('documents/'+path.name,content)
            archive.writestr('manifest.json', json.dumps({
                'format':'QX-Tenders-Backup', 'version':1,'created':now(),
                'db_sha256':hashlib.sha256(db.read_bytes()).hexdigest()
            }, ensure_ascii=False))
            archive.writestr('README.txt','QX Подборщик — резервная копия тендеров и документов. Создано: '+now()+'\nВосстановление выполняется через раздел «Тендеры», с предварительной проверкой и созданием защитной копии.')
    return result.getvalue()
