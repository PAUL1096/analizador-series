# Referencias de QA/QC de la comunidad meteorológica internacional

**Propósito:** informar el diseño del "analizador de series" de SENAMHI que valida y clasifica afectaciones (AF-*) en series de estaciones automáticas.
**Prioridad:** identificar qué REUSAR (librerías/algoritmos con umbrales citables) antes de reinventar.
**Fecha:** julio 2026. **Etiquetas:** [V]=verificado (visité la fuente), [I]=inferido/deducido, [NV]=no verificado.

Taxonomía AF-*: AF-MISS (ausencia total) · AF-GAP (huecos intermitentes) · AF-OUT (fuera de rango/spike) · AF-NOIS (ruido/varianza anómala) · AF-BIAS (sesgo/deriva/escalón/change-point) · AF-CST (constante/flatline/persistencia; incl. veleta trabada) · AF-REP (representatividad/ciclo diurno roto) · AF-RIS (riesgo infra, sin firma en serie — fuera de alcance).

---

## A. Resumen ejecutivo + recomendaciones

### Veredicto build-vs-adopt por AF-*
| AF-* | Recomendación | Herramienta/algoritmo a reusar |
|---|---|---|
| AF-MISS | **Adoptar (trivial)** | Conteo de esperados vs recibidos; ya lo calcula el Analizador. Todos los organismos lo tratan como test de integridad. |
| AF-GAP | **Adoptar lógica de "suficiencia"** | Umbral de completitud por ventana (KMA 90% = 54/60 min·h; CRC-SAS mínimos de conteo). No requiere librería. |
| AF-OUT | **ADOPTAR librería** | `ioos_qc` (gross_range + spike) y/o MetObs-toolkit (gross value + step). Umbrales de rango de Synoptic Data / TITAN / CRC-SAS. |
| AF-NOIS | **ADOPTAR + calibrar** | `ioos_qc.attenuated_signal_test` (varianza baja por ventana, std o rango). Complementar con rolling-std/z-score propio (ya en tu roadmap). |
| AF-BIAS | **ADOPTAR `ruptures`** (change-point) | `ruptures` (Pelt/Binseg/KernelCPD). Para homogeneización batch: `climatol`/`pyHomogeneity`. Ningún servicio operativo usa change-point formal → vas por delante. |
| AF-CST | **ADOPTAR librería** | `ioos_qc.flat_line_test` o MetObs-toolkit (persistence + repetitions). Umbrales KMA (180 min temp / 240 min viento), CRC-SAS (≥3 días idénticos incl. dirección viento → veleta trabada). |
| AF-REP | **Construir (poco soportado)** | Nadie tiene test nombrado "ciclo diurno roto". Proxy: apartamiento del ciclo estacional/diurno + consistencia interna. Es el AF-* más huérfano en la literatura operativa. |
| AF-RIS | Fuera de alcance de series | — |

### Qué adoptar YA (mantenido en 2026, Python, licencia permisiva)
1. **`ioos_qc`** (IOOS/QARTOD, Apache-2.0, Python≥3.11) — batería de tests genéricos de serie temporal con diseño de dos niveles SUSPECT/FAIL: `gross_range_test`, `spike_test`, `rate_of_change_test`, `flat_line_test`, `attenuated_signal_test`, `climatology_test`. Es lo más directamente reusable: son tests variable-agnósticos, no oceánicos pese al origen IOOS. Cubre AF-OUT, AF-CST, AF-NOIS, y da la arquitectura de flags. [V]
2. **`MetObs-toolkit`** (Univ. Gante, MIT, Python, JOSS 2024) — pensado para redes de observación de superficie no-tradicionales (exactamente tu caso): gross value, persistence, repetitions, step, window variation, buddy (+integración titanlib). Activamente mantenido (v1.1.1 jun-2026). Es el candidato más "a medida" de un analizador de series meteo. [V]
3. **`ruptures`** (BSD-2, Python 3.10-3.14, v1.1.10 sep-2025) — detección de change-points offline (Pelt, Binseg, Dynp, Window, BottomUp, KernelCPD). Es tu motor para AF-BIAS (escalón/deriva) que ningún servicio operativo tiene. [V]

### Qué solo MIRAR (metodología/umbrales, no adoptar el código)
- **Synoptic Data / MesoWest QC** — no es open-source pero su documentación pública lista tests y **umbrales numéricos por variable** (los mejores tabulados que encontré). Robar la tabla de rangos y tasas de cambio. [V]
- **TITAN / titanlib** (MET Norway, LGPL-3) — QC espacial (SCT, buddy, isolation). Releases estancados desde nov-2022; el paper ASR 2020 tiene umbrales operativos citables. Útil solo si tu red tiene densidad suficiente para chequeos espaciales (dudoso en los Andes). Mirar metodología. [V]
- **climatol** (R, GPL-3, v4.5-0 may-2026, activo) / **HOMER** / **ACMANT** / **RHtests** — homogeneización de series (AF-BIAS) para lotes mensuales/diarios, no operación en tiempo real. Mirar para reprocesos históricos. [V]
- **Durre et al. 2010 (GHCN-Daily)** — el paper canónico de QC automatizado con ~19 tests y umbrales; base común citada por todos los servicios latinoamericanos. (Sección C/D, Norteamérica.)

