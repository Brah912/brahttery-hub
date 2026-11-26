; Instalador de Brahttery hub (Inno Setup 6).
; Se genera solo con publicar.ps1; a mano (después de compilar.ps1):
;   ISCC.exe /DVersion=1.4.0 instalador.iss
; Para pruebas, una copia que no toca la instalación real ni el registro:
;   ISCC.exe /DVersion=1.4.0 /DPrueba /DCarpetaPrueba=C:\ruta instalador.iss
;
; La app va en una carpeta (el .exe + _internal\). Las actualizaciones automáticas descargan
; este mismo instalador y lo ejecutan en silencio: cierra la app, reemplaza la carpeta y la
; vuelve a abrir (ver [Run]).
; Se instala sólo para el usuario actual (sin permisos de administrador) en
; %LOCALAPPDATA%\Programs\Brahttery hub, así las actualizaciones automáticas pueden
; reemplazar el programa sin pedir nada.

#ifndef Version
  #define Version "0.0.0"
#endif
#define Nombre "Brahttery hub"
#define Exe "Brahttery hub.exe"

[Setup]
#ifdef Prueba
AppId={{6E0C2B1A-0000-4F00-9E00-50B7E7A00000}
AppName={#Nombre} (prueba)
DefaultDirName={#CarpetaPrueba}
OutputBaseFilename=Brahttery-hub-Setup-prueba-{#Version}
#else
; No cambies nunca este AppId: Windows lo usa para saber que es el mismo programa
AppId={{B19F4761-885D-4C03-BF3A-DE1ECEA7DD9C}
AppName={#Nombre}
DefaultDirName={autopf}\{#Nombre}
OutputBaseFilename=Brahttery-hub-Setup-{#Version}
#endif
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher=Brah912
AppPublisherURL=https://github.com/Brah912/brahttery-hub
AppSupportURL=https://github.com/Brah912/brahttery-hub
AppUpdatesURL=https://github.com/Brah912/brahttery-hub/releases/latest
VersionInfoVersion={#Version}
VersionInfoDescription=Instalador de {#Nombre}
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
UsePreviousTasks=yes
SetupIconFile=brahttery_hub.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nombre}
WizardStyle=modern
WizardSizePercent=100
Compression=lzma2/max
SolidCompression=yes
OutputDir=dist
; El propio instalador cierra la app si está abierta (ver [Code])
CloseApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"
Name: "inicio"; Description: "Abrir {#Nombre} al iniciar Windows (recomendado)"

[InstallDelete]
; versiones viejas: el .exe de un solo archivo que dejaba el actualizador y la carpeta interna
; anterior (así no quedan archivos de otra versión mezclados)
Type: files; Name: "{app}\Brahttery hub.old-*.exe"
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\{#Nombre}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#ifndef Prueba
; (la copia de prueba no crea accesos directos: tendrían el mismo nombre que los de la app real)
[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Exe}"; Tasks: escritorio
#endif

#ifndef Prueba
[Registry]
; Mismo valor que usa la opción "Iniciar con Windows" de la propia app
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BrahtteryHub"; \
    ValueData: """{app}\{#Exe}"" --inicio"; Tasks: inicio; Flags: uninsdeletevalue
; Por si estaba desactivada en el Administrador de tareas de una instalación anterior
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"; ValueType: binary; \
    ValueName: "BrahtteryHub"; ValueData: "02 00 00 00 00 00 00 00 00 00 00 00"; Tasks: inicio; Flags: uninsdeletevalue
; La decisión sobre el arranque ya está tomada (casilla del instalador): la app no la cambia
Root: HKCU; Subkey: "Software\BrahtteryHub"; ValueType: dword; ValueName: "InicioConfigurado"; ValueData: 1; \
    Flags: uninsdeletekey
; Nombre con el que salen sus notificaciones de Windows (avisos de batería baja)
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\BrahtteryHub"; ValueType: string; ValueName: "DisplayName"; \
    ValueData: "{#Nombre}"; Flags: uninsdeletekey
#endif

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir {#Nombre}"; Flags: nowait postinstall skipifsilent
; actualización automática (instalador en silencio): vuelve a abrir la app ya actualizada
Filename: "{app}\{#Exe}"; Parameters: "--actualizado"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
; versiones viejas que deja el actualizador
Type: files; Name: "{app}\Brahttery hub.old-*.exe"

[Code]
procedure CerrarApp();
var
  Codigo: Integer;
begin
  // Cierra la app (bandeja y ventana) para poder reemplazar o borrar el .exe
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#Exe}"', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CerrarApp();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    CerrarApp();
#ifndef Prueba
    // (la copia de prueba no toca el arranque de la app real)
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BrahtteryHub');
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'BrahtteryHub');
#endif
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    Datos := ExpandConstant('{userappdata}\{#Nombre}');
    if DirExists(Datos) and not UninstallSilent() then
      if MsgBox('¿Borrar también tus ajustes y el historial de batería?' #13#10#13#10 +
                'Si vas a volver a instalar Brahttery hub, elige No para conservarlos.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Datos, True, True, True);
  end;
end;
