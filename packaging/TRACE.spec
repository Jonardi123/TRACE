# Build on the target OS; Python/Tk and Python libraries are bundled, OCR is external.
from pathlib import Path
import sys
import tomllib

root = Path(SPECPATH).parent
version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
a = Analysis(
    [str(root / 'packaging/entry.py')], pathex=[str(root)],
    binaries=[], datas=[], hiddenimports=['osint_workbench.gui', 'PIL.ImageTk'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
options = [('X utf8', None, 'OPTION')]
gui = EXE(pyz, a.scripts, options, exclude_binaries=True, name='TRACE',
          debug=False, strip=False, upx=False, console=sys.platform == 'linux',
          disable_windowed_traceback=False)
cli = EXE(pyz, a.scripts, options, exclude_binaries=True, name='trace-cli',
          debug=False, strip=False, upx=False, console=True)
collection = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name='TRACE')
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='TRACE.app', bundle_identifier='io.github.jonardi123.trace',
                 info_plist={'CFBundleDisplayName': 'TRACE', 'CFBundleShortVersionString': version,
                             'NSHighResolutionCapable': True})
