@echo off
REM Lanzador de descarga de datos meteorologicos por estacion (SIGMA-DRD).
REM %~dp0 = carpeta de este .bat = raiz del proyecto -> cwd correcto para el script.
cd /d "%~dp0"

REM Busca el Python del entorno conda "analizador_series" en las rutas habituales
REM de Anaconda/Miniconda. Si no lo encuentra, usa el "python" del PATH (sirve si
REM se ejecuta desde un Anaconda Prompt con "conda activate analizador_series").
set "PY=python"
for %%D in ("%USERPROFILE%\.conda\envs" "%USERPROFILE%\anaconda3\envs" "%USERPROFILE%\miniconda3\envs" "C:\ProgramData\anaconda3\envs" "C:\ProgramData\miniconda3\envs") do (
    if exist "%%~D\analizador_series\python.exe" set "PY=%%~D\analizador_series\python.exe"
)

REM ─────────────────────────────────────────────────────────────────────────
REM  Si se pasan argumentos directamente, ejecutar sin preguntar.
REM  Ejemplo:
REM    Descargar_Datos_Meteo.bat --codigo 114066 --headless
REM ─────────────────────────────────────────────────────────────────────────
if not "%~1"=="" (
    "%PY%" descarga\descargar_datos_meteo_sigma.py %*
    goto fin
)

echo.
echo  ==============================================================
echo   DESCARGA DATOS METEOROLOGICOS POR ESTACION - SIGMA
echo   SENAMHI - Subdireccion de Gestion de Redes de Observacion
echo  ==============================================================
echo.
echo   Descarga series de tiempo por estacion:
echo     Columnas: Fecha, Hora, n_variable, flag_n_variable, ...
echo     Resolucion: 10 min / horaria / diaria segun variable
echo     Salida: DATA\datos_meteo\automaticas\  y  DATA\datos_meteo\convencionales\
echo.

REM ── MODO DE SELECCION ──────────────────────────────────────────────────────
echo   Modo de descarga:
echo     [1] Estaciones puntuales por codigo  -- para analisis especificos
echo     [2] Por DZ o categoria               -- para descargas masivas
echo.
SET /P MODO="  Opcion [1/2, default=1]: "
if "%MODO%"=="2" goto :modo_masivo

REM ── MODO PUNTUAL: por codigo ────────────────────────────────────────────────
:modo_puntual
echo.
echo   Ingresa los codigos separados por espacios (mira el codigo en
echo   data_ref/estaciones.db o en la pestana Emplazamiento compartido del Analizador).
echo   Ejemplo:  114066   (o varios:  114066 114140)
echo.
SET /P CODIGOS="  Codigos: "
if "%CODIGOS%"=="" (
    echo   Error: debes ingresar al menos un codigo.
    goto :fin
)
SET ARGS=--codigo %CODIGOS%
goto :fechas

REM ── MODO MASIVO: por DZ / categoria ────────────────────────────────────────
:modo_masivo
echo.
echo   Categoria de estaciones:
echo     [1] Ambas  (automaticas + convencionales)  -- default
echo     [2] Solo automaticas
echo     [3] Solo convencionales
echo.
SET /P CATOPT="  Opcion [1/2/3]: "
if "%CATOPT%"=="2" (set CAT=automatica) else if "%CATOPT%"=="3" (set CAT=convencional) else (set CAT=ambas)

SET /P DZS="  DZs (ej: 1 4 8  -- dejar en blanco = TODAS): "
echo.

SET ARGS=--categoria %CAT%
if not "%DZS%"=="" SET ARGS=%ARGS% --dz %DZS%

REM ── FECHAS (comun a ambos modos) ────────────────────────────────────────────
:fechas
echo.
echo   Periodo de descarga:
echo   (dejar en blanco = semana anterior calculada automaticamente)
echo.
SET /P FI="  Fecha inicio (YYYY-MM-DD): "
SET /P FF="  Fecha fin    (YYYY-MM-DD): "
echo.

REM ── OPCIONES ───────────────────────────────────────────────────────────────
SET /P HEADLESS="  Ocultar ventana Chrome durante login? (s/n  default: n): "
SET /P REDOWN="  Re-descargar CSVs que ya existen?    (s/n  default: n): "
echo.

if not "%FI%"==""       SET ARGS=%ARGS% --fecha-inicio %FI%
if not "%FF%"==""       SET ARGS=%ARGS% --fecha-fin %FF%
if /i "%HEADLESS%"=="s" SET ARGS=%ARGS% --headless
if /i "%REDOWN%"=="s"   SET ARGS=%ARGS% --no-omitir

echo  --------------------------------------------------------------
echo   Iniciando descarga con:  %ARGS%
echo  --------------------------------------------------------------
echo.

"%PY%" descarga\descargar_datos_meteo_sigma.py %ARGS%

:fin
echo.
echo  Descarga finalizada. Presiona cualquier tecla para cerrar.
pause >nul
