"""CI-only test fixture proving *installed* EXE preserves older QX tenders.

Never seed a nonempty real user database. The Windows job uses an isolated
runner account; this script also requires QX_CI_UPGRADE_FIXTURE=1.
"""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import argparse
import os
import sqlite3
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SAMPLE_ID='qx-ci-retained-tender'
SAMPLE_TITLE='CI: договор должен сохраниться при обновлении'
PROFILE_PRICE=7412.55


def directory():
    if os.environ.get('QX_CI_UPGRADE_FIXTURE') != '1':
        raise RuntimeError('Fixture is reserved for CI and cannot run without QX_CI_UPGRADE_FIXTURE=1')
    root = Path(os.environ.get('LOCALAPPDATA',''))
    if not str(root) or not root.is_dir():
        raise RuntimeError('LOCALAPPDATA is not available')
    return root / 'QXPodborshchik'


def seed():
    root = directory()
    root.mkdir(parents=True,exist_ok=True)
    db=root/'tenders.sqlite3'
    if db.exists():
        raise RuntimeError('CI fixture refuses to overwrite an existing tender database')
    with closing(sqlite3.connect(db)) as con:
        con.execute('CREATE TABLE schema_version(version INTEGER NOT NULL)')
        con.execute('INSERT INTO schema_version VALUES(1)')
        con.execute("""CREATE TABLE tenders (
            id TEXT PRIMARY KEY, number TEXT DEFAULT '', lot TEXT DEFAULT '',
            organization_id TEXT, title TEXT NOT NULL DEFAULT '',
            created_at TEXT, updated_at TEXT)""")
        con.execute('INSERT INTO tenders(id,title,created_at,updated_at) VALUES(?,?,?,?)',
                    (SAMPLE_ID,SAMPLE_TITLE,'2026-10-01','2026-10-01'))
        con.commit()
    from core.defaults import DEFAULT_QX_PRICES, DEFAULT_SETTINGS
    key=next(iter(DEFAULT_QX_PRICES))
    prices=json.loads(json.dumps(DEFAULT_QX_PRICES))
    prices[key]['price']=PROFILE_PRICE
    prices[key]['name']='CI пользовательская цена — не удалять'
    settings=json.loads(json.dumps(DEFAULT_SETTINGS))
    settings['sidebar_width']=370
    for name,data in (('qx_prices.json',prices),('settings.json',settings)):
        path=root/name
        if path.exists():raise RuntimeError('CI refuses to overwrite an existing user file: '+name)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    catalog=root.parent/'QX_Selector'/'user_catalog.sqlite3'
    if catalog.exists():raise RuntimeError('CI refuses to overwrite an existing equipment catalog')
    catalog.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(catalog)) as con:
        con.execute('CREATE TABLE catalog_items(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL COLLATE NOCASE, data_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(kind,name))')
        con.execute('INSERT INTO catalog_items(kind,name,data_json,created_at,updated_at) VALUES(?,?,?,?,?)',
                    ('case','CI Корпус, сохраняемый при обновлении','{"manufacturer":"QX Test"}', '2026-10-01','2026-10-01'))
        con.commit()
    print('CI old-schema fixture + user price/settings/catalog seeded')


def verify():
    root=directory()
    with closing(sqlite3.connect(root/'tenders.sqlite3')) as con:
        assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert con.execute('SELECT version FROM schema_version').fetchone()[0]==3
        assert con.execute('SELECT title FROM tenders WHERE id=?',(SAMPLE_ID,)).fetchone()[0]==SAMPLE_TITLE
    snapshots=list((root/'migration_snapshots').glob('QX_Before_Schema_v1_to_v3_*.sqlite3'))
    assert len(snapshots)==1, f'Expected one upgrade snapshot, got {len(snapshots)}'
    with closing(sqlite3.connect(snapshots[0])) as previous:
        assert previous.execute('SELECT version FROM schema_version').fetchone()[0]==1
        assert previous.execute('SELECT title FROM tenders WHERE id=?',(SAMPLE_ID,)).fetchone()[0]==SAMPLE_TITLE
    from core.defaults import DEFAULT_QX_PRICES
    key=next(iter(DEFAULT_QX_PRICES))
    prices=json.loads((root/'qx_prices.json').read_text(encoding='utf-8'))
    assert prices[key]['price']==PROFILE_PRICE
    assert prices[key]['name']=='CI пользовательская цена — не удалять'
    settings=json.loads((root/'settings.json').read_text(encoding='utf-8'))
    assert settings['sidebar_width']==370
    catalog=root.parent/'QX_Selector'/'user_catalog.sqlite3'
    with closing(sqlite3.connect(catalog)) as con:
        assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert con.execute('SELECT count(*) FROM catalog_items WHERE kind=? AND name=?',
                ('case','CI Корпус, сохраняемый при обновлении')).fetchone()[0]==1
    print('CI upgrade verified (tender, schema, snapshot, custom price, settings, catalog)')


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=('seed','verify'))
    args=p.parse_args()
    {'seed':seed,'verify':verify}[args.command]()
