"""
Día efectivo: por cada día, ¿llegó suficiente dato sub-diario para que un
promedio/valor diario calculado a partir de él sea representativo?

Dos usos distintos, con distinto nivel de riesgo sobre la convención exacta
de "día" (pendiente confirmar la convención meteorológica institucional
exacta con un especialista):

- evaluar_dias_efectivos(): banda genérica para explorar cualquier variable
  cruda. Usa DÍA CALENDARIO (medianoche a medianoche) — una simplificación
  documentada, no la convención institucional exacta.
- evaluar_concordancia_diaria(): chequea si un valor diario NATIVO (Tmax,
  Tmin, precipitación diaria acumulada — ya reportado por SENAMHI) tiene
  suficiente respaldo horario detrás. No depende de qué es un "día": ancla
  la ventana de 24h en el timestamp REAL de esa lectura diaria, así que es
  válida sea cual sea la convención institucional de acumulación/etiquetado.
"""
from __future__ import annotations

import hashlib
import inspect
import pickle
from pathlib import Path

import pandas as pd

from analizador_series.config import DIR_CACHE_DIAS_EFECTIVOS
from analizador_series.core import control_calidad, data_loader, deteccion_afectaciones


UMBRAL_DIA_EFECTIVO = 0.75

_COLUMNAS_DIAS_EFECTIVOS = ["n_esperado", "n_recibido", "pct_recibido", "efectivo"]
_COLUMNAS_CONCORDANCIA = ["valor_diario", "n_esperado", "n_recibido", "pct_recibido", "respaldado"]


def es_variable_diaria(cadencia: pd.Timedelta | None) -> bool:
    """
    True si la cadencia real de la variable ya es de 1 día o más (Tmax/Tmin/
    precipitación diaria acumulada). Para esas variables "% de lecturas del
    día" no tiene grados intermedios (1 esperada por día) — se excluyen por
    defecto de evaluar_dias_efectivos/construir_tabla_dias_efectivos.
    """
    return cadencia is not None and cadencia >= pd.Timedelta(days=1)


def evaluar_dias_efectivos(
    serie: pd.Series,
    cadencia: pd.Timedelta | None = None,
    umbral_pct: float = UMBRAL_DIA_EFECTIVO,
) -> pd.DataFrame:
    """
    Un día calendario por fila, en el rango [serie.index.min(), .max()]
    (anclado en el índice CRUDO, no en dropna() — a diferencia de
    _grilla_esperada, acá SÍ interesa capturar días con cero lecturas
    válidas dentro del rango pedido).
    """
    if serie.empty:
        return pd.DataFrame(columns=_COLUMNAS_DIAS_EFECTIVOS)

    cadencia = cadencia if cadencia is not None else deteccion_afectaciones.cadencia_inferida(serie)
    s_validos = pd.to_numeric(serie, errors="coerce").dropna()
    if cadencia is None or cadencia.total_seconds() <= 0 or len(s_validos) < 2:
        return pd.DataFrame(columns=_COLUMNAS_DIAS_EFECTIVOS)

    dias = pd.date_range(serie.index.min().normalize(), serie.index.max().normalize(), freq="D")
    n_esperado = pd.Timedelta(days=1) / cadencia

    conteo_por_dia = s_validos.groupby(s_validos.index.normalize()).size()
    n_recibido = conteo_por_dia.reindex(dias, fill_value=0)
    pct_recibido = n_recibido / n_esperado

    return pd.DataFrame({
        "n_esperado": n_esperado,
        "n_recibido": n_recibido,
        "pct_recibido": pct_recibido,
        "efectivo": pct_recibido >= umbral_pct,
    }, index=dias)


def construir_tabla_dias_efectivos(
    df_estacion: pd.DataFrame,
    variables: list[str],
    incluir_diarias: bool = False,
    umbral_pct: float = UMBRAL_DIA_EFECTIVO,
) -> dict[str, dict]:
    """
    df_estacion: una sola estación, indexada por datetime, una columna por
    variable (ej. df[df.codigo==estacion].set_index("datetime")).
    """
    resultado = {}
    for var in variables:
        if var not in df_estacion.columns:
            continue
        serie = df_estacion[var]
        cadencia = deteccion_afectaciones.cadencia_inferida(serie)
        es_diaria = es_variable_diaria(cadencia)
        resultado[var] = {
            "tabla": evaluar_dias_efectivos(serie, cadencia=cadencia, umbral_pct=umbral_pct),
            "cadencia": cadencia,
            "es_diaria": es_diaria,
            "aplica": (not es_diaria) or incluir_diarias,
        }
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# Concordancia: valor diario nativo vs. respaldo de su variable sub-diaria
# ══════════════════════════════════════════════════════════════════════════════

