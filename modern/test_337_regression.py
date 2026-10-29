"""QX 3.3.7: historical price/project and minimum-resolution regressions.
Run with: python modern/test_337_regression.py
Synthetic fixtures only; never changes persistent QX_UserData.
"""
import base64
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from docx import Document
from fastapi.testclient import TestClient
from core.defaults import DEFAULT_QX_PRICES
from core.storage import normalize_prices
from core.tz_parser import Requirements
from modern.server import app


def fixture():
    doc=Document()
    table=doc.add_table(rows=1,cols=4)
    for cell,value in zip(table.rows[0].cells,['Наименование характеристики','Значение характеристики','Единица измерения характеристики','Инструкция по заполнению характеристик в заявке']):
        cell.text=value
    for label,value,unit in [
        ('Диагональ экрана','≥ 27','Дюйм (25,4 мм)'),
        ('Количество ядер процессора','≥ 6','Штука'),
        ('Количество потоков процессора','≥ 12','Штука'),
        ('Объем установленной оперативной памяти','≥ 16','Гигабайт'),
        ('Объем накопителя SSD','≥ 480','Гигабайт'),
        ('Разрешение экрана','≥1920 x 1080',''),
        ('Беспроводная связь','Wi-Fi',''),
        ('Тип оперативной памяти','DDR4',''),
        ('Интерфейс накопителя SSD','NVMe',''),
        ('Наличие в корпусе порта Gigabit Ethernet 8P8C (RJ-45)','Да',''),
    ]:
        cells=table.add_row().cells
        for cell,value in zip(cells,[label,value,unit,'Участник закупки указывает в заявке конкретное значение характеристики']):cell.text=value
    out=BytesIO();doc.save(out);return out.getvalue()


class Regression337(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.client=TestClient(app,raise_server_exceptions=False)

    def test_missing_adapter_price_keeps_custom_values(self):
        old={k: dict(v) for k,v in DEFAULT_QX_PRICES.items() if k!='m2_key_e_adapter'}
        old['motherboard_amd']['price']=7777.77
        fixed=normalize_prices(old)
        self.assertEqual(fixed['motherboard_amd']['price'],7777.77)
        self.assertEqual(fixed['m2_key_e_adapter']['price'],0.0)
        self.assertNotIn('m2_key_e_adapter',old)

    def test_actual_docx_shape_and_select_missing_key(self):
        body=fixture()
        response=self.client.post('/api/parse',content=body,headers={'X-File-Name':'test_AIO.docx'})
        self.assertEqual(response.status_code,200,response.text)
        req=response.json()['reqs'][0]
        self.assertEqual(req['product_type'],'aio27')
        self.assertTrue(req['monitor_resolution_is_min'])
        prices={k:dict(v) for k,v in DEFAULT_QX_PRICES.items() if k!='m2_key_e_adapter'}
        prices['motherboard_amd']['price']=6333
        response=self.client.post('/api/select',json={'reqs':[req], 'prices':prices})
        self.assertEqual(response.status_code,200,response.text)
        plan=response.json()['plans'][0]
        adapter=[r for r in plan['rows'] if r['category']=='Переходник M.2 Key E']
        self.assertEqual(len(adapter),1)
        self.assertEqual(adapter[0]['price'],0)
        board=[r for r in plan['rows'] if r['category']=='Материнская плата'][0]
        self.assertEqual(board['price'],6333)
        resolution=[x for x in plan['checks'] if x['Проверка']=='Разрешение моноблока']
        self.assertEqual(resolution[0]['Статус'],'OK')
        self.assertIn('2560x1440',resolution[0]['Факт QX'])
        self.assertNotIn('Разрешение моноблока',str(plan['warnings']))
        req['quantity']=2
        project=self.client.post('/api/project/save',json={'reqs':[req], 'plans':[plan], 'prices':prices,'source_docx_base64':base64.b64encode(body).decode('ascii')})
        self.assertEqual(project.status_code,200,project.text)
        reopened=self.client.post('/api/project/load',content=project.content)
        self.assertEqual(reopened.status_code,200,reopened.text)
        obj=reopened.json()
        self.assertIn('m2_key_e_adapter',obj['qx_prices'])
        self.assertEqual(obj['qx_prices']['motherboard_amd']['price'],6333)
        self.assertEqual(obj['reqs'][0]['quantity'],2)
        self.assertEqual(len(obj['plans'][0]['rows']),len(plan['rows']))

    def test_exact_resolution_is_not_minimum(self):
        req=asdict(Requirements(product_type='aio27',monitor_inches=27,monitor_resolution='1920x1080',monitor_resolution_is_min=False,platform='amd'))
        response=self.client.post('/api/select',json={'reqs':[req], 'prices':DEFAULT_QX_PRICES})
        self.assertEqual(response.status_code,200,response.text)
        found=[x for x in response.json()['plans'][0]['checks'] if x['Проверка']=='Разрешение моноблока']
        self.assertEqual(found[0]['Статус'],'НЕ ПРОХОДИТ')

    def test_legacy_document_minimum_without_flag(self):
        req=asdict(Requirements(product_type='aio27',monitor_inches=27,monitor_resolution='1920x1080',monitor_resolution_is_min=False,platform='amd',raw_text='Разрешение экрана | ≥1920 x 1080 | | конкретное'))
        response=self.client.post('/api/select',json={'reqs':[req], 'prices':DEFAULT_QX_PRICES})
        self.assertEqual(response.status_code,200,response.text)
        found=[x for x in response.json()['plans'][0]['checks'] if x['Проверка']=='Разрешение моноблока']
        self.assertEqual(found[0]['Статус'],'OK')


if __name__=='__main__': unittest.main(verbosity=2)
