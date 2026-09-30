# Rediseño del Analizador de Series — Diseño (Fase 1)

- **Fecha:** 2026-07-13
- **Ámbito:** `analizador_series/` (Plotly Dash, puerto 8053)
- **Estado:** diseño validado en brainstorming; pendiente revisión de este spec antes de escribir el plan.
- **Entorno:** conda `miambiente` (`C:\Users\drd06\.conda\envs\miambiente\python.exe`).

---

## 1. Contexto y propósito

El Analizador de Series es una herramienta Dash independiente que opera sobre las series ya
descargadas de SIGMA (`DATA/datos_meteo/{automaticas,convencionales}/*.csv`, ya etiquetadas con
flags C/M/SD). **No es control de calidad (QC)** — es aseguramiento de datos.

El propósito rector (fijado en esta sesión) es doble y ambos giran sobre la taxonomía de
afectaciones **AF-\***:

1. **Validar y reclasificar los incidentes que emite el motor de alertas.** Hallazgo verificado
   (`docs/experimentos/informe_soporte_tesis.md`, `enums.py`, `catalogos_maestros.md`): **el motor
   solo emite `AF-MISS`** (afectación hardcodeada, GAP-3 del motor). Los otros 7 tipos AF-\* los
   asigna **el analista editando el incidente después de mirar la serie**. En automáticas ~46 % de
   los incidentes terminan siendo algo distinto a MISS (AF-BIAS 21 %, AF-GAP 15 %, AF-OUT 8 %, resto
   CST/REP/NOIS). El analizador es la **cabina de validación** que da la evidencia visual para
   asignar el AF-\* correcto.
2. **Descubrir afectaciones que el motor no ve.** El motor es de disponibilidad (D % ≥ 80 %), así
   que es ciego a datos presentes pero erróneos: una estación que transmite al 100 % pero está
   **congelada (AF-CST)** o **derivando (AF-BIAS)** nunca dispara alerta. El analizador barre esas
   firmas proactivamente.

**Principio rector (por el riesgo):** la detección de firmas AF-\* **sugiere, no dictamina**. Las
marcas son pistas para que el analista mire y confirme; el tipo AF final lo pone él. Coherente con
"aseguramiento, no QC" y con que el AF lo asigna el humano.

### Catálogo AF-\* (verdad de negocio, verificado en `catalogos_maestros.md`)

| Código | Qué es | ¿Firma en la serie? |
|---|---|---|
| AF-MISS | Ausencia total de dato | Sí — hueco total |
| AF-GAP | Registro discontinuo (huecos intermitentes) | Sí |
| AF-OUT | Valor fuera de rango físico (spike) | Sí |
| AF-NOIS | Ruido / varianza anómala | Sí |
| AF-BIAS | Sesgo / deriva / escalón de nivel | Sí (change-point) |
| AF-CST | Constante / congelado (flatline) | Sí — Δ≈0 sostenido |
| AF-REP | Pérdida de representatividad (p.ej. ciclo diurno roto) | Sí (difícil) |
| AF-RIS | Riesgo de infraestructura (caseta, cerco, letrero) | **No** — viene de campo, fuera del analizador |

---

## 2. Objetivos y no-objetivos

**Objetivos (Fase 1, standalone):**

- Separar la exploración de series de lo estadístico (R1).
- Mostrar **todas** las variables de una estación y elegir cuáles ver (R2).
- **Combinar** variables para chequeos de consistencia cruzada (R3).
- Paneles **compactos y de altura constante** (R4).
- Corregir la etiqueta "(instantánea)" mal aplicada (R5).
- Detectar firmas AF-\* como **pistas** para validar/descubrir (R6).

> **Alcance de red:** Fase 1 se centra en **estaciones automáticas** (grilla 10-min/horaria). El
> loader ya carga convencionales, pero las firmas AF y la consistencia cruzada son
> automáticas-céntricas; **convencionales** (cadencia diaria/manual) se revisan aparte.

**No-objetivos (explícitos):**

- **Integración con la BD de incidentes** (leer `sgo.db`/`sgo_v3.db`, saltar de una alerta a su
  serie, marcar el AF confirmado): **Fase 2**, fuera de este spec.
- **Reorganización de los archivos de datos por estación** (R7): track separado de infraestructura.
  No es bloqueante — `data_loader.cargar_estaciones()` ya fusiona y deduplica los CSV por estación.
- **Reimplementar QC** ni recalcular flags C/M/SD.
- Contraste con estaciones vecinas para AF-BIAS: opcional/Fase 2 (requiere alinear multi-estación).

---

## 3. Arquitectura

