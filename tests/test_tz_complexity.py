"""Meaningful difficulty categories, recognition limits and project persistence."""
from copy import deepcopy
from dataclasses import asdict
import unittest

from fastapi.testclient import TestClient
from core.tz_parser import Requirements, parse_tz
from modern.tz_complexity import assess_complexity
from modern.server import app

SIMPLE = 'Мышь проводная. Интерфейс подключения USB. Разрешение сенсора не менее 1200 dpi. Количество 10 шт.'
TECHNICAL = ('Системный блок\nКоличество: 10 шт.\nПроцессор: не менее 8 ядер\n'
             'Оперативная память: не менее 32 ГБ\nТип оперативной памяти: DDR5\nSSD: не менее 1024 ГБ\n'
             'USB 3.2 Gen 1: не менее 6\nUSB Type-C: не менее 2\nHDMI: не менее 2\nDisplayPort: не менее 2\n'
             'Высота корпуса: не более 200 мм\nШирина корпуса: не более 170 мм\nДлина корпуса: не более 400 мм\n'
             'Совместимость с существующей информационной системой.')
FORMAL = 'Требуется реестровый BIOS. Требуется сертификат ФСТЭК. Включение в реестр российской промышленной продукции.'
MEDIUM = TECHNICAL
COMPLEX = '\n'.join(f'Позиция {i+1}: Системный блок\n{TECHNICAL}' for i in range(4)) + '\n' + FORMAL


class ComplexityRules(unittest.TestCase):
    def assessment(self, source):
        reqs, text = parse_tz('ТЗ.txt', source.encode())
        return assess_complexity(text, reqs)

    def test_real_parser_reaches_three_distinct_levels_with_explanations(self):
        for source, level, label in [(SIMPLE, 'simple', 'Простое'), (MEDIUM, 'medium', 'Среднее'), (COMPLEX, 'complex', 'Сложное')]:
            with self.subTest(level=level):
                value = self.assessment(source)
                self.assertEqual(value['level'], level)
                self.assertEqual(value['label'], label)
                self.assertTrue(value['reasons'])
                self.assertIn('распознанным', value['disclaimer'])

    def test_formal_requirements_do_not_raise_technical_difficulty(self):
        first = self.assessment(SIMPLE)
        second = self.assessment(SIMPLE + '\n' + FORMAL)
        self.assertEqual(first['score'], second['score'])
        self.assertEqual(second['level'], 'simple')
        self.assertEqual(second['scope'], 'technical')
        keys = {item['key'] for item in second['additional_requirements']}
        self.assertTrue({'russian_registry', 'russian_bios', 'special_certification'} <= keys)
        self.assertFalse(keys & {item['key'] for item in second['factors']})

    def test_regulatory_table_rows_do_not_become_technical_constraints(self):
        reqs, source = parse_tz('simple.txt', SIMPLE.encode())
        ordinary = assess_complexity(source, reqs)
        formal_rows = [{'name':'Сертификат соответствия ФСТЭК', 'original_value':'Требуется'},
                       {'name':'Включение в российский реестр', 'original_value':'Обязательно'}] * 20
        updated = assess_complexity(source + '\n' + FORMAL, reqs, formal_rows)
        self.assertEqual(updated['score'], ordinary['score'])
        self.assertEqual(updated['metrics']['technical_constraints'], ordinary['metrics']['technical_constraints'])

    def test_minpromtorg_and_origin_certificates_are_separate_conditions(self):
        first = self.assessment(SIMPLE)
        result = self.assessment(SIMPLE + '\nТовар включён в реестр Минпромторга. Требуется сертификат СТ-1. Требуется сертификация ФСТЭК.')
        self.assertEqual(result['score'], first['score'])
        self.assertTrue({'russian_registry','origin_documents','special_certification'} <= {item['key'] for item in result['additional_requirements']})

    def test_no_meaningful_recognition_never_means_simple(self):
        for text, reqs in [('', []), ('Отсканированная страница', []), ('???', [Requirements()]), ('Договор поставки', [Requirements()])]:
            with self.subTest(text=text):
                self.assertEqual(assess_complexity(text, reqs)['level'], 'unknown')

    def test_quantity_and_plain_document_length_do_not_raise_difficulty(self):
        req = asdict(Requirements(ram_gb_min=16, quantity=1))
        first = assess_complexity('Оперативная память 16 ГБ.', [req])
        many = {**req, 'quantity':100000}
        second = assess_complexity('Оперативная память 16 ГБ.\n' + 'Общие сведения о поставке.\n' * 3000, [many])
        self.assertEqual(first['score'], second['score'])
        self.assertEqual(second['level'], 'simple')

    def test_repeated_regulatory_phrases_are_counted_once(self):
        req = Requirements(ram_gb_min=16, quantity=10)
        text = 'Требуется реестровый BIOS. ОС Astra Linux. Требуется сертификат ФСТЭК.'
        self.assertEqual(assess_complexity(text, [req])['score'], assess_complexity((text + '\n') * 30, [req])['score'])

    def test_negated_certificate_is_not_required(self):
        result = assess_complexity('Сертификат ФСТЭК не требуется. ОЗУ 16 ГБ.', [Requirements(ram_gb_min=16)])
        self.assertNotIn('special_certification', {factor['key'] for factor in result['factors']})

    def test_real_mutual_exclusion_requires_attention(self):
        result = assess_complexity('Требуется Wi-Fi; беспроводная связь запрещена.', [Requirements(need_wifi=True, forbid_wireless=True)])
        self.assertEqual(result['level'], 'complex')
        self.assertEqual(result['metrics']['contradictions'], 1)

    def test_two_minima_do_not_imply_a_contradiction(self):
        result = assess_complexity('ОЗУ не менее 64 ГБ. Поддерживаемый максимум не менее 32 ГБ.',
                                   [Requirements(ram_gb_min=64, ram_max_supported_gb_min=32, ram_modules_min=4, ram_slots_min=2)])
        self.assertEqual(result['metrics']['contradictions'], 0)

    def test_inputs_are_not_mutated_and_limits_are_explicit(self):
        rows = [asdict(Requirements(ram_gb_min=16))]
        before = deepcopy(rows)
        value = assess_complexity('Память 16 ГБ. ' * 160000, rows)
        self.assertEqual(rows, before)
        self.assertEqual(value['level'], 'unknown')
        self.assertTrue(value['metrics']['source_limited'])


class ComplexityAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def parse(self, text):
        result = self.client.post('/api/parse', content=text.encode(), headers={'X-File-Name':'test.txt'})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_upload_and_saved_project_preserve_each_document_assessment(self):
        documents, reqs = [], []
        for index, text in enumerate((SIMPLE, MEDIUM, COMPLEX)):
            parsed = self.parse(text)
            documents.append({'id':str(index), 'name':str(index)+'.txt', 'text':parsed['source_text'], 'complexity':parsed['complexity']})
            reqs.extend({**r, '_qx_doc_id':str(index)} for r in parsed['reqs'])
        saved = self.client.post('/api/project/save', json={'reqs':reqs, 'plans':[], 'tz_documents':documents})
        self.assertEqual(saved.status_code, 200)
        loaded = self.client.post('/api/project/load', content=saved.content)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual([d['complexity']['level'] for d in loaded.json()['tz_documents']], ['simple','medium','complex'])

    def test_older_project_gains_estimate_without_changing_requirements(self):
        parsed = self.parse(MEDIUM)
        reqs = [{**r, '_qx_doc_id':'source'} for r in parsed['reqs']]
        saved = self.client.post('/api/project/save', json={'reqs':reqs, 'plans':[], 'tz_documents':[{'id':'source','text':parsed['source_text'],'name':'old.txt'}]})
        loaded = self.client.post('/api/project/load', content=saved.content).json()
        self.assertEqual(loaded['reqs'], reqs)
        self.assertEqual(loaded['tz_documents'][0]['complexity']['level'], 'medium')

    def test_legacy_single_source_is_assessed_on_loading(self):
        parsed = self.parse(SIMPLE)
        saved = self.client.post('/api/project/save', json={'reqs':parsed['reqs'], 'plans':[], 'source_filename':'legacy.txt','source_text':parsed['source_text']})
        loaded = self.client.post('/api/project/load', content=saved.content).json()
        self.assertEqual(loaded['source_complexity']['level'], 'simple')

    def test_old_combined_assessment_is_replaced_with_technical_scope(self):
        parsed = self.parse(SIMPLE + '\n' + FORMAL)
        reqs = [{**r, '_qx_doc_id':'source'} for r in parsed['reqs']]
        old = {'id':'source', 'name':'old.txt', 'text':parsed['source_text'],
               'complexity':{'version':1, 'level':'complex', 'score':95}}
        saved = self.client.post('/api/project/save', json={'reqs':reqs,'plans':[],'tz_documents':[old]})
        loaded = self.client.post('/api/project/load', content=saved.content).json()
        assessment = loaded['tz_documents'][0]['complexity']
        self.assertEqual(assessment['scope'], 'technical')
        self.assertEqual(assessment['level'], 'simple')
        self.assertTrue(assessment['additional_requirements'])
