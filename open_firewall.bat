@echo off
title AION-Core — Ouverture des ports Firewall
echo.
echo  ================================================
echo   AION-Core ^— Ouverture des ports Firewall
echo   (necessaire pour acces Tailscale / reseau local)
echo  ================================================
echo.

:: Verifier droits administrateur
net session >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Ce script necessite des droits Administrateur.
    echo  Clic droit ^> "Executer en tant qu'administrateur"
    pause & exit /b 1
)

echo  [1/5] AION-Core Dashboard (port 8000)...
netsh advfirewall firewall delete rule name="AION-Core Dashboard" >nul 2>&1
netsh advfirewall firewall add rule name="AION-Core Dashboard" dir=in action=allow protocol=TCP localport=8000
echo  [OK]

echo  [2/5] QuickMind API (port 8765)...
netsh advfirewall firewall delete rule name="AION QuickMind" >nul 2>&1
netsh advfirewall firewall add rule name="AION QuickMind" dir=in action=allow protocol=TCP localport=8765
echo  [OK]

echo  [3/5] ProjectMind API (port 8766)...
netsh advfirewall firewall delete rule name="AION ProjectMind" >nul 2>&1
netsh advfirewall firewall add rule name="AION ProjectMind" dir=in action=allow protocol=TCP localport=8766
echo  [OK]

echo  [4/5] AION Services (port 8001)...
netsh advfirewall firewall delete rule name="AION Services" >nul 2>&1
netsh advfirewall firewall add rule name="AION Services" dir=in action=allow protocol=TCP localport=8001
echo  [OK]

echo  [5/5] Verification Tailscale...
where tailscale >nul 2>&1
if not errorlevel 1 (
    echo  Tailscale detecte. Verification de l'interface...
    tailscale status 2>nul | findstr /i "100\."
) else (
    echo  [INFO] Tailscale non detecte dans le PATH.
)

echo.
echo  ================================================
echo   Ports ouverts avec succes !
echo.
echo   Teste depuis ta tablette/telephone :
echo   - AION Dashboard : http://[IP-Tailscale]:8000
echo   - QuickMind      : http://[IP-Tailscale]:8765
echo   - ProjectMind    : http://[IP-Tailscale]:8766
echo  ================================================
echo.

:: Afficher l'IP Tailscale si disponible
for /f "tokens=*" %%i in ('tailscale ip --4 2^>nul') do (
    echo   Ton IP Tailscale : http://%%i:8000
)

pause
