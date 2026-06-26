@echo off
title AION-Core -- Suppression demarrage automatique
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

if exist "%STARTUP%\AION-Core.vbs" (
    del "%STARTUP%\AION-Core.vbs"
    echo [OK] Demarrage automatique desactive.
) else (
    echo [INFO] AION-Core n'etait pas en demarrage automatique.
)
if exist "%USERPROFILE%\Desktop\AION-Core.vbs" (
    del "%USERPROFILE%\Desktop\AION-Core.vbs"
    echo [OK] Raccourci bureau supprime.
)
pause
