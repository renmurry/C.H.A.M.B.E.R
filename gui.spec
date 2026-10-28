# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec -> dist/CHAMBER.exe  (windowed desktop app)
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ['rasterio', 'pyproj', 'shapely', 'cv2', 'fitz', 'pikepdf', 'pyogrio',
            'rapidocr_onnxruntime', 'onnxruntime']:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print('  [spec] skipping', pkg, '->', e)
hiddenimports += collect_submodules('chamber')
hiddenimports += ['rasterio._shim', 'rasterio.sample', 'rasterio.vrt',
                  'rasterio._features', 'rasterio.control', 'rasterio.crs']

# bundle the logo/icon assets
datas += [('assets/app.ico', 'assets'),
          ('assets/logo_48.png', 'assets'),
          ('assets/logo_64.png', 'assets'),
          ('assets/logo.png', 'assets'),
          ('assets/logo_512.png', 'assets'),
          ('assets/anim', 'assets/anim')]          # the stage animation clips

a = Analysis(['app.py'], pathex=['src'], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=['tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='CHAMBER', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, icon='assets/app.ico',
          disable_windowed_traceback=False, target_arch=None,
          codesign_identity=None, entitlements_file=None)
