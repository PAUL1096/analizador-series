# Analizador de Series meteorológicas

Herramienta **Dash** (puerto **8054**) de **aseguramiento de datos** (no QC) sobre series meteorológicas
ya descargadas de SIGMA. Descubre y ayuda a clasificar afectaciones **AF-\*** (MISS, GAP, OUT, NOIS,
BIAS, CST, REP) en las series de estaciones automáticas y convencionales.

Pestañas: Vista cruda · Estadística · Comparar · Panorama · **Emplazamiento compartido**
(estación automática vs. convencional co-ubicada, <100 m; excluye estaciones hidrológicas EHA/HLG/HLM).

> Extraída del repo `Dashboard-para-monitoreo-de-la-operatividad` (SGO) el **2026-07-14** para vivir
> como proyecto propio con entorno dedicado. Ver `docs/ESTADO_MIGRACION_Y_PENDIENTES.md`.

## Instalación desde GitHub (PC nueva)

Requisitos previos: **conda** (Anaconda/Miniconda), **Git** y **Google Chrome** (el descargador
hace el login de SIGMA con Chrome vía Selenium; el driver se resuelve solo).

```bash
# 1. Clonar (el repo es privado: tu cuenta de GitHub debe tener acceso)
git clone https://github.com/PAUL1096/analizador-series.git
cd analizador-series

# 2. Crear el entorno
conda create -n analizador_series python=3.12 -y
conda run -n analizador_series pip install -r requirements.txt

# 3. Credenciales de SIGMA (solo hacen falta para DESCARGAR)
copy sigma\.env.example sigma\.env      # en Git Bash: cp sigma/.env.example sigma/.env
```

Editar `sigma/.env` y completar **tu** usuario y contraseña de SIGMA:

```
SIGMA_URL=https://www.senamhi.gob.pe/sigma-dev
SIGMA_USUARIO=tu_usuario_sigma
SIGMA_PASSWORD=tu_password_aqui
```

`sigma/.env` está en `.gitignore`: **nunca** se sube al repo. Cada persona usa sus propias credenciales.

```bash
# 4. Descargar series (el clon trae el catálogo de estaciones, pero NO series: DATA/ no se versiona)
Descargar_Datos_Meteo.bat                                   # menú interactivo
Descargar_Datos_Meteo.bat --codigo 106077 100043 --headless # o directo por código

# 5. Abrir el analizador
Iniciar_Analizador.bat          # -> http://localhost:8054
```

Los `.bat` buscan el Python del env en `%USERPROFILE%\.conda\envs\analizador_series\`; si conda está
instalado en otra ruta, activar el env (`conda activate analizador_series`) antes de ejecutarlos.

## Estructura

```
analizador-series/
├── analizador_series/     # paquete Dash (core/ lógica pura · ui/ capa Dash · config/)
├── descarga/              # descargar_datos_meteo_sigma.py (series desde SIGMA)
├── data_ref/estaciones.db # catálogo de estaciones (versionado; extraído de sgo.db, sin
│                          #   entidad_responsable/propiedad_terreno)
├── sigma/.env.example     # plantilla de credenciales → copiar a sigma/.env (gitignored)
├── DATA/                  # series y cachés locales (gitignored, se generan al descargar/usar)
├── docs/                  # specs (Fase 1, control de calidad, emplazamiento compartido)
└── requirements.txt
```

Env dedicado conda **`analizador_series`** (Python 3.12), aislado de `miambiente` (producción SGO)
para no arrastrar `ruptures`/`scipy`/`dash-ag-grid` al pipeline SGO.

## Uso sin los .bat

```bash
conda activate analizador_series
python -m analizador_series.app                                        # dashboard
python descarga/descargar_datos_meteo_sigma.py --categoria automatica --dz 1 4   # descarga masiva
python descarga/descargar_datos_meteo_sigma.py --help                  # todas las opciones
python -m pytest -q                                                    # tests
```

## Notas

- `data_ref/estaciones.db` es un snapshot del catálogo de SGO: se desactualiza con altas/bajas de
  estaciones. Coordenadas, altitud y región se refrescan con `data_ref/actualizar_geodatos.py`.
- Pendientes de diseño: ver `docs/ESTADO_MIGRACION_Y_PENDIENTES.md`.
