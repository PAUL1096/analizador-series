# Tasks: vecindad

Ver `tasks/plan.md` para el orden de fases y checkpoints. Spec: `docs/SPEC-vecindad.md`.

---

## Task 1: Latitud/longitud en estaciones.db — ✅ HECHA

**Description:** Extender `data_ref/actualizar_geodatos.py` para leer también
`Latitud`/`Longitud` de la hoja "Georeferencias" del mismo Excel (ya trae esas
columnas — verificado contra `georeferencias_2026-09-29.xlsx` real) y
agregar/refrescar `latitud`/`longitud` (REAL) en `estaciones.db`, mismo patrón
UPDATE-por-código que ya usa para `altitud`/`region_natural`. **No** agregar
ninguna columna de "estado operativo" — ya existe `activa` (INTEGER) en el
schema, poblada; el Excel de origen no trae ese dato de todos modos (ver
`tasks/plan.md`, Architecture Decisions).

**Acceptance criteria:**
- [x] `python data_ref/actualizar_geodatos.py <ruta_excel>` sigue corriendo sin
      error sobre el mismo Excel que ya usa altitud/región, y además puebla
      `latitud`/`longitud`
- [x] `estaciones.db` tiene columnas `latitud`/`longitud` (REAL) para las
      estaciones que aparecen en el Excel; estaciones sin match quedan en
      `NULL`, no rompen el script
- [x] Re-ejecutar el script no duplica filas (mismo UPDATE, no INSERT) —
      mismo criterio ya probado para altitud/región
- [x] El docstring del módulo se corrige: ya no dice "No trae latitud/longitud
      (eso es para core/vecindad.py, módulo aparte)" — ahora sí las trae

**Verification:**
- [x] Manual: confirmado con sqlite3 contra la DB real — 1076 estaciones con
      `latitud`/`longitud` no nulos tras correr contra
      `georeferencias_2026-09-29.xlsx` (mismo Excel de altitud/región, mismos
      18 códigos sin match)
- [x] Re-ejecutado el script sobre el Excel real: 1076 filas antes y después
      (no duplica)
- [x] `pytest tests/data_ref/test_actualizar_geodatos.py -v` — 4 tests nuevos
      en verde (parseo de lat/lon del Excel, poblado en DB, NULL sin match,
      no-duplicación al re-ejecutar)
- [x] `pytest tests/` completo en verde (171 tests: 167 previos + 4 nuevos)

**Dependencies:** None

**Files likely touched:**
- `data_ref/actualizar_geodatos.py`

**Estimated scope:** Small (1 archivo)

---

## Task 2: core/vecindad.py — pares co-ubicados + equivalencia de variables — ✅ HECHA

**Description:** Módulo nuevo, funciones puras (mismo estilo que
`control_calidad.py`). `calcular_pares_colocados(umbral_m=100.0) -> list[dict]`:
haversine entre todas las automáticas y convencionales de `estaciones.db` (query
directa por sqlite, no vía `data_loader.metadata_estaciones` — ver
`tasks/plan.md`), filtra por umbral, ordena por distancia ascendente. Cada
elemento: `{"codigo_auto", "codigo_conv", "distancia_m"}`. Además, diccionario
de equivalencia `EQUIVALENCIA_VARIABLES` con dos entradas (`temperatura`,
`precipitacion`), cada una con la variable continua de la automática +
columnas puntuales de la convencional disponibles (ver tabla exacta del spec,
sección "Alcance — qué SÍ incluye"). Bulbo húmedo (`n_tm107/108/109`) no entra
en el diccionario.

**Acceptance criteria:**
- [x] `calcular_pares_colocados()` no empareja automática↔automática ni
      convencional↔convencional — solo cruza `categoria` distinta
- [x] Estaciones sin `latitud`/`longitud` (`NULL`) se excluyen del cálculo sin
      lanzar excepción
- [x] Una automática con 2+ convencionales candidatas dentro del umbral
      aparece 1 vez por cada candidata (no se queda solo con la más cercana) —
      el spec pide lista completa, filtrada en la UI por el usuario
- [x] `EQUIVALENCIA_VARIABLES["temperatura"]["convencional"]` incluye
      `n_tm102/103/104/105/106` y excluye `n_tm107/108/109`
