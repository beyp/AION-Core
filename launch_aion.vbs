
' AION-Core Launcher — Lance AION-Core silencieusement au demarrage Windows
' Placer dans : C:\Users\[User]\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\
' Ou utiliser le script install_startup.bat pour le faire automatiquement

Dim WshShell
Set WshShell = WScript.CreateObject("WScript.Shell")

' Chemin du projet AION-Core
Dim aionPath
aionPath = "C:\code\python\AION-Core"

' Lancer startaion.bat de maniere invisible
WshShell.Run "cmd /c """ & aionPath & "\startaion.bat""", 0, False

Set WshShell = Nothing
