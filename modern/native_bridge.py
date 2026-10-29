"""Native Windows file dialogs for QX Modern's embedded WebView2.

The portable embedded Python has no tkinter/_tkinter. Native dialogs are
opened using Windows PowerShell 5.1 / WinForms on a separate STA process; no
Python GUI toolkit is required. A disabled dialog has a browser fallback.
"""
from __future__ import annotations

import base64
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / 'QX_MODERN_ERROR.log'


# The portable Python 3.12 embeddable package intentionally has no _tkinter.
# Use the standard Windows PowerShell/.NET file picker in its own STA process.
# Never import tkinter from the modern interface.
_WINDOWS_FILE_DIALOG_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$d = if ($env:QX_DIALOG_MODE -eq 'save') {
    New-Object System.Windows.Forms.SaveFileDialog
} else {
    New-Object System.Windows.Forms.OpenFileDialog
}
$d.Title = $env:QX_DIALOG_TITLE
$d.Filter = $env:QX_DIALOG_FILTER
$d.CheckPathExists = $true
if ($env:QX_DIALOG_MODE -eq 'save') {
    $d.FileName = $env:QX_DIALOG_FILENAME
    $d.DefaultExt = $env:QX_DIALOG_EXT
    $d.AddExtension = $true
    $d.OverwritePrompt = $true
} else {
    $d.Multiselect = $false
    $d.CheckFileExists = $true
}
# The QX desktop window is always above the hidden PowerShell console.
# Give the dialog a topmost owner so that it opens visibly in front of QX.
$owner = New-Object System.Windows.Forms.Form
$owner.ShowInTaskbar = $false
$owner.TopMost = $true
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
$owner.Location = New-Object System.Drawing.Point(-32000, -32000)
try {
    if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        # ASCII transport prevents Windows PowerShell 5.1 codepage corruption
        # for Russian, Unicode and emoji characters in user-selected paths.
        $raw = [System.Text.Encoding]::UTF8.GetBytes($d.FileName)
        [Console]::WriteLine('QX_SELECTED:' + [Convert]::ToBase64String($raw))
    } else {
        [Console]::WriteLine('QX_CANCELLED')
    }
} finally {
    $d.Dispose()
    $owner.Dispose()
}
"""


def _windows_dialog_process(*, save: bool, title: str,
                            filetypes: list[tuple[str, str]], filename: str = '') -> str:
    import os
    import subprocess

    # Windows Forms uses semicolon-delimited patterns; tkinter used spaces.
    filters = []
    for label, patterns in filetypes:
        masks = ';'.join(part for part in str(patterns).replace(';', ' ').split()
                         if part.startswith('*') and '|' not in part)
        if masks:
            filters.extend((str(label).replace('|', ' '), masks))
    if not filters:
        filters = ['Все файлы', '*.*']
    env = os.environ.copy()
    env.update({
        'QX_DIALOG_MODE': 'save' if save else 'open',
        'QX_DIALOG_TITLE': str(title),
        'QX_DIALOG_FILTER': '|'.join(filters),
        'QX_DIALOG_FILENAME': filename if save else '',
        'QX_DIALOG_EXT': Path(filename).suffix.lstrip('.'),
    })
    args = ['powershell.exe', '-NoLogo', '-NoProfile', '-STA', '-Command',
            _WINDOWS_FILE_DIALOG_PS]
    try:
        proc = subprocess.run(args, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=300,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f'Windows file dialog unavailable: {exc}') from exc
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).decode('utf-8', errors='replace')[-1500:]
        raise RuntimeError('Windows file dialog failed: ' + detail.strip())
    for line in proc.stdout.decode('ascii', errors='replace').splitlines():
        if line.startswith('QX_SELECTED:'):
            encoded = line.partition(':')[2].strip()
            try:
                return base64.b64decode(encoded, validate=True).decode('utf-8')
            except (ValueError, UnicodeDecodeError) as exc:
                raise RuntimeError('Windows file dialog returned invalid path') from exc
        if line == 'QX_CANCELLED':
            return ''
    raise RuntimeError('Windows file dialog returned no selection status')


def file_dialog(*, save: bool, title: str, filetypes: list[tuple[str, str]],
                filename: str = '') -> str:
    if sys.platform != 'win32':
        raise RuntimeError('Нативный диалог QX доступен только в Windows')
    return _windows_dialog_process(save=save, title=title,
                                   filetypes=filetypes, filename=filename)


class QXNativeBridge:
    OPEN_TYPES = {
        'tz': (('Технические задания', '*.docx *.pdf *.xlsx *.xlsm *.odt *.txt *.csv *.md'), ('Все файлы', '*.*')),
        'project': (('Проекты QX', '*.qxproj *.json'), ('Все файлы', '*.*')),
        'tender_project': (('Проект расчёта QX', '*.qxproj'),),
        'catalog': (('Базы оборудования QX', '*.qxdb'), ('Все файлы', '*.*')),
        'supplier': (('Прайс-листы Excel', '*.xlsx'), ('Все файлы', '*.*')),
        'legacy': (('Архив старого QX', '*.zip'), ('Все файлы', '*.*')),
        'tender_backup': (('Резервная копия QX', '*.zip'), ('Все файлы', '*.*')),
        'tender_repair': (('Резервная копия для восстановления документов', '*.zip'), ('Все файлы', '*.*')),
        'tender_package': (('Пакет документов закупки ZIP', '*.zip'), ('Все файлы', '*.*')),
        'tender': (('Документы закупки', '*.docx *.pdf *.xlsx *.xlsm *.txt *.csv *.md *.xml *.doc *.xls *.rtf'), ('Все файлы', '*.*')),
    }
    ALLOWED_EXTS = {
        'tz': {'.docx', '.pdf', '.xlsx', '.xlsm', '.odt', '.txt', '.csv', '.md'},
        'project': {'.qxproj', '.json'},
        'tender_project': {'.qxproj'},
        'catalog': {'.qxdb'},
        'supplier': {'.xlsx'},
        'legacy': {'.zip'},
        'tender_backup': {'.zip'},
        'tender_repair': {'.zip'},
        'tender_package': {'.zip'},
        'tender': {'.docx','.pdf','.xlsx','.xlsm','.txt','.md','.csv','.xml','.doc','.xls','.rtf'},
    }

    def choose_file(self, kind: str) -> dict:
        if kind not in self.OPEN_TYPES:
            raise ValueError('Неизвестный тип файла')
        name = file_dialog(save=False, title='QX Подборщик — открыть файл',
                           filetypes=list(self.OPEN_TYPES[kind]))
        if not name:
            return {'cancelled': True}
        path = Path(name)
        if path.suffix.lower() not in self.ALLOWED_EXTS[kind]:
            raise ValueError(f'Неверный формат: {path.suffix}. Выберите подходящий файл.')
        raw = path.read_bytes()
        if len(raw) > (150 if kind in ('tender_backup', 'tender_repair') else 50) * 1024 * 1024:
            raise ValueError('Размер файла превышает установленный лимит')
        return {'cancelled': False, 'name': path.name, 'base64': base64.b64encode(raw).decode('ascii')}

    def save_file(self, filename: str, payload: str) -> dict:
        filename = Path(filename.replace('\\', '/')).name or 'QX_документ.bin'
        ext = Path(filename).suffix.lower()
        if ext not in {'.docx', '.xlsx', '.qxproj', '.qxdb', '.zip'}:
            raise ValueError('Недопустимый тип экспортируемого файла')
        raw = base64.b64decode(payload, validate=True)
        if len(raw) > 60 * 1024 * 1024:
            raise ValueError('Размер экспортируемого файла превышает 60 МБ')
        try:
            name = file_dialog(save=True, title='QX Подборщик — сохранить файл',
                               filetypes=[('Файл ' + ext.upper(), '*' + ext), ('Все файлы', '*.*')],
                               filename=filename)
        except RuntimeError as exc:
            # A disabled PowerShell policy must not make project/export saving
            # entirely unusable. Let WebView2 attempt a regular download.
            return {'browser_fallback': True, 'message': str(exc)}
        if not name:
            return {'cancelled': True}
        final = Path(name)
        if final.suffix.lower() != ext:
            final = final.with_suffix(ext)
        # Atomic write avoids corrupting a previous saved project if the write fails.
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(dir=final.parent, prefix='.qx_', suffix='.tmp', delete=False) as tmp:
            temp = Path(tmp.name)
            try:
                tmp.write(raw)
                tmp.flush()
                os.fsync(tmp.fileno())
            except Exception:
                temp.unlink(missing_ok=True)
                raise
        try:
            temp.replace(final)
        finally:
            temp.unlink(missing_ok=True)
        return {'cancelled': False, 'name': str(final)}

    def open_ai_models(self) -> dict:
        """Open only QX's dedicated local AI directory, never an arbitrary path."""
        from modern.local_ai import gguf_model_dir
        path = gguf_model_dir()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            import os
            os.startfile(str(path))
            return {'ok': True, 'path': str(path)}
        return {'ok': False, 'path': str(path),
                'message': 'Откройте эту папку в файловом менеджере.'}

    def open_external(self, url: str) -> dict:
        from urllib.parse import urlparse
        import webbrowser
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('zakupki.gov.ru','www.zakupki.gov.ru'):
            raise ValueError('Разрешено открывать только официальный сайт ЕИС')
        return {'ok':webbrowser.open(url)}

    def open_classic(self) -> dict:
        if sys.platform != 'win32':
            return {'ok': False, 'error': 'Классический интерфейс доступен только в Windows'}
        if getattr(sys,'frozen',False):
            subprocess.Popen([sys.executable, '--classic'], cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
            return {'ok':True}
        bat = ROOT / 'START_QX.bat'
        if not bat.is_file():
            return {'ok': False, 'error': 'Не найден START_QX.bat'}
        subprocess.Popen(['cmd.exe', '/c', str(bat)], cwd=str(ROOT), creationflags=subprocess.CREATE_NEW_CONSOLE)
        return {'ok': True}
