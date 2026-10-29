# PyInstaller 6.x: frozen Windows desktop bundle.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs
import importlib.util
from pathlib import Path
ROOT = Path(SPECPATH).resolve().parent  # SPECPATH is the windows_build directory
hidden = []
for pkg in ('uvicorn','fastapi','starlette','pydantic','webview','docx','openpyxl','pypdf','pandas','streamlit','core','modern','winotify'):
    hidden += collect_submodules(pkg)
extra_binary_files = []
extra_data_files = []
if importlib.util.find_spec('llama_cpp') is not None:
    # GGUF uses native DLLs which regular hiddenimports do not collect.
    hidden += collect_submodules('llama_cpp')
    extra_binary_files += collect_dynamic_libs('llama_cpp')
    extra_data_files += collect_data_files('llama_cpp')
source = Analysis(
    [str(ROOT / 'qx_entry.py')],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT/'modern'/'web'), 'modern/web'),
        (str(ROOT/'assets'), 'assets'),
        (str(ROOT/'templates'), 'templates'),
        (str(ROOT/'data'), 'data'),
        (str(ROOT/'app.py'), '.'),
        (str(ROOT/'.streamlit'), '.streamlit'),
    ] + extra_data_files,
    hiddenimports=hidden,
    binaries=extra_binary_files,
    hookspath=[],
    excludes=['tkinter.test', 'pytest', 'playwright'],
    noarchive=False,
)
pyz=PYZ(source.pure)
exe=EXE(pyz, source.scripts, [], exclude_binaries=True, name='QXPodborshchik', console=False,
    icon=str(ROOT/'assets'/'qx_icon.ico'), version=None, debug=False)
coll=COLLECT(exe, source.binaries, source.datas, strip=False, upx=False, name='QXPodborshchik')
