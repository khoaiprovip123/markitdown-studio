import importlib.util
import os

magika_spec = importlib.util.find_spec("magika")
if magika_spec and magika_spec.submodule_search_locations:
    magika_dir = magika_spec.submodule_search_locations[0]
    magika_models = (os.path.join(magika_dir, 'models'), 'magika/models')
    magika_config = (os.path.join(magika_dir, 'config'), 'magika/config')
else:
    magika_models = ('.venv/Lib/site-packages/magika/models', 'magika/models')
    magika_config = ('.venv/Lib/site-packages/magika/config', 'magika/config')

a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('packages', 'packages'), magika_models, magika_config],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MarkItDownStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MarkItDownStudio',
)
