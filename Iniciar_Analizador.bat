@echo off
REM Lanzador del Analizador de Series (copia standalone, env dedicado analizador_series).
REM %~dp0 = carpeta de este .bat = raiz del proyecto -> cwd correcto para `python -m`.
cd /d "%~dp0"

REM Python del env conda "analizador_series"; si no esta en la ruta por defecto
REM (otra PC u otra instalacion de conda), usa el python activo en el PATH.
set "PY=%USERPROFILE%\.conda\envs\analizador_series\python.exe"
if not exist "%PY%" set "PY=python"

set PYTHONIOENCODING=utf-8

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
    set LOCAL_IP=%%a
    goto :ip_found
)
:ip_found
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo  =====================================================================
echo   ANALIZADOR DE SERIES - Aseguramiento de Datos (copia de desarrollo)
echo   SENAMHI - Subdireccion de Gestion de Redes de Observacion
echo  =====================================================================
echo.
echo   Pestanas: Vista cruda / Estadistica / Comparar / Panorama /
echo   Emplazamiento compartido (automatica vs convencional co-ubicada).
echo.
echo   Tu PC     : http://localhost:8054
echo   Red local : http://%LOCAL_IP%:8054
echo.
echo   NOTA: puerto distinto al original (8053, repo SGO) para poder
echo   correr ambas copias a la vez sin conflicto.
echo.
echo   Datos leidos de:  DATA\datos_meteo\
echo.
echo  =====================================================================
echo   Presiona Ctrl+C para detener el servidor.
echo  =====================================================================
echo.

"%PY%" -m analizador_series.app

echo.
echo  El servidor se detuvo. Presiona cualquier tecla para cerrar.
pause >nul
