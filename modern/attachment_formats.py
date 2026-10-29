"""Legacy tender originals are retained as bytes; never executed or converted."""
from pathlib import Path

RAW_EXTENSIONS = frozenset({'.doc', '.xls', '.rtf'})
RAW_WARNING = 'Оригинал сохранён; автоматический анализ этого формата недоступен. Проверьте документ вручную.'
OLE_SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def validate_raw_document(filename: str, data: bytes) -> None:
    """A signature identifies the container, not its internal Office subtype."""
    suffix = Path(filename).suffix.lower()
    if suffix not in RAW_EXTENSIONS:
        raise ValueError('Неизвестный формат оригинала')
    if suffix in ('.doc', '.xls'):
        if len(data) < 512 or not data.startswith(OLE_SIGNATURE):
            raise ValueError('Полученный файл не является контейнером Office DOC/XLS')
    elif len(data) < 7 or not data.lstrip().lower().startswith(b'{\\rtf'):
        raise ValueError('Полученный файл не является RTF')
