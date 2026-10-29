"""Explicit opt-in, integrity-checked local GGUF installer for QX AI.

The model is never downloaded automatically at startup. All network traffic is
restricted to a user-initiated HTTPS download from an immutable upstream
revision and its file-delivery hosts. Documents are never uploaded.

The publisher's Q4_K_M file is ~1.12 GB: loading it or running inference is
*not* evidence the model has been evaluated for legal/technical correctness.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import re
import shutil
import threading
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from modern.local_ai import gguf_model_dir, gguf_runtime_available

MODEL_REPO = 'Qwen/Qwen2.5-1.5B-Instruct-GGUF'
MODEL_NAME = 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
MODEL_REVISION = '91cad51170dc346986eccefdc2dd33a9da36ead9'
MODEL_URL = f'https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{MODEL_NAME}'
MODEL_SHA256 = '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
MODEL_BYTES = 1_117_320_736
_CHUNK = 1024 * 1024
_LOCK = threading.Lock()
_CANCEL = threading.Event()
_STATE = {'state': 'idle', 'downloaded': 0, 'error': '', 'verified': False}
# Full SHA verification runs in a worker after a restart, never inside a GET.


def _approved_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        return (host == 'huggingface.co' or host.endswith('.huggingface.co') or
                host.endswith('.xethub.hf.co') or host.endswith('.hf.co') or
                host.endswith('.cloudfront.net'))
    except ValueError:
        return False


class _RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _approved_url(newurl):
            raise ValueError('Источник модели перенаправил загрузку на недоверенный адрес')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_model_source(request: Request):
    # Kept separate for isolated unit tests; no model data needs to be fetched
    # during application build or test execution.
    if not _approved_url(request.full_url):
        raise ValueError('Недоверенный источник GGUF')
    return build_opener(_RestrictedRedirect()).open(request, timeout=40)


def _safe_files() -> tuple[Path, Path]:
    directory = gguf_model_dir()
    if directory.is_symlink():
        raise ValueError('Папка моделей является ссылкой; загрузка запрещена')
    directory.mkdir(parents=True, exist_ok=True)
    model = directory / MODEL_NAME
    partial = directory / (MODEL_NAME + '.part')
    if any(p.is_symlink() for p in (model, partial)):
        raise ValueError('Файл модели является символической ссылкой; загрузка запрещена')
    if model.exists() and not model.is_file() or partial.exists() and not partial.is_file():
        raise ValueError('Неподходящий объект в папке моделей')
    return model, partial


def _update(**values):
    with _LOCK:
        _STATE.update(values)


def _status():
    with _LOCK:
        result = dict(_STATE)
    result.update({
        'name': MODEL_NAME,
        'model_id': 'gguf:' + MODEL_NAME,
        'title': 'Qwen2.5 1.5B Instruct · Q4_K_M',
        'bytes_total': MODEL_BYTES,
        'sha256': MODEL_SHA256,
        'license': 'Apache-2.0',
        'source_url': f'https://huggingface.co/{MODEL_REPO}/blob/{MODEL_REVISION}/{MODEL_NAME}',
        'runtime_ready': gguf_runtime_available(),
        'note': 'Один раз скачивается из Hugging Face (~1,12 ГБ); затем работает локально. Ответы требуют проверки.'
    })
    # File presence is not verification. 'verified' is set only by comparing
    # SHA-256 after download, never inferred from a GGUF header or file size.
    try:
        model = gguf_model_dir() / MODEL_NAME
        result['file_present'] = bool(model.is_file() and not model.is_symlink())
    except OSError:
        result['file_present'] = False
    return result


def _verify_existing_worker():
    """Check a model found at app startup without making any network requests."""
    try:
        model, _ = _safe_files()
        digest, length = _hash_existing(model)
        if length != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
            raise ValueError('Файл установленной модели повреждён или изменён: проверка SHA-256 не пройдена')
        _update(state='installed', downloaded=MODEL_BYTES, verified=True, error='')
    except (OSError, ValueError) as exc:
        _update(state='failed', verified=False, error=str(exc)[:300])


def model_install_status() -> dict:
    # This function is polled by the UI once a second. Reading and hashing a
    # 1.12 GB model here would stall the desktop HTTP server. Verify once in
    # a separate worker after process restart, and only on explicit status GET.
    with _LOCK:
        checking = _STATE['state'] == 'idle'
        if checking:
            try:
                model, _ = _safe_files()
                if model.is_file():
                    _STATE.update(state='verifying', downloaded=0, error='', verified=False)
                else:
                    checking = False
            except (OSError, ValueError):
                checking = False
        else:
            checking = False
    if checking:
        threading.Thread(target=_verify_existing_worker, name='QXModelVerifyOnStartup', daemon=True).start()
    return _status()


def _hash_existing(path: Path):
    h = sha256()
    size = 0
    with path.open('rb') as file:
        for data in iter(lambda: file.read(_CHUNK), b''):
            h.update(data)
            size += len(data)
            if size > MODEL_BYTES:
                raise ValueError('Частичный файл превышает ожидаемый размер')
    return h, size


def _download_worker():
    try:
        model, partial = _safe_files()
        if model.exists():
            digest, length = _hash_existing(model)
            if length == MODEL_BYTES and digest.hexdigest() == MODEL_SHA256:
                _update(state='installed', downloaded=MODEL_BYTES, verified=True)
                return
            raise ValueError('Файл модели уже существует, но контрольная сумма неверна. Переместите файл вручную.')
        existing = partial.stat().st_size if partial.exists() else 0
        if existing > MODEL_BYTES:
            raise ValueError('Неверный размер частичной загрузки')
        needed = MODEL_BYTES - existing
        free = shutil.disk_usage(str(partial.parent)).free
        if free < needed + 100 * 1024 * 1024:
            raise OSError('Недостаточно свободного места для модели (нужен дополнительный запас 100 МБ)')

        # Hash partial data before resuming; otherwise final SHA cannot verify
        # the whole model. Never assume a file is trusted just because it has
        # the expected extension and prefix.
        digest, existing = _hash_existing(partial) if existing else (sha256(), 0)
        if existing == MODEL_BYTES:
            if digest.hexdigest() != MODEL_SHA256:
                raise ValueError('Частично загруженный файл имеет неверную SHA-256')
        else:
            headers = {'User-Agent': 'QXPodborshchik/4.0 (opt-in GGUF installer)'}
            if existing:
                headers['Range'] = f'bytes={existing}-'
            response = _open_model_source(Request(MODEL_URL, headers=headers))
            try:
                final_url = response.geturl()
                if not _approved_url(final_url):
                    raise ValueError('Модель получена с неподтверждённого сервера')
                status = response.status
                content_range = response.headers.get('Content-Range', '')
                range_match = re.fullmatch(r'bytes\s+(\d+)-(\d+)/(\d+)', content_range)
                append = bool(existing > 0 and status == 206 and range_match and
                              int(range_match.group(1)) == existing and
                              int(range_match.group(2)) == MODEL_BYTES - 1 and
                              int(range_match.group(3)) == MODEL_BYTES)
                if existing and not append:
                    # Origin may ignore Range: restart cleanly instead of
                    # silently appending duplicate bytes.
                    if status != 200:
                        raise ValueError('Сервер модели не поддержал продолжение загрузки')
                    existing = 0
                    digest = sha256()
                if status not in (200, 206) or (not existing and status == 206):
                    raise ValueError(f'Неожиданный HTTP-ответ сервера модели: {status}')
                _update(downloaded=existing)
                with partial.open('ab' if existing else 'wb') as file:
                    while True:
                        if _CANCEL.is_set():
                            _update(state='cancelled', verified=False)
                            return
                        block = response.read(_CHUNK)
                        if not block:
                            break
                        existing += len(block)
                        if existing > MODEL_BYTES:
                            raise ValueError('Размер загрузки превышает размер официальной модели')
                        file.write(block)
                        digest.update(block)
                        _update(downloaded=existing)
                    file.flush()
                    os.fsync(file.fileno())
            finally:
                response.close()
        if _CANCEL.is_set():
            _update(state='cancelled', verified=False)
            return
        if existing != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
            # The partial file is deliberately kept for retry only when it is
            # incomplete. A full but invalid file must be removed.
            if existing == MODEL_BYTES:
                partial.unlink(missing_ok=True)
            raise ValueError('Контрольная сумма или размер модели не совпадают с опубликованными')
        os.replace(partial, model)
        _update(state='installed', downloaded=MODEL_BYTES, verified=True)
    except (OSError, ValueError, RuntimeError) as exc:
        _update(state='failed', error=str(exc)[:300], verified=False)


def start_model_install() -> dict:
    if not gguf_runtime_available():
        raise ValueError('GGUF-движок недоступен: необходим Windows-дистрибутив с llama-cpp-python')
    # Exactly one operation per desktop process; no automatic/background starts.
    with _LOCK:
        already_running = _STATE['state'] in ('downloading', 'verifying')
        if not already_running:
            _STATE.update(state='downloading', downloaded=0, error='', verified=False)
            _CANCEL.clear()
    if already_running:
        return _status()
    thread = threading.Thread(target=_download_worker, name='QXModelOptInDownload', daemon=True)
    thread.start()
    return _status()



def cancel_model_install() -> dict:
    with _LOCK:
        if _STATE['state'] == 'downloading':
            _CANCEL.set()
    return _status()
