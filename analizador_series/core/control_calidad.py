"""
Control de Calidad (CC) LOCAL del Analizador — capa de análisis propia de SGR.

No es el CC oficial de la SGD (Subdirección de Gestión de Datos): usa manuales
técnicos SENAMHI (MT-DRD-001/002/003) como referencia NUMÉRICA para reglas propias
de esta herramienta. El resultado nunca sale de esta máquina — no se sincroniza a
ninguna base institucional, no se comparte con SGD, no se conecta a ningún
sistema de alertas (ver docs/SPEC-control-calidad.md, restricción explícita del usuario).

Banderines: BUENO (pasa todo) / DUDOSO (no pasa una regla blanda) / MALO (fuera de
límite duro). Combinación por lectura: MALO > DUDOSO > BUENO (peor gana).
"""
from __future__ import annotations

import hashlib
import inspect
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from analizador_series.config import DIR_CACHE_CONTROL_CALIDAD
from analizador_series.core import data_loader, deteccion_afectaciones

_RUTA_CONFIG = Path(__file__).resolve().parent.parent / "config" / "control_calidad.yaml"
with open(_RUTA_CONFIG, encoding="utf-8") as _f:
    _CONFIG: dict = yaml.safe_load(_f)

BUENO, DUDOSO, MALO = "BUENO", "DUDOSO", "MALO"
_RANK = {MALO: 0, DUDOSO: 1, BUENO: 2}


def _combinar(*series_banderin: pd.Series) -> pd.Series:
    """Peor banderín gana (MALO > DUDOSO > BUENO), elemento a elemento."""
    series_banderin = [s for s in series_banderin if s is not None]
    if not series_banderin:
        raise ValueError("_combinar necesita al menos una serie")
    rank = pd.concat(series_banderin, axis=1).replace(_RANK)
    peor_rank = rank.min(axis=1)
    inverso = {v: k for k, v in _RANK.items()}
    return peor_rank.map(inverso)


def _pasos_para(cadencia: pd.Timedelta, ventana: pd.Timedelta) -> int:
    return max(round(ventana / cadencia), 1)


# ══════════════════════════════════════════════════════════════════════════════
# Automáticas
# ══════════════════════════════════════════════════════════════════════════════

def evaluar_limites_duros_automatica(serie: pd.Series, variable: str) -> pd.Series:
    """
    Límite físico duro (el más estricto entre MT-DRD-001 y MT-DRD-002, ver
    control_calidad.yaml). Fuera de rango -> MALO.
    """
    resultado = pd.Series(BUENO, index=serie.index)
    cfg = _CONFIG.get(variable, {}).get("limite_duro")
    if cfg is None:
        return resultado
    valores = pd.to_numeric(serie, errors="coerce")
    fuera = (valores < cfg["min"]) | (valores > cfg["max"])
    resultado[fuera.fillna(False)] = MALO
    return resultado


def evaluar_prueba_paso(
    serie: pd.Series, variable: str, cadencia: pd.Timedelta | None = None,
) -> pd.Series:
    """
    Salto máximo entre lecturas consecutivas (MT-DRD-002 §6.3.2.1, subreglas 31-40).
    Fuera del salto permitido -> DUDOSO. Solo aplica a automáticas.
    """
    resultado = pd.Series(BUENO, index=serie.index)
    cfg = _CONFIG.get(variable, {}).get("paso")
    if cfg is None:
        return resultado

    cadencia = cadencia if cadencia is not None else deteccion_afectaciones.cadencia_inferida(serie)
    if cadencia is None or cadencia.total_seconds() <= 0:
        return resultado

    valores = pd.to_numeric(serie, errors="coerce")

    if "max_delta_circular" in cfg:
        pasos = _pasos_para(cadencia, pd.Timedelta(hours=1))
        delta = (valores - valores.shift(pasos)).abs()
        delta_circular = np.minimum(delta, 360 - delta)
        viola = delta_circular >= cfg["max_delta_circular"]
        resultado[viola.fillna(False)] = DUDOSO
        return resultado

    if "max_delta" in cfg:
        pasos = _pasos_para(cadencia, pd.Timedelta(hours=1))
        delta = (valores - valores.shift(pasos)).abs()
        viola = (delta >= cfg["max_delta"]) if cfg.get("estricto") else (delta > cfg["max_delta"])
        if "min_delta" in cfg:
            viola = viola | (delta < cfg["min_delta"])
        resultado[viola.fillna(False)] = DUDOSO
        return resultado

    # Tabla de ventanas múltiples (temperatura, presión: 1h/2h/3h/6h/12h)
    for clave, horas in (("max_1h", 1), ("max_2h", 2), ("max_3h", 3), ("max_6h", 6), ("max_12h", 12)):
        if clave not in cfg:
            continue
        pasos = _pasos_para(cadencia, pd.Timedelta(hours=horas))
        delta = (valores - valores.shift(pasos)).abs()
        viola = delta > cfg[clave]
        resultado[viola.fillna(False)] = DUDOSO
    return resultado


