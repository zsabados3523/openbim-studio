; SPDX-License-Identifier: AGPL-3.0-or-later
; Instalador do OpenBIM Studio (NSIS). Instalação por usuário (sem administrador), pasta própria.
; Variáveis (passadas por makensis /D): PASTA_PACOTE (pasta pronta com env\, app\, licenses\ ...),
; SAIDA (caminho do .exe), VERSAO, ENV_TGZ (env.tgz com a pasta env\ inteira).
Unicode true
!include "MUI2.nsh"

Name "OpenBIM Studio"
OutFile "${SAIDA}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\OpenBIM Studio"
; reinstalar lembra a pasta escolhida da vez anterior (chave que o próprio instalador grava; /D= continua mandando)
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenBIM Studio" "InstallLocation"
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_LICENSE "${PASTA_PACOTE}\licenses\AGPL-3.0-or-later.txt"
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE PastaLeave
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

; $0 = 1 se a pasta de instalação já tem arquivos que não são de uma instalação nossa
Function PastaOcupada
  StrCpy $0 0
  IfFileExists "$INSTDIR\app\OpenBIM-Studio.pyw" fim
  IfFileExists "$INSTDIR\*.*" 0 fim
  FindFirst $1 $2 "$INSTDIR\*.*"
  laco:
    StrCmp $2 "" feito
    StrCmp $2 "." proximo
    StrCmp $2 ".." proximo
    StrCpy $0 1
    Goto feito
  proximo:
    FindNext $1 $2
    Goto laco
  feito:
    FindClose $1
  fim:
FunctionEnd

; $2 = arquivo; $0 vira 1 se ele existe e outro processo o está usando (abrir para escrita falha em programa em execução)
Function TestaEmUso
  IfFileExists "$2" 0 fim
  ClearErrors
  FileOpen $3 "$2" a
  IfErrors 0 livre
    StrCpy $0 1
    Goto fim
  livre:
    FileClose $3
  fim:
FunctionEnd

; $0 = 1 se o programa já instalado nesta pasta está aberto (reinstalar apagaria arquivos em uso e deixaria a instalação pela metade)
Function AppAberto
  StrCpy $0 0
  StrCpy $2 "$INSTDIR\env\python.exe"
  Call TestaEmUso
  StrCmp $0 1 fim
  StrCpy $2 "$INSTDIR\env\pythonw.exe"
  Call TestaEmUso
  StrCmp $0 1 fim
  StrCpy $2 "$INSTDIR\env\Library\bin\Qt6Core.dll"
  Call TestaEmUso
  fim:
FunctionEnd

; pasta com arquivos de outra coisa: instala numa subpasta própria, para nunca apagar o que não é nosso
Function AjustaPasta
  Call PastaOcupada
  StrCmp $0 1 0 +2
    StrCpy $INSTDIR "$INSTDIR\OpenBIM Studio"
FunctionEnd

Function PastaLeave
  StrCpy $3 "$INSTDIR"
  Call AjustaPasta
  StrCmp $3 "$INSTDIR" +2
    MessageBox MB_OK|MB_ICONINFORMATION "A pasta escolhida já tem outros arquivos. O programa será instalado em: $INSTDIR"
FunctionEnd

Section "OpenBIM Studio"
  ; também na instalação silenciosa (as páginas não rodam)
  Call AjustaPasta
  Call PastaOcupada
  StrCmp $0 0 +3
    MessageBox MB_OK|MB_ICONSTOP "A pasta de instalação já tem outros arquivos. Escolha outra pasta. Nada foi instalado." /SD IDOK
    Abort
  ; programa aberto: nada é apagado; pede para fechar (na instalação silenciosa, cancela com código de erro)
  verificar_aberto:
    Call AppAberto
    StrCmp $0 0 livre
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "O OpenBIM Studio está aberto. Feche o programa e clique em Tentar novamente. Nada foi apagado." /SD IDCANCEL IDRETRY verificar_aberto
    Abort "O OpenBIM Studio está aberto. Nada foi alterado."
  livre:
  ; espaço necessário (KB): o programa instalado ocupa ~1,4 GB; a página de pasta avisa se não couber
  AddSize 1500000
  SetOutPath "$INSTDIR"
  ; instalar por cima de versão anterior: limpa env\ e app\ para não misturar arquivos velhos e novos
  RMDir /r "$INSTDIR\env"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\licenses"
  File /r "${PASTA_PACOTE}\*.*"
  ; ambiente conda: um tar.gz único, extraído com o tar.exe do Windows (10 e 11)
  InitPluginsDir
  DetailPrint "Copiando o pacote do programa (cerca de 310 MB)..."
  File "/oname=$PLUGINSDIR\env.tgz" "${ENV_TGZ}"
  DetailPrint "Extraindo os arquivos do programa; isto leva de 1 a 3 minutos e a janela pode parecer parada..."
  nsExec::ExecToLog '"$SYSDIR\tar.exe" -xzf "$PLUGINSDIR\env.tgz" -C "$INSTDIR"'
  Pop $0
  StrCmp $0 0 +9
    RMDir /r "$INSTDIR\env"
    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\licenses"
    Delete "$INSTDIR\LGPL-COMO-TROCAR.md"
    Delete "$INSTDIR\FONTES.md"
    RMDir "$INSTDIR"
    MessageBox MB_OK|MB_ICONSTOP "Falha ao extrair os arquivos do programa (código $0). Nada foi instalado." /SD IDOK
    Abort
  Delete "$PLUGINSDIR\env.tgz"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\OpenBIM Studio"
  CreateShortcut "$SMPROGRAMS\OpenBIM Studio\OpenBIM Studio.lnk" "$INSTDIR\env\pythonw.exe" '-I "$INSTDIR\app\OpenBIM-Studio.pyw"' "$INSTDIR\env\pythonw.exe"
  CreateShortcut "$SMPROGRAMS\OpenBIM Studio\Desinstalar.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\OpenBIM Studio.lnk" "$INSTDIR\env\pythonw.exe" '-I "$INSTDIR\app\OpenBIM-Studio.pyw"' "$INSTDIR\env\pythonw.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenBIM Studio" "DisplayName" "OpenBIM Studio"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenBIM Studio" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenBIM Studio" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenBIM Studio" "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\OpenBIM Studio\OpenBIM Studio.lnk"
  Delete "$SMPROGRAMS\OpenBIM Studio\Desinstalar.lnk"
  RMDir "$SMPROGRAMS\OpenBIM Studio"
  Delete "$DESKTOP\OpenBIM Studio.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenBIM Studio"
  ; apaga só o que o instalador criou; a pasta de instalação só some se ficar vazia
  ; (se o usuário escolheu uma pasta que já tinha arquivos dele, eles ficam intactos)
  RMDir /r "$INSTDIR\env"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\licenses"
  Delete "$INSTDIR\LGPL-COMO-TROCAR.md"
  Delete "$INSTDIR\FONTES.md"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
