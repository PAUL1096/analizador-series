# Implementation Plan: módulo emplazamiento compartido

Spec: `docs/SPEC-emplazamiento-compartido.md` (aprobado 2026-09-30). Reemplaza el plan anterior
(control-calidad, 10/10 tareas completas, ver `tasks/todo.md` git history si hace
falta consultarlo).

## Overview

Pestaña nueva "Emplazamiento compartido" que superpone, para un par de estaciones co-ubicadas
(automática + convencional, <100m), la serie continua de la automática con los
puntos discretos de la convencional — temperatura o precipitación, sin ninguna
estadística de comparación (eso queda fuera del alcance de esta
herramienta). Es una vista de inspección visual rápida, no un estudio
de validación.

## Architecture Decisions

- **`estado_operatividad` del Success Criteria #1 ya existe — no hay que
  agregar ninguna columna para eso.** Verificado contra el schema real de
  `data_ref/estaciones.db`: ya tiene `activa INTEGER` (0/1), poblada para las
  1076 estaciones actualizadas por `actualizar_geodatos.py`. El Excel de origen
  (`georeferencias_2026-09-29.xlsx`, hoja "Georeferencias") tampoco trae una
  columna de estado operativo — solo `Latitud`/`Longitud` son datos nuevos que
  agregar. Task 1 se reduce a agregar esas dos columnas; donde el spec o el
  código necesiten "operatividad", se usa la columna `activa` ya existente
  (aunque el spec la deja fuera del filtro de la UI: "sin filtro de solo
  OPERATIVA en el dropdown").
- **`core/emplazamiento.py` consulta `estaciones.db` directamente** (mismo patrón
  de conexión sqlite que `data_ref/actualizar_geodatos.py`), en vez de pasar
  por `data_loader.metadata_estaciones()`. Esa función devuelve un DataFrame
  pensado para series ya cargadas (altitud/region_natural, no lat/lon/
  categoria puros) — mezclar ambos usos la complica sin necesidad. Consistente
  con el estilo "funciones puras en `core/`" del spec.
- **Sin caché en disco para `calcular_pares_colocados()`.** El propio spec lo
  aclara: 413×681 combinaciones es trivial (ya validado con datos reales, <1s).
  Los pares se recalculan en cada render de la pestaña — no vale la pena el
  patrón de caché con hash de versión de lógica que sí tiene
  `resultado_control_calidad_estacion` (ese cachea sobre históricos completos
  de CSV, un problema de otra escala).
- **Extensión de `overlay_multivar` es aditiva, no un rediseño.** `extra_series`
  hoy es `[{"nombre","serie","eje","dash"}]` con color fijo `#2ca02c` y `mode`
  implícito de línea (`go.Scattergl` con `line=...`, sin `mode` explícito →
  Plotly asume `"lines"`). Se agrega `"modo"` (default `"lines"`) y `"color"`
  (default `"#2ca02c"`, para no romper el único call site actual en
  `callbacks.py:865` que no pasa color). Cuando `modo="markers"` no se debe
  pasar `line=...` a la traza (Plotly ignora `line` en modo markers pero por
  claridad se arma el `dict` de kwargs condicionalmente).
- **`tab_emplazamiento` no toca `dd-codigos`/`dt-periodo` compartidos.** Sigue el
  patrón ya usado por `renderizar_tab` (Estadística/Comparar/Vista cruda
  reciben sus dropdowns ya poblados vía `State`, evitando la carrera de
  callbacks documentada en el comentario de `callbacks.py:351-355`) — Emplazamiento compartido
  puebla su propio dropdown de pares directamente desde
  `emplazamiento.calcular_pares_colocados()`, sin depender de qué haya elegido el
  usuario arriba.

## Task List

### Phase 1: Datos base (geodatos + core puro)
- [ ] Task 1: Latitud/longitud en estaciones.db
- [ ] Task 2: `core/emplazamiento.py` — pares co-ubicados + equivalencia de variables

### Checkpoint: Fase 1
- [ ] `pytest tests/` completo en verde (167 + nuevos)
- [ ] Smoke test: `calcular_pares_colocados()` sobre la DB real devuelve ~204
      pares, ordenados por distancia, ninguno automática↔automática

### Phase 2: Visualización (chart + UI)
- [ ] Task 3: Extender `overlay_multivar` (modo markers + color por serie)
- [ ] Task 4: `ui/tab_emplazamiento.py` — layout de la pestaña

### Checkpoint: Fase 2
- [ ] `pytest tests/` completo en verde
- [ ] Layout renderiza standalone (sin callbacks aún) sin excepciones

### Phase 3: Integración (callbacks + CC)
- [ ] Task 5: Callbacks de Emplazamiento compartido — cargar par, graficar, filtro de periodo
- [ ] Task 6: Checkbox de CC en Emplazamiento compartido

### Checkpoint: Completo
- [ ] `pytest tests/` completo en verde (167 + todos los nuevos)
- [ ] Smoke test en navegador (puerto ≠ 8053/8054/8060/8099): elegir un par
      real, ver la línea continua de la automática + puntos de la
      convencional distinguibles, cambiar variable (temperatura↔precipitación),
      cambiar periodo, activar/desactivar CC
- [ ] Success Criteria 1-7 de `docs/SPEC-emplazamiento-compartido.md` verificados por
      inspección (ninguna estadística de comparación, ninguna escritura fuera
      de la carpeta del proyecto)

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ningún CSV convencional real descargado localmente en este momento para probar en navegador (mismo bloqueo documentado en `tasks/todo.md` de control-calidad, Fase 2/3) | Medio — no se puede hacer smoke test end-to-end con datos reales de convencional | Los 204 pares vienen de `estaciones.db` (metadata, no requiere CSV descargado); si al momento de probar no hay CSV de la convencional del par elegido, documentar el bloqueo igual que se hizo en control-calidad (no es bug de esta tarea) y verificar con datos sintéticos + al menos un par cuya convencional sí tenga CSV descargado |
| `overlay_multivar` es compartida con Comparar — un cambio mal hecho rompe una pestaña ya en producción | Alto si se rompe, bajo si se sigue el plan | Task 3 lleva test explícito de "comportamiento default sin `modo`/`color` no cambia" antes de tocar `tab_emplazamiento`/callbacks que dependen de ella |
| Diccionario de equivalencia de variables convencionales fue confirmado con un solo CSV real (SAN REGIS, 104098) — otras convencionales podrían tener columnas distintas | Bajo (el spec ya lo asume: "una estación puede no tener alguna") | `core/emplazamiento.py` debe omitir sin error cualquier columna de la equivalencia que no exista en el CSV real de esa estación puntual — mismo patrón defensivo que `control_calidad.tiene_regla_cc` |

## Open Questions

Ninguna bloqueante — el spec ya cerró todas las asunciones (ver su sección
"Open Questions"). Los dos hallazgos de esta sesión de planeamiento
(`estado_operatividad` = `activa` ya existente; `core/emplazamiento.py` no reusa
`metadata_estaciones`) están resueltos arriba en Architecture Decisions, no
requieren decisión del usuario.
