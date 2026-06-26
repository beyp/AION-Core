@echo off
title AION-Core -- Installation demarrage automatique
echo.
echo  ================================================
echo   AION-Core -- Demarrage automatique Windows
echo  ================================================
echo.

:: Repertoire Startup de l'utilisateur courant
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

:: Copier le lanceur VBS dans Startup
echo  [1/3] Copie du lanceur dans Startup...
copy /Y "%~dp0launch_aion.vbs" "%STARTUP%\AION-Core.vbs" >nul
if errorlevel 1 (
    echo  [ERREUR] Impossible de copier dans %STARTUP%
    pause & exit /b 1
)
echo  [OK] Lanceur installe : %STARTUP%\AION-Core.vbs

:: Creer un raccourci sur le bureau
echo  [2/3] Raccourci bureau...
set DESKTOP=%USERPROFILE%\Desktop
copy /Y "%~dp0launch_aion.vbs" "%DESKTOP%\AION-Core.vbs" >nul 2>&1
if not errorlevel 1 echo  [OK] Raccourci cree sur le bureau

:: Test de lancement immediat
echo  [3/3] Lancement d'AION-Core...
start "" wscript.exe "%STARTUP%\AION-Core.vbs"

echo.
echo  ================================================
echo   Installation terminee !
echo.
echo   AION-Core se lancera automatiquement
echo   au prochain demarrage de Windows.
echo.
echo   Pour desinstaller :
echo   del "%STARTUP%\AION-Core.vbs"
echo  ================================================
echo.
pause
