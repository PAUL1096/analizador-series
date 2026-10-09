"""
Funciones puras para series derivadas.

Cada función toma una pd.Series indexada por datetime y retorna una pd.Series.
La idea es componer estas transformaciones desde la configuración YAML sin
hardcodear nada en la UI.
"""
from __future__ import annotations

import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from functools import lru_cache

from analizador_series.config import NOMBRES_YAML, SERIES_YAML


# ══════════════════════════════════════════════════════════════════════════════
# Transformaciones básicas (sobre serie ya indexada por datetime)
# ══════════════════════════════════════════════════════════════════════════════

def delta(s: pd.Series, lag: int = 1) -> pd.Series:
    """x(t) - x(t-lag). Si la serie es horaria, lag=1 significa 1 hora."""
    return s.diff(lag)


def abs_delta(s: pd.Series, lag: int = 1) -> pd.Series:
    """|x(t) - x(t-lag)|"""
    return s.diff(lag).abs()


def rolling_mean(s: pd.Series, ventana: int = 24) -> pd.Series:
    """Media móvil con ventana de N pasos."""
    return s.rolling(ventana, min_periods=max(2, ventana // 2)).mean()


def rolling_std(s: pd.Series, ventana: int = 24) -> pd.Series:
    """Desviación estándar móvil."""
    return s.rolling(ventana, min_periods=max(2, ventana // 2)).std()


def z_local(s: pd.Series, ventana: int = 24) -> pd.Series:
    """
    Z-score local: (x - μ_local) / σ_local, donde μ y σ se calculan sobre
    la ventana inmediatamente anterior. Equivale a la "distancia en sigmas"
    respecto del contexto reciente.
    """
    mu = rolling_mean(s, ventana)
    sigma = rolling_std(s, ventana)
    return (s - mu) / sigma.replace(0, np.nan)


def tasa_cambio_por_hora(s: pd.Series) -> pd.Series:
    """
    Tasa de cambio expresada en unidades-por-hora, normalizando por el Δt
    real entre observaciones. Útil cuando la frecuencia no es exactamente
    horaria.
    """
    if s.index.dtype.kind != "M":
        return pd.Series(index=s.index, dtype=float)
    dt_h = s.index.to_series().diff().dt.total_seconds() / 3600.0
    return s.diff() / dt_h.replace(0, np.nan)


# ══════════════════════════════════════════════════════════════════════════════
# Despacho desde configuración YAML
# ══════════════════════════════════════════════════════════════════════════════

_TIPOS = {
    "delta":        delta,
    "abs_delta":    abs_delta,
    "rolling_mean": rolling_mean,
    "rolling_std":  rolling_std,
    "z_local":      z_local,
    "tasa_cambio":  tasa_cambio_por_hora,
}


@lru_cache(maxsize=1)
def _cargar_config() -> dict:
    if not SERIES_YAML.exists():
        return {}
    with open(SERIES_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def _cargar_nombres() -> dict:
    if not NOMBRES_YAML.exists():
        return {}
    with open(NOMBRES_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def info_variable(variable: str) -> dict:
    """
    Retorna el bloque de configuración para una variable.
    Si no tiene bloque propio en series_disponibles.yaml, usa el bloque
    _default con el nombre/unidad de nombres_variables.yaml; y si tampoco
    está ahí, el propio código como nombre (último recurso).
    """
    cfg = _cargar_config()
    if variable in cfg:
        return cfg[variable]
    base = dict(cfg.get("_default", {}))
    nombre = _cargar_nombres().get(variable) or {}
    base["display_name"] = nombre.get("nombre") or variable
    base["unidad"] = nombre.get("unidad") or ""
    return base


def etiqueta_variable(variable: str, con_codigo: bool = False) -> str:
    """
    Nombre legible de una variable para mostrar en pantalla. Con
    con_codigo=True agrega el código de SIGMA (útil en selectores, donde
    quien conoce los códigos los busca así), salvo que el nombre ya lo traiga.
    """
    nombre = info_variable(variable).get("display_name") or variable
    if con_codigo and variable not in nombre:
        return f"{nombre} · {variable}"
    return nombre


def etiqueta_derivada(variable: str, id_serie: str) -> str:
    """
    Texto legible de una serie derivada para títulos y tablas, ej.
    "Cambio absoluto en 1 h · Humedad relativa" en vez del id interno
    (absdHR_1h). Si el id no está configurado, se devuelve tal cual.
    """
    spec = next((sp for sp in series_disponibles(variable) if sp.get("id") == id_serie), None)
    if spec is None:
        return id_serie
    return f"{spec.get('label', id_serie)} · {etiqueta_variable(variable)}"


def series_disponibles(variable: str) -> list[dict]:
    """Lista de series derivadas configuradas para una variable."""
    return info_variable(variable).get("series", []) or []


def calcular(s: pd.Series, spec: dict) -> pd.Series:
    """
    Aplica una serie derivada según su spec (un item del YAML).
    spec ejemplo: {tipo: delta, lag: 1, ...}
    """
    tipo = spec.get("tipo")
    fn = _TIPOS.get(tipo)
    if fn is None:
        return pd.Series(index=s.index, dtype=float)

    kwargs = {}
    if "lag" in spec:
        kwargs["lag"] = int(spec["lag"])
    if "ventana" in spec:
        kwargs["ventana"] = int(spec["ventana"])
    try:
        return fn(s, **kwargs)
    except TypeError:
        # Función no acepta esos kwargs
        return fn(s)


def calcular_lote(s: pd.Series, ids_seleccionados: list[str], variable: str) -> dict[str, pd.Series]:
    """
    Calcula todas las series derivadas con id en `ids_seleccionados`
    para una serie cruda dada de `variable`. Retorna {id: serie}.
    """
    out = {}
    specs = {sp["id"]: sp for sp in series_disponibles(variable)}
    for sid in ids_seleccionados:
        if sid in specs:
            out[sid] = calcular(s, specs[sid])
    return out
