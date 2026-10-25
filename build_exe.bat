@echo off
setlocal enabledelayedexpansion
echo ============================================
echo   C.H.A.M.B.E.R  -  Windows EXE builder
echo ============================================

REM --- Find a compatible Python (3.12/3.11/3.10/3.13). 3.14 is too new for
REM --- the geospatial libraries' ready-made builds, so we avoid it. ---
set "PYEXE="

REM 1) try the py launcher
for %%V in (3.12 3.11 3.10 3.13) do (
  if not defined PYEXE (
    py -%%V --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -%%V"
  )
)

REM 2) try common install folders directly
if not defined PYEXE (
  for %%P in (
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python310\python.exe"
  ) do (
    if not defined PYEXE if exist %%P set "PYEXE=%%P"
  )
)

if not defined PYEXE (
  echo [X] Could not find Python 3.10-3.13.
  echo     Re-run the Python 3.12 installer, tick "Add python.exe to PATH",
  echo     and ALSO tick "py launcher". Then run this again.
  echo.
  pause & exit /b 1
)
for /f "delims=" %%i in ('!PYEXE! --version') do echo Using interpreter: %%i

echo [1/4] Creating a fresh build environment...
if exist .venv_build rmdir /s /q .venv_build
!PYEXE! -m venv .venv_build || (echo [X] venv creation failed & pause & exit /b 1)
call .venv_build\Scripts\activate.bat

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip >nul

echo [3/4] Installing dependencies + PyInstaller ^(first run takes a few minutes^)...
pip install --prefer-binary -r requirements.txt pyinstaller || (echo [X] pip install failed - see message above & pause & exit /b 1)

echo [4/4] Building CHAMBER-CLI.exe ...
pyinstaller --noconfirm --clean cli.spec || (echo [X] build failed & pause & exit /b 1)

echo.
echo ============================================
echo   DONE.  Your tool is at:  dist\CHAMBER-CLI.exe
echo ============================================
echo Example:
echo   dist\CHAMBER-CLI.exe  C:\path\to\pdfs  -o  C:\path\to\out  --epsg auto --jobs 4
echo.
echo Build finished. Press any key to close this window.
pause >nul
endlocal
