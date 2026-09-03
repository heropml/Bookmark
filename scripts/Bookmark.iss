; Built by scripts/build_installer.py. Payload contains only public application files.
#ifndef AppVersion
  #error AppVersion must be supplied by build_installer.py
#endif
#ifndef PayloadDir
  #error PayloadDir must be supplied by build_installer.py
#endif
#ifndef OutputPath
  #error OutputPath must be supplied by build_installer.py
#endif

#ifdef TestInstall
  #define ProductName "Bookmark Installer Test"
  #define ProductId "{B4B29C9F-9207-4F89-9527-08E353DE5D29}"
  #define OutputName "Bookmark_TestSetup"
  #define ShortcutName "Bookmark Installer Test"
#else
  #define ProductName "Bookmark"
  #define ProductId "{5FD53220-7839-4D82-83C0-A1EDBF9E5C87}"
  #define OutputName "Bookmark_Setup_v" + AppVersion
  #define ShortcutName "书签"
#endif

[Setup]
AppId={{#ProductId}
AppName={#ProductName}
AppVersion={#AppVersion}
AppPublisher=MG_Project
AppPublisherURL=https://github.com/heropml/Bookmark
AppSupportURL=https://gitee.com/heropml/Bookmark
DefaultDirName={localappdata}\Programs\{#ProductName}
DefaultGroupName={#ProductName}
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename={#OutputName}
SetupIconFile={#PayloadDir}\assets\icons\bookmark.ico
UninstallDisplayIcon={app}\assets\icons\bookmark.ico
UninstallDisplayName={#ProductName} {#AppVersion}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
AllowNoIcons=yes
SetupLogging=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimp.OpenBookmarks=打开书签
chinesesimp.ImportBookmarks=导入书签 HTML
chinesesimp.SyncChrome=同步 Chrome 书签
chinesesimp.SyncEdge=同步 Edge 收藏夹
chinesesimp.GitDirectory=此目录是 Git 工程，请选择独立的安装目录，避免覆盖工程文件。
english.OpenBookmarks=Open bookmarks
english.ImportBookmarks=Import bookmark HTML
english.SyncChrome=Sync Chrome bookmarks
english.SyncEdge=Sync Edge bookmarks
english.GitDirectory=This folder is a Git project. Choose a separate installation folder to avoid overwriting it.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{cm:OpenBookmarks}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\scripts\manage.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\icon-aurora.ico"
Name: "{group}\{cm:ImportBookmarks}"; Filename: "{app}\launchers\windows\replace.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\bookmark.ico"
Name: "{group}\{cm:SyncChrome}"; Filename: "{app}\launchers\windows\sync-chrome.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\bookmark.ico"
Name: "{group}\{cm:SyncEdge}"; Filename: "{app}\launchers\windows\sync-edge.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\bookmark.ico"
Name: "{group}\{cm:UninstallProgram,{#ProductName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#ShortcutName}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\scripts\manage.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\icon-aurora.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\scripts\manage.py"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#ProductName}}"; Flags: nowait postinstall skipifsilent

[Code]
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
    if DirExists(ExpandConstant('{app}\.git')) or FileExists(ExpandConstant('{app}\.git')) then
    begin
      MsgBox(ExpandConstant('{cm:GitDirectory}'), mbError, MB_OK);
      Result := False;
    end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}\.git')) or FileExists(ExpandConstant('{app}\.git')) then
    Result := ExpandConstant('{cm:GitDirectory}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Locator, Services, Processes, Process: Variant;
  I, ExitCode: Integer;
  Executable, CommandLine, ManagePath, PythonPath, PythonwPath: String;
begin
  // This event runs only after the user confirms uninstall. Never kill by name alone.
  if CurUninstallStep <> usUninstall then Exit;
  PythonPath := Lowercase(ExpandConstant('{app}\runtime\python\python.exe'));
  PythonwPath := Lowercase(ExpandConstant('{app}\runtime\python\pythonw.exe'));
  ManagePath := Lowercase(ExpandConstant('{app}\scripts\manage.py'));
  Locator := CreateOleObject('WbemScripting.SWbemLocator');
  Services := Locator.ConnectServer('', 'root\CIMV2');
  Processes := Services.ExecQuery('SELECT * FROM Win32_Process WHERE Name = ''python.exe'' OR Name = ''pythonw.exe''');
  for I := 0 to Processes.Count - 1 do
  begin
    Process := Processes.ItemIndex(I);
    if not VarIsNull(Process.ExecutablePath) and not VarIsNull(Process.CommandLine) then
    begin
      Executable := Process.ExecutablePath;
      CommandLine := Process.CommandLine;
      Executable := Lowercase(Executable);
      CommandLine := Lowercase(CommandLine);
      if ((Executable = PythonPath) or (Executable = PythonwPath))
        and ((Pos('"' + ManagePath + '"', CommandLine) > 0)
          or (Pos(' ' + ManagePath + ' ', CommandLine + ' ') > 0))
        and (Pos(' --serve ', CommandLine + ' ') > 0) then
      begin
        ExitCode := Process.Terminate(0);
        if ExitCode <> 0 then
          RaiseException('Cannot stop the Bookmark service in this installation folder. Close it before uninstalling.');
      end;
    end;
  end;
end;
