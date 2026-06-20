@echo off
title AION-Core
echo.
echo  ================================================
echo   AION-Core v1.0 — AI-First Personal Orchestrator
echo  ================================================
echo.

cd /d C:\code\python\AION-Core
call .venv\Scripts\activate

echo Demarrage AION-Core...
python main.py

pause
