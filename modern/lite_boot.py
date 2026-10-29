"""Start/stop QX AI Lite server only for the duration of the QX desktop process."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

BASE = Path(os.environ.get('LOCALAPPDATA', '')) / 'QXPodborshchik' / 'QX_AI'
ENGINE = BASE / 'lite-engine' / 'llama-server.exe'
MODEL = BASE / 'lite-models' / 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
HEALTH = 'http://127.0.0.1:11435/health'


def lite_reachable(timeout=0.4):
    try:
        with urlopen(HEALTH, timeout=timeout) as response:
            return response.status == 200 and b'ok' in response.read(20000).lower()
    except (OSError, ValueError):
        return False


def start_lite():
    """Returns a child process owned by QX, or None if already running/missing."""
    if sys.platform != 'win32' or os.environ.get('QX_DISABLE_AUTO_AI') == '1':
        return None
    if lite_reachable():
        return None
    if not ENGINE.is_file() or not MODEL.is_file():
        return None
    try:
        with MODEL.open('rb') as file:
            if file.read(4) != b'GGUF' or not 700_000_000 < MODEL.stat().st_size < 1_500_000_000:
                return None
        command=[str(ENGINE), '--model', str(MODEL), '--host', '127.0.0.1', '--port', '11435',
                 '--ctx-size', '4096', '--parallel', '1', '--threads', '6']
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, cwd=str(ENGINE.parent),
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(100):
            if lite_reachable():
                return proc
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        proc.terminate()
        return None
    except (OSError, PermissionError, ValueError):
        return None


def stop_lite(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()
