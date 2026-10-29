"""Legacy tender originals are retained as bytes; never executed or converted."""
from pathlib import Path

RAW_EXTENSIONS = frozenset({'.doc', '.xls', '.rtf', '.rar', '.7z'})
RAW_WARNING = 'Оригинал сохранён; автоматический анализ этого формата недоступен. Проверьте документ вручную.'
OLE_SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
RAR_SIGNATURES = (b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')
SEVEN_Z_SIGNATURE = b'7z\xbc\xaf\x27\x1c'


def validate_raw_document(filename: str, data: bytes) -> None:
    """Check container headers, without parsing Office contents or archive entries.

    Original RAR/7z files are retained even when encrypted: no extraction,
    password guessing, decompression or archive-program invocation occurs.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in RAW_EXTENSIONS:
        raise ValueError('Неизвестный формат оригинала')
    if suffix in ('.doc', '.xls'):
        if len(data) < 512 or not data.startswith(OLE_SIGNATURE):
            raise ValueError('Полученный файл не является контейнером Office DOC/XLS')
    elif suffix == '.rar':
        if len(data) < 14 or not data.startswith(RAR_SIGNATURES):
            raise ValueError('Полученный файл не является архивом RAR')
    elif suffix == '.7z':
        if len(data) < 32 or not data.startswith(SEVEN_Z_SIGNATURE):
            raise ValueError('Полученный файл не является архивом 7z')
    elif len(data) < 7 or not data.lstrip().lower().startswith(b'{\\rtf'):
        raise ValueError('Полученный файл не является RTF')
