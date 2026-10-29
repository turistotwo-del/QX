"""Exercise the *running* packaged QX server using a temporary user database.

Unlike an import-only selfcheck, this verifies loopback routing, JSON, SQLite,
attachment storage, analysis and the bundled SPA over real HTTP. Safe to run in
CI on the installed exe. Never touches the user's QX data.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from urllib.request import Request, urlopen


def api_selfcheck() -> int:
    import uvicorn

    with tempfile.TemporaryDirectory(prefix='qx_frozen_api_') as tmp:
        # Import AFTER configuring the ephemeral directory: storage paths are
        # resolved at import time in the existing QX engine.
        os.environ['QX_DATA_DIR'] = tmp
        os.environ['QX_CATALOG_DIR'] = str(Path(tmp) / 'catalog')
        from modern.server import app
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        cfg = uvicorn.Config(app, host='127.0.0.1', port=port,
                             access_log=False, log_config=None, log_level='warning')
        server = uvicorn.Server(cfg)
        worker = threading.Thread(target=server.run, daemon=True, name='QXApiSelfcheck')
        worker.start()

        def call(method: str, path: str, payload=None, content_type='application/json', headers=None):
            raw = (json.dumps(payload, ensure_ascii=False).encode('utf-8')
                   if isinstance(payload, dict) else payload)
            h={'Content-Type':content_type}
            h.update(headers or {})
            req=Request(base+path, data=raw, headers=h, method=method)
            with urlopen(req, timeout=10) as response:
                body=response.read(2_000_000)
                return response.status, (json.loads(body) if response.headers.get_content_type() == 'application/json' else body)

        try:
            deadline=time.monotonic()+15
            while time.monotonic() < deadline:
                if not worker.is_alive(): raise RuntimeError('Встроенный сервер аварийно остановился')
                try:
                    status,result=call('GET','/api/health')
                    if status==200 and result.get('ok') is True: break
                except OSError:
                    time.sleep(.15)
            else: raise TimeoutError('Встроенный HTTP-сервер не ответил')

            status,boot=call('GET','/api/boot')
            assert status==200 and isinstance(boot.get('prices'),dict), 'Boot/prices endpoint'
            status,report=call('GET','/api/diagnostics')
            assert status==200 and report['version'].startswith('4.0.'), 'Packaged version mismatch'
            required={'Папка данных','База закупок','Файлы договоров','Свободное место','Локальный AI'}
            assert required <= {c['name'] for c in report['checks']}, 'Diagnostics incomplete'
            assert report['overall'] != 'error', 'Diagnostics reports installation errors'
            status,html=call('GET','/')
            assert status==200 and b'QX' in html, 'Bundled HTML frontend'
            status,js=call('GET','/app.js')
            assert status==200 and len(js)>1000, 'Bundled compiled frontend'
            status,created=call('POST','/api/tenders',{'title':'Проверка QX API','number':'0322100002526000466'})
            assert status==200, 'Creating tender failed'
            tender_id=created['tender']['id']
            status,loaded=call('GET',f'/api/tenders/{tender_id}')
            assert status==200 and loaded['tender']['title']=='Проверка QX API', 'Tender DB persistence'
            doc='В техническом задании требуется реестровый BIOS.'.encode('utf-8')
            status,saved=call('POST',f'/api/tenders/{tender_id}/documents',doc,
                              'application/octet-stream',{'x-file-name':'contract.txt'})
            assert status==200 and saved.get('document_id'), 'Attachment upload failed'
            status,audit=call('GET','/api/diagnostics/attachments')
            assert status==200 and audit['status']=='ok' and audit['valid']==1, 'SHA-256 document audit failed'
            # Test a real repair via the packaged HTTP server, with isolated
            # disposable data. No live contract or user profile is modified.
            status,snapshot=call('GET','/api/tenders/backup')
            assert status==200 and isinstance(snapshot,bytes), 'Tender backup failed'
            from modern import tender_store as store
            import hashlib
            stored=store.DOCUMENTS/(hashlib.sha256(doc).hexdigest()+'.txt')
            stored.write_bytes(b'damaged selfcheck fixture')
            status,preview=call('POST','/api/tenders/backup/repair-preview',snapshot,'application/zip')
            assert status==200 and preview['preview']['repairable']==1, 'Repair preview incomplete'
            status,repaired=call('POST','/api/tenders/backup/repair',snapshot,'application/zip',
                                 {'X-QX-Confirm-Repair':'REPAIR_DAMAGED_ATTACHMENTS_ONLY'})
            assert status==200 and repaired['repaired']==1, 'Repair operation failed'
            assert stored.read_bytes()==doc, 'Restored contract differs from original'
            status,analysis=call('POST',f'/api/tenders/{tender_id}/analyze',{})
            assert status==200 and 'Найдено требование' in analysis['analysis']['bios']['status'], 'BIOS extraction failed'
            status,all_tenders=call('GET','/api/tenders')
            assert status==200 and len(all_tenders['items'])==1, 'Tender listing failed'
            print('QX frozen HTTP selfcheck: OK (server, frontend, SQLite, file repair, BIOS, diagnostics)')
            return 0
        finally:
            server.should_exit=True
            worker.join(timeout=8)
            if worker.is_alive(): raise RuntimeError('HTTP-сервер не завершился после проверки')
