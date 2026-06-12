; installer.iss — Inno Setup 설치 스크립트 (Windows .exe 설치본 생성)
; 사전: PyInstaller 로 dist\CharacterTodo\ 가 만들어져 있어야 함 (build.bat 이 처리).

#define AppName "Character TODO"
#define AppVersion "0.1.0"
#define AppExe "CharacterTodo.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\CharacterTodo
DefaultGroupName=Character TODO
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=CharacterTodo-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 생성"; GroupDescription: "추가 작업:"
Name: "autostart"; Description: "로그인 시 자동 시작"; GroupDescription: "추가 작업:"; Flags: unchecked

[Files]
Source: "..\dist\CharacterTodo\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "uninstall_all.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Character TODO"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\Character TODO"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{group}\Character TODO 완전 삭제"; Filename: "{app}\uninstall_all.bat"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "CharacterTodo"; ValueData: """{app}\{#AppExe}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "지금 실행"; Flags: nowait postinstall skipifsilent
