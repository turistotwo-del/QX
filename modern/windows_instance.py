"""Windows desktop instance guard shared with Inno Setup AppMutex.

A running QX must never be silently closed by a background update. The same
mutex prevents duplicate desktop windows and their reminder workers.
"""
from __future__ import annotations
from contextlib import contextmanager
import sys

MUTEX_NAME='BROKTECH.QXModern'
ERROR_ALREADY_EXISTS=183


def _create_windows_mutex():
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    create=kernel.CreateMutexW
    create.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
    create.restype=wintypes.HANDLE
    handle=create(None,False,MUTEX_NAME)
    if not handle:
        raise OSError(ctypes.get_last_error(), 'Не удалось создать защиту экземпляра QX')
    return kernel,handle,ctypes.get_last_error()==ERROR_ALREADY_EXISTS


def _close_windows_mutex(kernel,handle):
    import ctypes
    from ctypes import wintypes
    close=kernel.CloseHandle
    close.argtypes=[wintypes.HANDLE]
    close.restype=wintypes.BOOL
    close(handle)


@contextmanager
def desktop_instance():
    if sys.platform!='win32':
        yield True
        return
    kernel,handle,already_running=_create_windows_mutex()
    try:
        yield not already_running
    finally:
        _close_windows_mutex(kernel,handle)


def already_running_message():
    if sys.platform=='win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                'QX Подборщик уже запущен. Переключитесь в открытое окно программы.',
                'QX Подборщик',0x40)
        except (OSError,AttributeError):
            pass
