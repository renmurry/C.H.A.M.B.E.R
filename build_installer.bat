@echo off
setlocal enabledelayedexpansion
echo ============================================
echo   C.H.A.M.B.E.R  -  Installer builder
echo ============================================

if not exist "dist\CHAMBER.exe" (
  echo [X] dist\CHAMBER.exe not found.
  echo     Run build_app.bat first to build the app, then run this.
  echo.
  pause & exit /b 1
)

REM locate the Inno Setup compiler
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
) do ( if not defined ISCC if exist %%P set "ISCC=%%P" )

if not defined ISCC (
  echo [X] Inno Setup not found.
  echo     Install it (free) from https://jrsoftware.org/isdl.php
  echo     then run this again.
  echo.
  pause & exit /b 1
)

echo Using: !ISCC!
"!ISCC!" installer.iss || (echo [X] compile failed & pause & exit /b 1)
echo.
echo ============================================
echo   DONE.  Installer is in:  installer_output\
echo   (CHAMBER-Setup-1.9.0.exe)
echo ============================================
echo.
pause
endlocal
