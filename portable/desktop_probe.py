"""Check QX Windows desktop dependencies without PowerShell -c quoting.

The probe only imports installed packages. It never writes user data, downloads
models, opens a window, or changes the Python runtime.
"""
from __future__ import annotations

import argparse
import sys
import traceback


def check() -> int:
    try:
        import webview  # noqa: F401 - pywebview must import its dependencies
        import clr  # noqa: F401 - ensures pythonnet/.NET can be loaded
        print("[QX] Desktop component import check: OK")
        return 0
    except Exception as exc:
        print(f"[QX] Desktop component import check: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def build_check() -> int:
    """Verify the local build backend used for source-only proxy-tools.

    Embeddable CPython does not expose isolated pip build environments like a
    normal system Python, so the installer explicitly uses --no-build-isolation.
    """
    try:
        import setuptools.build_meta  # noqa: F401
        import wheel  # noqa: F401
        print("[QX] Private Python build backend: OK")
        return 0
    except Exception as exc:
        print(f"[QX] Private Python build backend: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="QX Windows desktop component check")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--build-check", action="store_true")
    args = parser.parse_args()
    if args.build_check:
        return build_check()
    if args.check:
        return check()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
