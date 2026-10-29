"""Start bundled QX AI only when the desktop app is open; never download at runtime.

QX_AI is installed once into the user's LocalAppData by the first-run setup.
On a normal app start we just bring up a local, loopback-only Ollama server.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

AI_HOME = Path(os.environ.get('LOCALAPPDATA', '')) / 'QXPodborshchik' / 'QX_AI'


def ollama_reachable(timeout=0.4):
    try:
        with urlopen('http://127.0.0.1:11434/api/tags', timeout=timeout) as response:
            return response.status == 200 and b'models' in response.read(160_000)
    except (OSError, ValueError):
        return False


def runtime_candidates():
    home = Path(os.environ.get('LOCALAPPDATA', ''))
    return (AI_HOME / 'engine' / 'ollama.exe', home / 'Programs' / 'Ollama' / 'ollama.exe')


def start_ollama():
    """Return a process *owned by QX* or None for an existing/system server."""
    if sys.platform != 'win32' or os.environ.get('QX_DISABLE_AUTO_AI') == '1':
        return None
    if ollama_reachable():
        return None
    cli = next((p for p in runtime_candidates() if p.is_file()), None)
    if cli is None:
        return None
    env = os.environ.copy()
    env['OLLAMA_HOST'] = '127.0.0.1:11434'
    env['OLLAMA_NO_CLOUD'] = '1'
    if cli == runtime_candidates()[0]:
        env['OLLAMA_MODELS'] = str(AI_HOME / 'models')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        proc = subprocess.Popen([str(cli), 'serve'], env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(35):
            if ollama_reachable():
                return proc
            if proc.poll() is not None:
                break
            time.sleep(0.3)
        proc.terminate()
        return None
    except (OSError, PermissionError):
        return None


def stop_ollama(proc):
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
