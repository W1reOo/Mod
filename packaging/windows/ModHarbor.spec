# Build with Windows Python + PyInstaller; Wine-based builds use the same spec.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH).parent.parent
web_data, web_bins, web_hidden = collect_all('webview')
a = Analysis(
    [str(root / 'packaging' / 'windows' / 'desktop_entry.py')],
    pathex=[str(root)],
    binaries=web_bins,
    datas=web_data + collect_data_files('setuptools') + collect_data_files('clr_loader') + collect_data_files('pythonnet') + [
        (str(root / 'modmanager' / 'web'), 'modmanager/web'),
    ],
    hiddenimports=web_hidden + ['clr', 'clr_loader', 'pythonnet', 'webview.platforms.winforms', 'webview.platforms.edgechromium'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='ModHarbor', icon=str(root / 'packaging' / 'windows' / 'ModHarbor.ico'), debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    version=str(root / 'packaging' / 'windows' / 'version.txt'),
)