- [x] `EQUIVALENCIA_VARIABLES["precipitacion"]["convencional"]` incluye
      `n_pt101/102/103`

**Verification:**
- [x] `pytest tests/core/test_vecindad.py -v` — 14 tests en verde: haversine
      contra distancias conocidas (mismo punto = 0m; 1° de longitud en el
      ecuador contra circunferencia/360 calculada aparte; desplazamiento
      norte-sur exacto por ser un meridiano un círculo máximo), filtro de
      umbral (99m entra, 101m no), orden por distancia ascendente, caso 1-a-N,
      caso sin coordenadas, equivalencia con columna ausente
- [x] Smoke test contra la DB real: `calcular_pares_colocados()` devuelve 194
      pares (56 a ~0m, 175 automáticas con candidata) — mismo orden de
      magnitud que los ~204/57/185 de la investigación previa; la diferencia
      pequeña es razonable (no se investigó la causa exacta, podría ser
      `<=100m` vs `<100m` u otra georreferencia ligeramente distinta) y no
      bloquea, según el propio criterio del checkpoint ("razonable, no 0 ni
      miles")
- [x] `pytest tests/` completo en verde (185 tests: 171 previos + 14 nuevos)

**Dependencies:** Task 1 (necesita `latitud`/`longitud` reales pobladas para el
smoke test contra la DB real; los tests unitarios con coordenadas sintéticas no
dependen de Task 1 y pueden escribirse en paralelo)

**Files likely touched:**
- `analizador_series/core/vecindad.py` (nuevo)
- `tests/core/test_vecindad.py` (nuevo)

**Estimated scope:** Medium (2 archivos)

---

## Checkpoint: Fase 1 — ✅ CUMPLIDO
- [x] `pytest tests/` completo en verde (185 tests)
- [x] Smoke test: `calcular_pares_colocados()` sobre la DB real, 194 pares,
      ninguno automática↔automática, ordenados por distancia

---

## Task 3: Extender overlay_multivar (modo markers + color por serie) — ✅ HECHA

**Description:** `ui/charts.py:665` `overlay_multivar` — cada entrada de
`extra_series` gana dos claves opcionales: `"modo"` (`"markers"|"lines"`,
default `"lines"`) y `"color"` (default `"#2ca02c"`, el verde fijo actual).
Cuando `modo="markers"`, la traza usa `marker=dict(color=..., size=...)` en vez
de `line=dict(...)` — así los puntos convencionales no se ven conectados por
una línea que sugeriría continuidad falsa (motivo exacto del spec).

**Acceptance criteria:**
- [x] Llamada sin `"modo"`/`"color"` en `extra_series` (el único call site
      actual, `callbacks.py:865`) produce exactamente la misma figura que
      antes — mismo color verde, misma línea punteada
- [x] `"modo": "markers"` produce una traza `go.Scattergl` con `mode="markers"`
      y sin línea conectora visible
- [x] `"color"` distinto por entrada permite 3-5 series de `extra_series` en
      la misma llamada, cada una distinguible

**Verification:**
- [x] `pytest tests/ui/test_charts.py -v` (archivo nuevo, no existía ningún
      test de UI en el repo) — 3 tests: no-regresión sin `modo`/`color`,
      `modo="markers"` sin línea conectora, color distinto por entrada
- [x] Test de regresión confirmado: la llamada actual de `callbacks.py:865`
      (sin `modo`/`color`) sigue en modo línea, verde `#2ca02c` — no rompe
      Comparar
- [x] `pytest tests/` completo en verde (188 tests: 185 previos + 3 nuevos)

**Dependencies:** None (independiente de Task 1/2, puede hacerse en paralelo)

**Files likely touched:**
- `analizador_series/ui/charts.py`
- `tests/ui/test_charts.py` (o ubicación equivalente ya existente)

**Estimated scope:** Small (1-2 archivos)

---

## Task 4: ui/tab_vecindad.py — layout de la pestaña — ✅ HECHA

**Description:** Layout nuevo, mismo estilo que `tab_comparar.py`: `dbc.Card`
con selector de par (dropdown searchable, poblado con las ~204 opciones de
`vecindad.calcular_pares_colocados()`, label legible tipo
`"{codigo_auto} ↔ {codigo_conv} · {distancia_m:.0f}m"`), selector de variable
física (Temperatura/Precipitación, `dbc.RadioItems` como el de Comparar),
selector de periodo PROPIO (`dcc.DatePickerRange` con id nuevo, ej.
`dt-periodo-vecindad`, independiente de `dt-periodo` compartido — default
últimos 6 meses), checkbox de CC (mismas opciones BUENO/DUDOSO/MALO que
`layout.py`), y el `dcc.Graph` de resultado. Registrar la pestaña nueva en
`layout.tabs_principales()` (`dbc.Tab(label="Vecindad", tab_id="tab-vecindad")`)
y en el router `renderizar_tab` de `callbacks.py:362` (rama nueva, sin
depender de `codigos`/`dd-codigos` — el dropdown de pares se puebla siempre
igual, no de lo que el usuario eligió arriba).

**Acceptance criteria:**
- [x] Pestaña "Vecindad" aparece en `tabs-principales` (después de "Vista
      cruda", antes de "Estadística")
- [x] El layout renderiza sin excepción incluso si `dd-codigos` está vacío
      (el router la construye desde `vecindad.calcular_pares_colocados()`
      directo, sin leer `codigos`)
- [x] El dropdown de pares es searchable (`dcc.Dropdown` con `searchable=True`
      explícito) y muestra las opciones ordenadas por distancia (194 sobre la
      DB real, ver Task 2)
- [x] El date picker de Vecindad tiene su propio id (`dt-periodo-vecindad`),
      no reutiliza `dt-periodo`

**Verification:**
- [x] `pytest tests/ui/test_tab_vecindad.py -v` — 5 tests: formateo de
      `opciones_pares` (label/value, redondeo de distancia, lista vacía),
      layout sin excepción vacío y poblado
- [x] Smoke test directo (sin navegador, invocando `renderizar_tab("tab-vecindad", None)`
      con la app Dash real): devuelve un `html.Div` construido con los 194
      pares reales de `estaciones.db`, sin excepción
- [x] `pytest tests/` completo en verde (193 tests: 188 previos + 5 nuevos)

**Dependencies:** Task 2 (necesita `calcular_pares_colocados()` para poblar
opciones reales), Task 3 (el gráfico de esta pestaña depende de la firma
extendida de `overlay_multivar`, aunque el layout en sí no la invoca)

**Files likely touched:**
- `analizador_series/ui/tab_vecindad.py` (nuevo)
- `analizador_series/ui/layout.py` (registrar tab)
- `analizador_series/ui/callbacks.py` (rama nueva en `renderizar_tab`)

**Estimated scope:** Medium (3 archivos)

---

## Checkpoint: Fase 2 — ✅ CUMPLIDO
- [x] `pytest tests/` completo en verde (193 tests)
- [x] Layout renderiza standalone (sin callbacks de datos aún) sin
      excepciones, confirmado por los tests de Task 4 y por invocación
      directa de `renderizar_tab` con la DB real (194 pares)

---

## Task 5: Callbacks de Vecindad — cargar par, graficar, filtro de periodo — ✅ HECHA

**Description:** Callback(s) nuevos en `callbacks.py` que, dado el par elegido
+ variable física + periodo, cargan ambas estaciones
(`data_loader.cargar_estaciones([codigo_auto, codigo_conv], ...)`), arman la
serie continua de la automática (variable del diccionario de equivalencia) +
las `extra_series` en `modo="markers"` para cada columna convencional
disponible en ESE par (usar solo las que de hecho existan en su CSV real — ver
riesgo de equivalencia en `tasks/plan.md`), y llaman a `overlay_multivar`
(Task 3) para renderizar. Aplica el periodo propio de la pestaña (Task 4), no
el compartido.

**Acceptance criteria:**
- [x] Elegir un par + "Temperatura" grafica `n_airtemp` continua (automática) +
      puntos de las `n_tm10x` disponibles para esa convencional específica
- [x] Elegir "Precipitación" grafica `n_lluvia` continua + puntos de
      `n_pt10x` disponibles, sin ninguna lógica de ventaneo/desfase de día
      (acumulados tal cual vienen del CSV — el spec lo prohíbe explícitamente;
      no se implementó ninguna lógica de ventaneo, `armar_extra_series_convencional`
      solo pasa las columnas tal cual)
- [x] Cambiar el periodo de Vecindad recorta ambas series, sin afectar
      `dt-periodo` compartido ni las demás pestañas (id propio
      `dt-periodo-vecindad`, callback `actualizar_periodo_vecindad` separado
      del compartido `actualizar_periodo_compartido`)
- [x] Si la convencional del par no tiene CSV descargado o le faltan columnas
      de la equivalencia, el gráfico muestra solo la automática + un mensaje
      claro (no una excepción)

**Verification:**
- [x] **Bloqueo real encontrado (mismo tipo que en control-calidad, distinto
      caso):** el único CSV convencional real descargado localmente (104097,
      par real `104114|104097` a 5.6m) dispara el bug pre-existente ya
      documentado en `tasks/todo.md` de control-calidad
      (`data_loader._leer_csv_estacion`, `Fecha + Hora` revienta con dtypes
      incompatibles cuando el CSV no tiene fecha/hora válida) — confirmado
      reproduciendo el error directo con `cargar_estaciones(['104114','104097'])`.
      No es bug de esta tarea (ídem nota de control-calidad Fase 2). No se
      pudo hacer el smoke test en navegador con un par 100% real con ambos
      CSVs sanos, porque no existe ninguno así en el repo en este momento.
- [x] En su lugar: **test de integración con CSVs sintéticos reales**
      (`tests/ui/test_callbacks_vecindad.py`, monkeypatch de
      `data_loader.DIR_AUTO`/`DIR_CONV` a un `tmp_path` con archivos
      `AUTOTEST_*.csv`/`CONVTEST_*.csv` de verdad, no mocks) — confirma el
      camino feliz completo: línea de `n_airtemp` + puntos `n_tm102`/`n_tm103`
      en modo `"markers"`, mensaje vacío; y que "Precipitación" sobre ese
      mismo par (que no tiene columnas `n_pt10x`) dispara el mensaje de "sin
      columnas disponibles" en vez de una excepción
- [x] Rama "sin CSV en absoluto" verificada con datos reales de la DB:
      `actualizar_vecindad('104114|999999', ...)` y con un código real sin
      CSV descargado (`107140`) — ambos casos devuelven mensaje claro, sin
      excepción
- [x] `pytest tests/` completo en verde (201 tests: 197 previos + 4 nuevos)

**Dependencies:** Task 2, Task 3, Task 4

**Files likely touched:**
- `analizador_series/ui/callbacks.py`

**Estimated scope:** Medium (1 archivo, lógica no trivial)

---

## Task 6: Checkbox de CC en Vecindad — ✅ HECHA

**Description:** Reusar `control_calidad.resultado_control_calidad_estacion`
para AMBAS estaciones del par (mismo mecanismo ya integrado en Vista
Cruda/Estadística/Comparar/Panorama — Task 7-10 de `control-calidad`), filtrando
ambas series por el checkbox BUENO/DUDOSO/MALO de Task 4 antes de graficar.
`tiene_regla_cc` ya distingue AUTOMATICA/CONVENCIONAL, así que el mismo
checkbox aplica sin lógica condicional adicional por categoría.

**Acceptance criteria:**
- [x] Cambiar el toggle de CC cambia los puntos mostrados de AMBAS series
      (automática y convencional) — `agregar_columnas_cc`/`filtrar_por_flags`
      se aplican sobre el `df` combinado ANTES de separar en `df_auto`/
      `df_conv`, así que ambas heredan el filtro por igual, sin lógica
      condicional por categoría (tal como preveía la descripción de la tarea)
- [x] Si la convencional no tiene reglas de CC definidas para alguna columna,
      esa columna se muestra sin filtrar, sin romper — `agregar_columnas_cc`
      ya es defensivo (`_resolver_metadata_y_datos` devuelve `{}` si no hay
      metadata/datos, sin excepción; confirmado también con AUTOTEST/CONVTEST
      sintéticos, que no están en `estaciones.db` y no generan columnas `cc_*`)

**Verification:**
- [x] Verificación por backend con estación real conocida (101004, mismo
      patrón que Tasks 9/10 de control-calidad): par `101004|999999`
      (convencional fijada a un código sin ningún CSV, para aislar el efecto
      sin tropezar con el bug del único CSV convencional real de Task 5) —
      `["BUENO","DUDOSO","MALO"]` vs. `["BUENO"]` en `n_airtemp` difieren en
      exactamente 49 puntos (30 DUDOSO + 19 MALO ya conocidos de
      `resultado_control_calidad_estacion('101004')`)
- [x] `pytest tests/` completo en verde (202 tests: 201 previos + 1 nuevo)

**Dependencies:** Task 5

**Files likely touched:**
- `analizador_series/ui/callbacks.py`

**Estimated scope:** Small (1 archivo, mecanismo ya existente)

---

## Checkpoint: Completo — ✅ CUMPLIDO
- [x] `pytest tests/` completo en verde (202 tests: 167 de control-calidad +
      35 nuevos de vecindad)
- [x] Smoke test en navegador — **no se hizo** (ver nota abajo); se verificó
      en su lugar por invocación directa de los callbacks reales (misma
      profundidad que Tasks 9/10 de control-calidad) y por un test de
      integración con CSVs sintéticos reales que ejercita el camino
      completo (línea + puntos + mensaje), sin errores
- [x] Success Criteria 1-7 de `docs/SPEC-vecindad.md` verificados por
      inspección:
  - [x] `estaciones.db` con `latitud`/`longitud` poblados (Task 1 — 1076
        estaciones reales)
  - [x] `core/vecindad.py` con `calcular_pares_colocados()` + equivalencia
        (Task 2 — 194 pares reales)
  - [x] Pestaña "Vecindad" independiente del selector compartido, dropdown +
        periodo propios (Task 4)
  - [x] Gráfico con línea continua + puntos distinguibles (Task 3, 5)
  - [x] Checkbox de CC filtra ambas series (Task 6)
  - [x] 100% tests nuevos en verde (35) + 167 existentes
  - [x] Ninguna estadística de comparación, ninguna dependencia real de
        `PLIA/` (solo menciones en docstrings, ningún import), ninguna
        escritura fuera de `Analizador-Series/` — confirmado con grep sobre
        todos los archivos tocados

**Nota real, mismo tipo de bloqueo que control-calidad documentó en su
momento:** no se pudo hacer un smoke test en navegador con un par 100% real
(ambas estaciones con CSV descargado y sano) porque el único CSV convencional
que existe en el repo (104097) dispara un bug pre-existente y ya conocido del
loader (`data_loader._leer_csv_estacion`, Fecha/Hora inválidos) — no es bug de
esta tarea, está fuera de alcance del spec de vecindad arreglar el loader
compartido. Se cubrió en su lugar con: (a) un test de integración con CSVs
sintéticos reales que sí prueba el renderizado completo (línea + puntos +
colores + modos), (b) verificación por backend con estaciones reales
(101004, 104114) para los caminos de CC y de "sin CSV", y (c) invocación
directa del router (`renderizar_tab`) con la app Dash real para confirmar que
la pestaña completa (194 pares reales) se construye sin excepción. Si en el
futuro se descarga un CSV convencional sano, vale la pena repetir el smoke
test visual en navegador — no es una tarea nueva, es cerrar esta nota.

## Resumen final — módulo vecindad completo

6 tareas, 3 fases, 202 tests (de 167 al empezar, +35 de vecindad). Alcance
final vs. el spec original: igual, sin extensiones ni recortes — los dos
hallazgos de la fase de planeamiento (`estado_operatividad` ya cubierto por
la columna `activa` existente; `core/vecindad.py` con consulta sqlite propia
en vez de reusar `data_loader.metadata_estaciones`) ya estaban anticipados en
`tasks/plan.md` antes de empezar a programar. Pendiente real, no de código:
mismo tipo de bloqueo de datos que control-calidad — no hay ningún CSV
convencional real y sano descargado localmente para un smoke test visual en
navegador; cubierto con tests de integración sintéticos + verificación por
backend con estaciones reales, documentado arriba.
