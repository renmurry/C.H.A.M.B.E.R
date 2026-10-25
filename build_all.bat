@echo off
setlocal enabledelayedexpansion
echo ============================================
echo   C.H.A.M.B.E.R  -  Build app + command-line
echo ============================================
set "PYEXE="
for %%V in (3.12 3.11 3.10 3.13) do (
  if not defined PYEXE (
    py -%%V --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -%%V"
  )
)
if not defined PYEXE (
  for %%P in (
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
  ) do ( if not defined PYEXE if exist %%P set "PYEXE=%%P" )
)
if not defined PYEXE (
  echo [X] Could not find Python 3.10-3.13. Install Python 3.12 ^(tick "Add to PATH"^).
  pause & exit /b 1
)
for /f "delims=" %%i in ('!PYEXE! --version') do echo Using interpreter: %%i
echo [1/4] Creating a fresh build environment...
if exist .venv_build rmdir /s /q .venv_build
!PYEXE! -m venv .venv_build || (echo [X] venv failed & pause & exit /b 1)
call .venv_build\Scripts\activate.bat
echo [2/4] Upgrading pip...
python -m pip install --upgrade pip >nul
echo [3/4] Installing dependencies + PyInstaller ^(first run takes a few minutes^)...
pip install --prefer-binary -r requirements.txt pyinstaller || (echo [X] pip install failed & pause & exit /b 1)
echo [4/4] Building BOTH executables...
echo     - desktop app...
pyinstaller --noconfirm --clean gui.spec || (echo [X] app build failed & pause & exit /b 1)
echo     - command-line tool...
pyinstaller --noconfirm --clean cli.spec || (echo [X] cli build failed & pause & exit /b 1)
echo.
echo ============================================
echo   DONE.  Both are in the dist folder:
echo     dist\CHAMBER.exe       (double-click = desktop app)
echo     dist\CHAMBER-CLI.exe   (command line / automation)
echo ============================================
echo.
pause
endlocal
