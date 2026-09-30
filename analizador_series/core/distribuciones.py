"""
Funciones puras para describir la distribución de una serie:
percentiles, histogramas y descomposiciones por mes / hora-del-día.

Estos son los outputs que permiten responder operativamente
"qué valor de |ΔHR| consideramos anómalo": se mira el percentil 99 ó 99.5
de la distribución empírica.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# Percentiles
# ══════════════════════════════════════════════════════════════════════════════

def percentiles(s: pd.Series, ps: list[float] | None = None) -> dict[float, float]:
    """
    Retorna {percentil: valor} para los percentiles pedidos.
    ps en escala 0-100 (ej: [50, 95, 99, 99.5]).
    """
    if ps is None:
        ps = [50, 95, 99, 99.5]
    s_clean = pd.to_numeric(s, errors="coerce").dropna()
    if s_clean.empty:
        return {p: np.nan for p in ps}
    return {p: float(s_clean.quantile(p / 100.0)) for p in ps}


# ══════════════════════════════════════════════════════════════════════════════
# Histograma
# ══════════════════════════════════════════════════════════════════════════════

def histograma(s: pd.Series, bins: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """
    Histograma robusto: retorna (centros_bins, frecuencias_normalizadas).
    Excluye NaN. Si la serie es muy chica retorna arrays vacíos.
    """
    s_clean = pd.to_numeric(s, errors="coerce").dropna().values
    if len(s_clean) < 5:
        return np.array([]), np.array([])
    hist, edges = np.histogram(s_clean, bins=bins, density=False)
    centros = 0.5 * (edges[:-1] + edges[1:])
    return centros, hist


# ══════════════════════════════════════════════════════════════════════════════
# Boxplots por descomposición temporal
# ══════════════════════════════════════════════════════════════════════════════

def boxplot_por(s: pd.Series, dim: str = "mes") -> pd.DataFrame:
    """
    Construye los datos para boxplot agrupado por una dimensión temporal.
    `s` debe tener índice datetime.
    dim ∈ {'mes', 'hora', 'dia_semana', 'anio'}

    Retorna DataFrame con columnas: grupo, valor — listo para feed a Plotly.
    """
    if not isinstance(s.index, pd.DatetimeIndex):
        return pd.DataFrame(columns=["grupo", "valor"])

    s_clean = pd.to_numeric(s, errors="coerce")
    if dim == "mes":
        grupos = s_clean.index.month
    elif dim == "hora":
        grupos = s_clean.index.hour
    elif dim == "dia_semana":
        grupos = s_clean.index.dayofweek
    elif dim == "anio":
        grupos = s_clean.index.year
    else:
        return pd.DataFrame(columns=["grupo", "valor"])

    out = pd.DataFrame({"grupo": grupos, "valor": s_clean.values})
    return out.dropna(subset=["valor"])


# ══════════════════════════════════════════════════════════════════════════════
# Resumen estadístico
# ══════════════════════════════════════════════════════════════════════════════

def resumen(s: pd.Series) -> dict:
    """
    Resumen estadístico básico de una serie: n, media, std, min/max,
    percentiles p50/p95/p99/p99.5, y cantidad de NaN.
    """
    s_clean = pd.to_numeric(s, errors="coerce").dropna()
    n_total = len(s)
    n_validos = len(s_clean)
    if n_validos == 0:
        return {
            "n_total": n_total, "n_validos": 0, "n_nan": n_total,
            "media": None, "std": None, "min": None, "max": None,
            "p50": None, "p95": None, "p99": None, "p99_5": None,
        }
    pct = percentiles(s_clean, [50, 95, 99, 99.5])
    return {
        "n_total": n_total,
        "n_validos": n_validos,
        "n_nan": n_total - n_validos,
        "media": float(s_clean.mean()),
        "std":   float(s_clean.std()),
        "min":   float(s_clean.min()),
        "max":   float(s_clean.max()),
        "p50":   pct[50],
        "p95":   pct[95],
        "p99":   pct[99],
        "p99_5": pct[99.5],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Distribución de flags SIGMA
# ══════════════════════════════════════════════════════════════════════════════

def distribucion_flags(flags: pd.Series) -> dict[str, float]:
    """
    Retorna {flag: porcentaje} con los flags SIGMA (C / M / SD).
    """
    if flags.empty:
        return {}
    vc = flags.fillna("SD").value_counts(normalize=True) * 100
    return {str(k): float(v) for k, v in vc.items()}
