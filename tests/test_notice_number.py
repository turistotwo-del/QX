"""User-entered procurement numbers are canonical strings, never inferred IDs."""
import unittest

from modern.notice_number import normalize_notice

NUMBER = '0325100013726000029'
OTHER = '0322100002526000466'


class NoticeNumberInput(unittest.TestCase):
    def test_exact_numbers_keep_leading_zeroes(self):
        for number in (NUMBER, '00000000000000000001', '32612345678'):
            with self.subTest(number=number):
                self.assertEqual(normalize_notice(number), number)

    def test_common_pasted_prefixes_and_spacing(self):
        for value in (' ' + NUMBER + ' ', '№' + NUMBER, '# ' + NUMBER,
                      '№\u00a0' + NUMBER, '03251 00013726000029',
                      'Закупка № ' + NUMBER, 'Извещение: ' + NUMBER,
                      'Номер закупки: ' + NUMBER, 'НОМЕР ИЗВЕЩЕНИЯ № ' + NUMBER):
            with self.subTest(value=value):
                self.assertEqual(normalize_notice(value), NUMBER)

    def test_official_urls_extract_only_a_single_number(self):
        for host in ('zakupki.gov.ru', 'www.zakupki.gov.ru'):
            for key in ('regNumber', 'purchaseNumber', 'registrationNumber', 'searchString'):
                with self.subTest(host=host, key=key):
                    self.assertEqual(normalize_notice(f'https://{host}/epz/order/notice/ea20/view/common-info.html?{key}={NUMBER}'), NUMBER)
        self.assertEqual(normalize_notice('https://zakupki.kontur.ru/' + NUMBER), NUMBER)

    def test_invalid_and_ambiguous_input_is_rejected(self):
        values = (None, 325100013726000029, '', '12345', '1' * 18, '1' * 21,
                  NUMBER + '\n' + OTHER, 'Закупка ' + NUMBER + ' и ' + OTHER,
                  '０３２５１０００１３７２６００００２９',
                  'https://zakupki.gov.ru/notice?regNumber=' + NUMBER + '&regNumber=' + OTHER,
                  'https://zakupki.gov.ru/notice?regNumber=' + NUMBER + '&purchaseNumber=' + OTHER,
                  'https://zakupki.gov.ru/notice?regNumber=' + NUMBER + '00',
                  'https://zakupki.gov.ru/notice#regNumber=' + NUMBER,
                  'https://zakupki.gov.ru.evil.test/notice?regNumber=' + NUMBER,
                  'https://user:pass@zakupki.gov.ru/notice?regNumber=' + NUMBER,
                  'https://127.0.0.1/notice?regNumber=' + NUMBER,
                  'https://zakupki.gov.ru:8080/notice?regNumber=' + NUMBER,
                  'javascript:alert(' + NUMBER + ')', 'x' * 2049)
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_notice(value)


if __name__ == '__main__':
    unittest.main()