### Riesgo / advertencia
- Casi todos los umbrales publicados son para escala **diaria** (GHCN, CRC-SAS, ECA&D) o para variables/condiciones distintas a la costa/sierra peruana. **Deben recalibrarse** con datos SENAMHI antes de fijarlos. Los umbrales sub-diarios más aplicables son los de **Synoptic (rate-of-change por minutos)** y **KMA (step por minuto, persistencia en minutos)**.
- El origen oceánico de `ioos_qc` no impide su uso (tests genéricos), pero la nomenclatura y algunos defaults (attenuated signal) están pensados para oleaje/mareas — recalibrar.

---

## B. Tabla de proyectos open-source

| Proyecto | Organismo | Lenguaje | Licencia | Repo URL | AF-* que cubre | Veredicto de reuso |
|---|---|---|---|---|---|---|
| **ioos_qc** | IOOS (US) | Python ≥3.11 | Apache-2.0 | github.com/ioos/ioos_qc | AF-OUT, AF-CST, AF-NOIS, (AF-OUT climático) | **ADOPTAR.** Tests genéricos SUSPECT/FAIL. v2.3.0 (dic-2024). [V] |
| **MetObs-toolkit** | Univ. Gante (BE) | Python | MIT | github.com/vergauwenthomas/MetObs_toolkit | AF-OUT, AF-CST, AF-NOIS, AF-GAP | **ADOPTAR.** Diseñado para redes de superficie. v1.1.1 (jun-2026, activo). [V] |
| **ruptures** | ENS Paris-Saclay/CNRS | Python 3.10-3.14 | BSD-2-Clause | github.com/deepcharles/ruptures | AF-BIAS | **ADOPTAR.** Change-point offline. v1.1.10 (sep-2025, activo). [V] |
| **pyHomogeneity** | mmhs013 (indep.) | Python | MIT | github.com/mmhs013/pyHomogeneity | AF-BIAS | Adoptar puntual. Pettitt/SNHT/Buishand. Pura Python, estable pero baja mantención. [V] |
| **titanlib** | MET Norway | C++/Python/R | LGPL-3.0 | github.com/metno/titanlib | AF-OUT (espacial), AF-REP | Mirar/usar si hay densidad. SCT/buddy/isolation. v0.3.3 (nov-2022, releases estancados). [V] |
| **TITAN** | MET Norway | R | GPL (repo) [I] | github.com/metno/TITAN | AF-OUT (espacial) | Mirar metodología. Paper ASR 2020 con umbrales operativos. [V] |
| **climatol** | J.A. Guijarro (AEMET) | R | GPL-3 | cran.r-project.org/package=climatol | AF-BIAS, AF-MISS (infill) | Mirar (batch histórico). Homogeneización+relleno. v4.5-0 (may-2026, activo). [V] |
| **RHtests** | ECCC (Canadá) | R | (ver repo) [NV] | github.com/ECCC-CDAS/RHtests | AF-BIAS | Mirar. Change-point PMF/PMT en series con AR(1). [V] |
| **HOMER** | red europea (COST) | R | (paper) [NV] | (paper ResearchGate) | AF-BIAS | Mirar (batch mensual/anual). [V] |
| **ACMANT** | P. Domonkos | (dist. libre) | free [I] | github.com/dpeterfree/ACMANT | AF-BIAS | Mirar. Homogeneización automática. [V] |
| **SynopticPy** | B. Blaylock (indep.) | Python | MIT | github.com/blaylockbk/SynopticPy | (acceso a datos+flags QC) | Solo si usas la API Synoptic. v2026.6.0 (jun-2026, activo). [V] |
| **MetPyQC** | silve92 (indep.) | Python | MIT | github.com/silve92/MetPyQC | (preliminar) | No adoptar aún. "Preliminary", 5 estrellas. [V] |
| **MetPy** | NSF Unidata (US) | Python | BSD-3 [I] | github.com/Unidata/MetPy | — (NO tiene QC) | No sirve para QC; es cálculo/visualización. [V] |
| **RClimDex** | ETCCDI | R | (ver ETCCDI) [NV] | github (ETCCDI) | — (índices, no QC) | Fuera de alcance (índices climáticos). [V] |
| **PWSQC** | KNMI (de Vos 2019) | R | CC-BY-SA 4.0 | github.com/LottedeVos/PWSQC | AF-CST (FZ), AF-OUT (HI), AF-REP/espacial (SO) | Mirar/adaptar. QC de lluvia PWS; **umbrales por defecto legibles** en Filtersettings.txt. [V] |
| **QCwind** | KNMI (Chen 2021) | R | LICENSE presente (tipo [NV]) | github.com/jieyu97/QCwind | AF-OUT (range/step), AF-CST (persistence) | Mirar. QC de viento PWS: isolation/range/step/persistence + bias. [V] |
| **CrowdQCplus** | Fenner/Napoly (DE) | R | GPL-3 | github.com/dafenner/CrowdQCplus | AF-OUT, AF-REP (correlación multitud) | Mirar. Base de la QC de temperatura crowdsourced de KNMI. [V] |

> Nota licencias marcadas [NV]: RHtests, HOMER, RClimDex — no confirmé el archivo LICENSE explícito; verificar en el repo antes de reusar código.

---

## C. Metodología por organismo

### KMA (Corea) — RQMOD + esquema S-DoT · [V], vigente
Sistema operativo **RQMOD** = physical limit + climate range + step + persistence + internal consistency + median filter. (Fuente: Sensors/MDPI PMC10037411.)
- **Physical limit:** Temp −40 a 80 °C · HR 0-100% · Viento 0-60 m/s · Dirección 0-360°.
- **Climate range:** media ± n·σ mensual, **n = 3 a 9** (outlier climático).
- **Persistence:** sin variación **180 min (temp)** / **240 min (viento)** → falla.
- **Step:** **3 °C/min (temp)**, **10 %/min (HR)**, **10 m/s/min (viento)**.
- **Spatial:** test de mediana Madsen-Allerup, |T|>2.0; lapse rate 9.8 °C/km.
- **Suficiencia:** ≥54/60 registros 1-min por hora (90%). Relleno solo huecos <30 min.
- **Flags:** 0 normal / 1 dudoso o rellenado / 2 erróneo.

