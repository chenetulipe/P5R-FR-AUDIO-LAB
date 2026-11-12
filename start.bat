@echo off
chcp 65001 > nul
cd /d "%~dp0"
title P5R FR Audio Lab

echo.
echo   P5R FR Audio Lab - PERSONA 5 ROYAL MOD VF
echo   -----------------------------------------
echo.

rem 1. Trouver Python (sinon l'installer automatiquement)
set "PYEXE="
set "PYARG="
py -3 --version > nul 2> nul && (set "PYEXE=py" & set "PYARG=-3")
if not defined PYEXE python --version > nul 2> nul && set "PYEXE=python"
if not defined PYEXE (
    echo   Python n'est pas installe : installation automatique, patiente un peu...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
    echo.
    echo   Impossible d'installer Python automatiquement.
    echo   Installe-le depuis https://www.python.org/downloads/ puis relance ce fichier.
    pause
    exit /b 1
)

:launch
rem 2. Dependances Python (rapide si deja installees)
echo   Verification des dependances...
"%PYEXE%" %PYARG% -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo   L'installation des dependances a echoue. Verifie ta connexion internet puis relance.
    pause
    exit /b 1
)

rem 3. Outils audio (vgmstream, VGAudio) : telecharges au premier lancement
"%PYEXE%" %PYARG% server\install_tools.py
if errorlevel 1 (
    echo   Le telechargement des outils audio a echoue. Verifie ta connexion internet puis relance.
    pause
    exit /b 1
)

rem 4. Lancement (le navigateur s'ouvre tout seul)
echo   Lancement sur http://127.0.0.1:8005
echo   Laisse cette fenetre ouverte, ferme-la pour arreter l'outil.
echo.
"%PYEXE%" %PYARG% server\app.py
rem Code 3 = mise a jour installee : on relance sans rouvrir le navigateur
if errorlevel 3 if not errorlevel 4 (
    echo.
    echo   Mise a jour installee, redemarrage...
    set "P5R_NO_BROWSER=1"
    goto launch
)
pause
