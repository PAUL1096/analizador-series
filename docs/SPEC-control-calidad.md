# Spec: control-calidad — Pipeline de Control de Calidad local del Analizador

Module id: `control-calidad` (capability map: `control-calidad` → `emplazamiento`)

## Objetivo

El Analizador de Series hoy muestra la serie cruda tal como llega de SIGMA. La única
señal de calidad disponible es `flag_n_*` (de SIGMA, valores `C`/`M`/`SD`), usada hoy
solo parcialmente (día efectivo, con `["C"]` fijo) y no expuesta como control en el
resto de pestañas.

Se necesita una capa de control de calidad **propia de SGR, local a esta herramienta**,
que aplique reglas de validación por lectura (límites físicos, salto máximo entre
lecturas consecutivas, persistencia, coherencia) y deje el resultado disponible como
un flag adicional que el usuario pueda activar/desactivar en cualquiera de las 4
pestañas existentes (Estadística, Panorama, Comparar, Vista Cruda — incluido el panel
de día efectivo).

**Quién lo usa:** el propio equipo de SGR, al analizar series para detectar
incidentes — no es un producto institucional ni se comparte con otras unidades.

**Qué es éxito:** al elegir cualquier estación (automática o convencional) en
cualquier pestaña, el usuario puede alternar entre ver la serie cruda y ver la serie
con el CC propio aplicado (puntos `MALO` fuera, o resaltados; `DUDOSO` visible pero
distinguible), sin tener que esperar un recálculo notable si los datos de esa estación
no cambiaron desde la última vez.

## Alcance — qué SÍ incluye

- Reglas de límites duros, prueba de paso y prueba de persistencia para estaciones
  **automáticas**, y de coherencia interna + variación día-a-día por región/altitud
  para estaciones **convencionales** (fuente exacta de cada regla: ver tabla más
  abajo).
- Un flag nuevo por variable (`cc_n_<variable>`, valores `BUENO`/`DUDOSO`/`MALO`),
  independiente y adicional al `flag_n_*` de SIGMA — ambos filtros coexisten y son
  combinables en la UI.
- Cálculo sobre el histórico COMPLETO de la estación (no el periodo que el usuario
  esté mirando), cacheado en disco por estación, invalidado automáticamente si
  cambian los CSV de esa estación o si cambia la lógica del propio CC (mismo
  mecanismo ya implementado en `core/dias_efectivos.py`: `firma_estacion()` +
  hash de versión de lógica).
- Refresco mínimo de `data_ref/estaciones.db` con **altitud** y **región natural**
  (Costa/Sierra/Selva) por estación — dato que hoy falta ahí y que las reglas de
  convencionales necesitan. Fuente: `georeferencias_2026-09-29.xlsx` (o el export más
  reciente equivalente que el usuario provea).
- Toggle compartido en la fila de selectores comunes (no uno por pestaña), aplicable
  a las 4 pestañas existentes.

## Alcance — qué NO incluye (explícitamente fuera)

- **Nunca sale de la máquina que corre el Analizador.** No se sincroniza a
  `sgo.db`/`sgo_v3.db`, no se comparte con SGD, no se conecta al motor de alertas
  institucional (`Dashboard-para-monitoreo-de-la-operatividad`, otro repo). Esta es
  una restricción explícita y no negociable del usuario — no un detalle de
  implementación.
- No implementa el CC oficial de SGD (MT-DRD-002/003) completo ni pretende
  sustituirlo — usa esos manuales como REFERENCIA numérica para una capa de análisis
  propia, distinta y separada.
- No incluye la comparación por emplazamiento compartido automática↔convencional (module `emplazamiento`,
  spec aparte, depende de este).
- No incluye reglas para variables sin equivalente físico documentado (nubosidad,
  visibilidad, heliofanía, evaporación, calidad de agua) — quedan sin CC propio por
  ahora, se muestran solo crudas.
- No modifica ni reescribe los CSV crudos descargados de SIGMA — son la fuente de
  verdad tal cual llega.

## Reglas — fuente exacta y valores (ya verificados contra los manuales oficiales SENAMHI)

### Automáticas

