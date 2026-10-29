"""Faithful read-only preview of source document tables, independent of tender extraction."""
from __future__ import annotations
from io import BytesIO
from typing import Any
import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


def clean(s: Any) -> str:
    # Keep intentional linebreaks within Word cells, collapse other formatting noise.
    return re.sub(r"[ \t]+", " ", str(s or "").replace("\xa0", " ")).strip()


def split_text(text: str) -> dict:
    """Fallback for PDFs/TXT or old projects without original Word bytes."""
    all_tables, text_lines, buffer = [], [], []
    def flush():
        nonlocal buffer
        if buffer:
            headers = buffer[0] if len(buffer)>1 else ['Исходный текст']*len(buffer[0])
            rows = buffer[1:] if len(buffer)>1 else buffer
            all_tables.append({'title': f'Таблица {len(all_tables)+1}', 'headers': headers,
                               'rows': rows})
            buffer = []
    for line in text.splitlines():
        value=clean(line)
        if not value:
            flush();continue
        if ' | ' in value:
            parts=[clean(v) for v in re.split(r'\s*\|\s*', value)]
            if len(parts)>=2:
                if buffer and len(parts)!=len(buffer[0]): flush()
                buffer.append(parts);continue
        flush()
        text_lines.append(value)
    flush()
    if not all_tables and text_lines:
        all_tables = [{'title':'Текст документа', 'headers':['Содержание'],
                       'rows':[[v] for v in text_lines]}]
        text_lines=[]
    return {'tables':all_tables,'paragraphs':text_lines,'source':'text'}


def build_document_preview(filename: str, docx_bytes: bytes | None,
                           source_text: str='', characteristics: list|None=None) -> dict:
    if docx_bytes and filename.lower().endswith('.docx'):
        document = Document(BytesIO(docx_bytes))
        tables, paragraphs, recent_heading = [], [], ''
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                value = clean(Paragraph(child, document).text)
                if value:
                    paragraphs.append(value)
                    if len(value)<=140: recent_heading=value
            elif isinstance(child, CT_Tbl):
                t=Table(child, document)
                lines=[[clean(cell.text) for cell in row.cells] for row in t.rows]
                if not lines:continue
                count=max(len(row) for row in lines)
                lines=[row+['']*(count-len(row)) for row in lines]
                # Preserve actual Word cell values and order. The first Word row
                # is used as the visual header, not as a substituted field map.
                heading=(f'Таблица {len(tables)+1}' + (f' · {recent_heading[:100]}' if recent_heading else ''))
                tables.append({'title':heading,'headers':lines[0], 'rows':lines[1:]})
                recent_heading=''
        if tables:
            result={'tables':tables,'paragraphs':paragraphs,'source':'docx'}
        else:
            result=split_text(source_text or '\n'.join(paragraphs))
    elif characteristics:
        # Some older saves kept the extracted rows but not original DOCX bytes.
        result={'tables':[{'title':'Характеристики ТЗ',
                'headers':['Наименование характеристики','Значение характеристики',
                           'Единица измерения','Инструкция по заполнению'],
                'rows':[[clean(c.get('name')),clean(c.get('original_value')),
                         clean(c.get('unit')),clean(c.get('instruction'))]
                        for c in characteristics]}], 'paragraphs':[], 'source':'extracted'}
    else:
        result=split_text(source_text)
    result['filename']=filename
    result['table_count']=len(result['tables'])
    result['row_count']=sum(len(t['rows']) for t in result['tables'])
    return result
