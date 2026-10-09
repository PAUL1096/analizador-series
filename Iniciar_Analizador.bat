@echo off
REM Lanzador del Analizador de Series (copia standalone, env dedicado analizador_series).
REM %~dp0 = carpeta de este .bat = raiz del proyecto -> cwd correcto para `python -m`.
cd /d "%~dp0"

REM Busca el Python del entorno conda "analizador_series" en las rutas habituales
REM de Anaconda/Miniconda. Si no lo encuentra, usa el "python" del PATH (sirve si
REM se ejecuta desde un Anaconda Prompt con "conda activate analizador_series").
set "PY=python"
for %%D in ("%USERPROFILE%\.conda\envs" "%USERPROFILE%\anaconda3\envs" "%USERPROFILE%\miniconda3\envs" "C:\ProgramData\anaconda3\envs" "C:\ProgramData\miniconda3\envs") do (
    if exist "%%~D\analizador_series\python.exe" set "PY=%%~D\analizador_series\python.exe"
)

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
