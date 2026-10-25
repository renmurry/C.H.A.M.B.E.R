# Building CHAMBER-CLI.exe (Windows)

Produces a standalone `.exe` so the tool runs **without Python installed**.

## One time
- Windows PC with Python 3.10+ installed (**tick "Add Python to PATH"** during install).

## Build
1. Keep the project folder intact (it needs `run.py`, `src/`, `requirements.txt`,
   `cli.spec`, `build_exe.bat`).
2. **Double-click `build_exe.bat`** (or run it from a Command Prompt in this folder).
3. First run downloads packages and takes a few minutes.
4. Result: **`dist\CHAMBER-CLI.exe`**, and you can copy it anywhere.

## Use
```
CHAMBER-CLI.exe  C:\path\to\pdfs  -o  C:\path\to\out  --epsg auto --jobs 4
```

## Troubleshooting
- **"Python not found"** → reinstall Python with "Add to PATH".
- **PROJ/GDAL data error at runtime** → rebuild with `--clean` (the spec bundles
  that data via `collect_all`). If it persists, try a one-folder build:
  `pyinstaller --onedir --collect-all rasterio --collect-all pyproj run.py`.
- **Antivirus / SmartScreen warning** → routine false positive for unsigned
  one-file PyInstaller builds; allow it, or use the one-folder build.
- **Slow first launch** → one-file exes unpack to temp each run; one-folder is faster.