Se respeta el patrón actual: `core/` = lógica pura testeable sin Dash; `ui/` = capa Dash;
config en YAML.

### 3.1 Módulos

**Reutilizados sin cambiar su lógica:**
- `core/data_loader.py` — carga + merge + dedupe por (código, datetime); `variables_disponibles()`;
  `frecuencia_inferida()` (para distinguir cadencia vs falla).
- `core/series_derivadas.py`, `core/distribuciones.py`, `core/detector_eventos.py` — se consumen
  desde la pestaña Estadística intactos.

**Nuevos (core, lógica pura):**
- `core/deteccion_afectaciones.py` — dado (serie, timestamps, flags, `rango_fisico`, cadencia
  esperada) devuelve firmas AF-\* candidatas con parámetros y una **severidad**. Solo sugiere.
- `core/consistencia.py` — chequeos cruzados entre variables (T vs T-rocío, HR vs lluvia,
  veleta trabada, Tmax/Tmin/T). Incluye `punto_de_rocio(t, hr)` (Magnus, ver §5).

**UI reestructurada en pestañas (`dcc.Tabs`), cada una un módulo aislado:**
- `ui/layout.py` — shell + selectores compartidos (estación(es), periodo, flags) + `dcc.Tabs`.
- `ui/tab_panorama.py` (+ callbacks) — índice de triaje + tiras alineadas.
- `ui/tab_comparar.py` (+ callbacks) — overlay con presets + modo libre.
- `ui/tab_estadistica.py` — los paneles actuales movidos aquí.
- `ui/charts.py` — nuevos builders (`tira_variable`, `overlay_multivar`) + **fix de altura por
  panel** (R4, ver §6).

### 3.2 Dependencias nuevas (de la investigación web verificada, jul-2026)

- **`ruptures`** (BSD-2, mantenido) — detección de change-points (PELT) → AF-BIAS (escalón/deriva).
  Es lo único que no se reimplementa bien a mano.
- **`dash-ag-grid`** (MIT, mantenido) — tabla del índice de triaje (ordenable por severidad, badges,
  sparklines por celda).

**Construir nosotros (más explicable ante el analista, dependencias que ya están):**
CST/GAP/MISS/OUT/NOIS con pandas/numpy/scipy; punto de rocío (Magnus, 1 línea); consistencia
cruzada; veleta trabada; toda la visualización con Plotly nativo.
**Omitidos:** `pyod`, `MetPy` (pesados), `titanlib` (LGPL, estancado 2022, es QC espacial — solo se
usa su checklist de tests como referencia). **Diferido:** `stumpy` (solo si AF-REP no sale con
métodos simples: STL / correlación día-a-día / amplitud diurna).

### 3.3 Flujo de datos

```
selección estación(es) + periodo + flags
        │
        ▼
core.data_loader.cargar_estaciones()  → df (merge+dedupe, todas las variables)
        │  (dcc.Store, compartido)
        ├──► Panorama:  deteccion_afectaciones por variable → índice (ag-grid) + tiras (charts)
        ├──► Comparar:  consistencia (+ derivadas puntuales) → overlay doble-eje + violaciones
        └──► Estadística: series_derivadas / distribuciones / detector_eventos (como hoy)
```

---

## 4. Las tres pestañas

### 4.1 Panorama (híbrido) — validado

Dos zonas apiladas:

**① Índice de triaje** (componente `dash-ag-grid`): una fila por variable, ordenable, **ordenado por
severidad por defecto**. Columnas: `Severidad ▼ · Variable · Firma AF · % válidos · mini-tendencia
(sparkline) · cadencia`.

> **Caveat (verificar en implementación):** las *sparklines nativas* de AG Grid son función
> **Enterprise** (licenciada). Con el `dash-ag-grid` MIT/community, la mini-tendencia va por
> **cell renderer propio (SVG)**, o se omite de la tabla y queda solo en las tiras alineadas.

Distingue el **rojo real** de la firma AF del **ruido de grilla** (una
variable horaria en archivo 10-min marca ~17 % válidos pero **sin firma** = verde; no es falla, es
cadencia — resuelve la observación del "13 % válidos").

**② Panel alineado**: las variables que se abren desde el índice se apilan **compartiendo el eje de
tiempo**, con la firma resaltada en la propia tira (banda para CST/GAP, marcador para OUT). Permite
ver si dos variables cayeron **a la vez** (clave para validar el incidente) o son independientes.

