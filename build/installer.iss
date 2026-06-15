; installer.iss — Inno Setup 설치 스크립트 (Windows .exe 설치본 생성)
; 선택 단계: 단일 exe(dist\CharacterTodo.exe)를 설치본으로 감쌀 때만 사용.
; 기본 배포는 dist\CharacterTodo.exe 하나만 전달하면 되며 이 단계는 불필요하다.
; 사전: PyInstaller(onefile)로 dist\CharacterTodo.exe 가 만들어져 있어야 함.

#define AppName "Character TODO"
#define AppVersion "0.3.0"
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
Source: "..\dist\CharacterTodo.exe"; DestDir: "{app}"; Flags: ignoreversion
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
