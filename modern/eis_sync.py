"""One purchase-number action: verified facts, idempotent card, public attachments."""
from __future__ import annotations

from contextlib import contextmanager
from threading import Lock

from modern import tender_store as store
from modern.eis_public import fetch_notice_metadata, official_search_url, validate_notice
from modern.eis_metadata import fetch_notice_html_metadata
from modern.eis_discovery import discover_and_import
from modern.eis_document_download import build_official_opener, import_official_documents
from modern.procurement_sources import lookup_secondary, create_secondary_session

_locks_guard = Lock()
_locks = {}
FACT_FIELDS = ('title', 'customer', 'nmck', 'law', 'application_due_on', 'application_due_time',
               'auction_on', 'auction_time', 'results_on', 'results_time', 'supply_address',
               'payment_terms', 'warranty')


@contextmanager
def _notice_lock(number):
    with _locks_guard:
        entry = _locks.setdefault(number, [Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _locks_guard:
            entry[1] -= 1
            if not entry[1]:
                del _locks[number]


def _merge_empty_fields(tender_id, notice, source_url, source_name='ЕИС'):
    """Read + conditional fill in one SQLite transaction, preserving manual edits."""
    if not notice or not notice.get('verified'):
        return [], []
    candidates = {key:notice[key] for key in FACT_FIELDS if notice.get(key) not in ('', None)}
    validated = store._validate(candidates)
    applied, conflicts = [], []
    with store.transaction() as conn:
        current = conn.execute('SELECT * FROM tenders WHERE id=?', (tender_id,)).fetchone()
        if current is None:
            raise KeyError('Закупка не найдена')
        for field, value in validated.items():
            previous = current[field]
            if field.endswith('_time'):
                day_field = field[:-5] + '_on'
                if current[day_field] and current[day_field] != validated.get(day_field):
                    conflicts.append({'field':field, 'current':previous, 'received':value,
                                      'reason':'В карточке сохранена другая дата события'})
                    continue
            if previous in ('', None) or (field == 'nmck' and previous == 0):
                conn.execute(f'UPDATE tenders SET {field}=?, updated_at=? WHERE id=?',
                             (value, store.now(), tender_id))
                applied.append(field)
            elif str(previous) != str(value):
                conflicts.append({'field':field, 'current':previous, 'received':value})
        if applied:
            conn.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                         (tender_id, source_name[:150] + ': заполнены пустые поля ' + ', '.join(applied) +
                          '; источник: ' + source_url[:500], store.now()))
    return applied, conflicts


def _join_documents(first, second):
    if not first:
        return second
    if not second:
        return first
    result = dict(first)
    for key in ('imported', 'duplicates', 'warnings', 'failures', 'ignored', 'discovery_errors'):
        result[key] = list(first.get(key) or []) + list(second.get(key) or [])
    for key in ('found', 'checked_pages', 'success_count', 'failed_count'):
        result[key] = int(first.get(key) or 0) + int(second.get(key) or 0)
    result['limit_reached'] = bool(first.get('limit_reached') or second.get('limit_reached'))
    result['complete'] = bool(not result['failed_count'] and not result['ignored'] and not result['limit_reached'])
    result['documents'] = second.get('documents') or first.get('documents') or []
    return result


def sync_notice(number: str, *, download_documents=True, tender_id='', opener=None, progress=None) -> dict:
    """EIS first, independently retained results and explicit secondary provenance.

    The job API creates the local card first. This synchronous entry remains for
    existing callers; all external work belongs in a background worker.
    """
    number = validate_notice(number)
    if type(download_documents) is not bool:
        raise ValueError('Параметр загрузки документов должен быть Да/Нет')
    def report(stage, message, value):
        if progress:
            progress(stage, message, value)
    sources = []
    def source(name, result, document=False):
        sources.append({'name':name, 'url':result.get('source_url') or result.get('search_url') or '',
                        'status':'available' if result.get('available') or document and result.get('found') else 'unavailable',
                        'message':result.get('message') or '', 'error_type':result.get('error_type'),
                        'http_status':result.get('http_status')})
    with _notice_lock(number):
        if tender_id:
            item = store.get(tender_id)
            if not item:
                raise KeyError('Закупка не найдена')
            if item.get('number') != number:
                raise ValueError('Номер не совпадает с выбранной карточкой закупки')
        else:
            matches = [item for item in store.listing() if item.get('number') == number]
            if len(matches) > 1:
                raise ValueError('Есть несколько карточек этого номера. Откройте нужную карточку и повторите получение данных.')
            item = matches[0] if matches else store.create({'number':number})
            tender_id = item['id']
        # A single anonymous cookie session survives search -> card -> download.
        session = opener or build_official_opener()
        report('xml', 'Карточка сохранена. Проверяем извещение ЕИС.', 8)
        metadata = fetch_notice_metadata(number, opener=session)
        source('ЕИС: XML извещения', metadata)
        xml_links = metadata.get('documents') or []
        if not metadata.get('available') or not (metadata.get('notice') or {}).get('fields_fetched'):
            report('html', 'Проверяем публичную карточку ЕИС.', 20)
            metadata = fetch_notice_html_metadata(number, opener=session)
            source('ЕИС: публичная карточка', metadata)
        notice = metadata.get('notice') or {}
        if notice and notice.get('number') != number:
            raise ValueError('Получены данные другого извещения')
        fields_applied, conflicts = _merge_empty_fields(tender_id, notice, metadata.get('source_url') or '')
        primary_available = bool(metadata.get('available') and notice.get('verified') and notice.get('fields_fetched'))
        metadata_source = 'ЕИС' if primary_available else ''
        document_result = None
        if download_documents:
            if xml_links:
                report('download', 'Скачиваем вложения, перечисленные в XML ЕИС.', 35)
                urls = list(dict.fromkeys(row['url'] for row in xml_links))[:40]
                document_result = import_official_documents(tender_id, urls, opener=session, max_urls=40)
                document_result['found'] = len(urls)
            report('discover', 'Ищем документы на официальных страницах закупки.', 45)
            found_result = discover_and_import(tender_id, opener=session)
            source('ЕИС: документы', found_result, document=True)
            document_result = _join_documents(document_result, found_result)
        need_secondary = (not primary_available or any(not notice.get(key) for key in ('title','customer','nmck')) or
                          download_documents and (not document_result or not document_result.get('found') or document_result.get('failed_count')))
        secondary = None
        if need_secondary:
            report('fallback', 'Проверяем открытый дополнительный источник: Контур.Закупки.', 68)
            # This adapter owns a separate strictly scoped cookie session.
            secondary_session = create_secondary_session(number)
            secondary = lookup_secondary(number, opener=secondary_session.page)
            source(secondary.get('source_name') or 'Контур.Закупки (вторичный источник)', secondary)
            other = secondary.get('notice') or {}
            if other and other.get('number') != number:
                raise ValueError('Дополнительный источник вернул другую закупку')
            if secondary.get('available') and other.get('verified'):
                supplementary = {key:value for key,value in other.items() if key not in FACT_FIELDS or not notice.get(key)}
                applied, differences = _merge_empty_fields(tender_id, supplementary, secondary.get('source_url') or '',
                                                           secondary.get('source_name') or 'Вторичный источник')
                fields_applied.extend(applied)
                conflicts.extend(differences)
                if applied and primary_available:
                    metadata_source = 'ЕИС; дополнительные поля: ' + (secondary.get('source_name') or 'Контур.Закупки')
                if not primary_available and other.get('fields_fetched'):
                    metadata_source = secondary.get('source_name') or 'Контур.Закупки (вторичный источник)'
                notice = {**other, **{key:value for key,value in notice.items() if value not in ('',None,[])}}
            if download_documents and secondary.get('documents'):
                report('download', 'Скачиваем открытые документы дополнительного источника.', 82)
                from modern.procurement_sources import import_secondary_documents
                result = import_secondary_documents(tender_id, secondary['documents'], opener=secondary_session.documents)
                result['found'] = len(secondary['documents'])
                document_result = _join_documents(document_result, result)
        report('saving', 'Сохраняем полученные сведения и отчёт источников.', 96)
        metadata_available = bool(metadata_source)
        docs_complete = bool(document_result and document_result.get('found') and
                             not document_result.get('failed_count') and not document_result.get('ignored') and
                             not document_result.get('limit_reached'))
        partial = not metadata_available or bool(download_documents and not docs_complete)
        messages = []
        if metadata_available:
            messages.append('Источник сведений: ' + metadata_source + '.')
        else:
            messages.append('Карточка создана, но источники пока не предоставили проверяемые сведения.')
        messages.append('Заполнено пустых полей: ' + str(len(fields_applied)) + '.')
        if conflicts:
            messages.append('Существующие значения сохранены; расхождений: ' + str(len(conflicts)) + '.')
        if document_result is not None:
            messages.append('Новых документов: ' + str(len(document_result.get('imported') or [])) +
                            '; уже были: ' + str(len(document_result.get('duplicates') or [])) +
                            '; ошибок файлов: ' + str(document_result.get('failed_count') or 0) + '.')
            if not document_result.get('found'):
                messages.append('Открытые ссылки не найдены. Подробности доступа к каждому источнику — в отчёте.')
            if document_result.get('limit_reached'):
                messages.append('Достигнут лимит поиска или загрузки. Можно повторить запрос.')
            messages.append('Полнота комплекта документов ЕИС не подтверждена.')
        if metadata_source and metadata_source != 'ЕИС':
            messages.append('Сведения вторичного источника нужно сверить с извещением ЕИС.')
        return {'tender':store.detail(tender_id), 'notice':notice or None,
                'metadata_available':metadata_available, 'metadata_source':metadata_source,
                'source_url':metadata.get('source_url') if primary_available else (secondary or {}).get('source_url'),
                'search_url':official_search_url(number), 'fields_applied':list(dict.fromkeys(fields_applied)),
                'conflicts':conflicts, 'documents_result':document_result, 'sources':sources,
                'missing_fields':[key for key in FACT_FIELDS if not notice.get(key)],
                'metadata_error_type':metadata.get('error_type'), 'metadata_errors':metadata.get('errors', []),
                'partial':partial, 'message':' '.join(messages)}
