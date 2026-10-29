"""QX Tender workspace tests. Run with: python -m unittest discover -s tests -v."""
import os
import tempfile
from pathlib import Path
import unittest
from datetime import date
from io import BytesIO
from docx import Document

# Isolated DB, never test against the actual user's tenders.
TEST_ROOT=tempfile.TemporaryDirectory(prefix='qx_tenders_test_')
os.environ['QX_DATA_DIR']=TEST_ROOT.name

from modern import tender_store as t
from modern.tender_analysis import document_segments, analyze_documents
from fastapi.testclient import TestClient
from modern.server import app


def docx(*paragraphs):
    d=Document()
    for p in paragraphs: d.add_paragraph(p)
    o=BytesIO();d.save(o);return o.getvalue()

class TenderSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_db=(t.APP_DATA,t.DB_FILE,t.DOCUMENTS,t._INITIALIZED)
        t.APP_DATA=Path(TEST_ROOT.name)
        t.DB_FILE=t.APP_DATA/'tenders.sqlite3'
        t.DOCUMENTS=t.APP_DATA/'tender_documents'
        t._INITIALIZED=False
        t.initialize()
        cls.client=TestClient(app)

    @classmethod
    def tearDownClass(cls):
        t.APP_DATA,t.DB_FILE,t.DOCUMENTS,t._INITIALIZED=cls._old_db
        TEST_ROOT.cleanup()

    def test_01_sqlite_persistence(self):
        row=t.create({'title':'Тест 1','number':'0322100002526000466'})
        self.assertTrue(t.DB_FILE.is_file())
        self.assertEqual(t.get(row['id'])['title'],'Тест 1')

    def test_02_deduplicate(self):
        a=t.create({'title':'первый','number':'0322100002526000466'})
        b=t.create({'title':'второй','number':'0322100002526000466'})
        self.assertEqual(a['id'],b['id'])

    def test_03_organizations(self):
        o=t.add_org('ООО Тест','1234567890')
        row=t.create({'title':'орг','number':'0444444444444444444','organization_id':o})
        self.assertEqual(t.get(row['id'])['organization_id'],o)
        t.update(row['id'],{'organization_id':''})
        self.assertIsNone(t.get(row['id'])['organization_id'])

    def test_04_manual_status(self):
        row=t.create({'title':'Ожидаем'})
        t.update(row['id'],{'status':'Выиграли'})
        self.assertEqual(t.get(row['id'])['status'],'Выиграли')
        with self.assertRaises(ValueError): t.update(row['id'],{'status':'Контракт подписан'},manual=False)

    def test_05_deadline_calendar(self):
        x={'signed_on':'2026-10-01','due_on':'','due_days':30,'due_unit':'calendar'}
        self.assertEqual(t.calculate_deadline(x,today=date(2026,10,21))['remaining'],10)

    def test_06_deadline_work_warning(self):
        x={'signed_on':'2026-10-16','due_on':'','due_days':1,'due_unit':'work'}
        y=t.calculate_deadline(x,today=date(2026,10,16))
        self.assertEqual(y['due_on'],'2026-10-19')
        self.assertIn('производственного календаря',y['caution'])

    def test_07_no_deadline(self):
        self.assertEqual(t.calculate_deadline({})['label'],'Срок не установлен')

    def test_08_duplicate_project_key(self):
        a=t.link_project('uuid-1','расчёт 1','0000000000000000001.docx','',[],3000)
        b=t.link_project('uuid-1','расчёт 1','0000000000000000001.docx','',[],4000)
        self.assertEqual(a['tender_id'],b['tender_id'])
        self.assertEqual(b['purchase_cost'],4000)

    def test_09_project_number_dedup(self):
        a=t.link_project('uuid-2','ТЗ 1','0333333333333333333.docx','',[],100)
        b=t.link_project('uuid-3','ТЗ 2','0333333333333333333.docx','',[],200)
        self.assertEqual(a['tender_id'],b['tender_id'])
        self.assertEqual(b['purchase_cost'],300)

    def test_10_comments(self):
        x=t.create({'title':'заметки'})
        t.add_comment(x['id'],'Проверить реестровый BIOS')
        self.assertIn('реестровый BIOS',t.detail(x['id'])['comments'][0]['body'])

    def test_11_attachments(self):
        x=t.create({'title':'Документы'})
        b=docx('Требуется российский BIOS, включённый в реестр ПО.')
        id1=t.add_document(x['id'],'\u041a\u043e\u043d\u0442\u0440\u0430\u043a\u0442.docx',b)
        id2=t.add_document(x['id'],'\u041a\u043e\u043d\u0442\u0440\u0430\u043a\u0442.docx',b)
        self.assertEqual(id1,id2)
        _,d=t.document_bytes(x['id'],id1)
        self.assertEqual(b,d)

    def test_12_local_bios(self):
        output=analyze_documents([('Контракт.docx',docx('Наличие отечественного BIOS с реестровой записью обязательно.','Срок поставки составляет 20 календарных дней.'))])
        self.assertIn('Найдено требование',output['bios']['status'])
        self.assertEqual(len(output['summary']),6)
        self.assertEqual(output['bios']['evidence'][0]['location'],'абзац 1')

    def test_13_bios_absent(self):
        output=analyze_documents([('ТЗ.docx',docx('Монитор 27 дюймов, 1920x1080.'))])
        self.assertIn('не обнаружено',output['bios']['status'].lower())

    def test_14_non_registry_bios(self):
        output=analyze_documents([('ТЗ.docx',docx('UEFI BIOS с поддержкой загрузки с USB.'))])
        self.assertIn('упоминается',output['bios']['status'])

    def test_15_unsupported_doc(self):
        x=t.create({'title':'док'})
        with self.assertRaises(ValueError):t.add_document(x['id'],'bad.exe',b'fake')

    def test_16_attachment_safe_name(self):
        x=t.create({'title':'док2'})
        did=t.add_document(x['id'],'../a/../hello.txt',b'safe text')
        self.assertEqual(t.detail(x['id'])['documents'][0]['filename'],'hello.txt')

    def test_17_backup(self):
        data=t.backup_archive()
        self.assertGreater(len(data),200)
        import zipfile
        with zipfile.ZipFile(BytesIO(data)) as z:
            self.assertIn('tenders.sqlite3',z.namelist())
            self.assertTrue(any(x.startswith('documents/') for x in z.namelist()))

    def test_18_api_dashboard(self):
        r=self.client.get('/api/tenders')
        self.assertEqual(r.status_code,200)
        self.assertGreater(r.json()['summary']['total'],0)

    def test_19_api_eis_link_unverified(self):
        x=t.create({'title':'ЕИС','number':'0123456789012345678'})
        r=self.client.get('/api/tenders/'+x['id']+'/eis')
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['verified'])
        self.assertIn('zakupki.gov.ru',r.json()['url'])

    def test_20_api_analysis(self):
        x=t.create({'title':'Анализ'})
        b=docx('Оплата в течение 7 рабочих дней после приёмки.','Реестровый BIOS обязателен.')
        r=self.client.post('/api/tenders/'+x['id']+'/documents',content=b,headers={'X-File-Name':'contract.docx'})
        self.assertEqual(r.status_code,200)
        r=self.client.post('/api/tenders/'+x['id']+'/analyze',json={})
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['analysis']['bios']['evidence'])

    def test_21_not_fake_ai(self):
        x=t.create({'title':'Локальный AI'})
        r=self.client.post('/api/tenders/'+x['id']+'/local-ai',json={'question':'Поставка?'})
        self.assertEqual(r.status_code,422)

    def test_22_old_project_saved(self):
        r=self.client.post('/api/project/save',json={'reqs':[{'title':'ТИП 1'}], 'plans':[],'tender_project_key':'test-project-key'})
        self.assertEqual(r.status_code,200)
        obj=self.client.post('/api/project/load',content=r.content).json()
        self.assertEqual(obj['project_meta']['tender_project_key'],'test-project-key')

    def test_23_missing_source(self):
        output=analyze_documents([])
        self.assertIn('не обнаружено',output['bios']['status'].lower())

    def test_24_invalid_dates(self):
        row=t.create({'title':'ошибочная дата'})
        with self.assertRaises(ValueError):t.update(row['id'],{'due_on':'2026-13-55'})

    def test_26_edit_organization_with_existing_tender(self):
        oid=t.add_org('ООО Пример','1234567890')
        tender=t.create({'title':'Связь с организацией','organization_id':oid})
        updated=t.update_org(oid,name='ООО Пример Новый',inn='123456789012')
        self.assertEqual(updated['name'],'ООО Пример Новый')
        self.assertEqual(t.get(tender['id'])['organization_id'],oid)
        with self.assertRaises(ValueError):t.update_org(oid,name='')
        self.assertEqual(t.update_org(oid)['inn'],'123456789012')

    def test_27_api_org_patch(self):
        oid=t.add_org('ООО API','')
        response=self.client.patch('/api/tenders/organizations/'+oid,json={'name':'ООО API новое','inn':'0987654321'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['organization']['name'],'ООО API новое')
        self.assertEqual(self.client.patch('/api/tenders/organizations/'+oid,json={'name':''}).status_code,400)

    def test_25_record_history(self):
        row=t.create({'title':'История'})
        t.update(row['id'],{'status':'Заявка подана'})
        self.assertTrue(any('status' in x['label'] for x in t.detail(row['id'])['events']))

if __name__=='__main__':unittest.main(verbosity=2)