### CRC-SAS / SISSA (regional Sudamérica: Argentina, Brasil, Chile…) — QC en R · [V], 2023, vigente
Referente regional que engloba 1.083 estaciones (629 automáticas) de SMN, INMET, etc. Seis familias:
- **Rango fijo:** Temp −39 a 49 °C · Precip 0-300 mm · HR 0-100% · Presión estación 530-1060 hPa · Viento máx 0-62 m/s · Viento medio 0-26 m/s · Heliofanía 0-18 h.
- **Rango variable:** apartamientos vs ciclo estacional; múltiplos del IQR en ventanas 3-5 días; cuantiles gamma para precip.
- **Continuidad temporal:** CT01 persistencia (**≥3 días idénticos** → sospechoso, todas las variables incl. dirección viento) · CT02 persistencia de días secos (percentil 0.995/0.999) · CT03 saltos entre días (percentil 0.95/0.99/0.999) · control de picos con M-estimador y **MAD, umbral mín. 4.0** (nota explícita: las automáticas tienen picos breves frecuentes).
- **Consistencia entre variables:** tmin ≤ tmed ≤ tmax; amplitud térmica [0.01-30 °C].
- **Consistencia espacial:** regresión ponderada (concordancia >0.8), residuo >8 °C, corroboración de anomalías con umbral 2 °C.
- **Diseño clave:** dos niveles — *controles principales* (falla → **inválido**) vs *complementarios* (falla → **sospechoso**). Y reconoce explícitamente que en automáticas "no hay verificación manual posible": el motor marca, el analista reclasifica. (Respaldo directo a tu enfoque.)

### IDEAM (Colombia) — Manual M-GDI-M-M005 (2021) + Guía M-GCI-M-G002 v3 (2019) · [V], vigente
- Reglas operativas: ΔT >3 °C hora-a-hora = error (step); precip 10-min ≥30 mm = erróneo; "0.1 mm seguidos varios minutos" = sensor fallando (flatline); "iguales varias horas, verificar con otras variables" (constante).
- Límites de validación: Temp aire/máx/mín **−15 a 50 °C**; HR 0-100%; **Precip 24 h 0-350 mm** (0-250 Andina/Caribe/Orinoquia/Amazonía; 0-350 Pacífica); **Precip 1 h 0-60 mm**; consistencia diurna T13 ≥ T19 ≥ T07.
- **Estados de dato en DHIME:** preliminar (auto tras validación) → en revisión → definitivo.

### SMN (Argentina) — parcialmente [V]; vacío honesto
- Verificado: Nota Técnica SMN 2021-98 (QC de precipitación en tiempo real por comparación con satélite = consistencia espacial para lluvia); sistema OBSMET centraliza y hace QC en tiempo real.
- No verificado: batería general de tests con umbrales publicados. En la práctica el QC de las automáticas argentinas se hace vía CRC-SAS.

### INMET (Brasil) — infraestructura [V]; algoritmo QC no publicado
- Nota Técnica 001/2011: red EMA (Vaisala MAWS301), muestreo (promedios 1-min de 12 muestras a 5 s; viento medias 10-min; precip conteo de pulsos), **CCIM 24/7** monitorea funcionamiento de cada sensor/batería/panel → reporte de falla (útil para AF-MISS a nivel de red). Menciona "controle de qualidade" + ISO 9001 pero **no enumera tests ni umbrales**. INMET aporta 475 automáticas al QC de CRC-SAS (ahí sí hay umbrales).

### Synoptic Data / MesoWest (Univ. Utah, US) — [V], vigente (metodología pública, no open-source)
Batería con umbrales por variable (los mejores tabulados encontrados):
- **Range check** (`sl_range_check`): p.ej. temp −59.44 a 57.22 °C, viento 0-102.89 m/s (tabla de 70+ variables). Solo si pasa el rango se aplican los demás tests.
- **Rate of change** (`sl_rate_check`): presión 925 Pa/5min, 1000 Pa/15min, 1500 Pa/30-60min; temp 3 °C/1-3min hasta 20 °C/60min.
- **Persistence** (`sl_pers_check`): ventana 24 h; cambio mínimo requerido temp 0.1 °C, viento 0.25 m/s (48-72 h para radiación/suelo).
- **Spatial value check** (`sl_spatial_value_check`): vecinos ≤30 km, ≤200 m elevación, ±1.5..+0.5 h; diferencia temp 10 °C, ráfaga 40 m/s.
- **Percentile outlier**: alto si >99.5-pctil +10 °C; bajo si <0.5-pctil −15 °C (temp, requiere ≥3 años de historia).
- **MesoWest** aporta: regresión lineal multivariada (T/humedad/presión vs vecinas), persistencia de viento 24 h, y rechazo UU2DVAR (análisis variacional de superficie).

