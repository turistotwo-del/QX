"""QX 4.0.33: native file-save/open regressions (portable Python has no Tk)."""
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from modern import native_bridge as bridge


class NativeDialogs4033(TestCase):
    def test_native_windows_dialog_without_tkinter_with_unicode_name(self):
        dest = 'C:\\QX\\Сохранение\\Заявка № 3.qxproj'
        encoded = base64.b64encode(dest.encode('utf-8'))
        fake = SimpleNamespace(returncode=0, stdout=b'QX_SELECTED:' + encoded + b'\r\n', stderr=b'')
        with patch.object(bridge.subprocess if hasattr(bridge, 'subprocess') else __import__('subprocess'), 'run', return_value=fake) as run:
            result = bridge._windows_dialog_process(save=True, title='Сохранить', filetypes=[('Проекты QX', '*.qxproj')], filename='Тест.qxproj')
        self.assertEqual(dest, result)
        self.assertIn('-STA', run.call_args.args[0])
        self.assertEqual('save', run.call_args.kwargs['env']['QX_DIALOG_MODE'])
        self.assertEqual('*.qxproj', run.call_args.kwargs['env']['QX_DIALOG_FILTER'].split('|')[1])

    def test_file_picker_combined_masks_are_powershell_compatible(self):
        fake = SimpleNamespace(returncode=0, stdout=b'QX_CANCELLED\r\n', stderr=b'')
        with patch('subprocess.run', return_value=fake) as run:
            result = bridge._windows_dialog_process(save=False, title='Открыть', filetypes=[('ТЗ','*.docx *.pdf *.xlsx'), ('Все файлы','*.*')])
        self.assertEqual('', result)
        self.assertEqual('*.docx;*.pdf;*.xlsx', run.call_args.kwargs['env']['QX_DIALOG_FILTER'].split('|')[1])
        self.assertEqual('open', run.call_args.kwargs['env']['QX_DIALOG_MODE'])

    def test_rejected_process_status_does_not_silently_count_as_cancel(self):
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=1, stdout=b'', stderr=b'PowerShell blocked')):
            with self.assertRaisesRegex(RuntimeError, 'PowerShell blocked'):
                bridge._windows_dialog_process(save=True, title='Save', filetypes=[('All', '*.*')])

    def test_missing_powershell_returns_browser_fallback_for_save(self):
        with patch.object(bridge, 'file_dialog', side_effect=RuntimeError('powershell missing')):
            result = bridge.QXNativeBridge().save_file('QX_Project.qxproj', base64.b64encode(b'valid project').decode())
        self.assertTrue(result['browser_fallback'])

    def test_cancel_creates_no_file(self):
        with patch.object(bridge, 'file_dialog', return_value=''):
            result = bridge.QXNativeBridge().save_file('QX_Project.qxproj', base64.b64encode(b'data').decode())
        self.assertEqual({'cancelled': True}, result)

    def test_project_and_all_export_types_saved_without_tkinter(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ('.qxproj', '.xlsx', '.docx', '.qxdb', '.zip'):
                path = Path(tmp) / ('QX_Тест' + suffix)
                data = b'QX-test' + suffix.encode()
                with self.subTest(suffix=suffix), patch.object(bridge, 'file_dialog', return_value=str(path)):
                    result = bridge.QXNativeBridge().save_file(path.name, base64.b64encode(data).decode())
                    self.assertFalse(result['cancelled'])
                    self.assertEqual(data, path.read_bytes())

    def test_invalid_base64_never_opens_save_dialog(self):
        with patch.object(bridge, 'file_dialog') as selector:
            with self.assertRaises(ValueError):
                bridge.QXNativeBridge().save_file('QX_Project.qxproj', 'not base64')
            selector.assert_not_called()

    def test_open_document_uses_native_dialog_and_returns_content(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ТЗ.docx'
            p.write_bytes(b'office document')
            with patch.object(bridge, 'file_dialog', return_value=str(p)):
                result=bridge.QXNativeBridge().choose_file('tz')
            self.assertEqual('ТЗ.docx', result['name'])
            self.assertEqual(b'office document', base64.b64decode(result['base64']))

    def test_save_is_atomic_on_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.xlsx'
            p.write_bytes(b'old version')
            with patch.object(bridge, 'file_dialog', return_value=str(p)):
                result=bridge.QXNativeBridge().save_file('report.xlsx', base64.b64encode(b'new version').decode())
            self.assertEqual(b'new version', p.read_bytes())
            self.assertFalse(list(Path(tmp).glob('.qx_*.tmp')))
