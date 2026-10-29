import unittest
from modern.tender_analysis import document_segments, analyze_documents

class XmlEvidencePaths(unittest.TestCase):
    def test_repeated_elements_have_different_paths(self):
        xml='''<notice xmlns="urn:eis:test"><lots>
          <lot><sum>100000</sum><bios>BIOS без реестровых требований</bios></lot>
          <lot><sum>150000</sum><bios>Реестровый BIOS обязателен</bios></lot>
          </lots></notice>'''.encode()
        rows=document_segments('Извещение.xml',xml)
        paths={x['text']:x['location'] for x in rows}
        self.assertEqual(paths['sum: 100000'], 'XML: /notice[1]/lots[1]/lot[1]/sum[1]')
        self.assertEqual(paths['sum: 150000'], 'XML: /notice[1]/lots[1]/lot[2]/sum[1]')
        self.assertNotEqual(paths['sum: 100000'],paths['sum: 150000'])
        self.assertTrue(any('/lot[2]/' in x['location'] for x in rows))

    def test_corrupted_document_forces_manual_check(self):
        result=analyze_documents([('ТЗ.txt','BIOS должен быть в реестре российского ПО'.encode('utf-8')),('проект.pdf',b'not a PDF')])
        self.assertEqual(len(result['errors']),1)
        self.assertIn('Требуется уточнение',result['bios']['status'])
        self.assertEqual(result['files_analyzed'],1)
        self.assertTrue(result['bios']['evidence'])

if __name__ == '__main__':unittest.main()
