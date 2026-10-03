#ifndef TraceVersion
  #define TraceVersion "0.2.3"
#endif
#ifndef TraceSource
  #define TraceSource "..\dist\TRACE"
#endif
#ifndef TraceOutput
  #define TraceOutput "..\release"
#endif

[Setup]
AppId={{4DD449F2-D786-436D-A157-3725A5E95FE9}
AppName=TRACE
AppVersion={#TraceVersion}
AppPublisher=TRACE contributors
AppPublisherURL=https://github.com/Jonardi123/TRACE
DefaultDirName={localappdata}\Programs\TRACE
DefaultGroupName=TRACE
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#TraceOutput}
OutputBaseFilename=TRACE-{#TraceVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\TRACE.exe

[Files]
Source: "{#TraceSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TRACE"; Filename: "{app}\TRACE.exe"

[Run]
Filename: "{app}\TRACE.exe"; Description: "Open TRACE"; Flags: nowait postinstall skipifsilent
