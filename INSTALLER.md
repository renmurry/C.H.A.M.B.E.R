# Building the installer

Turns the app into a proper Windows installer with Start-menu and desktop
shortcuts (your logo icon) and an uninstaller.

## One time
Install **Inno Setup** (free): https://jrsoftware.org/isdl.php

## Steps
1. Build first: double-click **`build_all.bat`** (creates both `dist\CHAMBER.exe` and `dist\CHAMBER-CLI.exe`).
2. Double-click **`build_installer.bat`**.
3. The finished installer appears in **`installer_output\CHAMBER-Setup-1.9.0.exe`**.

Share that one Setup file with anyone. They run it and get C.H.A.M.B.E.R in
their Start menu (desktop app **and** a command-line shortcut) and, optionally, the desktop, with a clean uninstall entry.

> Note: the installer is unsigned, so Windows SmartScreen may warn on first run
> ("More info -> Run anyway"). Signing requires a paid certificate and is only
> needed for wide distribution; for personal/team use it's not required.
