#define MyAppName "AICodeReviewer"
#define MyAppPublisher "AICodeReviewer Team"
#define MyAppURL "https://github.com/gallaway-jp/AICodeReviewer"

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#ifndef SourceDir
  #define SourceDir ".."
#endif

#ifndef StagingDir
  #define StagingDir AddBackslash(SourceDir) + "build\\installer_payload"
#endif

#ifndef OutputDir
  #define OutputDir AddBackslash(SourceDir) + "dist\\installer"
#endif

[Setup]
AppId={{E96B5F18-4D12-45C5-BD0E-8E1E8AD63D6A}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\AICodeReviewer
DefaultGroupName=AICodeReviewer
AllowNoIcons=yes
LicenseFile={#SourceDir}\LICENSE
InfoAfterFile={#SourceDir}\README.md
OutputDir={#OutputDir}
OutputBaseFilename=AICodeReviewer-Setup-{#AppVersion}
SetupIconFile={#SourceDir}\src\aicodereviewer\assets\icon.ico
UninstallDisplayIcon={app}\AICodeReviewer.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=yes
VersionInfoVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#StagingDir}\AICodeReviewer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\AICodeReviewer.exe.sha256"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\config.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\AICodeReviewer"; Filename: "{app}\AICodeReviewer.exe"; Parameters: "--gui"; WorkingDir: "{app}"; Comment: "Launch the AICodeReviewer desktop GUI"
Name: "{autoprograms}\AICodeReviewer CLI"; Filename: "{app}\AICodeReviewer.exe"; WorkingDir: "{app}"; Comment: "Launch the AICodeReviewer command-line interface"
Name: "{autodesktop}\AICodeReviewer"; Filename: "{app}\AICodeReviewer.exe"; Parameters: "--gui"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AICodeReviewer.exe"; Parameters: "--gui"; WorkingDir: "{app}"; Description: "Launch AICodeReviewer GUI"; Flags: nowait postinstall skipifsilent

[Code]
var
  PreserveUserData: Boolean;

function InitializeUninstall(): Boolean;
begin
  PreserveUserData :=
    MsgBox(
      'Preserve AICodeReviewer user data stored in the install directory (config.ini and log files)?',
      mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2
    ) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not PreserveUserData then
  begin
    DeleteFile(ExpandConstant('{app}\config.ini'));
    DeleteFile(ExpandConstant('{app}\aicodereviewer.log'));
    DeleteFile(ExpandConstant('{app}\aicodereviewer-audit.log'));
  end;
end;