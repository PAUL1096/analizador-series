# Estado de la migración y pendientes — Analizador de Series

**Fecha:** 2026-07-14 · **Sesión:** migración desde el repo SGO a proyecto propio.
Este documento es el registro durable (por si se pierde la sesión del asistente). Vive dentro del
proyecto, no en la memoria del asistente (que está anclada al repo SGO).

---

## 1. Qué se hizo (Fase A — construir el standalone) — ✅ COMPLETA

Origen: `…/Desarrollos/Dashboard-para-monitoreo-de-la-operatividad/` (repo SGO).
Destino: `…/Desarrollos/Analizador-Series/` (este proyecto).

- **Carpeta y estructura** creadas (`analizador_series/`, `descarga/`, `DATA/datos_meteo/`,
  `data_ref/`, `sigma/`, `docs/`).
- **Entorno dedicado** conda `analizador_series` (Python 3.12) creado con las deps del `requirements.txt`
  (dash 4.4.0, dash-ag-grid 35.2.0, ruptures 1.1.10, scipy 1.18.0, plotly 6.9.0, pandas 3.0.3,
  numpy 2.5.1, selenium 4.46.0, etc.). Aislado de `miambiente` (producción SGO) a propósito.
- **Copiado** (no movido aún del repo SGO — ver Fase B): paquete `analizador_series/` (12 .py),
  descargador `descargar_datos_meteo_sigma.py`, 286 CSV de `DATA/datos_meteo/` (269 auto + 17 conv,
  ~235 MB), y credenciales `sigma/.env` (**copiadas**, no movidas: el pipeline SGO también las usa).
- **Catálogo de estaciones**: se extrajo SOLO la tabla `estaciones` de `sgo/sgo.db` a
  `data_ref/estaciones.db` (1076 estaciones) — NO se arrastró la BD de producción (tiene incidentes).
- **Paths reajustados**:
  - `analizador_series/config.py`: `SGO_DB` → **`CATALOGO_DB`** = `ROOT/data_ref/estaciones.db`.
  - `analizador_series/core/data_loader.py`: renombrado `SGO_DB`→`CATALOGO_DB` (import + 2 usos) + comentarios.
  - `descarga/descargar_datos_meteo_sigma.py`: `SGO_DB` repunta a `data_ref/estaciones.db`, y se
    **corrigió `ROOT_PROYECTO`** (`.parent.parent` → `.parent`, porque `descarga/` está 1 nivel bajo
    la raíz, no 2 como el `PIPELINE/automaticas/` original). Se limpió un `DATA/` vacío que su `mkdir`
    creó por error en `Desarrollos/` antes del fix.
- **Archivos de soporte**: `requirements.txt`, `.gitignore` (protege `sigma/.env`, `DATA/datos_meteo/`,
  `data_ref/estaciones.db`), `Iniciar_Analizador.bat`, `README.md`.
- **Docs preservados**: `docs/2026-07-13-rediseno-fase1-design.md` (spec) y
  `docs/referencias_qc_comunidad.md` (investigación de referentes).

### Verificado (re-derivado, no por plausibilidad)
- Deps importan en el env nuevo; `dash-ag-grid`, `ruptures`, `scipy` OK.
- `analizador_series.app` importa y construye el `Dash` app (layout + callbacks) sin error.
- `data_loader.codigos_disponibles()` → **141 estaciones** con CSV, cruzadas contra el catálogo (con nombre/DZ).
- Descargador: `ROOT_PROYECTO`, catálogo, `sigma/.env` y `DIR_AUTO` resuelven en la carpeta nueva;
  `cargar_estaciones()` → 1076. (NO se probó descarga real con Selenium — eso lo valida el usuario.)

---

## 1.1 Fase 1 — rediseño: M1 (núcleo de detección) + M3 (pestañas) — ✅ COMPLETA (2026-08-05)

Plan ejecutado: `C:\Users\drd06\.claude\plans\linear-noodling-riddle.md`. Alcance de esta pasada:
núcleo de detección AF-* + tests, y reestructurar la UI en pestañas (Estadística migrada intacta,
Panorama/Comparar como placeholders). **Panorama y Comparar funcionales quedan para M5/M6.**

