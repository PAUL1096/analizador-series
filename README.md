# Analizador de Series meteorológicas

Herramienta web local (Dash, se abre en el navegador) de **aseguramiento de datos** sobre
series meteorológicas descargadas de **SIGMA**. Ayuda a descubrir y clasificar afectaciones
**AF-\*** (MISS, GAP, OUT, NOIS, BIAS, CST, REP) en estaciones automáticas y convencionales.

Pestañas:

| Pestaña | Para qué sirve |
|---|---|
| **Vista cruda** | Ver las series tal como vienen de SIGMA, con días efectivos y valores sospechosos. |
| **Estadística** | Series derivadas, distribuciones y eventos que superan un percentil. |
| **Comparar** | Consistencia entre variables de una misma estación. |
| **Panorama** | Índice de triaje AF-\* de varias estaciones a la vez. |
| **Emplazamiento compartido** | Estación automática vs. convencional que comparten emplazamiento (<100 m). No incluye estaciones hidrológicas (EHA, HLG, HLM). |

---

## Instalación paso a paso (Windows)

Se hace **una sola vez por computadora**. Toma unos 15 minutos.

### 0. Lo que necesitas antes de empezar

| Requisito | Cómo conseguirlo |
|---|---|
| **Acceso al repositorio** | El repo es privado: pide al responsable que te agregue como colaborador en GitHub y acepta la invitación que llega a tu correo. |
| **Git** | Descargar e instalar desde <https://git-scm.com/download/win> (opciones por defecto). |
| **Anaconda o Miniconda** | <https://www.anaconda.com/download> o <https://docs.anaconda.com/miniconda/> (opciones por defecto). |
| **Google Chrome** | Lo usa el descargador para iniciar sesión en SIGMA. |
| **Usuario y contraseña de SIGMA** | Los tuyos propios, con permiso para consultar datos. |

### 1. Descargar el código

Abre **Anaconda Prompt** (búscalo en el menú Inicio) y ejecuta, una línea a la vez:

```bat
cd %USERPROFILE%\Documents
git clone https://github.com/PAUL1096/analizador-series.git
cd analizador-series
```

La primera vez, Git abre una ventana del navegador para que inicies sesión en GitHub.
Si dice *"Repository not found"*, tu cuenta todavía no tiene acceso (ver paso 0).

### 2. Crear el entorno de Python

En la misma ventana de Anaconda Prompt:

```bat
conda create -n analizador_series python=3.12 -y
conda activate analizador_series
pip install -r requirements.txt
```

Tarda unos minutos. Para comprobar que quedó bien:

```bat
python -m pytest -q
```

Debe terminar con algo como `251 passed, 1 skipped`, sin ningún `failed`.

### 3. Configurar tus credenciales de SIGMA

Solo hacen falta para **descargar** datos. En la misma ventana:

```bat
copy sigma\.env.example sigma\.env
notepad sigma\.env
```

En el Bloc de notas reemplaza los valores de ejemplo por los tuyos, guarda y cierra:

```
SIGMA_URL=https://www.senamhi.gob.pe/sigma-dev
SIGMA_USUARIO=tu_usuario_sigma      <- tu usuario
SIGMA_PASSWORD=tu_password_aqui     <- tu contraseña
```

> `sigma\.env` **nunca se sube a GitHub** (está excluido a propósito). Cada persona usa sus
> propias credenciales. No compartas ese archivo.

### 4. Descargar datos

El repositorio trae el catálogo de estaciones, pero **no trae series**: cada quien descarga
las que necesita. En la carpeta del proyecto, haz doble clic en **`Descargar_Datos_Meteo.bat`**
y responde el menú:

1. **Modo:** `1` para estaciones puntuales por código (lo habitual) o `2` para descargas
   masivas por DZ o categoría.
2. **Códigos:** separados por espacio, ej. `4728B11C 100043`.
3. **Fechas:** formato `AAAA-MM-DD`. Si las dejas en blanco, descarga la semana anterior.
4. **Ocultar Chrome / re-descargar:** Enter acepta el valor por defecto.

