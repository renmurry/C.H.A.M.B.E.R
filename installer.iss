; Inno Setup script for C.H.A.M.B.E.R.
; Build first with build_all.bat (creates both exes in dist\), then compile this.

#define MyAppName "C.H.A.M.B.E.R"
#define MyAppVersion "1.9.0"
#define MyAppPublisher "Ren"
#define MyAppExe "CHAMBER.exe"
#define MyCliExe "CHAMBER-CLI.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\C.H.A.M.B.E.R
DefaultGroupName=C.H.A.M.B.E.R
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=CHAMBER-Setup-{#MyAppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\CHAMBER.exe";     DestDir: "{app}"; Flags: ignoreversion
Source: "dist\CHAMBER-CLI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md";                  DestDir: "{app}"; Flags: ignoreversion
Source: "assets\app.ico";             DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\C.H.A.M.B.E.R";           Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\app.ico"
Name: "{group}\C.H.A.M.B.E.R (command line)"; Filename: "{cmd}"; Parameters: "/K cd /d ""{app}"" && echo Run:  CHAMBER-CLI.exe --help"; IconFilename: "{app}\app.ico"
Name: "{group}\Uninstall C.H.A.M.B.E.R"; Filename: "{uninstallexe}"
Name: "{autodesktop}\C.H.A.M.B.E.R";     Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch C.H.A.M.B.E.R now"; Flags: nowait postinstall skipifsilent
