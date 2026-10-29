"""Write / check Inno Setup macros using the version reported by the app."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modern.release_info import inno_defines, SETUP_BASENAME


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--print-installer', action='store_true')
    args=parser.parse_args()
    if args.print_installer:
        print(SETUP_BASENAME + '.exe')
        return 0
    target=Path(__file__).with_name('qx_version.iss')
    expected=inno_defines()
    if args.check:
        if not target.exists() or target.read_text(encoding='utf-8') != expected:
            print('Installer version macros out of date', file=sys.stderr)
            return 1
        print('Version macros: OK')
    else:
        target.write_text(expected, encoding='utf-8')
        print('Generated', target.name)
    return 0


if __name__=='__main__':
    sys.exit(main())