# t: se prefiere n_airtemp (sin sufijo) sobre n_airtemp_inst para el respaldo
# sub-diario — misma razón y misma evidencia re-derivada de datos reales que
# en core.consistencia.PRESETS (ver esa nota para el detalle completo).
# Sigue pendiente de confirmación definitiva por el equipo de catálogo SIGMA.
PARES_CONCORDANCIA = {
    "n_maxat":   ["n_airtemp", "n_airtemp_inst"],
    "n_minat":   ["n_airtemp", "n_airtemp_inst"],
    "n_dayrain": ["n_lluvia", "n_rain_10m"],
}


def evaluar_concordancia_diaria(
    serie_diaria: pd.Series,
    serie_subdiaria: pd.Series,
    cadencia_subdiaria: pd.Timedelta | None = None,
    umbral_pct: float = UMBRAL_DIA_EFECTIVO,
) -> pd.DataFrame:
    """
    Una fila por cada lectura válida de serie_diaria (ej. n_maxat a las
    07:00). Ventana mirada: (ts - 24h, ts] de serie_subdiaria — el propio
    timestamp del reporte diario como ancla, no un día calendario asumido.
    """
    diarios = pd.to_numeric(serie_diaria, errors="coerce").dropna()
    if diarios.empty:
        return pd.DataFrame(columns=_COLUMNAS_CONCORDANCIA)

    cadencia_subdiaria = (
        cadencia_subdiaria if cadencia_subdiaria is not None
        else deteccion_afectaciones.cadencia_inferida(serie_subdiaria)
    )
    if cadencia_subdiaria is None or cadencia_subdiaria.total_seconds() <= 0:
        return pd.DataFrame(columns=_COLUMNAS_CONCORDANCIA)

    subdiaria = pd.to_numeric(serie_subdiaria, errors="coerce").dropna().sort_index()
    idx = subdiaria.index
    n_esperado = pd.Timedelta(days=1) / cadencia_subdiaria
    ventana = pd.Timedelta(days=1)

    filas = []
    for ts, valor in diarios.items():
        lo = idx.searchsorted(ts - ventana, side="right")
        hi = idx.searchsorted(ts, side="right")
        n_recibido = int(hi - lo)
        pct = n_recibido / n_esperado
        filas.append((ts, valor, n_esperado, n_recibido, pct, pct >= umbral_pct))

    df = pd.DataFrame(filas, columns=["ts"] + _COLUMNAS_CONCORDANCIA)
    return df.set_index("ts")


def construir_tabla_concordancia(
    df_estacion: pd.DataFrame,
    umbral_pct: float = UMBRAL_DIA_EFECTIVO,
) -> dict[str, dict]:
    """
    Por cada variable diaria nativa de PARES_CONCORDANCIA presente en
    df_estacion, usa la primera candidata sub-diaria presente en las
    columnas de la estación. Variables sin candidata disponible no pueden
    evaluarse y se omiten.
    """
    resultado = {}
    for var_diaria, candidatas in PARES_CONCORDANCIA.items():
        if var_diaria not in df_estacion.columns:
            continue
        var_subdiaria = next((c for c in candidatas if c in df_estacion.columns), None)
        if var_subdiaria is None:
            continue
        resultado[var_diaria] = {
            "tabla": evaluar_concordancia_diaria(
                df_estacion[var_diaria], df_estacion[var_subdiaria], umbral_pct=umbral_pct,
            ),
            "variable_subdiaria": var_subdiaria,
        }
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# Caché en disco por estación — "día efectivo" es un chequeo de calidad sobre
# el HISTÓRICO COMPLETO, no sobre el periodo que el usuario esté mirando en
# un momento dado. Antes se recalculaba (evaluar_dias_efectivos +
# evaluar_concordancia_diaria, esta última con un for-loop en Python por cada
# lectura diaria nativa) en CADA consulta de Vista cruda, sobre el recorte de
# periodo vigente — carísimo con series largas y, además, sin sentido: el
# resultado no depende del periodo elegido, solo de los datos ya descargados.
# Ahora se calcula una vez por estación, se guarda en disco, y solo se
# recalcula si cambiaron sus CSV (ver data_loader.firma_estacion) — consultar
# un periodo distinto nunca dispara este cálculo de nuevo.
# ══════════════════════════════════════════════════════════════════════════════

# Fijo, no el de "Flags a incluir" de la UI: "día efectivo" es un chequeo de
# calidad de dato, no una vista que deba cambiar según qué flags el usuario
# decida mirar en pantalla en un momento dado.
FLAGS_CACHE_DIA_EFECTIVO = ["C"]


