"""No live network: deterministic tests of safe public EIS RSS handling."""
from __future__ import annotations
import io
import unittest
from modern.eis_public import parse_public_rss, lookup_notice, validate_notice, official_search_url

N='0322100002526000466'

RSS=(f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>ЕИС</title>
<item><title>Закупка № {N} — моноблоки</title><link>https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber={N}</link><description>Уведомление {N}</description></item>
<item><title>Посторонняя закупка № 0322100002526000467</title><link>https://zakupki.gov.ru/</link><description>Другое</description></item>
</channel></rss>''').encode('utf-8')

class Reply:
    def __init__(self,data):self.data=io.BytesIO(data)
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.data.read(n)

class Opener:
    def __init__(self,data):self.data=data
    def open(self,req,timeout):
        assert req.full_url.startswith('https://zakupki.gov.ru/')
        assert timeout <= 10
        return Reply(self.data)

class TestEisPublic(unittest.TestCase):
    def test_safe_search_url(self):
        self.assertEqual(official_search_url(N).split('searchString=')[1],N)
    def test_no_arbitrary_url_input(self):
        for bad in ('https://evil.com',N+'00','1'+N+'0','abc',''):
            with self.assertRaises(ValueError):validate_notice(bad)
    def test_exact_match(self):
        r=parse_public_rss(RSS,N)
        self.assertEqual(len(r),1)
        self.assertTrue(r[0]['link_verified'])
        self.assertIn(N,r[0]['url'])
    def test_third_party_urls_fallback(self):
        evil=RSS.replace(b'https://zakupki.gov.ru/',b'https://evil.test/')
        r=parse_public_rss(evil,N)
        self.assertFalse(r[0]['link_verified'])
        self.assertIn('zakupki.gov.ru',r[0]['url'])
    def test_official_host_but_wrong_notice_link_is_rejected(self):
        other=b'regNumber=0322100002526000467'
        r=parse_public_rss(RSS.replace(b'regNumber='+N.encode(),other),N)
        self.assertEqual(len(r),1)
        self.assertFalse(r[0]['link_verified'])
        self.assertIn('searchString='+N,r[0]['url'])

    def test_official_generic_homepage_is_not_direct_notice(self):
        r=parse_public_rss(RSS.replace(
            ('https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber='+N).encode(),
            b'https://zakupki.gov.ru/'),N)
        self.assertEqual(len(r),1)
        self.assertFalse(r[0]['link_verified'])

    def test_untrusted_doctype_is_rejected(self):
        with self.assertRaises(Exception):parse_public_rss(b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>',N)
    def test_lookup_success_is_not_contract_verification(self):
        r=lookup_notice(N,opener=Opener(RSS))
        self.assertTrue(r['available']);self.assertEqual(len(r['matches']),1)
        self.assertNotIn('status',r['matches'][0]);self.assertNotIn('contract_price',r['matches'][0])
    def test_unreachable_fallback(self):
        r=lookup_notice(N,opener=Opener(b'<html>bad</html>'))
        self.assertFalse(r['available']);self.assertEqual(r['matches'],[])
    def test_xml_entity_attack_is_handled(self):
        attack=b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>'
        r=lookup_notice(N,opener=Opener(attack))
        self.assertFalse(r['available'])
        self.assertEqual(r['matches'],[])
    def test_large_reply_rejected(self):
        r=lookup_notice(N,opener=Opener(b'x'* (2*1024*1024+1)))
        self.assertFalse(r['available']);self.assertEqual(r['matches'],[])

if __name__=='__main__':unittest.main()
