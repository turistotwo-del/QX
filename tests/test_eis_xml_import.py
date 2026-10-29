"""Manual import of genuine source XML (not undocumented EIS API)."""
import unittest
from modern.tender_analysis import document_segments, analyze_documents

class OfficialXML(unittest.TestCase):
    def test_xml_preserves_data_and_evidence(self):
        data='''<?xml version="1.0" encoding="UTF-8"?>
        <notice xmlns="urn:eis:test"><purchaseNumber>0322100002526000466</purchaseNumber><description>Требуется реестровый BIOS</description><delivery>Поставка 20 календарных дней</delivery></notice>'''.encode()
        seg=document_segments('Извещение.xml',data)
        self.assertTrue(any('purchaseNumber' in x['location'] for x in seg))
        self.assertTrue(any('0322100002526000466' in x['text'] for x in seg))
        summary=analyze_documents([('Извещение.xml',data)])
        self.assertIn('Найдено требование',summary['bios']['status'])
        self.assertEqual(summary['bios']['evidence'][0]['file'],'Извещение.xml')
    def test_external_entities_rejected(self):
        evil=b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>'
        with self.assertRaises(Exception): document_segments('notice.xml',evil)

if __name__=='__main__':unittest.main()
