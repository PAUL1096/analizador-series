# Spec: emplazamiento compartido — Comparación visual automática↔convencional co-ubicada

Module id: `emplazamiento` (capability map: `control-calidad` → `emplazamiento`, depende de
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
explícita del usuario: son herramientas separadas.** `emplazamiento` no reemplaza ni
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
  para comparar contra `n_tm102`/`n_tm103` en PLIA — pero como `emplazamiento` no calcula
  agregados propios (solo superpone lo que ya existe), usa directamente
  **`n_airtemp`** (la serie continua) como referencia visual — el usuario ve la
  línea completa y los puntos de máx/mín diaria encima, sin que el Analizador
  calcule ningún máximo/mínimo por su cuenta.

## Alcance — qué SÍ incluye

- Refrescar `data_ref/estaciones.db` con `latitud`, `longitud`, `estado_operatividad`
  (extiende el script `data_ref/actualizar_geodatos.py` que ya existe de
  `control-calidad`, mismo Excel de origen).
- `core/emplazamiento.py`: `calcular_pares_colocados(umbral_m=100)` — haversine entre
  todas las automáticas y convencionales de `estaciones.db`, ya validado con datos
  reales (204 pares, 57 a 0.0m exactos, 185 de 413 automáticas con candidata).
- Diccionario de equivalencia (`temperatura`, `precipitacion`), cada uno con la
  variable continua de la automática + las variables puntuales de la convencional
  disponibles para ese par (una estación puede no tener alguna).
- Pestaña nueva `ui/tab_emplazamiento.py`, **independiente del selector compartido**
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

## Revisión de alcance (2026-09-30, tras ver el resultado real)

Al probar con datos reales, dos correcciones al diseño original, confirmadas
con el usuario antes de implementar:

- **Catálogo oficial de SIGMA** (confirmado en Análisis → DataMonitor):
  `n_tm102`/`n_tm103` son **Máxima/Mínima diaria** (sin hora puntual real);
  `n_tm104`/`105`/`106` son lecturas a **horas sinópticas exactas** (07h/13h/19h);
  `n_pt101` es **Total diaria**; `n_pt102`/`n_pt103` son **07h/19h**. El
  diseño original asumía todas homogéneas — no lo eran. Fix: cada punto
  convencional se desplaza de medianoche a su hora real (puntual) o al
  mediodía con símbolo distinto — diamante — (diaria), para no comparar
  "diarias contra el instante equivocado de la curva horaria" ni insinuar
  que una diaria es una lectura puntual. Ver `core.emplazamiento.EQUIVALENCIA_VARIABLES`
  (metadata `tipo`/`hora` por columna) y `armar_extra_series_convencional`.
- **Panel de diferencias — excepción acotada al límite de abajo, no su
  eliminación:** se agregó un panel de diferencias (convencional − automática)
  **solo para las columnas "puntual"** (07h/13h/19h), porque ahí la
  automática SÍ tiene un valor real en ese instante exacto con el que
  comparar directo — no es una estadística agregada, es una resta punto a
  punto. Las "diaria" (máx/mín/total) siguen **sin** diferencia: calcularla
  exigiría que emplazamiento compartido compute su propio agregado diario de la automática,
  y esa rigurosidad sigue siendo tarea exclusiva de PLIA (el límite de abajo
  sigue vigente para ese caso). Ver `core.emplazamiento.calcular_diferencias_puntuales`
  y `ui.charts.panel_diferencias_emplazamiento`.

## Revisión de alcance, Ronda 2 (2026-09-30, mismo día — rediseño completo)

Con datos reales de convencional ya descargados, el usuario probó el gráfico
de Ronda 1 y señaló que mezclar horas sinópticas y diarias en un mismo punto
de comparación no permitía apreciar bien los datos. Tras discutir la física
real del proceso de observación convencional (la probeta se vacía en cada
lectura; el "día meteorológico" cierra a las 07h), se rediseñó por completo
en 4 gráficos separados por tipo de comparación, con dos hallazgos nuevos
verificados con datos reales:

- **La automática SÍ tiene sus propios extremos/acumulados diarios
  reales, sin que emplazamiento compartido calcule nada:** `n_maxat`/`n_minat` (Máx/Mín
  Diaria, confirmado 482 registros reales en 4728B11C) y `n_dayrain`
  (acumulado diario, 486 registros reales) — el equivalente exacto de
  `n_tm102`/`n_tm103`/`n_pt101` de la convencional. Respaldo si estas
  columnas no existen, **siempre marcado con una nota explícita**
  ("calculado por el Analizador — la automática no reporta oficialmente
  este valor"), nunca silencioso:
  - Temperatura: el máximo/mínimo de `n_maxath`/`n_minath` (el pico/valle
    que la automática YA agrega por hora) a lo largo del día — **nunca**
    `n_airtemp` (corregido tras un error real de esta misma sesión: `n_airtemp`
    subestima picos intra-hora — verificado en 104114, 16.6°C de max(n_airtemp)
    vs. 18.8°C real de max(n_maxath) el mismo día; ver tasks/todo.md).
  - Precipitación: suma de `n_lluvia` en la ventana 07h→07h (ver más abajo).
  Ver `core.emplazamiento.calcular_extremos_diarios_automatica` y
  `calcular_acumulado_diario_automatica`.
- **`n_pt101` tiene un desfase de fecha real frente a `n_dayrain`,
  verificado con datos reales (21/21 casos no triviales en 106077):** SIGMA
  fecha `n_pt101` con el día que **empieza** la ventana nocturna
  (`n_pt103[D] + n_pt102[D+1] = n_pt101[D]`), mientras que `n_dayrain` de la
  automática se fecha con el día que la **cierra** (07:00 de ese día). Para
  comparar el mismo período físico, `n_pt101` se corre un día hacia adelante
  antes de restar — ver `desfase_dias_cierre` en `EQUIVALENCIA_VARIABLES` y
  `calcular_diferencias_precipitacion_diaria`.
- **Ventaneo 07h/19h de precipitación — excepción explícitamente autorizada
  por el usuario, no una reversión del límite general:** se suma `n_lluvia`
  de la automática en las ventanas 19:01→07:00 (nocturna) y 07:01→19:00
  (diurna) para comparar contra `n_pt102`/`n_pt103` — cálculo propio de
  emplazamiento compartido, marcado siempre como tal en el título del gráfico ("cálculo
  propio de emplazamiento compartido, no la lógica de PLIA"). El filtro de CC ya aplicado en
  el pipeline evita que outliers de sensor (se encontró uno real, -11162mm en
  `n_lluvia`) contaminen la suma. Ver `core.emplazamiento.calcular_ventaneo_automatica`.

**4 gráficos resultantes** (antes eran 2): para cada variable física, un
gráfico principal + uno secundario + sus 2 diferencias correspondientes — ver
`ui.tab_emplazamiento.layout` (`g-emplazamiento-1/2/diff-1/diff-2`) y
`ui.callbacks._figuras_emplazamiento_temperatura`/`_figuras_emplazamiento_precipitacion`.
Detalle completo de la discusión y verificación en `tasks/todo.md`.

## Alcance — qué NO incluye (explícitamente fuera)

- **Ninguna estadística de comparación rigurosa** (bias/MAE/RMSE, Kendall/
  Pearson, KS, BIASS/POD/FAR, coeficiente de inconsistencia — la batería real
  de `PLIA/comparacion_core.py`) — eso sigue siendo tarea exclusiva de PLIA,
  herramienta separada por decisión explícita del usuario. Las excepciones
  ya autorizadas (Ronda 2, arriba) son: (a) diferencia punto a punto
  automática-menos-convencional en el mismo instante exacto (horas
  sinópticas) — no es una estadística agregada; (b) usar extremos/acumulados
  diarios que SIGMA ya calculó para la automática (`n_maxat`/`n_minat`/
  `n_dayrain`) — no es que emplazamiento compartido los calcule; (c) el ventaneo 07h/19h de
  precipitación, que sí es un cálculo propio de emplazamiento compartido pero acotado a una
  suma simple con ventana fija, siempre marcado como tal. Ninguna de estas
  reemplaza ni aproxima el rigor estadístico de PLIA.
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
analizador_series/core/emplazamiento.py             → pares co-ubicados + equivalencia, nuevo
analizador_series/ui/tab_emplazamiento.py           → layout de la pestaña, nuevo
analizador_series/ui/callbacks.py              → callbacks de la pestaña (agregar)
analizador_series/ui/charts.py                 → extender overlay_multivar (modo/color)
data_ref/actualizar_geodatos.py                → extender (lat/lon/estado_operatividad)
tests/core/test_emplazamiento.py                    → nuevo
```

## Code Style

Igual que `control_calidad.py`: funciones puras en `core/`, type hints, docstrings
solo donde el WHY no es obvio. Nombres en español, snake_case.

```python
def calcular_pares_colocados(umbral_m: float = 100.0) -> list[dict]:
    """
    [{"codigo_auto","codigo_conv","distancia_m"}], ordenado por distancia. Sin
    indexado espacial (413×681 combinaciones, trivial) — ver docs/SPEC-emplazamiento-compartido.md
    para la validación con datos reales (204 pares al momento de escribir esto).
    """
```

## Testing Strategy

pytest, `tests/core/test_emplazamiento.py`, mismo patrón que `test_control_calidad.py`:

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
  PLIA, no a `emplazamiento`.

## Success Criteria

1. `data_ref/estaciones.db` tiene `latitud`/`longitud`/`estado_operatividad`
   poblados (script re-ejecutable, mismo patrón que `altitud`/`region_natural`).
2. `core/emplazamiento.py` con `calcular_pares_colocados()` y el diccionario de
   equivalencia (`temperatura`, `precipitacion`), cada uno con la lista de columnas
   convencionales disponibles y su etiqueta legible.
3. Pestaña "Emplazamiento compartido" nueva, independiente del selector compartido, con su propio
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
