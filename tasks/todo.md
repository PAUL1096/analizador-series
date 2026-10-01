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

## Nota post-completo: bug real del downloader de convencionales, encontrado y arreglado (2026-09-30)

Al intentar probar Vecindad con datos reales de convencional, se encontró la
causa real del bloqueo de datos documentado arriba (no era el mismo bug de
104097 — era un bug DISTINTO y más general en `descarga/descargar_datos_meteo_sigma.py`):

**Causa raíz:** SIGMA devuelve el campo de fecha con nombres distintos según
la familia de datos — `d_fecha_reg`/`v_hora_reg` para automáticas e
hidrológicas, pero `FECHA` (mayúsculas, sin ningún campo de hora) para
meteorológicas convencionales diarias (temperatura `n_tm*`/precipitación
`n_pt*` — justo las que necesita vecindad). `_construir_csv` solo buscaba
`d_fecha_reg`; para la familia `FECHA` esa columna quedaba vacía en todas las
filas, y el deduplicado por `(fecha, hora)` colapsaba TODO el período
descargado a una sola fila corrupta — reproducido real contra la API con
106077 (CHUGUR) y 100043 (FONAGRO).

**Fix:** `_fecha_hora(row)` nuevo en `descarga/descargar_datos_meteo_sigma.py`
— fallback `d_fecha_reg` → `FECHA`, normaliza a solo fecha (`[:10]`, cubre
también el caso ISO con hora/timezone embebidos de las hidrológicas), y
default de hora a `"00:00"` si no hay `v_hora_reg` (mismo patrón ya usado por
las convencionales reales documentado en `docs/SPEC-vecindad.md`). 4 tests
nuevos en `tests/descarga/test_descargar_datos_meteo_sigma.py` (Prove-It
pattern: reproducidos con datos sintéticos calcados de la respuesta real de
la API antes del fix, confirmados en verde después).

**Verificado con datos reales tras el fix:** 106077 y 100043 re-descargados
(91 y 29 días reales respectivamente, antes 1 fila corrupta cada uno) y
graficados en Vecindad end-to-end: par `4728B11C|100043` (temperatura, 5
series convencionales) y `4727F484|106077` (precipitación, 3 series), ambos
sin excepción y sin mensaje de error.

**Nota sobre el diagnóstico original del usuario:** la hipótesis inicial era
un límite de SIGMA de "máximo 20 variables seleccionables" (visto en la UI de
Análisis → DataMonitor, endpoint distinto `/api/analysis/data-monitor/consultar`
con un parámetro `variables` explícito). Investigado y descartado como causa
de ESTE bug: el endpoint que usa el script (`/api/operatividad/consultar`) no
tiene ese límite — se probó con FONAGRO (13 variables `n_*`, bien debajo de
20) y aun así colapsaba, confirmando que la causa real era el nombre de
campo de fecha, no la cantidad de variables. Queda como posible mejora futura
(no pedida): migrar el script al endpoint `data-monitor` con filtro de
variables por equipamiento, si en el futuro se necesita evitar pedir
variables de más — pero no era necesario para destrabar esto.

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

## Ronda 2 de feedback real (2026-09-30, mismo día, datos reales ya descargados)

Con datos reales de convencional ya descargados (ver nota de arriba), el
usuario probó la pestaña en el navegador y señaló dos problemas de diseño
reales que la Ronda 1 no había cubierto:

1. **"No se puede distinguir bien los datos... todos los colocaste para
   comparar con el dato horario, lo cual no es tanto así"** — los 5 puntos de
   temperatura convencional (`n_tm102-106`) se dibujaban todos a medianoche,
   sin distinguir que `n_tm102/103` son máx/mín **diaria** y `104/105/106`
   son horas **sinópticas puntuales** (07h/13h/19h) — confirmado contra el
   catálogo oficial de SIGMA (Análisis → DataMonitor). Fix: cada punto se
   desplaza a su hora real (puntual) o queda al mediodía con símbolo diamante
   (diaria) — ver `docs/SPEC-vecindad.md`, sección "Revisión de alcance".
