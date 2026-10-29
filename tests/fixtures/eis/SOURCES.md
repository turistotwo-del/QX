These are **layout regression fixtures, not live EIS captures**. Field values,
purchase numbers, document IDs and customer names are test data. No claim of
current EIS connectivity follows from passing these fixtures.

Layouts were cross-checked against public parser source on 2026-10-29:

- https://github.com/kaatarn-protecs/Kaykupki_scraper/blob/HEAD/zakupki_scraper.py
  (`extract_document_links`, RFC5987 header handling, search registry blocks).
- https://github.com/bigboiii300/Goszakupki_parser/blob/HEAD/main.py
  (`download_docs_epz`: `div.col.clipText`, the documents.html sibling tab;
  plain-span `Окончание подачи заявок`, standalone `div.price`).
- https://github.com/Homyakin/ZakupkiParser/blob/HEAD/src/test/resources/test_files/purchaseNotice_test.xml
  (223 XML shape: `purchaseNoticeData/registrationNumber`, `name`,
  `attachments/document/fileName/url`; historical HTTP URLs).

The optional data attributes and ID-bound search-link cases in tests are
compatibility/safety tests; they were not observed on live EIS.