### TITAN / titanlib (MET Norway) — [V]
QC con énfasis espacial (simultáneo para todas las obs del mismo instante):
- **Plausibilidad (rango):** temp −50 a 40 °C, precip 0-100 mm.
- **Buddy check:** temp flag si desvío >2σ del promedio de caja (3 km, ≥4 vecinos); precip >5σ (solo in-situ) o >7σ (con radar).
- **SCT (spatial consistency test):** umbral por categoría de estación (Cat I OMM: >12× varianza de error; Cat II/III: >4× en temp positiva, >8× en negativa); subdominio ~100 km, ≥50 obs; escala vertical 200 m.
- **Isolation:** temp flag si <5 vecinos en 15 km y 200 m; precip si <3 vecinos en 25 km.
- **DEM/elevación:** desvío >500 m del modelo GMTED2010 → no usa su propia elevación.
- **Precip-temp cross-check:** pluviómetro no calefaccionado descartado si T<2 °C.
- Advertencia del propio paper: "no existen umbrales SCT universalmente válidos; dependen de la aplicación."

### Base normativa común (citada por todos)
Durre et al. (2010), Estévez et al. (2011/2015), Meek & Hatfield (1994), Feng et al. (2004); guías OMM WMO-No.1238 (*Guidelines on QC Procedures for Data from AWS*) y WMO-No.8 (CIMO Guide).

### OMM / WMO — normativa de referencia para AWS · [V]

**Aclaración de numeración (corrección).** El referente normativo directo de QC para estaciones automáticas es la guía WMO/CBS ET-AWS *"Guidelines on Quality Control Procedures for Data from Automatic Weather Stations"* (I. Zahumenský; 3ª sesión del Expert Team on Requirements for Data from AWS, Ginebra, 28 jun–2 jul 2004). **Este documento NO es "WMO-No.1238".** WMO-No.1238 es en realidad el *"Manual on the High-quality Global Data Management Framework for Climate"* (HQ-GDMFC, adoptado por el Congreso OMM Cg-18, 2019) — un marco de gestión/custodia de datos climáticos, no una batería de tests de QC. La atribución previa en este doc (§C "Base normativa común" y §E) conflaba dos documentos distintos; el contenido de tests que sigue es el de la guía ET-AWS 2004, que sí es la fuente de los umbrales sub-diarios. [V]

**Niveles de QC (guía ET-AWS 2004).** Dos niveles: **B-QC (Basic QC)** en el sitio de la AWS, en tiempo real, sobre muestras crudas y valores instantáneos de 1-min; y **E-QC (Extended QC)** en el centro de proceso (DPC) sobre datos Level II, repitiendo y ampliando los chequeos. Distingue QC automático vs manual; alcance = una sola AWS (QC espacial fuera de alcance). Respaldo normativo directo a tu arquitectura "motor marca → analista reclasifica".
- **Límites físicos/plausibles** (B-QC): Temp aire −80..+60 °C · Punto de rocío −80..+35 °C · HR 0-100% · Presión 500-1100 hPa · Viento 0-75 m/s · Radiación solar 0-1600 W/m² · Intensidad precip 0-40 mm/min. [V]
- **Step / consistencia temporal** (variación MÁX. entre valores 1-min sucesivos): Temp aire 3 °C · Punto de rocío 2 °C · Temp suelo 5 cm 1 °C / 100 cm 0.1 °C · HR 10% · Presión 0.5 hPa · Viento (media 2-min) 20 m/s. [V]
- **Persistencia** (variación MÍNIMA requerida en el período): Temp aire 0.1 °C/60 min · Temp suelo 5 cm 0.1 °C/120 min · 100 cm 0.1 °C/240 min · HR 1%/60 min · Viento 0.5 m/s/60 min. [V]
- **Consistencia interna:** punto de rocío ≤ temp · viento=0 ⇒ dirección=0 · racha ≥ viento medio · nubosidad=0 incompatible con precip>0 · radiación>500 W/m² ⇒ heliofanía>0. [V]
- **Flags (5 categorías):** *good* (pasa B-QC) / *inconsistent* (falla consistencia interna) / *doubtful/suspect* (falla consistencia temporal) / *erroneous/wrong* (falla límite plausible) / *missing* (muestras insuficientes: <66% general, <75% viento). [V]
- Advertencia: umbrales extraídos del documento vía fetch (resumen automático), son valores por defecto genéricos OMM — reverificar contra el PDF y recalibrar a costa/sierra peruana antes de fijarlos en norma.

**WMO-No.8 (CIMO Guide).** El *Guide to Instruments and Methods of Observation* trata el QC de datos de AWS con el mismo esquema B-QC/E-QC y la misma familia de tests (integridad, límites, consistencia temporal/interna); es la fuente OMM "paraguas", mientras que los umbrales operativos concretos viven en la guía ET-AWS 2004. [I]

**Mapa a AF-*:** límites físicos → AF-OUT · step → AF-OUT (spike/salto) · persistencia (variación mínima) → AF-CST + AF-NOIS · consistencia interna (viento=0⇒dir=0, racha≥media) → AF-CST (veleta) / AF-OUT · missing por muestras insuficientes → AF-MISS / AF-GAP.

