"""Regression tests for product-specific peripheral catalogs in QX Modern."""
from __future__ import annotations
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from modern.server import app
from core.tz_parser import Requirements
from core import storage

SAVED = {
 'keyboard':[{'name':'Клавиатура RQ-100','data':{'price':1290.0,'registry_number':'KB-121', 'wired':True,'usb':True}}],
 'mouse':[{'name':'Мышь RQ-200','data':{'price':870.0,'registry_number':'MS-222','wired':True,'usb':True}}],
 'monitor':[{'name':'Монитор RQ-240','data':{'price':12490.0,'registry_number':'MN-333','inches':23.8,'refresh_hz':75,'resolution':'1920x1080'}}],
 'equipment_profile':[{'name':'Бештау H610 материнская плата','data':{'manufacturer':'Бештау'}}],
}

class PeripheralUIAndLogicTests(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(app)
  self.prices=storage.load_prices()
  self.settings=storage.load_settings()

 def fake_catalog(self, kind):
  return SAVED.get(kind,[])

 def test_boot_provides_separate_catalogs(self):
  with patch('core.user_catalog.list_items',side_effect=self.fake_catalog):
   r=self.client.get('/api/boot')
   self.assertEqual(r.status_code,200,r.text)
   b=r.json()['catalogs']
   for kind in ('keyboard','mouse','monitor','equipment_profile'):
    self.assertEqual(b[kind],SAVED[kind])

 def test_explicit_keyboard_mouse_monitor_selection_in_calculation(self):
  cases=[('keyboard','Клавиатура RQ-100',1290.0,'Клавиатура'),('mouse','Мышь RQ-200',870.0,'Мышь'),('monitor','Монитор RQ-240',12490.0,'Монитор')]
  for kind,name,price,category in cases:
   with self.subTest(kind=kind):
    req=asdict(Requirements(product_type=kind,quantity=59,equipment_profile_name='Бештау H610 материнская плата'))
    if kind in ('keyboard','mouse'): req[f'{kind}_source_mode']='catalog'
    req[f'{kind}_catalog_item']=name
    with patch('core.user_catalog.list_items',side_effect=self.fake_catalog), patch('core.user_catalog.get_item',side_effect=AssertionError('Motherboard profile must never load for peripherals')):
     response=self.client.post('/api/select',json={'reqs':[req],'prices':self.prices,'settings':self.settings})
    self.assertEqual(response.status_code,200,response.text[:500])
    plan=response.json()['plans'][0]
    self.assertEqual(1,len(plan['rows']))
    self.assertEqual(plan['rows'][0]['category'],category)
    self.assertEqual(plan['rows'][0]['name'],name)
    self.assertEqual(plan['rows'][0]['price'],price)
    self.assertEqual(plan['registry']['registry_number'],SAVED[kind][0]['data']['registry_number'])

 def test_default_keyboard_mouse_remains_qx(self):
  for kind in ('keyboard','mouse'):
   req=asdict(Requirements(product_type=kind,quantity=4))
   with patch('core.user_catalog.list_items',side_effect=self.fake_catalog):
    response=self.client.post('/api/select',json={'reqs':[req],'prices':self.prices,'settings':self.settings})
   self.assertEqual(response.status_code,200)
   self.assertEqual(response.json()['plans'][0]['rows'][0]['source'],'QX')

 def test_changing_source_rebuilds_prices_not_old_locked_price(self):
  req=asdict(Requirements(product_type='keyboard',quantity=1))
  with patch('core.user_catalog.list_items',side_effect=self.fake_catalog):
   prev=self.client.post('/api/select',json={'reqs':[req],'prices':self.prices,'settings':self.settings}).json()['plans'][0]
   prev['rows'][0]['price']=99999;prev['rows'][0]['_locked']=True
   req['keyboard_source_mode']='catalog';req['keyboard_catalog_item']='Клавиатура RQ-100'
   resp=self.client.post('/api/select',json={'reqs':[req],'previous':[prev],'prices':self.prices,'settings':self.settings})
  self.assertEqual(resp.status_code,200,resp.text[:500])
  self.assertEqual(resp.json()['plans'][0]['rows'][0]['price'],1290)

 def test_ui_has_dedicated_catalog_picker_for_all_three_types(self):
  ui=(ROOT/'modern/web/app.js').read_text(encoding='utf-8')
  self.assertIn('Выбор клавиатуры',ui)
  self.assertIn('Выбор мыши',ui)
  self.assertIn('Выбор модели из базы мониторов',ui)
  self.assertIn('open-peripheral-catalog',ui)

if __name__=='__main__':unittest.main(verbosity=2)
