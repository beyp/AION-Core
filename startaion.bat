@echo off
title AION-Core
cls

:START
echo.
echo  ================================================
echo   AION-Core v1.0 ^— AI-First Personal Orchestrator
echo  ================================================
echo.

cd /d C:\code\python\AION-Core

:: ── Liberer le port 8000 si occupe ─────────────────────────────
echo  [1/3] Verification port 8000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo  [!] Port 8000 occupe par PID %%a ^- Liberation en cours...
    taskkill /PID %%a /F >nul 2>&1
    timeout /t 1 /nobreak >nul
)
echo  [OK] Port 8000 libre.

:: ── Activer le venv ─────────────────────────────────────────────
echo  [2/3] Activation environnement Python...
call .venv\Scripts\activate

:: ── Lancer AION ─────────────────────────────────────────────────
echo  [3/3] Demarrage AION-Core...
echo.
python main.py

:: ── Gestion du retour ────────────────────────────────────────────
:: os.execv() remplace le process Python → ce point n'est jamais atteint
:: Si on arrive ici c'est un crash ou arret manuel

if %ERRORLEVEL% EQU 0 (
    :: Arret propre (ex: restart via mise a jour deja gere par os.execv)
    goto END
)

:: Crash ou erreur
echo.
echo  [ERREUR] AION-Core s'est arrete avec le code %ERRORLEVEL%
echo  Redemarrage dans 5 secondes... (Ctrl+C pour annuler)
timeout /t 5 /nobreak >nul
cls
goto START

:END
echo.
echo  AION-Core arrete proprement.
pause