```
┌ Índice de triaje (ag-grid, orden por severidad) ─────────────────────┐
│ Sev ▼ │ Variable      │ Firma AF        │ %vál │ tendencia │ cadencia │
│ ●Alta │ Temp. Aire    │ AF-CST plano 3d │ 100% │ ▁▂▁▔▔▔▔▔  │ horaria  │◄ sel
│ ●Alta │ Precipitación │ AF-OUT pico     │  96% │ ▁▁▁█▁▁▁    │ 10-min   │
│ ●Med  │ Presión       │ AF-GAP 8%       │  88% │ ▁▂ ⋯ ▂▁    │ horaria  │
│ ○OK   │ Humedad Rel.  │ sin firma       │ 17%*│ ▂▇▂▇▂▇     │ horaria  │
└──────────────────────────────────────────────────────────────────────┘
┌ Panel alineado (eje de tiempo compartido) ───────────────────────────┐
│ Temp. Aire   [AF-CST] ▁▂▁▔▔▔▔▔▔▔▔▔▔▔▔                                 │
│ Precipitación[AF-OUT] ▁▁▁▁▁▁█▁▁▁▁▁▁▁▁                                 │
│              May31 ── Jun7 ── Jun14 ── Jun21 ── Jun28                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Comparar — validado (presets + modo libre)

Overlay de 2–3 variables sobre eje de tiempo compartido, **doble eje Y** cuando difieren las
unidades (`make_subplots(specs=[[{"secondary_y":True}]])`). **Chips de presets** que codifican los
chequeos de dominio + **modo libre** para cualquier par:

| Preset | Qué resalta | AF sugerido |
|---|---|---|
| **T vs T-rocío** | `T-rocío > T` (imposible); rocío calculado de T+HR (Magnus) | AF-OUT / AF-BIAS |
| **HR vs Lluvia** | HR pegada 100 % sin lluvia; lluvia con HR baja | AF-CST / incoherencia |
| **Viento vel/dir** | dirección constante con velocidad > 0 (veleta trabada) | AF-CST (dirección) |
| **Tmax/Tmin/T** | T fuera de [Tmin, Tmax] del día; Tmax < Tmin | AF-OUT |

Las violaciones se marcan con banda + marcadores y un **veredicto** textual con la sugerencia de
clasificación. Igual que en Panorama: sugiere, no dictamina.

### 4.3 Estadística — definida (mover intacto)

Los paneles actuales (`histograma_con_percentiles`, `boxplot_por_grupo`, `heatmap_eventos_mes_hora`,
tabla de eventos por percentil, selector de serie derivada, slider de percentil) se **mudan tal cual**
a `ui/tab_estadistica.py`. Sin cambios funcionales en Fase 1.

---

## 5. Detección de firmas AF-\* (core.deteccion_afectaciones)

Funciones puras; cada una devuelve `{tipo, severidad, parametros, indices_afectados}` o vacío.
Umbrales configurables por variable en YAML (ver §7). **Todas son sugerencias.**

| Firma | Método (construir, salvo BIAS) | Notas |
|---|---|---|
| **AF-CST** | racha de `Δ==0` (o `rolling(w).std()==0`) ≥ N pasos | veleta trabada = AF-CST sobre dirección con vel>0 |
| **AF-GAP** | reindex a grilla esperada + rachas de NaN intermitentes | usa cadencia esperada, no la grilla del archivo |
| **AF-MISS** | ausencia total en el periodo / racha larga de NaN | lo único que el motor ya detecta |
| **AF-OUT** | fuera de `rango_fisico` de la variable, o `|Δ|` excesivo | umbral físico > detector estadístico genérico |
| **AF-NOIS** | z-score del rolling-std por encima de umbral | dispersión anómala |
| **AF-BIAS** | `ruptures.Pelt(model="rbf")` → change-points de nivel/tendencia | **única dependencia de detección** |
| **AF-REP** | diferido: STL / correlación día-a-día / colapso de amplitud diurna | evaluar antes de traer `stumpy` |

**Severidad** (para ordenar el índice): función simple de (tipo AF × magnitud × duración). Definir
tabla explícita en implementación; p.ej. CST/OUT largos → Alta, GAP/NOIS → Media, sin firma → OK.

**Punto de rocío (Magnus, WMO; equivale a Bolton-1980 de MetPy):**

```python
g = np.log(hr / 100) + 17.62 * t / (243.12 + t)
td = 243.12 * g / (17.62 - g)   # °C, desde t (°C) y hr (%)
```

---

## 6. Correcciones puntuales

- **R4 — altura de panel:** hoy `charts.py:173` fija **altura total** repartida por porcentajes, por
  lo que al quitar la derivada el único panel se estira al 100 %. Cambio: **altura fija por panel**
  (`height = cabecera + n_paneles * alto_panel`), de modo que quitar series **encoge** la figura en
  vez de estirar el panel restante. Aplica a las tiras del Panorama y al panel apilado.
- **R5 — etiqueta "(instantánea)":** en `series_disponibles.yaml`, `n_humedad` y `n_humedad_inst`
  comparten `display_name "Humedad Relativa (instantánea)"`. `n_humedad` es casi seguro el
  **agregado horario**, no la instantánea. **Acción:** verificar la definición exacta contra el
  catálogo de variables SIGMA antes de reetiquetar (no adivinar). Revisar la convención `_inst` para
  el resto de variables con par (`n_airtemp`/`n_airtemp_inst`, `n_presatm`/`n_presatm_inst`).

---

## 7. Configuración (YAML)

- `series_disponibles.yaml` — se mantiene (define series derivadas por variable, ya trae
  `rango_fisico`). Se corrigen los `display_name` (R5).
- **Nuevo `afectaciones.yaml`** (o sección en el existente) — umbrales AF por variable:
  ventana/longitud mínima de racha para CST, umbral de rolling-std para NOIS, penalización de
  `ruptures` para BIAS, cadencia esperada para GAP, etc. Mantener el enfoque YAML-driven del proyecto.

---

## 8. Manejo de errores y bordes

- Estación sin CSV / periodo sin datos → índice y paneles vacíos con mensaje claro, sin excepción.
- Variable ausente para una estación → fila del índice marcada "sin datos", no error.
- Cadencia mixta entre variables → `frecuencia_inferida()` por variable; la detección de GAP usa la
  cadencia esperada de cada variable, no una global.
- NaN por flags excluidos → se preservan como hueco en la serie cruda (comportamiento actual); la
  detección opera sobre los valores incluidos según el filtro de flags.
- `ruptures` sobre series muy cortas o casi todo NaN → guardas que devuelven "sin firma" en vez de
  fallar.
- Multi-estación / multi-anual (~125k puntos × N) → el índice de triaje resume; las tiras dibujan
  solo variables abiertas. Vigilar rendimiento; degradar a downsampling si hace falta (medir antes).
- **Coste de detección en la carga del Panorama:** las firmas baratas (CST/GAP/MISS/OUT/NOIS) son
  vectorizadas (pandas/numpy) y se calculan al vuelo; **AF-BIAS con `ruptures` es la cara** — sobre
  17 variables × N estaciones puede volver lenta la carga. Calcular BIAS de forma
  **perezosa/cacheada** (o con penalización gruesa/downsampling), nunca en cada render. Medir antes
  de optimizar.

---

## 9. Pruebas

- **core puro, unit tests** (sin Dash), estilo del proyecto:
  - `deteccion_afectaciones`: series sintéticas con firma conocida (flatline inyectado → AF-CST;
    huecos → AF-GAP; spike fuera de rango → AF-OUT; escalón → AF-BIAS vía ruptures; ruido → AF-NOIS)
    y series limpias → sin firma (guardar contra falsos positivos).
  - `consistencia`: casos construidos con violación (T-rocío > T; HR 100 % sin lluvia; dirección
    constante con vel>0) y casos coherentes.
  - `punto_de_rocio`: valores de referencia conocidos (T, HR → Td esperado).
- **charts**: builders devuelven `go.Figure` con el nº de paneles y altura esperados (verifica R4).
- Smoke test de la app: cada pestaña renderiza con una estación real de `DATA/datos_meteo/`.

---

## 10. Pendientes / a verificar antes o durante implementación

1. Definición exacta de `n_humedad` vs `n_humedad_inst` (y demás `_inst`) contra el catálogo SIGMA (R5).
2. Tabla de severidad concreta para ordenar el índice de triaje.
3. Umbrales AF iniciales por variable (se afinan con datos reales; no bloquean el diseño).
4. Confirmar que `dash-ag-grid` se instala limpio en `miambiente`.
5. Confirmar cómo se rinde la mini-tendencia en `dash-ag-grid` community (cell renderer SVG propio;
   la sparkline nativa es Enterprise).
6. Medir el coste de `ruptures` (AF-BIAS) en la carga del Panorama antes de decidir cacheo/perezoso.

---

## 11. Fuera de alcance → Fase 2 (registrado, no se diseña aquí)

- Integración con la BD de incidentes: listar alertas abiertas por estación, saltar de la alerta a la
  variable+ventana, marcar el AF-\* confirmado sobre el incidente.
- Contraste con estaciones vecinas (AF-BIAS).
- Cruce de escalón (AF-BIAS) con la fecha de la visita de mantenimiento (ítem 5 del catálogo).
- Reorganización física de `DATA/datos_meteo/` (track de infraestructura).
