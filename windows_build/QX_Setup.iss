#define MyAppName "QX Подборщик Modern"
#include "qx_version.iss"
#define MyAppVersion QXAppVersion
#define MyAppExeName "QXPodborshchik.exe"
[Setup]
AppId={{9D5031E9-8DF7-4DC0-868C-41AC647F9347}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=QX / БРОКТЕХНОЛОДЖИ
DefaultDirName={localappdata}\Programs\QX Podborshchik
DefaultGroupName=QX Подборщик
OutputDir=out
OutputBaseFilename={#QXOutputBase}
SetupIconFile=..\assets\qx_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
AppMutex=BROKTECH.QXModern
CloseApplications=no
RestartApplications=no
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
VersionInfoCompany=БРОКТЕХНОЛОДЖИ
VersionInfoDescription=QX Tender Workspace
VersionInfoProductName=QX Подборщик Modern
VersionInfoProductVersion={#QXProductVersion}
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: checkedonce
[Files]
Source: "..\dist\QXPodborshchik\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\portable\auto_ai.ps1"; DestDir: "{app}\portable"; Flags: ignoreversion
[Icons]
Name: "{group}\QX Подборщик"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\qx_icon.ico"; AppUserModelID: "BROKTECH.QXModern"
Name: "{autodesktop}\QX Подборщик"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\qx_icon.ico"; AppUserModelID: "BROKTECH.QXModern"; Tasks: desktopicon
[Run]
; Run QX AI installation after copying the main app; silent CI/enterprise installs never download AI in silent mode.
Filename: "powershell.exe"; Parameters: "-NoLogo -NoProfile -ExecutionPolicy Bypass -File ""{app}\portable\auto_ai.ps1"""; Description: "Установить локальную нейросеть QX AI"; StatusMsg: "Установка QX AI Lite (llama.cpp + Qwen2.5 1.5B)..."; Flags: skipifsilent
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить QX Подборщик"; Flags: nowait postinstall skipifsilent
[Code]
// User files under %LOCALAPPDATA%\QXPodborshchik and legacy QX_Selector are
// deliberately NEVER deleted by the uninstaller.