- **`core/deteccion_afectaciones.py`** (nuevo): `detectar_cst/gap/miss/out/nois/bias` +
  `detectar_todas()`. Cadencia esperada se infiere EMPÍRICAMENTE por variable
  (`cadencia_inferida()`, moda de Δt entre lecturas válidas) — no se guessea en YAML, evita el
  error de tipo R5. Umbrales en minutos reales (`config/afectaciones.yaml`), convertidos a pasos
  según esa cadencia — así el mismo umbral aplica igual a una variable horaria que a una de 10-min.
- **`core/consistencia.py`** (nuevo): `punto_de_rocio` (Magnus) + 4 chequeos cruzados (T-rocío,
  HR-lluvia, veleta trabada, Tmax/Tmin/T).
- **37 tests** (`tests/core/`, pytest instalado en el env `analizador_series` + `pytest.ini` en la
  raíz) — todos en verde, gate cumplido antes de tocar la UI.
- **UI reestructurada en 3 pestañas** (`dbc.Tabs` con swap dinámico de `children` vía callback,
  no children estáticos — evita que `dcc.Graph` se monte oculto con ancho 0): `ui/tab_estadistica.py`
  (contenido movido tal cual, mismos ids), `ui/tab_panorama.py` y `ui/tab_comparar.py`
  (placeholders "Próximamente"). Selectores compartidos (estaciones/periodo/flags) + los 3
  `dcc.Store` + el `dcc.Interval` viven en la raíz, fuera de las pestañas.
- **Riesgo real resuelto:** al remontar la pestaña Estadística, `dd-variable` no se repoblaba solo
  (su único trigger es `dd-codigos`, que no cambia al volver). Se resolvió con un router de
  pestañas que hornea las opciones frescas de `dd-variable` directamente al construir el layout
  de la pestaña (ver `ui/callbacks.py: renderizar_tab` + `_opciones_variable`).

### Verificado (re-derivado, no por plausibilidad)
- Los 37 tests pasan (`pytest tests/ -v`).
- Smoke test end-to-end real en navegador (puerto 8099, sin tocar el 8053 del original en
  producción): carga inicial, cascada estación→variable→gráficos idéntica a antes, cambio entre
  las 3 pestañas, y el caso crítico — volver a Estadística tras pasar por Panorama/Comparar,
  incluso habiendo cambiado de estación en otra pestaña — todo se recalcula solo, sin regresión.
  Server log sin ninguna excepción Python (todo 200). Único hallazgo: un `ReferenceError` de
  consola (benigno, ya previsto) cuando `dd-variable` no existe en el DOM — no afecta el estado ni
  la funcionalidad.
- **R5 (etiqueta "instantánea" ambigua) confirmado como NO resoluble por código:** la propia guía
  del proyecto (`docs/sistemas/Analizador_Series_Guia.md`) dice que hay que confirmar con el equipo
  que mantiene el catálogo SIGMA. Se dejó diferido, no se adivinó ningún rename — y de hecho el
  nuevo `cadencia_inferida()` hace innecesario adivinarlo para la detección de firmas.
- **Entorno para seguir desarrollando esto:** usar `C:\Users\drd06\.conda\envs\analizador_series\python.exe`
  (tiene pytest, ruptures, dash-ag-grid — no `miambiente`, que es el del original en producción).
- **Puerto 8053 sigue ocupado por el original** (repo SGO, uso operativo diario, no se toca). Para
  probar esta copia hay que levantarla en otro puerto.

---

## 1.2 Fase 1 — rediseño: M5 (Panorama) + M6 (Comparar) — ✅ COMPLETA (2026-08-05)

Panorama y Comparar ahora funcionales (dejaron de ser placeholders). Núcleo reusado de M1 sin
modificar su lógica (solo se agregó `PRESETS`/`resolver_variables`/`ejecutar_preset` a
`consistencia.py`, y `panorama.py` nuevo para la agregación de la tabla).

