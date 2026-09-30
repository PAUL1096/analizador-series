@echo off
REM Lanzador del Analizador de Series (copia standalone, env dedicado analizador_series).
REM %~dp0 = carpeta de este .bat = raiz del proyecto -> cwd correcto para `python -m`.
cd /d "%~dp0"

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
echo   Pestanas: Panorama (indice de triaje AF-*) / Comparar (consistencia
echo   cruzada) / Estadistica (series derivadas y distribuciones).
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

"C:\Users\drd06\.conda\envs\analizador_series\python.exe" -m analizador_series.app

echo.
echo  El servidor se detuvo. Presiona cualquier tecla para cerrar.
pause >nul
