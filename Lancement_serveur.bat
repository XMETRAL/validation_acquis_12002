@echo off
cd /d "%~dp0"
REM === Site validation_acquis (serveur_web) : exe dedie + server.py/.env2 ===

REM 1) Port lu dans .env2 (pour arreter proprement l'instance precedente)
set "PORT="
if exist ".env2" for /f "usebackq tokens=1,2 delims==" %%A in (".env2") do if /i "%%A"=="BACKEND_PORT" set "PORT=%%B"
if not defined PORT set "PORT=12002"

REM 2) Interpreteur dedie a ce site (copie de python.exe)
set "PYEXE=%~dp0Axe-SRVWEB-12002.exe"

REM 3) Arreter UNIQUEMENT ce serveur : son port + son exe dedie (isolation)
REM    (refait a chaque relance : boucle ci-dessous)
:boucle
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  echo Instance sur le port %PORT% - PID %%P - arret...
  taskkill /PID %%P /F >nul 2>&1
)
for %%D in ("%PYEXE%") do taskkill /IM "%%~nxD" /F >nul 2>&1
REM Laisse le temps au port de se liberer (ping : "timeout" echoue sans console)
ping -n 3 127.0.0.1 >nul

REM 4) Lancement de server.py (qui lit .env2 et demarre Waitress)
echo [%date% %time%] Demarrage du serveur >> relance_serveur.log
"%PYEXE%" server.py
REM 5) Serveur arrete : relance automatique (la tache planifiee reste active)
echo [%date% %time%] Serveur arrete (code %errorlevel%), relance dans 10 s >> relance_serveur.log
ping -n 11 127.0.0.1 >nul
goto boucle