**Límites duros** (el más estricto entre MT-DRD-001 "Instalación y Operación de
Estaciones", SGR, Tablas 02/03/05/06/07, y MT-DRD-002 "Control de Calidad — datos
automáticas", SGD, §6.3.1.1) — se usa MT-DRD-001 (más estricto, es el propio de SGR)
como límite duro; si una variable no está en MT-DRD-001, se usa el de MT-DRD-002:

| Variable | Límite duro (MT-DRD-001, SGR) |
|---|---|
| Temperatura del aire | -40 a 50 °C |
| Humedad relativa | 1 a 100 % |
| Precipitación (horaria) | 0.02 a 500 mm/h |
| Precipitación (acumulada) | 0 a 500 mm |
| Velocidad del viento | 0 a 50 m/s |
| Dirección del viento | 1 a 360° (MT-DRD-002, SGR no lo tabula) |
| Radiación solar | 0 a 1300 W/m² |
| Presión atmosférica (EMA) | 550 a 1100 hPa |
| Presión atmosférica (EAMA) | 550 a 1050 hPa |
| Nivel de agua | 0 a 35 m (MT-DRD-002, SGR no lo tabula igual) |

**Prueba de paso** (salto máximo entre lecturas consecutivas — MT-DRD-002 §6.3.2.1,
subreglas 31-40):

| Variable | Δ máx. 1h | Δ máx. 2h | Δ máx. 3h | Δ máx. 6h | Δ máx. 12h |
|---|---|---|---|---|---|
| Temperatura | 4°C | 7°C | 9°C | 15°C | 25°C |
| Presión atmosférica | 3 hPa | 6 hPa | 9 hPa | 18 hPa | 36 hPa |

| Variable | Condición |
|---|---|
| Humedad relativa | \|ΔHR\| ≤ 45% (subregla 33) |
| Velocidad del viento | \|ΔVV\| < 10.0 m/s (subregla 38) |
| Dirección del viento | min(\|ΔVD\|, 360-\|ΔVD\|) < 150° (subregla 39) |
| Radiación solar | 0 ≤ \|ΔRs\| ≤ 555 W/m² (subregla 40) |

Un dato que no cumple la prueba de paso → `DUDOSO` (no `MALO`; solo un límite duro
produce `MALO`).

**Prueba de persistencia** (MT-DRD-002 §6.3.2.2, subreglas 41-46): si una lectura
horaria tiene el mismo valor que las 3 horas previas consecutivas (4 lecturas
idénticas en total) → las 4 lecturas se marcan `DUDOSO`. Aplica a: temperatura,
humedad relativa, dirección del viento, velocidad del viento, presión atmosférica,
radiación solar. **No aplica** a precipitación ni nivel de agua (el manual las excluye
explícitamente).

### Convencionales

**Límites duros de temperatura** (MT-DRD-003 §6.3.2, subreglas 2.G-2.I): -30 a 45°C
como límite duro (`MALO` fuera de ese rango); dentro de ese rango pero en la banda
-30 a -28°C o 43 a 45°C → `DUDOSO` (valor extremo pero no descartado).

**Coherencia interna** (MT-DRD-003 §6.3.1/6.3.3, subreglas 1.A-3.C): máxima diaria >
mínima diaria; máxima diaria ≥ instantáneas de 07/13/19h; mínima diaria ≤
instantáneas de 07/13/19h — un dato que rompe estas comparaciones → `MALO`.

**Variación día a día** (MT-DRD-003 §6.3.2, subregla 2.N) — necesita región natural +
altitud de la estación (de `data_ref/estaciones.db`, ver Alcance):

| Región + altitud | Variación máx. entre días consecutivos |
|---|---|
| Costa, ≤600 msnm | ≤ 5.0 °C |
| Sierra o Selva, 600-3800 msnm | ≤ 10.0 °C |
| Sierra, >3800 msnm | ≤ 15.0 °C |

Fuera de esa variación → `DUDOSO`.

## Tech Stack

Python 3.12, pandas, pytest. Sin dependencias nuevas (haversine/reglas de umbral no
necesitan librerías adicionales a las ya instaladas en el env `analizador_series`).

## Commands

```
Test:  C:\Users\drd06\.conda\envs\analizador_series\python.exe -m pytest tests/ -v
Correr app: python analizador_series/app.py  (puerto configurable, no usar 8053/8099)
```

## Project Structure

```
analizador_series/core/control_calidad.py    → reglas puras (sin Dash), nuevo
analizador_series/config/control_calidad.yaml → umbrales con cita a manual+subregla, nuevo
data_ref/actualizar_geodatos.py               → refresco de altitud/región natural, nuevo
analizador_series/ui/layout.py                → agregar el toggle compartido de CC
analizador_series/ui/callbacks.py             → leer el toggle, aplicar el filtro
tests/core/test_control_calidad.py            → nuevo, mismo patrón que test_dias_efectivos.py
```

## Code Style

Mismo estilo que el resto de `core/`: funciones puras, type hints, docstring solo
cuando el WHY no es obvio (ver `dias_efectivos.py` como referencia — comentarios que
citan manual+subregla, no explican qué hace la línea). Nombres de función en español,
snake_case, mismo patrón que `evaluar_dias_efectivos`/`construir_tabla_*`.

```python
def evaluar_prueba_paso(serie: pd.Series, variable: str) -> pd.Series:
    """
    Salto máximo entre lecturas consecutivas (MT-DRD-002 §6.3.2.1, subreglas 31-40).
    Solo aplica a automáticas — convencionales usan evaluar_variacion_diaria().
    """
```

## Testing Strategy

pytest, `tests/core/test_control_calidad.py`, mismo patrón que
`tests/core/test_dias_efectivos.py`: una clase por función pública, casos límite
exactos de cada subregla citada (ej. exactamente 4.0°C de salto = pasa, 4.01°C =
`DUDOSO`). Más una clase `TestCacheControlCalidad` (calco de
`TestCacheDiasEfectivosEstacion`) que verifica reuso de caché, invalidación por
versión de lógica, y compatibilidad con caché pre-existente sin la llave nueva.

## Boundaries

- **Always:** correr `pytest tests/` completo antes de dar una tarea por terminada;
  citar manual+subregla en cada umbral de `control_calidad.yaml`; nunca escribir
  sobre los CSV crudos de `DATA/datos_meteo/`.
- **Ask first:** cambiar la ubicación del toggle en la UI si no es un control
  compartido; agregar cualquier dependencia nueva a `requirements.txt`.
- **Never:** escribir o sincronizar el resultado del CC hacia
  `Dashboard-para-monitoreo-de-la-operatividad`, `sgo.db`, `sgo_v3.db`, o cualquier
  sistema fuera de este repo; mezclar la columna `cc_n_*` con `flag_n_*` de SIGMA en
  el mismo campo (deben quedar separadas y ambas filtrables).

## Success Criteria

1. `core/control_calidad.py` tiene una función pura por regla (límites duros, paso,
   persistencia, coherencia interna, variación diaria) + una `evaluar_todas()` que
   combina todo por variable, con `MALO` > `DUDOSO` > `BUENO` en severidad.
2. Cada umbral numérico en `config/control_calidad.yaml` cita el manual y la
   subregla exacta de donde sale (mismo patrón que los comentarios ya existentes de
   R5 en `dias_efectivos.py`).
3. `resultado_control_calidad_estacion(codigo)` cachea en disco por estación, se
   invalida solo si cambian los CSV o la lógica (test que lo prueba, igual que
   `TestCacheDiasEfectivosEstacion`).
4. Las 4 pestañas (Estadística, Panorama, Comparar, Vista Cruda + día efectivo)
   respetan el toggle compartido de CC, combinable con el filtro de flags de SIGMA
   ya existente.
5. `data_ref/estaciones.db` tiene `altitud` y `region_natural` poblados para las
   estaciones convencionales usadas en las reglas de variación diaria.
6. 100% de los tests nuevos en verde + los tests existentes (87 al momento de
   escribir esto) siguen en verde.
7. Ninguna escritura de red ni a rutas fuera de `Analizador-Series/` en todo el
   módulo — verificable por inspección (no hay imports de `requests`/`sqlite3` hacia
   otra base que no sea `data_ref/estaciones.db`, no hay paths hacia
   `Dashboard-para-monitoreo-de-la-operatividad`).

## Open Questions

Ninguna bloqueante — las 7 asunciones surgidas al escribir este spec fueron
confirmadas o corregidas por el usuario antes de guardarlo (ver historial de la
sesión): flags `BUENO`/`DUDOSO`/`MALO`, cálculo sobre histórico completo con caché
igual al de día efectivo (no incremental por período de descarga).