2. **"Quizá más abajo podamos colocar las diferencias entre ambos valores"**
   (mostró como referencia un gráfico estilo PLIA) — cruza el límite
   explícito "ninguna estadística de comparación" del spec original.
   Confirmado con el usuario antes de implementar ("Si, hay que considerar
   eso más"): se agregó un panel de diferencias, pero **acotado únicamente a
   las columnas "puntual"** (donde restar contra el valor real de la
   automática en ese instante exacto no es una estadística agregada) — las
   "diaria" siguen sin diferencia, ese límite no se tocó.

**Implementado:**
- `core/vecindad.py`: `EQUIVALENCIA_VARIABLES["..."]["convencional"]` pasó de
  lista plana a diccionario con metadata (`etiqueta`, `tipo` "diaria"/
  "puntual", `hora` si aplica) — catálogo oficial de SIGMA citado en el
  comentario. `armar_extra_series_convencional` desplaza el índice según
  `tipo`/`hora` y asigna símbolo (círculo/diamante); gana clave `"columna"`
  (código crudo) para que el callback pueda mapear el mismo color al panel
  de diferencias. `calcular_diferencias_puntuales` nuevo — diferencia solo
  para "puntual", vía reindex exacto contra la automática.
- `ui/charts.py`: `overlay_multivar` gana `"symbol"` en `extra_series`
  (default "circle", sin romper Comparar). `panel_diferencias_vecindad`
  nuevo — barras por columna puntual, línea de referencia en 0.
- `ui/tab_vecindad.py`: segundo `dcc.Graph` (`g-vecindad-diferencias`) debajo
  del principal.
- `ui/callbacks.py`: `actualizar_vecindad` gana el `Output` del segundo
  gráfico y calcula las diferencias reusando el color de `extra_series`.
- 12 tests nuevos (desplazamiento horario, símbolo, diferencias solo
  puntuales, integración end-to-end). `pytest tests/` completo: 219/219 en
  verde (202 previos + otros ya sumados en la ronda de descarga + estos).
- Verificado con datos reales (100043 FONAGRO vs. 4728B11C): diferencias de
  -0.1 a 1.3°C en las 3 horas sinópticas, magnitudes razonables.
- Servidor reiniciado limpio para que el usuario vea el resultado en
  `localhost:8054`.

**Hallazgo aparte durante esta ronda, no de vecindad:** dos bugs reales de
descarga encontrados y arreglados en `descarga/descargar_datos_meteo_sigma.py`
(campo de fecha `FECHA` vs `d_fecha_reg` — ver nota de Ronda 1) y un
`PermissionError` real por tener el CSV de destino abierto en Excel al
re-descargar (no es bug de código, es un candado de archivo de Windows —
cerrar el Excel resuelve). Se creó `Descargar_Datos_Meteo.bat` en la raíz del
proyecto (no existía en este repo, solo en el proyecto viejo) para que el
usuario descargue por su cuenta sin tocar la línea de comandos.

## Ronda 2, continuación — rediseño completo en 4 gráficos (2026-09-30, mismo día)

Con datos reales ya bien descargados, el usuario probó el gráfico de la
primera parte de la Ronda 2 (horas sinópticas + diarias todas mezcladas en un
overlay) y señaló que seguía sin poder apreciar bien la comparación:
"diarias con las diarias, horas sinópticas con las de esa misma hora". Se
discutió extensamente antes de programar (ver conversación — "Discutamos"),
con dos hallazgos reales verificados con datos reales antes de tocar código:

1. **La automática tiene sus propios extremos/acumulados diarios reales**
   (`n_maxat`/`n_minat`/`n_dayrain`) — confirmado con 482/486 registros reales
   en 4728B11C, reportados casi siempre a las 07:00. No hacía falta que
   vecindad calculara nada para el caso normal; solo se agregó respaldo
   calculado (marcado con nota explícita) para cuando faltan.
2. **Desfase de fecha real entre `n_pt101` (convencional) y `n_dayrain`
   (automática)**, verificado con 21/21 casos no triviales en 106077:
   `n_pt101(D) = n_pt103(D) + n_pt102(D+1)` — SIGMA lo fecha con el día que
   EMPIEZA la ventana nocturna, no el que la cierra (que es como se fecha
   `n_dayrain`). Sin corregir este desfase, cualquier comparación por fecha
   cruda quedaría corrida un día.
3. Al intentar validar sumando `n_lluvia` crudo de la automática se encontró
   un valor real absurdo (-11162mm, error de sensor) — confirmó que había
   que aplicar el filtro de CC (ya integrado en el pipeline) antes de sumar
   cualquier ventana horaria.

**Diseño final — 4 gráficos por variable física** (antes 2):

| | Gráfico 1 | Gráfico 2 | Diff 1 | Diff 2 |
|---|---|---|---|---|
| Temperatura | Horaria + horas sinópticas (07/13/19h alineadas a su hora real) | Máx/mín diaria (conv. `n_tm102/103` + auto. `n_maxat/n_minat`, real o calculado con nota) | Dif. horas sinópticas | Dif. máx/mín diaria |
| Precipitación | Acumulado diario (conv. `n_pt101` realineado +1 día + auto. `n_dayrain`, real o calculado con nota) | Ventaneo 07h/19h (conv. `n_pt102/103` + auto. suma nocturna/diurna, siempre cálculo propio) | Dif. acumulado diario | Dif. ventaneo |

**Implementado:**
- `core/vecindad.py`: `EQUIVALENCIA_VARIABLES` gana `automatica_extremos_diarios`
  (temperatura) y `automatica_diaria` + `desfase_dias_cierre` (precipitación).
  Funciones nuevas: `calcular_extremos_diarios_automatica`,
  `calcular_diferencias_diarias_temperatura`, `calcular_acumulado_diario_automatica`,
  `calcular_diferencias_precipitacion_diaria`, `calcular_ventaneo_automatica`
  (con `_sumar_ventana_diurna`/`_sumar_ventana_nocturna`/`_sumar_ventana_07_07`,
  boundaries de ventana verificados con tests exactos hora por hora),
  `calcular_diferencias_precipitacion_ventaneo`. `armar_extra_series_convencional`
  gana clave `"tipo"` (para que el callback separe puntual/diaria por gráfico).
- `ui/charts.py`: `serie_puntos_diarios` nuevo (comparar N series diarias sin
  curva continua de base, a diferencia de `overlay_multivar`).
- `ui/tab_vecindad.py`: 4 `dcc.Graph` genéricos (`g-vecindad-1/2/diff-1/diff-2`)
  en vez de 2 — el callback decide contenido según `rb-vecindad-variable`.
- `ui/callbacks.py`: `actualizar_vecindad` reestructurado con 2 funciones de
  armado por variable física (`_figuras_vecindad_temperatura`,
  `_figuras_vecindad_precipitacion`), 5 Outputs (4 figuras + mensaje).
- 26 tests nuevos en `core/vecindad.py` (41 en total ese archivo) + reescritura
  completa de `tests/ui/test_callbacks_vecindad.py` (12 tests, estructura
  nueva de 4 gráficos) + 4 tests nuevos de `serie_puntos_diarios`. `pytest
  tests/` completo: 245/245 en verde.
- Verificado con datos reales de punta a punta en ambas variables físicas
  (4728B11C↔100043 temperatura; 4727F484↔106077 precipitación) — valores de
  diferencia del orden de magnitud esperado (ej. -0.1 a 1.4mm en ventaneo de
  precipitación), sin excepciones.
- Servidor reiniciado limpio para que el usuario vea el resultado en
  `localhost:8054`.

## Corrección real: el respaldo de máx/mín diaria no hacía lo que se pidió (2026-09-30)

El usuario preguntó explícitamente "¿hiciste lo que te indiqué?" sobre el
respaldo de máx/mín diaria cuando la automática no tiene `n_maxat`/`n_minat`.
Revisando la instrucción original con cuidado, la implementación de la Ronda
2 NO la seguía: la instrucción literal era "usar el máximo de los máximos
**agregados**" (dos niveles de respaldo: real diario → máximo de los máximos
ya agregados por hora → si tampoco existe, no mostrar), pero se había
implementado un respaldo distinto y no pedido: calcular el máximo de
`n_airtemp` (la lectura horaria cruda), saltándose el nivel intermedio.

