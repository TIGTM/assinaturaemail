; GTM Signature Agent - Per-User Installer
; Empacotado com Inno Setup 6
;
; Comportamento:
; - Instala em %LOCALAPPDATA%\GTMSignatureAgent (sem precisar admin)
; - Pergunta o e-mail corporativo durante o setup (PCs standalone nao
;   conseguem detectar sozinhos)
; - Cria duas Tarefas Agendadas no contexto do usuario, com --email
;   ja embutido no comando:
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
Name: "{userprograms}\GTM\Sincronizar assinatura agora"; Filename: "{app}\{#AppExeName}"; Parameters: "--email={code:GetUserEmail}"; WorkingDir: "{app}"
Name: "{userprograms}\GTM\Desinstalar GTM Signature Agent"; Filename: "{uninstallexe}"

[Run]
; Cria tarefa que roda em todo logon, com o e-mail embutido
Filename: "{cmd}"; \
  Parameters: "/c schtasks /Create /TN ""GTMSignatureSync_Logon"" /TR ""\""{app}\{#AppExeName}\"" --email={code:GetUserEmail}"" /SC ONLOGON /RL LIMITED /F"; \
  Flags: runhidden waituntilterminated

; Cria tarefa que roda todo dia as 10:00, com o e-mail embutido
Filename: "{cmd}"; \
  Parameters: "/c schtasks /Create /TN ""GTMSignatureSync_Daily"" /TR ""\""{app}\{#AppExeName}\"" --email={code:GetUserEmail}"" /SC DAILY /ST 10:00 /RL LIMITED /F"; \
  Flags: runhidden waituntilterminated

; Sincroniza imediatamente, com o e-mail informado
Filename: "{app}\{#AppExeName}"; \
  Parameters: "--email={code:GetUserEmail}"; \
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

[Code]
var
  EmailPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  EmailPage := CreateInputQueryPage(wpWelcome,
    'Identificacao do usuario',
    'Qual o seu e-mail corporativo?',
    'Digite o e-mail @gtmalimentos.com.br ou @pescadosbemfresco.com.br ' +
    'que voce usa no Outlook. O agente vai usar esse e-mail para baixar ' +
    'a sua assinatura da VPS automaticamente.');
  EmailPage.Add('E-mail:', False);
end;

function IsValidEmail(email: String): Boolean;
var
  e: String;
begin
  e := Lowercase(Trim(email));
  Result := (Pos('@gtmalimentos.com.br', e) > 0) or
            (Pos('@pescadosbemfresco.com.br', e) > 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = EmailPage.ID then
  begin
    if not IsValidEmail(EmailPage.Values[0]) then
    begin
      MsgBox('E-mail invalido. Digite um endereco terminado em ' +
             '@gtmalimentos.com.br ou @pescadosbemfresco.com.br.',
             mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function GetUserEmail(Param: String): String;
begin
  Result := Lowercase(Trim(EmailPage.Values[0]));
end;
