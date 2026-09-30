# Spec: vecindad — Comparación visual automática↔convencional co-ubicada

Module id: `vecindad` (capability map: `control-calidad` → `vecindad`, depende de
`control-calidad` solo para su checkbox de CC — el resto es independiente).

## Objetivo

Hoy el Analizador no tiene forma de ver, en un mismo gráfico, la serie de una
estación automática junto a la de la convencional que comparte su emplazamiento
(<100m) — la pestaña "Comparar" existente es estructuralmente de una sola estación
(compara dos VARIABLES de la misma estación, no dos ESTACIONES). Se necesita una
pestaña nueva que permita elegir un par co-ubicado y ver ambas series superpuestas,
para inspección visual rápida (¿la automática y la convencional cuentan más o menos
la misma historia, o hay algo raro?) — sin pretender la rigurosidad estadística de un
estudio de validación formal.

**Quién lo usa:** el equipo de SGR, para una revisión visual rápida de cualquier
estación de la red que tenga una convencional cerca — no reemplaza estudios de
comparación formales (ver "Relación con otros proyectos" abajo).

**Qué es éxito:** elegir un par de la lista (204 candidatos ya validados por
distancia real), elegir "Temperatura" o "Precipitación", y ver la serie continua de
la automática con los puntos de la convencional superpuestos, distinguibles a simple
vista (no una línea conectando 3 puntos/día, que sugeriría falsamente continuidad).

## Relación con otros proyectos (para no confundir alcance)

**PLIA** (`SGR TEMPORALES/PLIA/`) es un proyecto de investigación completo y aparte,
con su propio crosswalk verificado de 17 pares y una batería estadística rigurosa
(`scripts/comparacion_core.py`: sesgo/MAE/RMSE, Kendall/Pearson, KS, BIASS/POD/FAR,
coeficiente de inconsistencia — citando SMN NT 2023-135 y NT 2024-167). **Decisión
explícita del usuario: son herramientas separadas.** `vecindad` no reemplaza ni
reimplementa esa rigurosidad — es una vista rápida para explorar CUALQUIER par de la
red (no solo esos 17), usando el emparejamiento por distancia GPS ya calculado. Se
usaron los CSV reales de PLIA únicamente para confirmar la nomenclatura real de
variables convencionales (ver siguiente sección) — ninguna lógica ni dato de PLIA se
importa al Analizador.

## Qué se confirmó con datos reales de PLIA (cambia el diseño original)

El CSV real `PLIA/convencionales/104098_2025-09-01_2026-07-31.csv` (335 días,
estación SAN REGIS convencional) mostró la estructura real:

```
Fecha,Hora,n_pt101,n_pt102,n_pt103,n_tm102,n_tm103,n_tm104,n_tm105,n_tm106,n_tm107,n_tm108,n_tm109
```

- **Un único registro por día** (Hora siempre "00:00"), con TODAS las variables de
  ese día ya en la misma fila — no hay que alinear por hora, coincide con el diseño
  ya implícito en `control_calidad.evaluar_coherencia_interna` (comparación fila a
  fila).
- **Sin columnas `flag_*`** en absoluto — a diferencia de las automáticas. El
  mecanismo de CC (`control_calidad.agregar_columnas_cc` +
  `data_loader.filtrar_por_flags`) ya tolera esto sin cambios (si `flag_col` no
  existe, se lo salta).
- **Sin humedad relativa ni presión** — coincide con lo que ya se sabía (ningún CSV
  convencional visto hasta ahora las trae). El diccionario de equivalencia de
  variables queda acotado a temperatura y precipitación únicamente para v1.
- **`n_tm107/108/109` son temperatura de BULBO HÚMEDO**, no comparable directamente
  con `n_airtemp` (bulbo seco) de la automática — se excluyen de la equivalencia (no
  hay overlay significativo posible sin una conversión que este spec no cubre).
- El código real usa **`n_maxath`/`n_minath`** (extremos horarios de la automática)
  para comparar contra `n_tm102`/`n_tm103` en PLIA — pero como `vecindad` no calcula
  agregados propios (solo superpone lo que ya existe), usa directamente
  **`n_airtemp`** (la serie continua) como referencia visual — el usuario ve la
  línea completa y los puntos de máx/mín diaria encima, sin que el Analizador
  calcule ningún máximo/mínimo por su cuenta.

## Alcance — qué SÍ incluye

- Refrescar `data_ref/estaciones.db` con `latitud`, `longitud`, `estado_operatividad`
  (extiende el script `data_ref/actualizar_geodatos.py` que ya existe de
  `control-calidad`, mismo Excel de origen).
- `core/vecindad.py`: `calcular_pares_colocados(umbral_m=100)` — haversine entre
  todas las automáticas y convencionales de `estaciones.db`, ya validado con datos
  reales (204 pares, 57 a 0.0m exactos, 185 de 413 automáticas con candidata).
- Diccionario de equivalencia (`temperatura`, `precipitacion`), cada uno con la
  variable continua de la automática + las variables puntuales de la convencional
  disponibles para ese par (una estación puede no tener alguna).
- Pestaña nueva `ui/tab_vecindad.py`, **independiente del selector compartido**
  (`dd-codigos`/Periodo de arriba) — carga sus propios dos códigos al elegir un par,
  con su propio selector de periodo (default últimos 6 meses, igual que Vista
  Cruda).
- Checkbox de CC, reusando `control_calidad.resultado_control_calidad_estacion` para
  ambas estaciones del par (ya funciona para automáticas y convencionales).
- Extensión chica a `charts.overlay_multivar`: sus `extra_series` hoy solo dibujan
  líneas conectadas (`mode` fijo); se agrega `"modo": "markers"|"lines"` (default
  "lines", no rompe el uso actual en Comparar) y color por entrada (hoy todas las
  `extra_series` comparten un verde fijo) — necesario para mostrar 3-5 puntos
  convencionales distinguibles entre sí sobre la línea continua.