def evaluar_persistencia(serie: pd.Series, variable: str) -> pd.Series:
    """
    4 lecturas horarias idénticas consecutivas (la actual + 3 previas) -> las 4 se
    marcan DUDOSO (MT-DRD-002 §6.3.2.2, subreglas 41-46). Excluida explícitamente
    para precipitación y nivel de agua (persistencia=false en control_calidad.yaml).
    """
    resultado = pd.Series(BUENO, index=serie.index)
    if not _CONFIG.get(variable, {}).get("persistencia", False):
        return resultado

    valores = pd.to_numeric(serie, errors="coerce")
    iguales = (valores.diff(1) == 0) & (valores.diff(2) == 0) & (valores.diff(3) == 0)
    marcar = iguales.copy()
    for k in (1, 2, 3):
        marcar = marcar | iguales.shift(-k, fill_value=False)
    resultado[marcar] = DUDOSO
    return resultado


def evaluar_automatica(
    serie: pd.Series, variable: str, cadencia: pd.Timedelta | None = None,
) -> pd.Series:
    """Combina límites duros + prueba de paso + persistencia para una automática."""
    return _combinar(
        evaluar_limites_duros_automatica(serie, variable),
        evaluar_prueba_paso(serie, variable, cadencia),
        evaluar_persistencia(serie, variable),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Convencionales — nomenclatura TM (MT-DRD-003 §6.3), no n_airtemp.
# ══════════════════════════════════════════════════════════════════════════════

_TM_MAX_DIARIA = "n_tm102"
_TM_MIN_DIARIA = "n_tm103"
_TM_SECO = ("n_tm104", "n_tm105", "n_tm106")      # bulbo seco 07/13/19h
_TM_HUMEDO = ("n_tm107", "n_tm108", "n_tm109")    # bulbo húmedo 07/13/19h
_VARIABLES_TEMPERATURA_CONVENCIONAL = {_TM_MAX_DIARIA, _TM_MIN_DIARIA, *_TM_SECO, *_TM_HUMEDO}


def evaluar_limites_duros_convencional(serie: pd.Series, variable: str) -> pd.Series:
    """
    Límite duro de temperatura convencional (MT-DRD-003 subregla 2.G): -30/45°C
    duro, fuera -> MALO. Bandas -30/-28 y 43/45 (subreglas 2.H/2.I), dentro del duro
    pero extremas -> DUDOSO. Solo aplica a las 8 variables TM de temperatura.
    """
    resultado = pd.Series(BUENO, index=serie.index)
    if variable not in _VARIABLES_TEMPERATURA_CONVENCIONAL:
        return resultado

    cfg = _CONFIG["n_tm_temperatura"]
    valores = pd.to_numeric(serie, errors="coerce")

    duro = cfg["limite_duro"]
    fuera_duro = (valores < duro["min"]) | (valores > duro["max"])
    resultado[fuera_duro.fillna(False)] = MALO

    baja, alta = cfg["banda_dudosa_baja"], cfg["banda_dudosa_alta"]
    en_banda = (
        ((valores >= baja["min"]) & (valores <= baja["max"]))
        | ((valores >= alta["min"]) & (valores <= alta["max"]))
    ) & ~fuera_duro
    resultado[en_banda.fillna(False)] = DUDOSO
    return resultado


def evaluar_coherencia_interna(df_estacion: pd.DataFrame) -> dict[str, pd.Series]:
    """
    Coherencia entre máx/mín diaria e instantáneas de 07/13/19h, y bulbo seco vs.
    húmedo a la misma hora (MT-DRD-003 §6.3.2, subreglas 2.A-2.L). Compara fila a
    fila (cada fila trae el set de lecturas de ese día/reporte). Variables ausentes
    en df_estacion se omiten sin error.
    """
    presentes = {v: df_estacion[v] for v in _VARIABLES_TEMPERATURA_CONVENCIONAL if v in df_estacion.columns}
    resultado = {v: pd.Series(BUENO, index=df_estacion.index) for v in presentes}

    def _marcar_mal(condicion_rota: pd.Series, *variables: str) -> None:
        condicion_rota = condicion_rota.fillna(False)
        for v in variables:
            if v in resultado:
                resultado[v][condicion_rota] = MALO

    if _TM_MAX_DIARIA in presentes and _TM_MIN_DIARIA in presentes:
        _marcar_mal(presentes[_TM_MAX_DIARIA] <= presentes[_TM_MIN_DIARIA], _TM_MAX_DIARIA, _TM_MIN_DIARIA)

    if _TM_MAX_DIARIA in presentes:
        for inst in (*_TM_SECO, *_TM_HUMEDO):
            if inst in presentes:
                _marcar_mal(presentes[_TM_MAX_DIARIA] < presentes[inst], _TM_MAX_DIARIA, inst)

    if _TM_MIN_DIARIA in presentes:
        for inst in _TM_SECO:
            if inst in presentes:
                _marcar_mal(presentes[_TM_MIN_DIARIA] > presentes[inst], _TM_MIN_DIARIA, inst)

    for seco, humedo in zip(_TM_SECO, _TM_HUMEDO):
        if seco in presentes and humedo in presentes:
            _marcar_mal(presentes[seco] < presentes[humedo], seco, humedo)

    return resultado


def evaluar_variacion_diaria(
    serie: pd.Series, region_natural: str | None, altitud: float | None,
) -> pd.Series:
    """
    Variación máxima entre días consecutivos, según región climática + altitud
    (MT-DRD-003 subregla 2.N, ver control_calidad.yaml). Fuera del máximo -> DUDOSO.
    Sin region_natural/altitud (metadata faltante) -> BUENO sin evaluar, no lanza
    excepción.
    """
    resultado = pd.Series(BUENO, index=serie.index)
    if region_natural is None or altitud is None:
        return resultado

    bandas = _CONFIG["variacion_diaria_temperatura"]
    max_delta: float | None = None
    if region_natural == "Costa" and altitud <= bandas["costa"]["altitud_max"]:
        max_delta = bandas["costa"]["max_delta"]
    elif region_natural in ("Sierra", "Selva"):
        if altitud <= bandas["sierra_selva_baja"]["altitud_max"]:
            max_delta = bandas["sierra_selva_baja"]["max_delta"]
        else:
            max_delta = bandas["sierra_alta"]["max_delta"]

    if max_delta is None:
        return resultado

    valores = pd.to_numeric(serie, errors="coerce")
    delta = (valores - valores.shift(1)).abs()
    viola = delta > max_delta
    resultado[viola.fillna(False)] = DUDOSO
    return resultado


def evaluar_convencional(
    df_estacion: pd.DataFrame, region_natural: str | None, altitud: float | None,
) -> dict[str, pd.Series]:
    """
    Combina límites duros + coherencia interna + variación diaria para todas las
    variables de temperatura convencional presentes en df_estacion.
    """
    coherencia = evaluar_coherencia_interna(df_estacion)
    resultado = {}
    for variable in _VARIABLES_TEMPERATURA_CONVENCIONAL:
        if variable not in df_estacion.columns:
            continue
        serie = df_estacion[variable]
        piezas = [
            evaluar_limites_duros_convencional(serie, variable),
            evaluar_variacion_diaria(serie, region_natural, altitud),
        ]
        if variable in coherencia:
            piezas.append(coherencia[variable])
        resultado[variable] = _combinar(*piezas)
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# Punto de entrada único
# ══════════════════════════════════════════════════════════════════════════════

def tiene_regla_cc(variable: str, categoria: str) -> bool:
    """
    True si existe alguna regla de CC definida para esta variable+categoria en
    control_calidad.yaml — no todas las variables la tienen todavía (ver
    docs/SPEC-control-calidad.md, "qué NO incluye"). Pensada para que la UI
    pueda distinguir, en el selector de variables, cuáles se evalúan con CC y
    cuáles se muestran solo crudas.
    """
    categoria = (categoria or "").upper()
    if categoria == "AUTOMATICA":
        return variable in _CONFIG
    if categoria == "CONVENCIONAL":
        return variable in _VARIABLES_TEMPERATURA_CONVENCIONAL
    return False


def evaluar_todas(
    df_estacion: pd.DataFrame,
    categoria: str,
    variables: list[str] | None = None,
    region_natural: str | None = None,
    altitud: float | None = None,
) -> dict[str, pd.Series]:
    """
    Decide qué batería de reglas aplicar según `categoria` ("AUTOMATICA"/
    "CONVENCIONAL", ver data_ref/estaciones.db) y devuelve {variable: banderin}
    para las variables de df_estacion cubiertas por alguna regla. Una variable sin
    regla definida en control_calidad.yaml no aparece en el resultado — no hay CC
    para esa variable todavía, no es un error.
    """
    categoria = (categoria or "").upper()

    if categoria == "CONVENCIONAL":
        return evaluar_convencional(df_estacion, region_natural, altitud)

    if categoria == "AUTOMATICA":
        variables = variables if variables is not None else list(df_estacion.columns)
        resultado = {}
        for variable in variables:
            if variable not in df_estacion.columns or variable not in _CONFIG:
                continue
            resultado[variable] = evaluar_automatica(df_estacion[variable], variable)
        return resultado

    return {}


# ══════════════════════════════════════════════════════════════════════════════
# Motivo legible por lectura — qué regla objeta cada punto DUDOSO/MALO, para el
# hover del gráfico (pedido del usuario tras ver los puntos resaltados sin
# poder saber por qué). Funciones SEPARADAS de evaluar_*/evaluar_todas (que
# siguen devolviendo solo severidad, sin tocar su forma ya usada en varios
# lugares) — recalculan las mismas sub-reglas ya vectorizadas, así que no hay
# lógica duplicada, solo se etiqueta qué regla produjo cada severidad.
# ══════════════════════════════════════════════════════════════════════════════

def _construir_motivo(reglas: dict[str, pd.Series]) -> pd.Series:
    """
    reglas: {nombre_regla: pd.Series[banderin]}, todas con el mismo índice.
    Devuelve un texto por lectura, uniendo (con "; ") el nombre de cada regla
    que NO dio BUENO en ese punto — vacío ("") si todas dieron BUENO.
    """
    index = next(iter(reglas.values())).index
    motivo = pd.Series("", index=index, dtype=object)
    for nombre, resultado in reglas.items():
        aplica = (resultado != BUENO).reindex(index, fill_value=False)
        if not aplica.any():
            continue
        separador = np.where(motivo == "", "", "; ")
        motivo = motivo.mask(aplica, motivo + separador + nombre)
    return motivo


def explicar_motivo_automatica(
    serie: pd.Series, variable: str, cadencia: pd.Timedelta | None = None,
) -> pd.Series:
    """Motivo legible por lectura para una variable de estación automática."""
    duro = _CONFIG.get(variable, {}).get("limite_duro")
    nombre_duro = (
        f"límite duro ({duro['min']} a {duro['max']})" if duro else "límite duro"
    )
    reglas = {
        nombre_duro: evaluar_limites_duros_automatica(serie, variable),
        "prueba de paso": evaluar_prueba_paso(serie, variable, cadencia),
        "persistencia (4 lecturas idénticas)": evaluar_persistencia(serie, variable),
    }
    return _construir_motivo(reglas)


def explicar_motivo_convencional(
    df_estacion: pd.DataFrame, region_natural: str | None, altitud: float | None,
) -> dict[str, pd.Series]:
    """Motivo legible por lectura para las variables de temperatura convencional."""
    coherencia = evaluar_coherencia_interna(df_estacion)
    resultado = {}
    for variable in _VARIABLES_TEMPERATURA_CONVENCIONAL:
        if variable not in df_estacion.columns:
            continue
        serie = df_estacion[variable]
        reglas = {
            "límite duro": evaluar_limites_duros_convencional(serie, variable),
            "variación diaria (según región/altitud)": evaluar_variacion_diaria(serie, region_natural, altitud),
        }
        if variable in coherencia:
            reglas["coherencia interna"] = coherencia[variable]
        resultado[variable] = _construir_motivo(reglas)
    return resultado


def explicar_motivos(
    df_estacion: pd.DataFrame,
    categoria: str,
    variables: list[str] | None = None,
    region_natural: str | None = None,
    altitud: float | None = None,
) -> dict[str, pd.Series]:
    """Punto de entrada único de motivos, calco de evaluar_todas() pero para texto."""
    categoria = (categoria or "").upper()

    if categoria == "CONVENCIONAL":
        return explicar_motivo_convencional(df_estacion, region_natural, altitud)

    if categoria == "AUTOMATICA":
        variables = variables if variables is not None else list(df_estacion.columns)
        resultado = {}
        for variable in variables:
            if variable not in df_estacion.columns or variable not in _CONFIG:
                continue
            resultado[variable] = explicar_motivo_automatica(df_estacion[variable], variable)
        return resultado

    return {}


# ══════════════════════════════════════════════════════════════════════════════
# Caché en disco por estación — mismo mecanismo que core.dias_efectivos: se
# calcula una vez sobre el HISTÓRICO COMPLETO de la estación, se guarda en disco,
# y solo se recalcula si cambiaron sus CSV o la lógica de este archivo. Nunca sale
# de esta máquina (docs/SPEC-control-calidad.md).
# ══════════════════════════════════════════════════════════════════════════════

def _version_logica_cache() -> str:
    """
    Huella de este archivo + control_calidad.yaml (los umbrales) +
    deteccion_afectaciones.cadencia_inferida (de la que depende
    evaluar_prueba_paso) — mismo mecanismo que dias_efectivos._version_logica_cache.
    Cualquier cambio a las reglas O a los umbrales invalida el caché solo, sin
    que nadie tenga que borrar DATA/cache_control_calidad/*.pkl a mano.
    """
    fuente = Path(__file__).read_bytes()
    fuente += _RUTA_CONFIG.read_bytes()
    fuente += inspect.getsource(deteccion_afectaciones.cadencia_inferida).encode("utf-8")
    return hashlib.sha256(fuente).hexdigest()[:16]


_VERSION_LOGICA_CACHE = _version_logica_cache()


def _ruta_cache(codigo: str) -> Path:
    return DIR_CACHE_CONTROL_CALIDAD / f"{codigo.upper()}.pkl"


def _ruta_cache_motivos(codigo: str) -> Path:
    # Archivo separado del de severidad (_ruta_cache) — evita romper la forma
    # ya usada de resultado_control_calidad_estacion() en varios lugares
    # (agregar_columnas_cc, dias_efectivos.py, tests).
    return DIR_CACHE_CONTROL_CALIDAD / f"{codigo.upper()}_motivos.pkl"


def _resolver_metadata_y_datos(codigo: str):
    """
    (categoria, region_natural, altitud, grp) para una estación, o None si no
    hay metadata o no hay datos descargados — usado por
    _calcular_resultado_estacion y _calcular_motivos_estacion, para no repetir
    la misma resolución dos veces.
    """
    meta = data_loader.metadata_estaciones([codigo])
    if meta.empty:
        return None
    fila = meta.iloc[0]
    categoria = fila["categoria"]
    altitud = None if pd.isna(fila["altitud"]) else float(fila["altitud"])
    region_natural = None if pd.isna(fila["region_natural"]) else fila["region_natural"]

    df = data_loader.cargar_estaciones([codigo])
    if df.empty:
        return None
    grp = df[df["codigo"] == codigo.upper()].sort_values("datetime").set_index("datetime")
    return categoria, region_natural, altitud, grp


def _calcular_resultado_estacion(codigo: str) -> dict[str, pd.Series]:
    resuelto = _resolver_metadata_y_datos(codigo)
    if resuelto is None:
        return {}
    categoria, region_natural, altitud, grp = resuelto
    return evaluar_todas(grp, categoria=categoria, region_natural=region_natural, altitud=altitud)


def _calcular_motivos_estacion(codigo: str) -> dict[str, pd.Series]:
    resuelto = _resolver_metadata_y_datos(codigo)
    if resuelto is None:
        return {}
    categoria, region_natural, altitud, grp = resuelto
    return explicar_motivos(grp, categoria=categoria, region_natural=region_natural, altitud=altitud)


def agregar_columnas_cc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas cc_{variable} a un df multi-estación (columnas codigo+datetime)
    usando el caché por estación (resultado_control_calidad_estacion). Alinea por
    (codigo, datetime): el caché es sobre el histórico completo de cada estación,
    acá se toma el recorte que corresponda a las filas de df. Solo agrega columnas
    — filtrar por ellas es responsabilidad de data_loader.filtrar_por_flags(...,
    prefijo_flag="cc_").
    """
    if df.empty:
        return df
    df2 = df.copy()
    for codigo, idxs in df2.groupby("codigo").groups.items():
        resultado_cc = resultado_control_calidad_estacion(codigo)
        fechas = df2.loc[idxs, "datetime"].to_numpy()
        for variable, serie_cc in resultado_cc.items():
            col = f"cc_{variable}"
            if col not in df2.columns:
                df2[col] = pd.NA
            df2.loc[idxs, col] = serie_cc.reindex(fechas).to_numpy()
    return df2


def resultado_control_calidad_estacion(codigo: str) -> dict[str, pd.Series]:
    """
    {variable: pd.Series[banderin]} sobre el HISTÓRICO COMPLETO de la estación —
    cacheado en disco, se recalcula solo si cambiaron sus CSV o la lógica del CC
    desde la última vez.
    """
    codigo = codigo.upper()
    firma_actual = data_loader.firma_estacion(codigo)
    ruta = _ruta_cache(codigo)

    if ruta.exists():
        try:
            with open(ruta, "rb") as f:
                cache = pickle.load(f)
            if (
                cache.get("firma") == firma_actual
                and cache.get("version_logica") == _VERSION_LOGICA_CACHE
            ):
                return cache["resultado"]
        except Exception:
            pass  # caché corrupta/de otra versión — se recalcula abajo

    resultado = _calcular_resultado_estacion(codigo)
    DIR_CACHE_CONTROL_CALIDAD.mkdir(parents=True, exist_ok=True)
    with open(ruta, "wb") as f:
        pickle.dump({
            "firma": firma_actual,
            "version_logica": _VERSION_LOGICA_CACHE,
            "resultado": resultado,
        }, f)
    return resultado


def resultado_motivos_cc_estacion(codigo: str) -> dict[str, pd.Series]:
    """
    {variable: pd.Series[str]} — motivo legible por lectura (vacío si BUENO),
    sobre el HISTÓRICO COMPLETO de la estación. Mismo mecanismo de caché que
    resultado_control_calidad_estacion, en un archivo separado — pensado para
    el hover del gráfico (ui/charts.panel_crudo_multivariable), no para
    filtrar (eso sigue siendo solo la severidad).
    """
    codigo = codigo.upper()
    firma_actual = data_loader.firma_estacion(codigo)
    ruta = _ruta_cache_motivos(codigo)

    if ruta.exists():
        try:
            with open(ruta, "rb") as f:
                cache = pickle.load(f)
            if (
                cache.get("firma") == firma_actual
                and cache.get("version_logica") == _VERSION_LOGICA_CACHE
            ):
                return cache["resultado"]
        except Exception:
            pass  # caché corrupta/de otra versión — se recalcula abajo

    resultado = _calcular_motivos_estacion(codigo)
    DIR_CACHE_CONTROL_CALIDAD.mkdir(parents=True, exist_ok=True)
    with open(ruta, "wb") as f:
        pickle.dump({
            "firma": firma_actual,
            "version_logica": _VERSION_LOGICA_CACHE,
            "resultado": resultado,
        }, f)
    return resultado