### NOAA MADIS (US) — QC multinivel para redes mesoscala · [V], vigente
QC del Meteorological Assimilation Data Ingest System. Chequeos **estáticos** (una estación, un instante: validez, consistencia interna, consistencia vertical) y **dinámicos** (usan el entorno: consistencia de posición, temporal y espacial). Nivel 1 = menos sofisticado, nivel 3 = más. Base: NWS TSP 88-21-R2 (1994).
- **Nivel 1 — validez (rango):** Temp aire −60..130 °F (≈−51..54 °C) · Punto de rocío −90..90 °F · Viento 0-250 kt · Presión nivel mar 846-1100 mb · Visibilidad 0-100 mi. [V]
- **Nivel 2 — consistencia temporal (rate-of-change):** Temp aire ±35 °F/h · Presión nivel mar ±15 mb/h. **Interna:** punto de rocío ≤ temperatura. **Espacial estadístico:** marca la obs que falló QC el 75% del tiempo en 7 días. [V]
- **Nivel 3 — consistencia espacial (buddy):** interpolación óptima (OI) contra vecinos; marca desvíos grandes salvo que el reanálisis excluyendo vecinos problemáticos concuerde. [V]
- **Flags (data descriptor):** Z=preliminar/sin QC · C=coarse (solo N1) · S=screened (N1-2 OK) · V=verified (N1-3 OK) · X=rechazado (falla N1) · Q=questioned (N1 OK, falla N2-3) · G/B=bueno/malo subjetivo. [V]
- **Mapa AF-*:** validez→AF-OUT · rate-of-change→AF-OUT (salto) · interna→consistencia/AF-CST · buddy/espacial→AF-OUT espacial + AF-REP.

### GHCN-Daily — Durre et al. (2010) · [V] — el paper canónico (19 tests)
QC totalmente automatizado, validado manualmente (false-positive ≤20% por test; 0.24% del dataset marcado). Cinco categorías en secuencia, cada test ignora valores ya marcados: **integridad básica → outliers → consistencia interna/temporal → consistencia espacial → megaconsistencia**. Umbrales citables (escala diaria):
- **Integridad:** *naught* (TMAX=TMIN=0 °C, o =−17.8 °C, ⇒ cero usado como código de faltante) · *duplicate* (año=año o mes=mes con ≥3 no-cero; TMAX=TMIN en ≥10 días/mes) · *world-record* (temp <−89.4 o >57.7 °C · PRCP >1828.8 mm · SNOW >1925 mm · SNWD >11460 mm) · *streak* (**≥20 valores idénticos consecutivos** en TMAX/TMIN o PRCP; ≥10 en SNOW; ≥90 en SNWD) · *frequent-value* (9/10 idénticos ≥pctil30 · 8/10 ≥pctil50 · 7/10 ≥pctil70 · 5/10 ≥pctil90, PRCP). [V]
- **Outliers:** *gap* (hueco en la distribución mensual **≥10 °C** temp · **≥300 mm** PRCP · ≥350 mm SNWD) · *climatological* (**|z|≥6.0**, media/σ biweight, ventana 15 días, mín 100 valores; TMAX/TMIN) · *percentil PRCP* (≥9× pctil95 si T media >0 °C; ≥5× pctil95 si ≤0 °C). [V]
- **Consistencia interna/temporal:** *spike/dip* (**≥25 °C** más cálido/frío que el día previo Y el siguiente) · *lagged range* (TMAX ≥ máx[TMIN(−1..+1)] **+40 °C**, y análogos con TOBS) · *snow-temp* (SNOW>0 con mín[TMIN(−1..+1)] ≥7 °C) · consistencia SNOW-SNWD. [V]
- **Consistencia espacial** (vecinos ≤75 km): *regression check* (residuo **≥8 °C** Y residuo normalizado **≥4.0**) · *corroboration* (la anomalía del target difiere **≥10 °C** de todas las anomalías de 3-7 vecinos, ventana ±1 día). [V]
- **Megaconsistencia:** TMIN > TMAX máx histórico del mes, o TMAX < TMIN mín histórico (mín 140 valores). [V]
- **Mapa AF-*:** naught/duplicate→AF-CST/AF-BIAS · world-record/gap/climatological/percentil→AF-OUT · spike/dip/lagged→AF-OUT (spike) · streak/frequent-value→AF-CST · regression/corroboration→AF-OUT espacial + AF-REP · megaconsistencia→AF-OUT.

### ECCC (Canadá) · [V] parcial
Homogeneización por change-point con **RHtests** (PMF/PMT sobre series con AR(1); ya en tabla B) → AF-BIAS. ECCC aplica además consistencia temporal + espacial (interstation, regresión) sobre datos diarios (línea Vincent et al.). No verifiqué umbrales ECCC específicos publicados → vacío honesto; el aporte citable es la metodología RHtests.

### EUMETNET / ECA&D / E-OBS (KNMI, Región VI OMM) — QC diario con umbrales citables · [V], vigente
ECA&D (KNMI) es RCC OMM Región VI; financiado por EUMETNET 2003-2008, KNMI desde 2009. QC automático con intervención manual posible; el flag manual (series no-blended) se propaga a la serie blended. **Flags: 0=válido · 1=sospechoso · 9=faltante.** Umbrales del ATBD (escala diaria):
- **Rango fijo:** TX/TN/TG −90..60 °C · RR (precip) 0..<300 mm · PP (presión) 900..<1080 hPa · HU (HR) 5..100% · FG (viento medio) 0..46 m/s · FX (racha) 0..76 m/s · DD (dirección) 0..360° · SD (nieve) <300 cm (≤400 m) / <800 cm (400-2000 m) / <1500 cm (≥2000 m) · CC (nubosidad) 0..8. [V]
- **Outlier climatológico:** valor fuera de la media diaria a largo plazo ± **5σ** (ventana 5 días centrada; requiere ≥10 muestras/día y ≥25 días de registro). [V]
- **Repetición (persistencia):** RR ≥10 días idénticos si >1.0 mm (o ≥5 días si >5.0 mm) · PP/TX/TN/TG ≥5 días idénticos · FG ≥6 días si ≥2.0 m/s · FX ≥5 días si ≥4.0 m/s · **DD ≥6 días idénticos si >0.5° ⇒ veleta trabada**. [V]
- **Consistencia interna:** TX ≥ TG ≥ TN. [V]
- **Homogeneidad (batch):** SNHT, Buishand range, Pettitt, Von Neumann ratio → AF-BIAS. [V]
- **Mapa AF-*:** rango fijo + 5σ → AF-OUT · repetición N días → AF-CST (DD → veleta) · homogeneidad → AF-BIAS · TX≥TG≥TN → consistencia interna / AF-REP. Es la 2ª tabla de umbrales diarios citables (junto a CRC-SAS) y aporta la regla explícita de dirección de viento repetida.

