#define MyAppName "MrTris_AUTO"
#define MyAppVersion "1.0.4"
#define MyAppPublisher "MrTris"
#define SourceRoot "..\..\build\package\MrTris_AUTO"

[Setup]
AppId={{B28A1BD5-8CA1-4D02-98C7-09C0EF7F117A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\build\installer
OutputBaseFilename=MrTris_AUTO_Setup_v1.0.4
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayName={#MyAppName}
SetupIconFile=..\..\icon.ico
UninstallDisplayIcon={app}\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MrTris_AUTO"; Filename: "{app}\runtime\python\python.exe"; Parameters: """{app}\MrTris_AUTO.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Diagnostics"; Filename: "{app}\runtime\python\python.exe"; Parameters: """{app}\MrTris_AUTO_Diagnostics.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Repair"; Filename: "{app}\runtime\python\python.exe"; Parameters: """{app}\MrTris_AUTO_Repair.py"" --backup-db --sync-presets"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\MrTris_AUTO"; Filename: "{app}\runtime\python\python.exe"; Parameters: """{app}\MrTris_AUTO.py"""; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\runtime\python\python.exe"; Parameters: """{app}\MrTris_AUTO.py"""; WorkingDir: "{app}"; Description: "Launch MrTris_AUTO"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure StopRunningAppProcesses();
var
  ResultCode: Integer;
  AppDir: String;
  Command: String;
begin
  AppDir := ExpandConstant('{app}');
  Command := '$app = ''' + AppDir + '''; ' +
    'Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like ($app + ''*'') } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }';
  Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoLogo -NoProfile -ExecutionPolicy Bypass -Command "' + Command + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Sleep(1000);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningAppProcesses();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  MsgBox('Uninstall removes only application files. User data in %LOCALAPPDATA%\MrTris_AUTO and output videos in Videos\AutoReview are kept.', mbInformation, MB_OK);
  Result := True;
end;
