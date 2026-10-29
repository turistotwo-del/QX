"""Windows application entry point (PyInstaller onedir distribution)."""
from pathlib import Path
import os
import sys
import tempfile
import traceback
from datetime import datetime


def _load_eis_dependencies() -> None:
    """Import provider dependencies without requesting data or starting models."""
    import importlib
    for module in ('requests', 'bs4', 'defusedxml', 'modern.eis_sync', 'modern.eis_jobs'):
        importlib.import_module(module)


def eis_dependency_selfcheck() -> int:
    # tender_store initializes on import; never use a real profile for this probe.
    names = ('QX_DATA_DIR', 'QX_CATALOG_DIR', 'QX_PORTABLE_DATA_DIR')
    previous = {name: os.environ.get(name) for name in names}
    try:
        with tempfile.TemporaryDirectory(prefix='qx_eis_dependencies_') as home:
            for name in names:
                os.environ[name] = str(Path(home) / name.lower())
            _load_eis_dependencies()
        print('QX EIS dependencies: OK')
        return 0
    except Exception as exc:
        print('QX EIS dependencies: FAILED:', type(exc).__name__,
              'Required EIS libraries are missing or incompatible; repair the private runtime.', file=sys.stderr)
        return 1
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def selfcheck() -> int:
    """Non-GUI smoke test of the real frozen app; used by Windows CI."""
    try:
        with tempfile.TemporaryDirectory(prefix='qx_selfcheck_') as home:
            os.environ['QX_DATA_DIR'] = home
            os.environ['QX_CATALOG_DIR'] = str(Path(home) / 'catalog')
            os.environ['QX_PORTABLE_DATA_DIR'] = str(Path(home) / 'portable')
            _load_eis_dependencies()
            from modern import tender_store
            from modern.server import STATIC, boot, health
            if not (Path(STATIC) / 'index.html').is_file():
                raise RuntimeError('Статические файлы интерфейса не упакованы')
            if not (Path(STATIC) / 'app.js').is_file():
                raise RuntimeError('JavaScript интерфейса отсутствует')
            if not (Path(STATIC).parents[1] / 'assets' / 'qx_icon.ico').is_file():
                raise RuntimeError('Не найдена иконка приложения')
            tender_store.initialize()
            if health()['ok'] is not True:
                raise RuntimeError('Локальный сервер не готов')
            config = boot()
            if 'prices' not in config or 'catalogs' not in config:
                raise RuntimeError('Расчётный движок не инициализирован')
            print('QX selfcheck: OK')
            return 0
    except Exception as exc:
        print('QX selfcheck: FAILED:', type(exc).__name__, str(exc), file=sys.stderr)
        return 1


def _desktop_error_log(exc: BaseException) -> Path | None:
    """Log a failed desktop start *outside the installation directory*.

    No automatic upload. A log may contain local file paths, so it remains
    on the user's machine and should only be shared deliberately.
    """
    try:
        from modern import tender_store
        folder = tender_store.APP_DATA / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        logfile = folder / 'QX_Startup_Error.log'
        # Bounded traceback: logs should not grow without limit on repeated failures.
        if logfile.exists() and logfile.stat().st_size > 1024 * 1024:
            logfile.replace(folder / 'QX_Startup_Error.previous.log')
        with logfile.open('a', encoding='utf-8') as stream:
            stream.write('\n--- ' + datetime.now().astimezone().isoformat(timespec='seconds') + ' ---\n')
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=stream)
        return logfile
    except (OSError, RuntimeError):
        # Logging must never hide the original launch error.
        return None


def run_desktop() -> int:
    """One checked GUI entrypoint, including the PyInstaller --windowed build."""
    try:
        from modern.start import launch
        from modern.windows_instance import desktop_instance, already_running_message
        with desktop_instance() as first:
            if not first:
                already_running_message()
                return 0
            launch()
        return 0
    except Exception as exc:
        log = _desktop_error_log(exc)
        message = ('Не удалось запустить QX Подборщик.\n\n'
                   + f'{type(exc).__name__}: {str(exc)[:350]}\n\n'
                   + ('Подробности сохранены:\n' + str(log) if log else
                      'Не удалось записать диагностический журнал.'))
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message,
                                                 'QX Подборщик — ошибка запуска', 0x10)
            except (OSError, AttributeError, RuntimeError):
                pass
        print(message, file=sys.stderr)
        return 1


def main():
    if '--version' in sys.argv:
        from modern.release_info import RELEASE_LABEL
        print('QX Подборщик ' + RELEASE_LABEL)
        return 0
    if '--eis-selfcheck' in sys.argv:
        return eis_dependency_selfcheck()
    if '--selfcheck' in sys.argv:
        return selfcheck()
    if '--data-selfcheck' in sys.argv:
        # CI/update diagnostics on the *configured* user profile rather than a
        # throwaway DB. A safe migration snapshot is made before any DDL.
        try:
            from modern import tender_store as store
            store.initialize()
            with store.connection() as con:
                if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise RuntimeError('SQLite quick_check failed')
                version=store._read_schema_version(con)
                if version != store.SCHEMA_VERSION:
                    raise RuntimeError('Unexpected user database schema version')
            print('QX user data selfcheck: OK')
            return 0
        except Exception as exc:
            print('QX user data selfcheck: FAILED:',type(exc).__name__,str(exc),file=sys.stderr)
            return 1
    if '--profile-selfcheck' in sys.argv:
        # Check the actual legacy profile used by the installed QX.  This is
        # deliberately separate from --selfcheck's disposable test profile.
        try:
            from core import storage, user_catalog
            prices=storage.load_prices()
            settings=storage.load_settings()
            cases=user_catalog.list_items('case')
            if not prices or not isinstance(settings,dict) or not isinstance(cases,list):
                raise RuntimeError('Invalid QX legacy user profile')
            print('QX user profile selfcheck: OK')
            return 0
        except Exception as exc:
            print('QX user profile selfcheck: FAILED:',type(exc).__name__,str(exc),file=sys.stderr)
            return 1
    if '--api-selfcheck' in sys.argv:
        from modern.frozen_http_check import api_selfcheck
        return api_selfcheck()
    if '--ai-selfcheck' in sys.argv:
        # Checks the native inference DLLs in the packaged EXE.  No model is
        # downloaded, opened or inferred at install time.
        try:
            from llama_cpp import Llama
            if not callable(Llama): raise ImportError('Llama runtime unavailable')
            print('QX GGUF runtime selfcheck: OK')
            return 0
        except (ImportError, OSError, RuntimeError) as exc:
            print('QX GGUF runtime selfcheck: FAILED:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if '--classic' in sys.argv:
        from streamlit.web.cli import main as streamlit_main
        base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
        sys.argv=['streamlit','run',str(base/'app.py'),'--server.headless=false',
                  '--browser.gatherUsageStats=false','--server.fileWatcherType=none']
        streamlit_main()
        return 0
    return run_desktop()


if __name__ == '__main__':
    sys.exit(main())