### MeteoSwiss — SwissMetNet · [V], vigente (metodología; sin umbrales públicos)
~260 estaciones automáticas, datos 10-min. QC operacional en **dos niveles**: (1) tiempo real online = tests de plausibilidad → alarmas instantáneas; (2) diario = QC sobre datos crudos de los 3 meses previos. Familias de tests: estructura del registro, rango/límites, consistencia temporal e interna, persistencia y consistencia espacial. QC automático + manual; herramientas del data-warehouse fijan flags. Cubre AF-OUT, AF-CST (persistencia), AF-NOIS, AF-REP (espacial). No hallé umbrales numéricos públicos → nivel metodológico.

### DWD (Alemania) · [V], vigente (niveles de calidad; sin umbrales públicos)
QC en **cuatro pasos secuenciales QC1–QC4** (los tres primeros sobre datos de alta resolución temporal; el 4º = revisión climatológica final). Cada valor recibe un **Qualitätsniveau (QN)** que indica por qué procedimiento pasó (tras 1980, QN máx=10) más un flag de estado. Datos separados en `historical/` (QC completo, versionado) vs `recent/` (QC no cerrado). Original archivado tras corrección de valores puntuales. Batería: límite/rango, consistencia temporal e interna, chequeos espaciales. Ref: Kaspar et al. (2013). No hallé umbrales numéricos públicos → nivel metodológico/gobernanza.

### BoM (Australia) · [V], vigente (monitoreo operacional; sin umbrales públicos)
~695 AWS, muestreo 1-min (publicado como obs 30-min). Software de monitoreo de datos 1-min en tiempo real + acceso remoto para vigilar la operación; los QC Operators verifican los cambios de la mesa de comunicaciones; prácticas alineadas con OMM. El sistema "marca errores" pero BoM no publica la tabla de umbrales. Aporte para tu caso: modelo de **monitoreo de operatividad de red en tiempo real** (AF-MISS a nivel de red/telemetría). Ref: BoM AWS Review (2017).

### Copernicus C3S / CDS (ECMWF/UE) · [V], vigente (marco EQC, no batería nueva)
La **EQC (Evaluation and Quality Control) function** (C3S_51) aplica chequeos de QC + tests de homogeneidad a observaciones y metadatos siguiendo estándares OMM, apoya el rescate de datos y armoniza el acceso a grandes archivos; sirve colecciones in-situ ya QC-adas (tierra desde 1755; E-OBS para Europa). Aporte: nivel de **gobernanza / aseguramiento** (homogeneización = AF-BIAS; completitud = AF-MISS; trazabilidad de metadatos) más que tests con umbrales nuevos. Ref: climate.copernicus.eu EQC + factsheet QA CDS.

### KNMI — nota de convergencia · [V]
KNMI aloja ECA&D (arriba) y desarrolla PWSQC/QCwind/CrowdQCplus (tabla B). No hay validación de red adicional nueva que agregar más allá de lo listado; el punto a retener es que la misma institución cubre tanto el QC diario climatológico (ECA&D) como el QC sub-diario de redes crowdsourced.

---

## D. Matriz AF-* → referentes y umbrales concretos

### AF-MISS (ausencia total)
- Test de integridad/valor faltante universal (KMA QC01; CRC-SAS; monitoreo CCIM de INMET a nivel de red). [V]
- `ioos_qc`: no hay test específico; se maneja como flag MISSING. [V]
- **WMO ET-AWS:** flag *missing* cuando las muestras válidas caen por debajo de <66% (general) / <75% (viento) del período de agregación [V]. **ECA&D:** flag=9 [V]. **MADIS/BoM:** monitoreo de red en tiempo real (software 1-min) detecta pérdida de transmisión por estación → AF-MISS a nivel de telemetría [V].

### AF-GAP (huecos intermitentes)
- **Suficiencia por ventana:** KMA ≥54/60 registros por hora (90%) [V]; CRC-SAS mínimos de conteo por día [V]; IDEAM ≥16 días/mes (temp), ≥20 días/mes (precip) [V]; **WMO ET-AWS** umbral de muestras válidas <66%/<75% viento → *missing* [V]; **ECA&D** exige ≥10 muestras/día y ≥25 días de registro para calcular estadísticos (si no, no aplica el test) [V].
- Sin librería dedicada; lógica de completitud propia.

