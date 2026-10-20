; Reader Simulator setup (Inno Setup 6). Per-user, no admin.
; Build: ..\tools\inno\ISCC.exe ReaderSimulator.iss   (after ..\app\build.ps1)
#define AppName "Reader Simulator"
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppExe "ReaderSimulator.exe"
#define Bin "..\app\bin"

[Setup]
AppId={{6C2B7E7A-3F0D-4C51-9A57-2E6B3C8D9F41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Reader Simulator contributors
AppCopyright=Copyright (c) 2026 PewPewzxc and Reader Simulator contributors
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} setup
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DefaultGroupName={#AppName}
LicenseFile=LICENSE.txt
OutputDir=Output
OutputBaseFilename=ReaderSimulator-Setup
SetupIconFile=..\app\ReaderSimulator.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
MinVersion=10.0
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Bin}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Bin}\{#AppExe}.config"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Bin}\frames\*.png"; DestDir: "{app}\frames"; Flags: ignoreversion
Source: "{#Bin}\frames\*.keys"; DestDir: "{app}\frames"; Flags: ignoreversion
Source: "{#Bin}\samples\*"; DestDir: "{app}\samples"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := IsDotNetInstalled(net48, 0);
  if not Result then
    SuppressibleMsgBox('Reader Simulator needs the .NET Framework 4.8, which is part of Windows 10 (May 2019 update or newer) and Windows 11.' + #13#10 +
      'Please update Windows, or install .NET Framework 4.8 from Microsoft, then run this setup again.', mbCriticalError, MB_OK, IDOK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  // Downloaded builds and simulated SD cards (books, reading progress) are kept unless the user says yes; silent uninstalls keep them.
  if CurUninstallStep = usPostUninstall then
  begin
    Data := ExpandConstant('{localappdata}\ReaderSimulator');
    if DirExists(Data) and not UninstallSilent then
      if MsgBox('Also delete the downloaded firmware builds and the simulated SD cards (with any books you added)?' + #13#10#13#10 + Data,
          mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Data, True, True, True);
  end;
end;