- **`core/panorama.py`** (nuevo): `construir_indice_triaje()` — una fila por (estación, variable),
  severidad Alta/Media/OK/**N/D** (N/D = la estación no mide esa variable, vía
  `data_loader.variables_propias_estacion()` — lee solo encabezados de sus CSV, distingue "no la
  mide" de "la mide pero con MISS real"). Pre-ordenada por severidad en Python.
- **`ui/tab_panorama.py`**: tabla `dash-ag-grid` (checkboxes de selección multi-fila, API nueva
  `rowSelection: {mode: multiRow, checkboxes: true}` — confirmada funcionando) + panel alineado
  (tope 8 filas simultáneas) + checkbox "Incluir AF-BIAS" (apagado por defecto, es caro).
- **`ui/tab_comparar.py`**: 4 presets (T-rocío, HR-lluvia, veleta trabada, Tmax/Tmin/T) + modo
  libre, con selector de estación propio (Comparar opera sobre una sola estación a la vez).
- **`ui/charts.py`**: `panel_alineado_panorama` (altura fija por panel, bandas para
  CST/GAP/MISS, marcadores para OUT/NOIS/BIAS) y `overlay_multivar` (doble eje Y automático).

### 🐛 Bug real encontrado y corregido durante el smoke test con datos reales
`_grilla_esperada()` (usada por `detectar_gap`/`detectar_miss`) anclaba la grilla esperada en
`serie.index.min()` del DataFrame **crudo** (todas las variables fusionadas), no en la fase de las
lecturas VÁLIDAS de esa variable. Con datos reales de Puerto Pizarro esto producía un **falso
AF-MISS/AF-GAP masivo** sobre una variable horaria 100% completa, porque el índice crudo arrancaba
en un timestamp de otra columna (ej. `:10`) desfasado de la fase real de los datos (`:00`) — todo
punto válido "no calzaba" con la grilla. Corregido: la grilla ahora se ancla en la fase de
`serie.dropna()` pero conserva el rango completo de `serie` (para no perder huecos genuinos al
inicio/final, ej. una estación que dejó de reportar). Agregado test de regresión permanente
(`test_no_dispara_por_desfase_de_fase_con_otra_variable`). El caso de El Chira (hueco real de ~23
meses sin ningún CSV descargado para ese periodo) se verificó que sigue mostrando AF-MISS
correctamente — no era el mismo bug, era una afectación real.

También se encontró y corrigió un `NameError` (faltaban imports de `dcc`/`dbc` en
`ui/callbacks.py`) durante el mismo smoke test — sin impacto en producción porque nunca llegó a
ejecutarse fuera de esta sesión de desarrollo.

### Verificado (re-derivado, no por plausibilidad, con datos reales de 104109/103068)
- 54 tests en verde (17 nuevos: 7 de `panorama.py`, 6 de presets en `consistencia.py`, 1 de
  regresión del bug de fase, más ajustes).
- Smoke test en navegador: tabla de Panorama poblada y coloreada por severidad con las 2
  estaciones reales; panel alineado con banda AF-MISS calzando exactamente el hueco real de
  El Chira; encoge al desmarcar filas (R4 aplicado desde el diseño). Preset T-rocío muestra T y
  T-rocío calculado (no T vs HR crudo) con veredicto "sin violaciones"; HR-lluvia muestra doble eje
  + violaciones + veredicto; Tmax/Tmin/T falla con mensaje claro en estaciones sin esa variable
  (esperado — solo `105134 PIURA` la tiene, no confirmado con Piura por falta de tiempo en esta
  sesión). Regresión cero en Estadística confirmada de nuevo.
- **AF-BIAS es lento de verdad:** con 2 estaciones y ~32 variables tardó ~48s en la tabla completa.
  Además, activarlo e interactuar con la pestaña mientras corre puede dejar el navegador en un
  estado visualmente "atascado" (título "Updating..." sin contenido) — se resuelve con un reload de
  página, no es un bug de datos, es un tema de UX bajo carga pesada. Pendiente si se quiere pulir:
  deshabilitar la interacción mientras `chk-incluir-bias` está calculando.

### Pendiente de esta pasada (no bloqueante)
- No se probó el preset Tmax/Tmin/T con una estación que sí tenga la variable (`105134 PIURA`).
- El glitch de UI bajo AF-BIAS + interacción rápida no se investigó a fondo (mitigación: reload).

---

## 1.3 Fase B — consolidación: datos + código viejo — ✅ COMPLETA (2026-08-05)

Tras probar la copia nueva, se decidió adelantar la Fase B (antes "pendiente hasta confiar en la
copia nueva" — ver §2.1 histórico más abajo, ya resuelto) en lo que toca a **datos y UI vieja**,
dejando aparte el descargador por la razón que sigue.

- **`DATA/datos_meteo/` (387 MB, 355 archivos) se MOVIÓ de verdad** desde el repo SGO a este
  proyecto — no es una copia nueva, son los mismos bytes reubicados (verificado: mismo conteo de
  archivos antes/después). Motivo: esa carpeta no estaba en git en ningún lado (ni aquí ni en SGO)
  — copiar en vez de mover hubiera dejado 387 MB duplicados sin fuente de verdad única.
- **Junction de Windows** en la ubicación vieja (`SGO/DATA/datos_meteo` → apunta a
  `Analizador-Series/DATA/datos_meteo`) — así el **descargador que se sigue usando a diario**
  (`SGO/PIPELINE/automaticas/descargar_datos_meteo_sigma.py` + su
  `scripts/pipeline/Descargar_Datos_Meteo.bat`) sigue funcionando exactamente igual, sin cambiar
  nada del flujo de descarga, pero ahora escribe (a través del junction) directo a la carpeta real
  de este proyecto. **No se tocó ni el descargador ni `sigma/.env`** — el descargador propio de
  este proyecto (`descarga/descargar_datos_meteo_sigma.py`) nunca se probó con una descarga real,
  así que no se retira el mecanismo probado hasta validar el nuevo.
- **Código de la UI vieja eliminado de SGO**: `analizador_series/` (14 archivos, estaban en git →
  recuperables vía `git log`/`git checkout` si hiciera falta) + su lanzador
  `scripts/visualizadores/Iniciar_Analizador_Series.bat`. **Comiteado** (`e0d86cd`, rama
  `feat/sgo-v3-cierre-desarrollo`, 15 archivos, solo esos — se agregó por nombre, no `git add -A`,
  para no mezclar con los otros cambios sin relación que ya tenía el repo).
- **Verificado**: `data_loader.codigos_disponibles()` desde la copia nueva devuelve **178
  estaciones** (antes 141) — incluye las 27 descargadas el mismo día vía el flujo viejo, prueba de
  que el junction funciona de punta a punta.

**Nota del usuario para más adelante:** eventualmente quiere que este proyecto tenga su propio
repo git (uno nuevo, no el de SGO). No se hizo `git init` todavía.

---

## 1.4 Fase 1 — rediseño: M7 (Vista cruda: rendimiento + "Día efectivo") — ✅ COMPLETA (2026-08-21)

La pestaña "Vista cruda" (la idea propuesta en §2.6, más abajo) se construyó en una sesión
intermedia no documentada en este archivo — este bloque cubre la sesión de hoy, que la encontró
lenta al punto de congelar el navegador con estaciones de historial largo, encontró la causa raíz
(no lo que se sospechaba a primera vista) y la rediseñó. También cierra las preguntas abiertas de
§2.5 y §2.6.

**Rendimiento — causas encontradas y corregidas, de más a menos impacto:**
- **Bug crítico:** la lista "valores diarios con respaldo insuficiente" de Vista cruda no tenía
  tope — con una estación de historial largo y Tmax/Tmin nativos con respaldo horario imperfecto,
  generaba decenas de miles de `<li>` (verificado: 73.027 en un caso real) que React intentaba
  crear de una sola vez, congelando la pestaña varios minutos. Ahora la tabla-resumen muestra un
  conteo agregado por variable, no la lista día a día.
- **`data_loader.cargar_estaciones()` releía TODO el histórico de una estación en cada consulta**,
  incluso pidiendo un periodo corto (una estación puede tener un CSV de 25 MB cubriendo 15 años).
  Ahora se descartan por nombre de archivo los CSV fuera del rango pedido antes de leerlos, y los ya
  leídos se cachean en memoria por (ruta, mtime, tamaño) — `data_loader._leer_csv_estacion_actual`.
- **El dataset completo viajaba como JSON entre navegador y servidor en cada interacción**
  (`dcc.Store`) — con series largas, eso era lento independientemente de cuánto se optimizara la
  lectura de disco. Ahora `store-datos-crudos` guarda solo una "receta" chica (códigos/periodo/
  flags); el DataFrame real vive cacheado en el servidor (`ui.callbacks._CACHE_CONSULTAS`,
  `_resolver_datos_crudos`).
- **Periodo por defecto ya no es el histórico completo**: al elegir estación se auto-cargaba todo
  el rango disponible (§2.5 ya había señalado este síntoma en Panorama; acá se resolvió en la raíz
  compartida). Ahora arranca en los últimos 6 meses (`ui.callbacks.MESES_PERIODO_DEFAULT`); el
  selector de fechas compartido sigue permitiendo ampliarlo a mano. **Cierra §2.5** (el punto de
  "botones rápidos de periodo" queda resuelto por la vía de un default más chico, no por botones
  7/30/90 — no se construyeron esos botones).
- **`go.Scatter` (SVG) → `go.Scattergl` (WebGL)** en las trazas de series largas — la
  recomendación pendiente de §2.5, aplicada hoy. **Corrección a esa nota:** se descubrió que
  Plotly.js (confirmado en este entorno, Plotly 6.9.0) desactiva en silencio las trazas Scattergl
  en un eje con `rangebreaks` (warning de consola: *"scattergl traces do not work on axes with
  rangebreaks"*, sin error visible para el usuario — el gráfico simplemente queda en blanco). El
  builder de Vista cruda (`charts.panel_crudo_multivariable`) era el único con `rangebreaks` (para
  comprimir huecos largos de estaciones caídas) y tuvo que dejar de comprimirlos para poder usar
  Scattergl — un hueco largo ahora ocupa su ancho real en el eje de tiempo en vez de recortarse.
  Trade-off aceptado a favor de la velocidad.

**Bug encontrado y corregido (no de rendimiento):** al armar el `Store` liviano se descartaban las
columnas `flag_*`, así que Vista cruda no tenía forma de resaltar puntos con flag M aunque el
usuario los incluyera en "Flags a incluir" — Estadística sí las conservaba (por eso ahí sí se veían
resaltados). Corregido: `_resolver_datos_crudos` ahora conserva `flag_*` (sin costo de red, ya que
el DataFrame no viaja completo por el Store) y `panel_crudo_multivariable` pinta los puntos M en
rojo igual que `serie_temporal_apilada`.

**Rediseño de Vista cruda — cierra §2.6:**
- Layout mitad/mitad: izquierda (más ancha) las series crudas + un selector de variables a graficar
  (arranca con 6 tildadas, no todas — una estación puede tener 40+ variables propias); derecha, un
  mapa de calor compacto "día efectivo por sensor" (una fila por variable, un día por columna,
  verde/gris), mostrando SIEMPRE todos los sensores de la estación, no solo los tildados a la
  izquierda.
- **"Día efectivo" se precalcula una vez por estación y se cachea en disco**
  (`DATA/cache_dias_efectivos/{CODIGO}.pkl`, gitignored), en vez de recalcularse en cada consulta.
  Se invalida solo si cambiaron los CSV de esa estación (`data_loader.firma_estacion` — huella por
  mtime/tamaño, no relee contenido). Consultar un periodo distinto en la pestaña **nunca** dispara
  este cálculo de nuevo — el panel de día efectivo quedó deliberadamente desacoplado del selector de
  "Periodo" compartido (`ui.callbacks.actualizar_dias_efectivos_crudo` no depende de
  `store-datos-crudos`). Calculado con flags fijos a `["C"]`
  (`dias_efectivos.FLAGS_CACHE_DIA_EFECTIVO`), sin importar qué flags tenga tildados el usuario
  arriba — es un chequeo de calidad, no una vista que deba cambiar con eso.

### Verificado (re-derivado, no por plausibilidad)
- Los 75 tests unitarios existentes siguen pasando sin cambios.
- Reproducido el cuelgue de 73.000 filas con una estación real (472A446C · BETA SANTIAGO, 45
  variables, histórico 2010–2026) instrumentando con trazas de rendimiento del navegador antes y
  después del fix; confirmado que el mismo escenario (histórico completo, 45 variables) carga
  completo tras la corrección.
- Confirmada la incompatibilidad Scattergl+rangebreaks con una figura standalone en este entorno
  (mismo Plotly 6.9.0 del proyecto): el warning de consola citado arriba apareció textual.
- Confirmado el highlight de flag M generando las 2 trazas esperadas (línea azul + marcadores
  rojos) para una variable con flags M reales (109091 · SAUCEPAMPA, `n_rauv_a_inst`, 1.301 puntos M
  en su histórico).

### Pendiente / a tener en cuenta para la próxima sesión
- El caché de "día efectivo" solo tiene una llave por estación (no por combinación de flags) —
  fijo a `C`. Si en el futuro se necesita que refleje otro criterio, hay que extender la clave.
- La tabla-resumen de Vista cruda ya no lista fechas puntuales de "valores sospechosos", solo un
  conteo por variable — no hay drill-down día a día todavía (se decidió así el 2026-08-21 porque
  la lista sin límite fue la causa del cuelgue de 73.000 filas; si hace falta el detalle puntual,
  construirlo como acción explícita — ej. exportar o expandir por fila — no como lista siempre
  visible).
- Ambiente de pruebas de esta sesión: con la máquina bajo poca RAM libre, la extensión
  `claude-in-chrome` resultó poco confiable para probar esta app en el navegador (timeouts de
  captura de pantalla incluso con la página sana) — el servidor MCP `chrome-devtools` (protocolo
  CDP directo) dio resultados consistentes. Preferirlo si se vuelve a probar esta app en navegador.
- Sigue sin `git init` en este proyecto (ver nota en §1.3) — el usuario lo confirmó explícitamente
  para hoy: por ahora solo esta documentación, sin control de versiones todavía.

---

## 2. Pendientes

### 2.1 Fase B — limpiar el repo SGO — ✅ hecha en lo esencial (ver §1.3), 1 punto pendiente
`analizador_series/` (código UI) y `DATA/datos_meteo/` (movida de verdad, no copiada) ya se
retiraron de SGO — ver §1.3 para el detalle. **Sigue vivo a propósito**:
`PIPELINE/automaticas/descargar_datos_meteo_sigma.py` + `scripts/pipeline/Descargar_Datos_Meteo.bat`
— es el único mecanismo de descarga PROBADO; recién cuando el descargador propio de este proyecto
(`descarga/descargar_datos_meteo_sigma.py`) se valide con una descarga real, tiene sentido
retirarlo también de SGO. NO tocar `sigma/` en SGO (otros pipelines la usan). Commit del borrado
de `analizador_series/` ya hecho (`e0d86cd`) — sin pendientes en este punto.

### 2.2 Investigación de referentes — ✅ COMPLETA (2026-07-14, 35.6 KB)
`docs/referencias_qc_comunidad.md` cubre: resumen ejecutivo build-vs-adopt por AF-*, tabla de proyectos
open-source, metodología de TODOS los organismos (KMA/CRC-SAS/IDEAM/SMN/INMET/Synoptic/TITAN + OMM
ET-AWS/MADIS/GHCN-Durre 2010/ECCC/ECA&D-EUMETNET/MeteoSwiss/DWD/BoM/Copernicus), matriz AF-*→umbrales,
y fuentes. **Corrección importante:** "WMO-No.1238" estaba MAL atribuido — es el *Manual on HQ-GDMFC*
(datos climáticos), NO la guía de QC de AWS; la guía real es ET-AWS (Zahumenský 2004). **Caveats:**
umbrales operativos de MeteoSwiss/DWD/BoM/Copernicus no publicados (quedan a nivel metodológico); los
umbrales de la guía OMM ET-AWS salen de extracción automática del PDF — reverificar contra el PDF antes
de citarlos en norma.
**Hallazgo accionable clave:** adoptar **`ioos_qc`** (Apache-2.0; gross_range/spike/rate_of_change/
flat_line/attenuated_signal/climatology), **`MetObs-toolkit`** (MIT, diseñado para redes de superficie)
y **`ruptures`** (AF-BIAS). Umbrales sub-diarios más aplicables: Synoptic (rate-of-change) y KMA
(step/persistencia por minuto). Recalibrar todo con datos SENAMHI.

### 2.3 Rediseño Fase 1 (el desarrollo en sí) — M1+M3+M5+M6 hechos (ver §1.1/§1.2)
Spec en `docs/2026-07-13-rediseno-fase1-design.md`. Las 3 pestañas están funcionales de punta a
punta. Lo que queda de la spec original, no bloqueante:
- **`ioos_qc` + `MetObs-toolkit`** nunca se sumaron al requirements (hallazgo de la investigación
  de referentes) — se construyó todo a mano en `deteccion_afectaciones.py`/`consistencia.py` en
  vez de adoptarlos. Evaluar si vale la pena migrar después de calibrar con datos reales.
- ~~Probar el preset Tmax/Tmin/T con `105134 PIURA`~~ → **HECHO, confirmado por el usuario
  (2026-09-29): funciona.**
- R5 (etiqueta "instantánea" ambigua) sigue diferido para confirmación OFICIAL del equipo de
  catálogo SIGMA, pero el 2026-09-29 apareció evidencia corroborante independiente: en
  `Dashboard-para-monitoreo-de-la-operatividad/PIPELINE/automaticas/01_procesamiento_csv.py`
  (`_SENSOR_LOOKUP`, líneas ~34-97) hay familias de variables donde SIGMA usa explícitamente el
  patrón `_INST` vs `_PROM` (ej. `N_RAUV_A_INST`/`N_RAUV_A_PROM`, `N_VOLAG_INST_H`/`N_VOLAG_PROM`).
  Para las familias sin `_PROM` explícito (airtemp, humedad, presión, radsolar) la variable sin
  sufijo ocupa ese mismo rol estructural — segunda fuente independiente, no solo estadística sobre
  datos reales, que apunta en la misma dirección que la decisión provisional del 04/09. Sigue sin
  ser confirmación textual de SIGMA, pero sube la confianza. Ver `DATA/automaticas/01_csvs/<DZ>/
  sensores.csv` y `variables.csv` de ese pipeline para el detalle crudo por estación.
- Calibrar umbrales de `config/afectaciones.yaml` con más datos reales (hoy son valores iniciales
  razonables, no medidos — ej. la ventana de AF-NOIS puede dar falsos positivos borderline con
  ventanas muy cortas, visto en pruebas). **Idea nueva del usuario (2026-09-29), sin explorar
  todavía:** calibrar contra las reglas de control de calidad fino que ya aplica la SGD (Subdirección
  de Gestión de Datos, ver `Documentacion/comprension_negocio/cadena_valor_dato_sgr_sgd.md`) en vez
  de valores puestos a ojo — el Analizador ya consume el resultado de SGD indirectamente vía
  `flag_n_*`/`filtrar_por_flags`, pero los umbrales de `afectaciones.yaml` (ej. `out.delta_max`) son
  independientes de esas reglas. Ese documento describe la frontera de responsabilidad, no los
  umbrales numéricos exactos de SGD — para calibrar de verdad hace falta pedírselos directamente a
  SGD, no están en ningún repo revisado hoy.
- El glitch de UI bajo AF-BIAS + interacción rápida (ver §1.2) no se investigó a fondo — el usuario
  lo volvió a confirmar el 2026-09-29 (AF-BIAS sigue demorando mucho).
- **Caché de "día efectivo" ya no se invalida solo por CSV** (2026-09-29): se agregó
  `_version_logica_cache()` en `core/dias_efectivos.py` — hashea el propio archivo +
  `deteccion_afectaciones.cadencia_inferida`, y ese hash entra a la clave de invalidación del
  `.pkl` junto a `firma_estacion` y `umbral_pct`. Cualquier cambio futuro a esa lógica invalida el
  caché solo, sin que nadie tenga que acordarse de borrar `DATA/cache_dias_efectivos/*.pkl` a mano.
  3 tests nuevos en `tests/core/test_dias_efectivos.py` (`TestCacheDiasEfectivosEstacion`). Efecto
  colateral esperado: los 45 `.pkl` existentes hoy quedaron automáticamente obsoletos por este mismo
  cambio y se recalcularán solos en la próxima consulta — es la prueba de que el mecanismo funciona.

### 2.4 Sesión nueva rooteada acá
Para desarrollar Fase 1 conviene abrir una sesión del asistente con **`Analizador-Series/` como raíz**
(memoria/CLAUDE/git son por-proyecto). Considerar `git init` acá cuando se decida publicar.
**Ya se hizo** (sesión 2026-08-05): todo lo de M1 a M6 + Fase B de consolidación se construyó desde
una sesión rooteada en `Visualizador/` (otro proyecto), por eso este documento es la única memoria
confiable — la próxima sesión debería abrirse ya en `Analizador-Series/` como raíz.

### 2.5 Mejoras discutidas hoy (2026-08-05), NO implementadas — ✅ resuelto en §1.4 (2026-08-21)
- **Zoom lento en series de varios años**: causa confirmada — `go.Scatter` (SVG) en
  `ui/charts.py` no escala a millones de puntos (10 años a 10 min). Fix recomendado y **verificado
  que funciona en este entorno** (Plotly 6.9.0 ya instalado, `go.Scattergl` construye 10x más rápido
  que `go.Scatter` con 3M puntos de prueba): cambiar las trazas de la serie cruda a `go.Scattergl`
  (WebGL) — casi un cambio de nombre de clase, sin tocar la lógica. Aplica a
  `serie_temporal_apilada` (Estadística, mismo código que tenía el original en SGO — nunca se
  tocó), y a los builders nuevos de Panorama/Comparar. Pendiente decidir: ¿solo en esta copia, o
  también aplicarlo si algún día se retoma el original? (el original ya no existe — ver §1.3 — así
  que en la práctica esto ya solo aplica acá).
- **Panorama mezcla incidentes viejos con nuevos**: el índice de triaje evalúa severidad sobre todo
  el periodo cargado, que por defecto es el historial completo de la estación — el usuario señaló
  que eso no calza con su flujo real (validar una alerta puntual, o revisar solo lo reciente sin
  repetir ruido de incidentes ya documentados). Mitigación hoy: acotar el selector de "Periodo"
  compartido a mano. Mejora propuesta, no construida: botones rápidos de periodo (7/30/90 días)
  junto al selector, para acotar de un clic.

### 2.6 Idea nueva del usuario (cierre de sesión 2026-08-05): vista cruda multivariable + "Día efectivo" — ✅ construida y rediseñada, ver §1.4 (2026-08-21)

Pedido explícito, sin diseñar ni construir todavía — para la próxima sesión. Resumen fiel de lo
que pidió, para no perder matices:

1. **Una vista que muestre TODAS las variables de la estación como series de tiempo crudas**, sin
   la parte "estadística" de hoy (sin series derivadas, sin histogramas, sin percentiles).
   Estadística sigue mostrando UNA variable a la vez con todo ese aparataje; esto sería lo
   opuesto: todas las variables a la vez, solo la serie cruda — más cercano en espíritu al panel
   alineado de Panorama, pero mostrando siempre todas las variables, no solo las que el usuario
   "abre" desde una tabla.
2. **Lógica de "DÍA EFECTIVO"** en esa misma vista: por cada día calendario, si el % de lecturas
   sub-diarias recibidas (respecto a lo esperado según la cadencia real de esa variable) es
   **≥ 75%**, marcar ese día como efectivo — evidenciarlo visualmente. Motivo explícito del
   usuario: por debajo de ese umbral no se puede calcular un dato diario medio confiable (si
   solo llegaron, digamos, 15 de las 24 horas esperadas, el promedio diario de esa variable no es
   representativo).
3. **Pregunta que el propio usuario dejó abierta, sin resolver** — confirmar antes de diseñar:
   ¿esto aplica solo a variables horarias/sub-diarias por defecto, con un **botón aparte** para
   sumar también las variables que ya son nativamente diarias (Tmax/Tmin, etc. — no tiene sentido
   evaluarles "% de lecturas del día" del mismo modo, porque ya SON el dato diario)? El usuario se
   inclina por defecto = solo horarias/sub-diarias, con un toggle para incluir las diarias aparte.

**Piezas ya existentes para reusar (no reinventar):**
- `core/deteccion_afectaciones.cadencia_inferida(serie)` — ya infiere la cadencia real por
  variable; de ahí sale cuántas lecturas se esperan por día calendario (ej. horaria → 24/día).
- El patrón de `core/panorama.py` (agregación pura, testeable sin Dash) es el molde a seguir para
  una función nueva tipo `dias_efectivos(serie, umbral=0.75) -> pd.Series` (por día calendario,
  True/False o el % exacto).
- `ui/charts.panel_alineado_panorama` ya sabe pintar bandas de color sobre un eje de tiempo
  compartido para varias variables a la vez — la vista nueva podría ser una variante de ese
  builder, siempre mostrando todas las variables (no vía tabla de triaje), con una banda de
  "día efectivo / no efectivo" en vez de (o además de) las firmas AF-*.

**Explícitamente NO diseñado todavía** (para no improvisar en la próxima sesión sin alinear
primero): dónde vive esta vista (¿pestaña nueva, o dentro de Panorama, o modo alterno de
Estadística?), cómo se visualiza el día efectivo (¿banda bajo el eje X de cada serie, calendario
tipo heatmap aparte, columna en una tabla?), y si el 75% es fijo o configurable por variable en
YAML (mismo patrón que `afectaciones.yaml`).

**Resuelto (ver §1.4, 2026-08-21):** pestaña propia "Vista cruda" (ya existía de una sesión
intermedia); el día efectivo terminó como heatmap aparte a la derecha (no banda bajo cada serie, esa
banda se sacó por el rediseño de §1.4), siempre con TODAS las variables de la estación. El 75%
sigue fijo (`dias_efectivos.UMBRAL_DIA_EFECTIVO`), no configurable por variable en YAML — no se
tocó ese punto.

---

## 3. Acoplamientos residuales con SGO (para autonomía total, futuro)
- `data_ref/estaciones.db` es un **snapshot** del catálogo de `sgo.db`; se desactualiza si SGR da de
  alta/baja estaciones. Refrescar re-extrayendo, o portar un mini-generador de catálogo.
- El descargador comparte lógica de login SIGMA con el pipeline SGO (ahora duplicada). Aceptado.