Los archivos quedan en `DATA\datos_meteo\automaticas\` y `DATA\datos_meteo\convencionales\`.

> Las **convencionales** suelen tener datos solo hasta algunos meses atrás (se digitan
> después). Si dice *"sin datos en el período"*, prueba con fechas más antiguas.

### 5. Abrir el analizador

Doble clic en **`Iniciar_Analizador.bat`** y abre en el navegador:

- **<http://localhost:8054>** desde tu computadora.
- La ventana negra también muestra una dirección de **red local** para abrirlo desde otra PC
  de la misma red.

Deja la ventana negra abierta mientras usas la herramienta; ciérrala (o `Ctrl+C`) para
detenerla. Si descargas datos nuevos con la herramienta abierta, usa el botón
**↺ Actualizar lista**.

---

## Actualizar a la última versión

En Anaconda Prompt, dentro de la carpeta del proyecto:

```bat
git pull
conda activate analizador_series
pip install -r requirements.txt
```

Tus datos descargados (`DATA\`) y tus credenciales (`sigma\.env`) no se tocan.

## Problemas frecuentes

| Mensaje o síntoma | Causa y solución |
|---|---|
| `Faltan credenciales de SIGMA en ...sigma\.env` | No hiciste el paso 3, o dejaste los valores de ejemplo. |
| Chrome se abre y el login falla o se queda esperando | Usuario/contraseña incorrectos en `sigma\.env`, o SIGMA no responde. Prueba entrar a SIGMA manualmente con el navegador. |
| `"python" no se reconoce como un comando...` al abrir un `.bat` | Conda está instalado en una ruta no habitual. Abre Anaconda Prompt, ejecuta `conda activate analizador_series`, entra a la carpeta del proyecto y ejecuta el `.bat` escribiendo su nombre. |
| `Codigo no encontrado en el catálogo` | El código no existe en `data_ref\estaciones.db` o está mal escrito. Revisa mayúsculas (ej. `4728B11C`). |
| La herramienta dice *"Sin datos descargados"* | Esa estación no tiene CSV en `DATA\`. Descárgala (paso 4). |
| La página no abre / puerto ocupado | Ya hay otro analizador abierto. Cierra la otra ventana negra. |

---

## Uso desde la línea de comandos (opcional)

Con el entorno activo (`conda activate analizador_series`), desde la carpeta del proyecto:

```bat
REM Abrir el analizador
python -m analizador_series.app

REM Descargar estaciones puntuales en un periodo
python descarga\descargar_datos_meteo_sigma.py --codigo 4728B11C 100043 --fecha-inicio 2026-06-01 --fecha-fin 2026-06-30

REM Descarga masiva (automaticas de las DZ 1 y 4)
python descarga\descargar_datos_meteo_sigma.py --categoria automatica --dz 1 4

REM Todas las opciones del descargador
python descarga\descargar_datos_meteo_sigma.py --help

REM Pruebas automaticas
python -m pytest -q
```

## Estructura del proyecto

```
analizador-series/
├── Iniciar_Analizador.bat      # abre la herramienta (http://localhost:8054)
├── Descargar_Datos_Meteo.bat   # descarga series desde SIGMA (menú)
├── analizador_series/          # código de la herramienta (core/ lógica · ui/ pantallas · config/)
├── descarga/                   # descargador de series desde SIGMA
├── data_ref/estaciones.db      # catálogo de estaciones (código, nombre, DZ, clasificación, coordenadas)
├── sigma/.env.example          # plantilla de credenciales → copiar a sigma/.env
├── DATA/                       # series descargadas y cachés (se crea solo; no se sube a GitHub)
├── docs/                       # especificaciones técnicas
├── tests/                      # pruebas automáticas
└── requirements.txt            # dependencias de Python
```

## Notas

- El catálogo `data_ref/estaciones.db` es una foto fija: no refleja altas o bajas de
  estaciones posteriores. Coordenadas, altitud y región se refrescan con
  `data_ref/actualizar_geodatos.py` a partir de un export "Georeferencias" de SIGMA.
- El control de calidad (BUENO/DUDOSO/MALO) es propio de esta herramienta y se calcula en
  tu computadora: no reemplaza el control de calidad oficial de la SGD ni se envía a
  ningún sistema.
