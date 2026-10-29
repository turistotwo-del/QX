from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence, Tuple


def write_bytes(path: str | Path, data: bytes) -> str:
    """Write bytes to the chosen path and return its absolute path."""
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(bytes(data))
    return str(p)


def _windows_save_dialog(
    default_filename: str,
    *,
    title: str,
    filetypes: Sequence[Tuple[str, str]],
    initial_dir: str | None,
) -> str | None:
    """Native Win32 Save As dialog. Safe to call from Streamlit's script thread."""
    import ctypes
    from ctypes import wintypes

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    filters = list(filetypes or [("Все файлы", "*.*")])
    if not any(mask == "*.*" for _, mask in filters):
        filters.append(("Все файлы", "*.*"))
    filter_text = "".join(f"{label}\0{mask}\0" for label, mask in filters) + "\0"

    filename_buffer = ctypes.create_unicode_buffer(32768)
    filename_buffer.value = str(default_filename)[:32760]
    suffix = Path(default_filename).suffix.lstrip(".")

    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = None
    ofn.hInstance = None
    ofn.lpstrFilter = filter_text
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(filename_buffer, wintypes.LPWSTR)
    ofn.nMaxFile = len(filename_buffer)
    ofn.lpstrInitialDir = str(initial_dir) if initial_dir else None
    ofn.lpstrTitle = title
    # OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
    ofn.Flags = 0x00000002 | 0x00000800 | 0x00000008
    ofn.lpstrDefExt = suffix or None

    result = ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn))
    if result:
        return filename_buffer.value
    err = ctypes.windll.comdlg32.CommDlgExtendedError()
    if err:
        raise RuntimeError(f"Windows Save As error: 0x{int(err):08X}")
    return None  # user cancelled



def _powershell_save_dialog(
    default_filename: str,
    *,
    title: str,
    filetypes: Sequence[Tuple[str, str]],
    initial_dir: str | None,
) -> str | None:
    """Open SaveFileDialog in a separate STA PowerShell process.

    This avoids calling the legacy common-dialog DLL from Streamlit's worker thread,
    which can crash on some Windows builds with an access-violation exception.
    """
    import subprocess

    filters = list(filetypes or [("Все файлы", "*.*")])
    if not any(mask == "*.*" for _, mask in filters):
        filters.append(("Все файлы", "*.*"))
    filter_text = "|".join(part for label, mask in filters for part in (str(label), str(mask)))
    suffix = Path(default_filename).suffix.lstrip(".")

    env = os.environ.copy()
    env["QX_SAVE_TITLE"] = str(title or "Сохранить файл")
    env["QX_SAVE_FILENAME"] = str(default_filename or "")
    env["QX_SAVE_FILTER"] = filter_text
    env["QX_SAVE_DIR"] = str(initial_dir or "")
    env["QX_SAVE_EXT"] = suffix
    script = r"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.SaveFileDialog
$d.Title = $env:QX_SAVE_TITLE
$d.FileName = $env:QX_SAVE_FILENAME
$d.Filter = $env:QX_SAVE_FILTER
if ($env:QX_SAVE_DIR) { $d.InitialDirectory = $env:QX_SAVE_DIR }
if ($env:QX_SAVE_EXT) { $d.DefaultExt = $env:QX_SAVE_EXT }
$d.AddExtension = $true
$d.OverwritePrompt = $true
$d.CheckPathExists = $true
if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $d.FileName
}
"""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, creationflags=creationflags, timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "PowerShell Save As error").strip())
    selected = (proc.stdout or "").strip().splitlines()
    return selected[-1].strip() if selected else None

def _tk_save_dialog(
    default_filename: str,
    *,
    title: str,
    filetypes: Sequence[Tuple[str, str]],
    initial_dir: str | None,
) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Нативное окно сохранения недоступно: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        selected = filedialog.asksaveasfilename(
            parent=root,
            title=title,
            initialdir=initial_dir or None,
            initialfile=default_filename,
            defaultextension=Path(default_filename).suffix,
            filetypes=list(filetypes or [("Все файлы", "*.*")]),
        )
    finally:
        root.destroy()
    return selected or None


def save_bytes_dialog(
    data: bytes,
    default_filename: str,
    *,
    title: str = "Сохранить файл",
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    initial_dir: str | None = None,
) -> str | None:
    """Show an OS Save As dialog and save bytes to the user-selected path."""
    types = tuple(filetypes or (("Все файлы", "*.*"),))
    if os.name == "nt":
        selected = _powershell_save_dialog(
            default_filename, title=title, filetypes=types, initial_dir=initial_dir
        )
    else:  # useful for development/testing on non-Windows machines
        selected = _tk_save_dialog(
            default_filename, title=title, filetypes=types, initial_dir=initial_dir
        )
    if not selected:
        return None
    return write_bytes(selected, data)
