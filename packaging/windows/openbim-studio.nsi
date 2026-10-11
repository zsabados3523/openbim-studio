; SPDX-License-Identifier: AGPL-3.0-or-later
; Instalador do OpenBIM Studio (NSIS). Instalação por usuário (sem administrador), pasta própria.
; Variáveis (passadas por makensis /D): PASTA_PACOTE (pasta pronta com env\, app\, licenses\ ...),
; SAIDA (caminho do .exe), VERSAO, ENV_TXZ (env.txz com a pasta env\ inteira).
Unicode true
!include "MUI2.nsh"

Name "OpenBIM Studio"
OutFile "${SAIDA}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\OpenBIM Studio"
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_LICENSE "${PASTA_PACOTE}\licenses\AGPL-3.0-or-later.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "OpenBIM Studio"
  SetOutPath "$INSTDIR"
  File /r "${PASTA_PACOTE}\*.*"
  ; ambiente conda: um tar.xz único, extraído com o tar.exe do Windows (10 e 11)
  InitPluginsDir
  SetCompress off ; o tar.xz já está compactado
  File "/oname=$PLUGINSDIR\env.txz" "${ENV_TXZ}"
  SetCompress auto
  nsExec::ExecToLog '"$SYSDIR\tar.exe" -xf "$PLUGINSDIR\env.txz" -C "$INSTDIR"'
  Pop $0
  StrCmp $0 0 +3
    MessageBox MB_OK|MB_ICONSTOP "Falha ao extrair os arquivos do programa (código $0)."
    Abort
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\OpenBIM Studio"
  CreateShortcut "$SMPROGRAMS\OpenBIM Studio\OpenBIM Studio.lnk" "$INSTDIR\env\pythonw.exe" '"$INSTDIR\app\OpenBIM-Studio.pyw"' "$INSTDIR\env\pythonw.exe"
  CreateShortcut "$SMPROGRAMS\OpenBIM Studio\Desinstalar.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\OpenBIM Studio.lnk" "$INSTDIR\env\pythonw.exe" '"$INSTDIR\app\OpenBIM-Studio.pyw"' "$INSTDIR\env\pythonw.exe"
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
  ; só apaga a pasta se for mesmo a do programa (evita apagar uma pasta escolhida por engano)
  IfFileExists "$INSTDIR\app\OpenBIM-Studio.pyw" 0 +2
    RMDir /r "$INSTDIR"
SectionEnd
