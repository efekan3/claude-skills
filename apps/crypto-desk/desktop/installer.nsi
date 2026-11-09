; Koersdesk per-user Windows installer (no administrator rights needed).
; Build: makensis installer.nsi   (after `npm run build:win`)
Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!define APP "Koersdesk"
!define VERSION "1.0.0"
!define SRC "dist\Koersdesk-win32-x64"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

!include "MUI2.nsh"

Name "${APP}"
OutFile "dist\Koersdesk-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP}"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
BrandingText "${APP} ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "${APP} installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "${APP}"

!define MUI_ICON "icon.ico"
!define MUI_UNICON "icon.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Koersdesk.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Koersdesk now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Koersdesk (required)" SecApp
  SectionIn RO
  ; Close a running copy so files can be replaced on update.
  nsExec::Exec 'taskkill /IM Koersdesk.exe /F'
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  File "icon.ico"
  WriteUninstaller "$INSTDIR\Uninstall Koersdesk.exe"
  WriteRegStr HKCU "Software\${APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${APP}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall Koersdesk.exe"'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  CreateShortCut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\Koersdesk.exe" "" "$INSTDIR\icon.ico" 0
SectionEnd

Section "Desktop shortcut" SecDesk
  CreateShortCut "$DESKTOP\${APP}.lnk" "$INSTDIR\Koersdesk.exe" "" "$INSTDIR\icon.ico" 0
SectionEnd

LangString DESC_App ${LANG_ENGLISH} "The Koersdesk app and a Start menu shortcut."
LangString DESC_Desk ${LANG_ENGLISH} "A Koersdesk shortcut on your desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} $(DESC_App)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesk} $(DESC_Desk)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  nsExec::Exec 'taskkill /IM Koersdesk.exe /F'
  Delete "$DESKTOP\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\${APP}"
SectionEnd
