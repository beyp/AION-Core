@echo off
title AION-Core Installation
echo.
echo  ================================
echo   AION-Core — Installation
echo  ================================
echo.

cd /d C:\code\python\AION-Core

echo [1/4] Creation du venv...
python -m venv .venv

echo [2/4] Activation du venv...
call .venv\Scripts\activate

echo [3/4] Installation des dependances...
pip install -r requirements.txt

echo [4/4] Configuration...
if not exist .env (
    copy .env.example .env
    echo Fichier .env cree. Edite-le avec tes cles API.
)

if not exist data mkdir data
if not exist logs mkdir logs

echo.
echo  ================================
echo   Installation terminee !
echo  ================================
echo.
echo  Etapes suivantes :
echo  1. Edite .env avec ta GROQ_API_KEY
echo  2. Lance : startaion.bat
echo  3. Ouvre : http://localhost:8000
echo.
pause