### AF-OUT (fuera de rango / spike) — **cobertura más fuerte**
- **Rango físico:** Synoptic (temp −59.44..57.22 °C, viento 0..102.89) [V]; CRC-SAS (temp −39..49, precip 0..300) [V]; TITAN (temp −50..40, precip 0..100) [V]; KMA (temp −40..80) [V]; IDEAM (temp −15..50, precip1h 0..60) [V].
- **Spike:** `ioos_qc.spike_test` (suspect/fail_threshold, método average o differential) [V]; CRC-SAS control de picos MAD umbral ≥4.0 [V].
- **Rate of change / step:** Synoptic (temp 3 °C/1-3min..20 °C/60min; presión 925-1500 Pa) [V]; KMA (3 °C/min) [V]; `ioos_qc.rate_of_change_test` (threshold en unidades/seg) [V]; MetObs-toolkit step (max_increase_per_second) [V].
- **Climatológico:** `ioos_qc.climatology_test` (tspan/vspan/fspan por periodo) [V]; Synoptic percentil >99.5+10 °C [V]; KMA media±n·σ (n=3-9) [V]; **GHCN-Daily |z|≥6.0** (biweight, ventana 15 días) [V]; **ECA&D media diaria ±5σ** (ventana 5 días) [V]; GHCN gap ≥10 °C / percentil PRCP ≥9× pctil95 [V].
- **Rango físico (nuevos):** WMO ET-AWS (temp −80..60, punto rocío −80..35, presión 500-1100, viento 0-75, radiación 0-1600 W/m², precip 0-40 mm/min) [V]; MADIS (temp −60..130 °F, viento 0-250 kt, SLP 846-1100 mb) [V]; ECA&D (temp −90..60, RR 0..300, PP 900..1080, FG 0..46, FX 0..76) [V].
- **Espacial:** GHCN regression (residuo ≥8 °C Y normalizado ≥4.0) + corroboration (anomalía ≥10 °C de todos los vecinos) [V]; MADIS buddy por OI [V].
- **Rate-of-change / step (nuevos):** MADIS (temp ±35 °F/h; SLP ±15 mb/h) [V]; WMO ET-AWS step 1-min (temp 3 °C, HR 10%, presión 0.5 hPa, viento 20 m/s) [V].

### AF-NOIS (ruido / varianza anómala)
- **`ioos_qc.attenuated_signal_test`**: varianza baja por ventana (std o range; suspect/fail_threshold, test_period, min_obs) [V]. Único test nombrado directamente aplicable.
- KMA climate range media±n·σ [V]; CRC-SAS apartamientos IQR ventanas 3-5 días [V].
- **WMO ET-AWS persistencia** (variación mínima requerida: temp 0.1 °C/60 min, HR 1%/60 min, viento 0.5 m/s/60 min — varianza por debajo = sospechoso) [V]; **MeteoSwiss** test de persistencia operacional en su batería de 2 niveles [V].
- Complementar con rolling-std / z-score propio (tu roadmap).

### AF-BIAS (sesgo / deriva / escalón / change-point)
- **`ruptures`** (Pelt/Binseg/Dynp/Window/BottomUp/KernelCPD; costos l1/l2/rbf/normal/ar) — detección formal de change-points [V]. Ningún servicio operativo lo usa → adelanto.
- **`pyHomogeneity`** (Pettitt, SNHT, Buishand Q/R/LR/U; alpha, sim) [V].
- **climatol / RHtests / HOMER / ACMANT** — homogeneización batch [V].
- **ECA&D / EUMETNET:** batería de homogeneidad SNHT + Buishand range + Pettitt + Von Neumann ratio (change-point diario/mensual) [V]. **Copernicus C3S (EQC):** homogeneización de series in-situ como función operacional del CDS [V].
- Proxy operativo en servicios: step/salto (KMA 3 °C/min; CRC-SAS CT03; IDEAM ΔT>3 °C/h) [V].

### AF-CST (constante / flatline / persistencia; veleta trabada) — bien soportado
- **`ioos_qc.flat_line_test`**: rango de ventana < tolerance durante suspect_threshold (seg) → SUSPECT; fail_threshold → FAIL [V].
- **MetObs-toolkit**: persistence (timewindow, min_records) + repetitions (max_N_repetitions) [V].
- KMA: 180 min temp / 240 min viento [V]. CRC-SAS CT01: ≥3 días idénticos, aplica a **dirección de viento → veleta trabada** [V]. Synoptic: 24 h, cambio mín temp 0.1 °C / viento 0.25 m/s [V]. IDEAM: "iguales varias horas" / "0.1 mm seguidos = sensor fallando" [V].
- **WMO ET-AWS persistencia** (temp <0.1 °C/60 min, HR <1%/60 min, viento <0.5 m/s/60 min) [V]. **GHCN-Daily:** streak ≥20 valores idénticos consecutivos (TMAX/TMIN/PRCP), ≥10 SNOW, ≥90 SNWD; frequent-value 9/10..5/10 según percentil [V]. **ECA&D:** repetición ≥5 días (T, PP) / ≥10 días RR>1mm / ≥6 días viento; **DD ≥6 días idénticos si >0.5° ⇒ veleta trabada** (regla explícita, complementa CT01 de CRC-SAS) [V].
- Veleta trabada = dirección constante con velocidad>0: cubierta por CT01 (CRC-SAS) y por flat_line sobre la dirección condicionado a velocidad>0 (lógica propia). [V]/[I]

### AF-REP (pérdida de representatividad / ciclo diurno roto) — **el más huérfano**
- Ningún test nombrado. Proxies: apartamiento del ciclo estacional/diurno (CRC-SAS rango variable) [V]; consistencia interna diurna T13≥T19≥T07 (IDEAM) [V]; climate range + internal consistency (KMA) [V]; SCT espacial (TITAN) para incoherencia con vecinas [V].
- **Nuevos proxies:** GHCN-Daily corroboración espacial (anomalía del target vs vecinos, ≥10 °C) [V]; ECA&D consistencia interna TX≥TG≥TN [V]; MADIS buddy/OI [V]. Ninguno es "ciclo diurno roto" nombrado; siguen siendo proxies.
- Construir a medida (comparación del ciclo diurno esperado vs observado).

---

## E. Fuentes