## Alcance — qué NO incluye (explícitamente fuera)

- **Ninguna estadística de comparación** (sesgo, MAE, RMSE, correlación, tests) —
  eso es PLIA, herramienta separada por decisión explícita del usuario.
- **Ninguna firma automática de divergencia** (tipo AF-REP) — decidido en la sesión
  anterior, solo vista visual.
- Sin humedad relativa, presión ni viento en la convencional (no confirmado que
  existan en los CSV reales — se agregaría después, si aparece un caso real).
- Sin bulbo húmedo (`n_tm107/108/109`) — no comparable directamente con la
  automática.
- Sin ventaneo de precipitación 07-19h/19-07h con desfase de día (la lógica cuidadosa
  de `PLIA/comparacion_core.py`) — se muestran los acumulados de la convencional tal
  cual vienen (`n_pt101`/`102`/`103`), sin recalcular nada.
- No se usa el crosswalk de PLIA como fuente de pares (decisión explícita: separado).
- Sin filtro de "solo OPERATIVA" en el dropdown de pares — se listan los 204, el
  usuario filtra escribiendo en el buscador (mismo patrón ya usado en toda la app).

## Tech Stack

Igual que el resto del proyecto — Python 3.12, pandas, Dash, Plotly. Sin
dependencias nuevas (haversine es trigonometría estándar, ya se probó con `math` en
la sesión de investigación).

## Commands

```
Test:  C:\Users\drd06\.conda\envs\analizador_series\python.exe -m pytest tests/ -v
Correr app: python -m analizador_series.app  (puerto configurable, no usar 8053/8054)
```

## Project Structure

```
analizador_series/core/vecindad.py             → pares co-ubicados + equivalencia, nuevo
analizador_series/ui/tab_vecindad.py           → layout de la pestaña, nuevo
analizador_series/ui/callbacks.py              → callbacks de la pestaña (agregar)
analizador_series/ui/charts.py                 → extender overlay_multivar (modo/color)
data_ref/actualizar_geodatos.py                → extender (lat/lon/estado_operatividad)
tests/core/test_vecindad.py                    → nuevo
```

## Code Style

Igual que `control_calidad.py`: funciones puras en `core/`, type hints, docstrings
solo donde el WHY no es obvio. Nombres en español, snake_case.

```python
def calcular_pares_colocados(umbral_m: float = 100.0) -> list[dict]:
    """
    [{"codigo_auto","codigo_conv","distancia_m"}], ordenado por distancia. Sin
    indexado espacial (413×681 combinaciones, trivial) — ver docs/SPEC-vecindad.md
    para la validación con datos reales (204 pares al momento de escribir esto).
    """
```

## Testing Strategy

pytest, `tests/core/test_vecindad.py`, mismo patrón que `test_control_calidad.py`:

- `calcular_pares_colocados`: haversine contra distancias conocidas (casos
  sintéticos con coordenadas de distancia exacta calculable a mano), filtro de
  umbral, orden por distancia, caso 1-a-N (una estación con 2+ candidatas), caso sin
  `latitud`/`region_natural` (metadata faltante no rompe).
- Equivalencia de variables: variable ausente en una estación puntual se omite sin
  error (mismo patrón defensivo de todo el proyecto).
- `overlay_multivar` extendido: test de que `modo="markers"` no dibuja línea
  conectora (verificar `mode` de la traza resultante) y que el comportamiento actual
  (sin `modo`, o `modo="lines"`) no cambia — no romper Comparar.

## Boundaries

- **Always:** correr `pytest tests/` completo antes de dar una tarea por
  terminada; no modificar `PLIA/` ni su crosswalk bajo ninguna circunstancia (es
  de otro proyecto, con su propia gobernanza).
- **Ask first:** cambiar el umbral de 100m por defecto; agregar humedad/presión/
  viento a la equivalencia si aparece un CSV convencional real que las tenga.
- **Never:** importar o depender de código de `SGR TEMPORALES/PLIA/`; calcular
  agregados propios (máximos/mínimos/acumulados) que dupliquen lo que PLIA ya hace
  con rigor — si hace falta esa rigurosidad, es señal de que la tarea pertenece a
  PLIA, no a `vecindad`.

## Success Criteria

1. `data_ref/estaciones.db` tiene `latitud`/`longitud`/`estado_operatividad`
   poblados (script re-ejecutable, mismo patrón que `altitud`/`region_natural`).
2. `core/vecindad.py` con `calcular_pares_colocados()` y el diccionario de
   equivalencia (`temperatura`, `precipitacion`), cada uno con la lista de columnas
   convencionales disponibles y su etiqueta legible.
3. Pestaña "Vecindad" nueva, independiente del selector compartido, con su propio
   dropdown de pares (searchable, 204 opciones ordenadas por distancia) y su propio
   selector de periodo.
4. Gráfico: línea continua de la automática + puntos (no líneas) de cada columna
   convencional disponible para ese par y esa variable física, cada uno con color y
   nombre distinguibles en el hover/leyenda.
5. Checkbox de CC (reusa `control_calidad`) filtra ambas series.
6. 100% de los tests nuevos en verde + los 167 existentes siguen en verde.
7. Ninguna estadística de comparación, ninguna dependencia de `PLIA/`, ninguna
   escritura fuera de `Analizador-Series/` — verificable por inspección.

## Open Questions

Ninguna bloqueante — todas las asunciones de la ronda de Specify fueron confirmadas
o corregidas con datos reales de PLIA antes de escribir este spec (ver "Qué se
confirmó con datos reales" arriba).
