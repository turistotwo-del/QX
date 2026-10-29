"""Windows app launcher for the QX Modern local TypeScript interface."""
from __future__ import annotations
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
_ICON_HANDLES: list[object] = []


def _apply_windows_window_icon(icon_path: Path) -> None:
    """Apply the custom QX icon to the native WebView window and taskbar."""
    if os.name != 'nt' or not icon_path.exists():
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        pid = kernel32.GetCurrentProcessId()

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        load_image = user32.LoadImageW
        load_image.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        load_image.restype = wintypes.HANDLE

        hicon_big = load_image(None, str(icon_path), IMAGE_ICON, 64, 64, LR_LOADFROMFILE)
        hicon_small = load_image(None, str(icon_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = load_image(None, str(icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not hicon_small:
            hicon_small = hicon_big

        if hicon_big:
            _ICON_HANDLES.append(hicon_big)
        if hicon_small and hicon_small != hicon_big:
            _ICON_HANDLES.append(hicon_small)

        # SetWindowLongPtr must not receive an untyped 64-bit handle on x64.
        # WM_SETICON is sufficient for the running window and taskbar button.
        # Use pointer-sized types on Win64: C long is only 32 bits on Windows.
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        ctypes.c_size_t, ctypes.c_ssize_t]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_ssize_t)
        user32.EnumWindows.argtypes = [enum_proc_type, ctypes.c_ssize_t]
        user32.EnumWindows.restype = wintypes.BOOL

        def _enum_proc(hwnd, _lparam):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value != pid or not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if 'QX Подборщик' not in title.value:
                return True
            if hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, int(hicon_big))
            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, int(hicon_small))
            return True

        for _ in range(8):
            cb = enum_proc_type(_enum_proc)
            user32.EnumWindows(cb, 0)
            time.sleep(0.15)
    except Exception:
        return


def _start_loopback_server(app, *, timeout: float = 10.0):
    """Start the local API without a bind/close/rebind port race.

    Uvicorn receives the *same listening socket* that reserved the ephemeral
    port. An unrelated process cannot steal the port between allocation and
    startup. A failed HTTP health check must also stop the server and release
    its socket, including when Uvicorn exits before accepting connections.
    """
    import uvicorn

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(('127.0.0.1', 0))
        listener.listen(2048)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            app, host='127.0.0.1', port=port, log_level='warning',
            access_log=False, log_config=None))
        # uvicorn Server.run explicitly supports pre-bound sockets.
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]},
                                  name='QXLocalHTTP', daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{port}/'
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not thread.is_alive():
                raise RuntimeError('Локальный сервер QX завершился до запуска')
            try:
                with urllib.request.urlopen(url + 'api/health', timeout=0.25) as response:
                    if response.status == 200:
                        return server, thread, listener, url
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        raise RuntimeError('Локальный сервер QX не ответил за отведённое время')
    except BaseException:
        if 'server' in locals():
            server.should_exit = True
        if 'thread' in locals() and thread.is_alive():
            thread.join(timeout=2)
        listener.close()
        raise


def _show_windows_qx(url: str) -> None:
    """Keep QX in its own WebView2 window, not an Edge --app browser.

    A browser subprocess is not owned by the application's event loop: Edge
    can forward or terminate a subprocess while QX's server remains tied to
    that subprocess's lifetime. That caused ERR_CONNECTION_REFUSED when QX
    closed its server before the forwarded Edge window was gone.
    """
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            'Не установлен компонент окна QX (pywebview). '
            'Закройте программу и заново запустите ЗАПУСТИТЬ_QX.cmd '
            'с доступом к интернету. Обычный Edge больше не используется.'
        ) from exc

    icon_path = ROOT / 'assets' / 'qx_icon.ico'
    if not icon_path.is_file():
        raise RuntimeError('Отсутствует оригинальная иконка QX: assets/qx_icon.ico')

    window = webview.create_window(
        'QX Подборщик — Modern', url,
        width=1450, height=920, min_size=(1050, 680),
        background_color='#0b1423',
        js_api=__import__('modern.native_bridge', fromlist=['QXNativeBridge']).QXNativeBridge(),
        text_select=True,
    )
    # pywebview emits 'shown' on the GUI thread. Win32 HWND enumeration and
    # icon setting must not block that GUI thread during its first repaint.
    def on_shown():
        threading.Thread(target=_apply_windows_window_icon, args=(icon_path,),
                         name='QXWindowIcon', daemon=True).start()

    window.events.shown += on_shown
    try:
        webview.start(gui='edgechromium', debug=False)
    except Exception as exc:
        raise RuntimeError(
            'Не удалось открыть фирменное окно QX через Microsoft Edge WebView2. '
            'Проверьте установленный WebView2 Runtime. '            + f'Причина: {type(exc).__name__}: {exc}'
        ) from exc


def launch():
    from modern.server import app
    from modern.ollama_boot import start_ollama, stop_ollama
    from modern.lite_boot import start_lite, stop_lite, ENGINE as LITE_ENGINE, MODEL as LITE_FILE

    if sys.platform == 'win32':
        try:
            import ctypes
            # The same stable application identity as the Windows installer.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BROKTECH.QXModern')
        except (OSError, AttributeError):
            pass

    owned_lite_process = start_lite()
    owned_ai_process = start_ollama() if not (LITE_ENGINE.is_file() and LITE_FILE.is_file()) else None
    try:
        server, thread, listener, url = _start_loopback_server(app)
    except BaseException:
        stop_ollama(owned_ai_process)
        stop_lite(owned_lite_process)
        raise

    reminder_stop = threading.Event()
    reminder_thread = None
    if sys.platform == 'win32':
        def _reminder_watch():
            from modern.reminders import dispatch
            while not reminder_stop.is_set():
                dispatch(icon_path=ROOT / 'assets' / 'qx_icon.png')
                if reminder_stop.wait(60):
                    break

        reminder_thread = threading.Thread(target=_reminder_watch,
                                           name='QXReminders', daemon=True)
        reminder_thread.start()
    try:
        if sys.platform == 'win32':
            _show_windows_qx(url)
        else:
            opened = webbrowser.open(url)
            if not opened:
                raise RuntimeError('Не удалось открыть интерфейс QX в браузере.')
            print('QX Modern:', url)
            try:
                input('Нажмите Enter, чтобы остановить сервер QX...')
            except EOFError:
                thread.join()
    finally:
        stop_lite(owned_lite_process)
        stop_ollama(owned_ai_process)
        reminder_stop.set()
        if reminder_thread is not None:
            reminder_thread.join(timeout=1)
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


if __name__ == '__main__':
    try:
        launch()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            from datetime import datetime
            from modern import tender_store
            tender_store.APP_DATA.mkdir(parents=True, exist_ok=True)
            diagnostic = tender_store.APP_DATA / 'QX_MODERN_ERROR.log'
            with diagnostic.open('a', encoding='utf-8') as logfile:
                logfile.write('\n--- ' + datetime.now().isoformat() + ' ---\n')
                logfile.write(traceback.format_exc())
        except Exception:
            pass
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, str(exc), 'QX Modern — ошибка запуска', 0x10)
            except Exception:
                pass
        sys.exit(1)
