@echo off
title AION-Core
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

pause
