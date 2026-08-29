; TriggerWord installer - Inno Setup 6
; Builds a per-user installer that bundles an embedded Python runtime, so a
; non-technical user needs nothing installed first. Build with build.ps1.

#define AppName "TriggerWord"
#define AppVersion "1.1.2"
#define AppPublisher "SCARYLASERS"
#define AppURL "https://github.com/scarylasers/triggerword"

[Setup]
AppId={{7A2F1C64-9B3E-4E27-9C1B-7D6A5E8F2B10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=https://discord.gg/r4z4EVnt9U
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Per-user install: no admin prompt, and the app folder stays writable.
PrivilegesRequired=lowest
; launcher.py holds this mutex while running, so installing or uninstalling
; over a running copy asks the user to close it rather than leaving locked
; files behind.
AppMutex=TriggerWord.SCARYLASERS.Running
OutputDir=dist
OutputBaseFilename=TriggerWord-Setup-{#AppVersion}
SetupIconFile=..\static\images\triggerword_icon_logo.ico
UninstallDisplayIcon={app}\static\images\triggerword_icon_logo.ico
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; App payload (staged by build.ps1 - see that script for exactly what is included)
Source: "build\payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "launcher.py"; WorkingDir: "{app}"; IconFilename: "{app}\static\images\triggerword_icon_logo.ico"
Name: "{group}\{#AppName} User Guide"; Filename: "{app}\guide.html"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "launcher.py"; WorkingDir: "{app}"; IconFilename: "{app}\static\images\triggerword_icon_logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "launcher.py"; WorkingDir: "{app}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Runtime leftovers that are created after install
Type: files; Name: "{app}\launcher.log"
Type: filesandordirs; Name: "{app}\python\__pycache__"
Type: dirifempty; Name: "{app}"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nTriggerWord is a soundboard that listens: say a word, it plays the sound. Everything runs on your own machine - no account, no cloud.%n%nPython is included, so there is nothing else to install.