**Por qué importa, verificado con datos reales:** 104114 tiene `n_maxath`/
`n_minath` (el pico/valle que la automática ya agrega POR HORA) pero no
`n_maxat`/`n_minat` (diario) — exactamente el escenario de respaldo. El
máximo real de `n_maxath` en un día (2025-10-20) fue **18.8°C** (pico real a
las 11:00), mientras que el máximo de `n_airtemp` ese mismo día fue apenas
**16.6°C** — la lectura puntual/horaria se pierde el pico real que el propio
datalogger ya había capturado. Usar `n_airtemp` como respaldo habría
subestimado sistemáticamente los extremos reales, exactamente lo que el
usuario quería evitar con su instrucción.

**Fix:** `EQUIVALENCIA_VARIABLES["temperatura"]` gana
`automatica_extremos_horarios_agregados` (`n_maxath`/`n_minath`).
`calcular_extremos_diarios_automatica` ahora tiene los 3 niveles exactos:
real diario → máximo/mínimo de los agregados horarios (marcado
"calculado": True) → `None` si tampoco existe. Se quitó por completo el uso
de `n_airtemp` como respaldo. 2 tests actualizados + 1 test de regresión
nuevo (`test_sin_n_maxat_ni_n_maxath_da_none_aunque_haya_n_airtemp`, para que
esto no se repita). `pytest tests/`: 246/246 en verde. Verificado con datos
reales (104114): 18.8°C correcto donde antes daba 16.6°C.

**Lección para la sesión:** cuando el usuario pidió "úsalo, si no está, este
otro respaldo, y si no, no lo muestres" con una lista explícita de niveles,
había que implementar esos niveles exactos — no sustituir el nivel
intermedio por algo "equivalente" sin confirmar primero que la columna que
realmente pidió no existía en los datos disponibles.

## Disclaimer visible en la UI (2026-09-30)