def _version_logica_cache() -> str:
    """
    Huella de TODO el código que determina el resultado cacheado — no un
    número de versión que alguien tiene que acordarse de subir a mano.
    Cualquier cambio a este archivo (PARES_CONCORDANCIA, UMBRAL_DIA_EFECTIVO,
    las funciones evaluar_*/construir_tabla_*, etc.) o a
    deteccion_afectaciones.cadencia_inferida (de la que depende directamente
    esta lógica) cambia el hash y por lo tanto invalida el caché en disco.

    Antes de esto, la caché solo se invalidaba si cambiaban los CSV de la
    estación (ver firma_estacion) — un cambio de código dejaba el .pkl
    "válido" según su propia lógica de invalidación y había que acordarse de
    borrar DATA/cache_dias_efectivos/*.pkl a mano (pasó de verdad el
    2026-09-04 con el cambio de PARES_CONCORDANCIA — costó dos vueltas de
    prueba en navegador notar que el fix "no se veía" solo por esto).

    También incluye el archivo completo de control_calidad.py: cuando
    flags_cc no es None, este módulo llama a
    control_calidad.agregar_columnas_cc, así que un cambio a las reglas del CC
    propio también debe invalidar el resultado cacheado acá.
    """
    fuente = Path(__file__).read_bytes()
    fuente += inspect.getsource(deteccion_afectaciones.cadencia_inferida).encode("utf-8")
    fuente += Path(control_calidad.__file__).read_bytes()
    return hashlib.sha256(fuente).hexdigest()[:16]


_VERSION_LOGICA_CACHE = _version_logica_cache()


def _ruta_cache(codigo: str) -> Path:
    return DIR_CACHE_DIAS_EFECTIVOS / f"{codigo.upper()}.pkl"


def _calcular_resultado_estacion(codigo: str, umbral_pct: float, flags_cc: list[str] | None = None) -> dict:
    df = data_loader.cargar_estaciones([codigo])
    if df.empty:
        return {"resultado_de": {}, "resultado_conc": {}}

    df = data_loader.filtrar_por_flags(df, FLAGS_CACHE_DIA_EFECTIVO)

    if flags_cc is not None:
        # CC propio del Analizador (core.control_calidad) — capa independiente
        # del flag_n_* de SIGMA de arriba. Una lectura debe pasar AMBOS filtros
        # para contar como "recibida" en día efectivo.
        df = control_calidad.agregar_columnas_cc(df)
        df = data_loader.filtrar_por_flags(df, flags_cc, prefijo_flag="cc_")

    grp = df[df["codigo"] == codigo.upper()].sort_values("datetime").set_index("datetime")
    propias = data_loader.variables_propias_estacion(codigo)
    variables = sorted(v for v in propias if v in grp.columns)

    # incluir_diarias=True: cachea la tabla de TODAS las variables sin filtrar
    # por "aplica" — ese filtro depende del switch de la UI (que sí puede
    # cambiar sin recalcular nada) y se aplica en ui/callbacks.py al leer.
    resultado_de = construir_tabla_dias_efectivos(
        grp, variables, incluir_diarias=True, umbral_pct=umbral_pct,
    )
    resultado_conc = construir_tabla_concordancia(grp, umbral_pct=umbral_pct)
    return {"resultado_de": resultado_de, "resultado_conc": resultado_conc}


def resultado_dias_efectivos_estacion(
    codigo: str, umbral_pct: float = UMBRAL_DIA_EFECTIVO, flags_cc: list[str] | None = None,
) -> dict:
    """
    {"resultado_de": {...todas las variables propias...}, "resultado_conc": {...}}
    sobre el HISTÓRICO COMPLETO de la estación — cacheado en disco, se
    recalcula solo si cambiaron sus CSV, el umbral, el CC propio elegido, o la
    lógica, desde la última vez.

    flags_cc: None (default) = ignora el CC propio, igual que antes de que
    existiera (solo filtra por FLAGS_CACHE_DIA_EFECTIVO, el "C" de SIGMA). Una
    lista (ej. ["BUENO"]) exige además que la lectura pase el CC propio del
    Analizador (core.control_calidad) para contar como "recibida".
    """
    codigo = codigo.upper()
    firma_actual = data_loader.firma_estacion(codigo)
    flags_cc_clave = tuple(sorted(flags_cc)) if flags_cc is not None else None
    ruta = _ruta_cache(codigo)

    if ruta.exists():
        try:
            with open(ruta, "rb") as f:
                cache = pickle.load(f)
            if (
                cache.get("firma") == firma_actual
                and cache.get("umbral_pct") == umbral_pct
                and cache.get("flags_cc") == flags_cc_clave
                and cache.get("version_logica") == _VERSION_LOGICA_CACHE
            ):
                return cache["resultado"]
        except Exception:
            pass  # caché corrupta/de otra versión — se recalcula abajo

    resultado = _calcular_resultado_estacion(codigo, umbral_pct, flags_cc)
    DIR_CACHE_DIAS_EFECTIVOS.mkdir(parents=True, exist_ok=True)
    with open(ruta, "wb") as f:
        pickle.dump({
            "firma": firma_actual,
            "umbral_pct": umbral_pct,
            "flags_cc": flags_cc_clave,
            "version_logica": _VERSION_LOGICA_CACHE,
            "resultado": resultado,
        }, f)
    return resultado
