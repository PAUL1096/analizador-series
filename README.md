# Analizador de Series meteorológicas

Herramienta **Dash** (puerto 8053) de **aseguramiento de datos** (no QC) sobre series meteorológicas
ya descargadas de SIGMA. Descubre y ayuda a clasificar afectaciones **AF-\*** (MISS, GAP, OUT, NOIS,
BIAS, CST, REP) en las series de estaciones automáticas y convencionales.

> Extraída del repo `Dashboard-para-monitoreo-de-la-operatividad` (SGO) el **2026-07-14** para vivir
> como proyecto propio con entorno dedicado. Ver `docs/ESTADO_MIGRACION_Y_PENDIENTES.md`.

## Estructura

```
Analizador-Series/
├── analizador_series/     # paquete Dash (core/ lógica pura · ui/ capa Dash · config/)
├── descarga/              # descargar_datos_meteo_sigma.py (series desde SIGMA)
├── DATA/datos_meteo/      # series por estación {CODIGO}_{fi}_{ff}.csv (snapshot, gitignored)
├── DATA/cache_dias_efectivos/  # caché en disco de "día efectivo" por estación (gitignored, ver docs/)
├── data_ref/estaciones.db # catálogo de estaciones (extraído de sgo.db; solo tabla `estaciones`)
├── sigma/.env             # credenciales SIGMA (gitignored — NUNCA versionar)
├── docs/                  # spec de rediseño Fase 1 + referencias QC de la comunidad
└── requirements.txt
```

## Entorno

Env dedicado conda **`analizador_series`** (Python 3.12) — aislado de `miambiente` (producción SGO)
para no arrastrar `ruptures`/`scipy`/`dash-ag-grid` al pipeline SGO.

```bash
# Recrear el entorno desde cero:
conda create -n analizador_series python=3.12 -y
conda run -n analizador_series pip install -r requirements.txt
```

## Uso

```bash
# Dashboard (o doble clic en Iniciar_Analizador.bat)
python -m analizador_series.app        # -> http://localhost:8053

# Descargar series nuevas desde SIGMA (requiere sigma/.env)
python descarga/descargar_datos_meteo_sigma.py --categoria automatica --dz 1 4
```

## Antes de publicar (repo público)

- `sigma/.env` y `DATA/datos_meteo/` ya están en `.gitignore`.
- **Revisar `data_ref/estaciones.db`**: contiene metadata (`entidad_responsable`, `propiedad_terreno`)
  que quizá no deba ser pública. Está gitignored por defecto.
- Rediseño Fase 1 pendiente: ver `docs/2026-07-13-rediseno-fase1-design.md` y
  `docs/referencias_qc_comunidad.md` (librerías a adoptar: `ioos_qc`, `MetObs-toolkit`, `ruptures`).