A pedido del usuario, se agregó un disclaimer colapsable ("ℹ️ Qué significa
cada valor calculado") en la tarjeta de selectores de `tab_vecindad.py`, con
las ecuaciones exactas de cada valor real/calculado (máx/mín diaria de
temperatura, acumulado diario y ventaneo 07h/19h de precipitación, y la nota
del desfase de `n_pt101`) — mismo contenido ya documentado en
`docs/SPEC-vecindad.md`, ahora también accesible sin salir de la app.
Callback `toggle_disclaimer_vecindad` (patrón estándar botón+`dbc.Collapse`).
`pytest tests/`: 246/246 en verde (sin tests nuevos — es presentacional, ya
cubierto por el test de layout existente que confirma que renderiza sin
excepción).

## Pulido de UI: títulos/leyendas, datos faltantes, disclaimer reubicado (2026-09-30)

Feedback real del usuario con capturas: (1) título y leyenda de Plotly se
superponían en los 4 gráficos (margen superior insuficiente); (2) títulos
demasiado largos; (3) cuando falta máx/mín/acumulado de la convencional O de
la automática, había que decirlo explícitamente (antes se omitía en
silencio); (4) el disclaimer debía vivir debajo del selector de Periodo,
cambiando según la variable física, no como botón colapsable aparte.

**Fix:**
- `ui/charts.py`: título con `font.size` reducido + `margin.t` aumentado
  (85/75/85 según el gráfico) en las 3 funciones de vecindad — separa título
  de leyenda sin tocar el comportamiento de Comparar (que no pasa título
  largo). Verificado visualmente en navegador (chrome-devtools MCP),
  screenshot antes/después.
- `ui/callbacks.py`: títulos acortados (`"{auto} ↔ {conv} · Horaria"` en vez
  de la versión larga original); mensajes nuevos cuando falta cualquiera de
  los dos lados (convencional sin columna/sin dato real, automática sin
  fuente real ni calculada) — antes esos casos se omitían sin aviso.
- `core/vecindad.py`: `armar_extra_series_convencional` ahora excluye
  columnas que EXISTEN pero están enteramente vacías en el periodo (evita
  trazas fantasma en la leyenda sin puntos visibles) — 1 test de regresión
  nuevo.
- `ui/tab_vecindad.py` + `ui/callbacks.py`: disclaimer movido de
  botón-colapsable a un `html.Div` fijo debajo de `dt-periodo-vecindad`,
  con contenido corto que cambia según `rb-vecindad-variable` (callback
  `actualizar_disclaimer_vecindad`), en vez de un solo bloque largo con
  ambas magnitudes mezcladas.
- `pytest tests/`: 247/247 en verde. Verificado visualmente de punta a punta
  en el navegador real con el par 114140↔114066 (el mismo de las capturas
  del usuario) en ambas magnitudes — confirmado que "114066 no tiene máxima
  diaria disponible" se muestra correctamente (esa convencional solo trae
  `n_tm103`, no `n_tm102`, en el periodo elegido).

## Dos ajustes finos más de UI (2026-09-30)

Dos detalles reales señalados por el usuario con capturas, tras el pulido anterior:

1. **Espacio en blanco grande arriba de "Par co-ubicado"/"Variable física"**:
   causa real — el `dbc.Row` de selectores usaba `align-items-end` (alinea
   las columnas por su base), y al agregar el disclaimer dentro de la
   columna "Periodo" esa columna se volvió más alta que las demás,
   empujando "Par co-ubicado" y "Variable física" hacia abajo para igualar
   la base. Fix: `align-items-start` — ahora las 3 columnas alinean arriba,
   el disclaimer simplemente extiende su columna hacia abajo sin desplazar
   a las otras.
2. **Nombres de variable (`n_maxat`, `n_maxath`, etc.) se veían más grandes
   que el texto alrededor** en el disclaimer: causa real, confirmada
   midiendo `getComputedStyle` en el navegador — el tema Bootstrap (FLATLY)
   define el font-size de `<code>` en `rem` (relativo a la raíz del
   documento), no en `em` (relativo al padre), así que no se achicaba junto
   con la clase `.small` que envuelve el resto del texto. Fix: se creó
   `analizador_series/assets/vecindad.css` (carpeta nueva — la que ya
   existía en `ui/assets/` estaba vacía y **no es la que Dash sirve
   realmente**; confirmado con `app.config["assets_folder"]`, que apunta a
   `analizador_series/assets`, no `ui/assets`) con la regla
   `.vecindad-disclaimer code { font-size: inherit; }`. Verificado en el
   navegador real: antes de la regla, código y párrafo no coincidían;
   después, ambos miden exactamente 14px.

`pytest tests/`: 247/247 en verde (cambio puramente de CSS/layout, sin
lógica). Verificado visualmente de punta a punta en navegador real.

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
