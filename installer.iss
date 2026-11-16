; Inno Setup script for the Windows installer.
; Build the app first (python build.py), then: iscc /DAppVersion=1.1.0 installer.iss

#define AppName "Reel to MP3"
#define AppExe "Reel to MP3.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8C4C3A55-6F2B-4E7D-9B1A-5A0D2E6C7F31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Reel to MP3
AppPublisherURL=https://github.com/Erickv4rr/reel-to-mp3
AppSupportURL=https://github.com/Erickv4rr/reel-to-mp3/issues
AppUpdatesURL=https://github.com/Erickv4rr/reel-to-mp3/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=Reel-to-MP3-Setup
SetupIconFile=build\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; clear the previous version's bundled files before installing the new ones
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
