; GTM Signature Agent - Per-User Installer
; Empacotado com Inno Setup 6
;
; Comportamento:
; - Instala em %LOCALAPPDATA%\GTMSignatureAgent (sem precisar admin)
; - Cria duas Tarefas Agendadas no contexto do usuario:
;     * GTMSignatureSync_Logon  (dispara em todo logon)
;     * GTMSignatureSync_Daily  (dispara todo dia as 10:00)
; - Roda sync inicial logo apos a instalacao
; - Desinstalacao limpa: remove tarefas, executavel, arquivos de log

#define AppName "GTM Signature Agent"
#define AppVersion "0.2.0"
#define AppPublisher "GTM Alimentos"
#define AppExeName "GTMSignatureAgent.exe"

[Setup]
AppId={{8b3a7e2d-9c4f-4b1a-a5d7-1e2f3c4d5e6f}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://assinatura.gtmalimentos.com.br
DefaultDirName={userappdata}\GTMSignatureAgent
DefaultGroupName=GTM
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=GTMSignatureAgentSetup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=GTM Signature Agent

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "GTMSignatureAgent.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\GTM\Sincronizar assinatura agora"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{userprograms}\GTM\Desinstalar GTM Signature Agent"; Filename: "{uninstallexe}"

[Run]
; Cria tarefa agendada que roda em todo logon
Filename: "{cmd}"; \
  Parameters: "/c schtasks /Create /TN ""GTMSignatureSync_Logon"" /TR ""\""{app}\{#AppExeName}\"""" /SC ONLOGON /RL LIMITED /F"; \
  Flags: runhidden waituntilterminated

; Cria tarefa agendada que roda todo dia as 10:00
Filename: "{cmd}"; \
  Parameters: "/c schtasks /Create /TN ""GTMSignatureSync_Daily"" /TR ""\""{app}\{#AppExeName}\"""" /SC DAILY /ST 10:00 /RL LIMITED /F"; \
  Flags: runhidden waituntilterminated

; Sincroniza imediatamente para o usuario nao precisar esperar o proximo logon
Filename: "{app}\{#AppExeName}"; \
  Description: "Sincronizar assinatura agora"; \
  Flags: postinstall runhidden nowait skipifsilent

[UninstallRun]
Filename: "{cmd}"; \
  Parameters: "/c schtasks /Delete /TN ""GTMSignatureSync_Logon"" /F"; \
  Flags: runhidden; \
  RunOnceId: "DelLogonTask"

Filename: "{cmd}"; \
  Parameters: "/c schtasks /Delete /TN ""GTMSignatureSync_Daily"" /F"; \
  Flags: runhidden; \
  RunOnceId: "DelDailyTask"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\GTMSignatureAgent"