**Open-source / librerías (todas [V]):**
- ioos_qc: https://github.com/ioos/ioos_qc · https://ioos.github.io/ioos_qc/ · https://pypi.org/project/ioos-qc/
- ioos_qc módulo qartod (algoritmos/parámetros): https://ioos.github.io/ioos_qc/_modules/ioos_qc/qartod.html
- MetObs-toolkit: https://github.com/vergauwenthomas/MetObs_toolkit · https://metobs-toolkit.readthedocs.io/en/v0.4.0/examples/qc_example.html · JOSS 10.21105/joss.05916
- ruptures: https://github.com/deepcharles/ruptures · https://centre-borelli.github.io/ruptures-docs/
- pyHomogeneity: https://github.com/mmhs013/pyHomogeneity · https://pypi.org/project/pyhomogeneity/
- titanlib: https://github.com/metno/titanlib · https://pypi.org/project/titanlib/
- TITAN (paper ASR 2020, umbrales): https://asr.copernicus.org/articles/17/153/2020/ · repo: https://github.com/metno/TITAN
- climatol: https://cran.r-project.org/package=climatol · https://www.climatol.eu/
- RHtests: https://github.com/ECCC-CDAS/RHtests
- HOMER/ACMANT: https://github.com/dpeterfree/ACMANT · https://acmant.eu/
- SynopticPy: https://github.com/blaylockbk/SynopticPy · https://pypi.org/project/SynopticPy/
- MetPyQC: https://github.com/silve92/MetPyQC
- MetPy: https://github.com/Unidata/MetPy

**Metodología por organismo:**
- Synoptic Data QC (umbrales): https://docs.synopticdata.com/services/mesonet-data-qc
- KMA / S-DoT: https://pmc.ncbi.nlm.nih.gov/articles/PMC10037411/ · https://jkwra.or.kr/articles/xml/v2e1/
- CRC-SAS reporte QC 2023: https://sissa.crc-sas.org/wp-content/uploads/2023/11/Reporte_CRC-SASS_FINAL_calidad_19oct23.pdf
- IDEAM Manual QC M-GDI-M-M005: https://www.ideam.gov.co/sites/default/files/mapa-de-procesos/m-gdi-m-m005_manual_control_de_calidad_verificacion_v1.pdf
- IDEAM Guía M-GCI-M-G002 v3: https://www.ideam.gov.co/sites/default/files/mapa-de-procesos/m-gci-m-g002_guia_metodologica_de_la_operacion_estadistica_variables_meteorologicas.pdf
- INMET Nota Técnica 001/2011: https://www.cemtec.ms.gov.br/wp-content/uploads/2019/02/Nota_Tecnica-Rede_estacoes_INMET.pdf
- SMN NT 2021-98 / 2018-52: https://repositorio.smn.gob.ar/handle/20.500.12160/1607 · https://repositorio.smn.gob.ar/bitstream/handle/20.500.12160/891/Nota_tecnica_SMN_2018-52.pdf.pdf

**OMM / WMO (todas [V] salvo nota):**
- Guía ET-AWS QC (Zahumenský 2004), texto y umbrales: https://silo.tips/download/guidelines-on-quality-control-procedures-for-data-from-automatic-weather-station · https://www.researchgate.net/publication/228826920
- WMO-No.1238 = *Manual on the High-quality Global Data Management Framework for Climate* (NO es la guía de QC de AWS): https://library.wmo.int/records/item/56975 · https://community.wmo.int/en/high-quality-global-data-management-framework-climate-hq-gdmfc
- WMO-No.8 CIMO Guide: https://community.wmo.int/site/knowledge-hub/programmes-and-initiatives/instruments-and-methods-of-observation-programme-imop/guide-instruments-and-methods-of-observation-wmo-no-8

**Norteamérica:**
- NOAA MADIS QC (niveles + flags): https://madis.ncep.noaa.gov/madis_qc.shtml · https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml
- GHCN-Daily, Durre et al. (2010), *J. Appl. Meteor. Climatol.* 49(8): https://www.ncei.noaa.gov/pub/data/ghcn/daily/papers/durre-menne-etal2010.pdf · https://journals.ametsoc.org/view/journals/apme/49/8/2010jamc2375.1.xml
- ECCC RHtests: https://github.com/ECCC-CDAS/RHtests (ya en tabla B)

**Europa / Oceanía:**
- ECA&D ATBD (KNMI, umbrales de QC diario + homogeneidad): https://knmi-ecad-assets-prd.s3.amazonaws.com/documents/atbd.pdf · https://www.ecad.eu
- MeteoSwiss SwissMetNet QC (data-warehouse; EMS 2009): https://www.researchgate.net/publication/253779475 · https://www.meteoswiss.admin.ch/weather/measurement-systems/land-based-stations/automatic-measurement-network.html
- DWD QC / Qualitätsniveau: https://www.dwd.de/EN/climate_environment/climatemonitoring/climatedatamanagement/qualityassurance/quali.html · https://www.dwd.de/DE/leistungen/klimadatendeutschland/qualitaetsniveau.html
- BoM AWS Review (2017): https://www.bom.gov.au/sites/default/files/2025-06/review-of-bureau-of-meteorology-automatic-weather-stations-2017.pdf
- Copernicus C3S EQC / QA-CDS: https://climate.copernicus.eu/evaluation-and-quality-control-observations · https://climate.copernicus.eu/c3s51-evaluation-and-quality-control-function-climate-data-store · https://climate.copernicus.eu/sites/default/files/2020-04/C3S_Factsheet_Quality_Assurance_20190613.pdf
