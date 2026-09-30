"""
Detección de eventos sobre series derivadas usando umbrales empíricos
(percentiles de la propia distribución).

Filosofía: el umbral NO se decide a priori — se calcula como un percentil
de la distribución observada y se reporta cuántos eventos lo exceden.
Esto es lo que permite descubrir reglas de aseguramiento basadas en evidencia.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def detectar_excedencias(
    df_serie: pd.DataFrame,
    columna: str,
    percentil: float = 99.0,
    umbral_absoluto: float | None = None,
    direccion: str = "ambos",
) -> pd.DataFrame:
    """
    Marca filas donde `columna` excede un umbral.

    Si se pasa `umbral_absoluto` se usa ese valor directamente.
    Si no, el umbral se calcula como el percentil pedido de los valores no-NaN
    de la propia columna.

    direccion:
      "ambos"     : |valor| > umbral  (absoluto)
      "positivo"  : valor > umbral
      "negativo"  : valor < -umbral

    Retorna DataFrame original filtrado a las filas excedentes, con columnas
    adicionales: umbral_usado, abs_valor.
    """
    if columna not in df_serie.columns or df_serie.empty:
        return pd.DataFrame()

    serie = pd.to_numeric(df_serie[columna], errors="coerce")
    serie_clean = serie.dropna()
    if serie_clean.empty:
        return pd.DataFrame()

    if umbral_absoluto is not None:
        umbral = float(umbral_absoluto)
    else:
        if direccion == "ambos":
            umbral = float(serie_clean.abs().quantile(percentil / 100.0))
        else:
            umbral = float(serie_clean.quantile(percentil / 100.0))

    if direccion == "ambos":
        mask = serie.abs() > umbral
    elif direccion == "positivo":
        mask = serie > umbral
    elif direccion == "negativo":
        mask = serie < -umbral
    else:
        mask = pd.Series(False, index=serie.index)

    out = df_serie.loc[mask].copy()
    if out.empty:
        return out
    out["umbral_usado"] = umbral
    out["abs_valor"] = serie.loc[mask].abs().values
    return out.reset_index(drop=True)


def patron_recurrencia(
    eventos: pd.DataFrame,
    dim: str = "hora_del_dia",
) -> pd.DataFrame:
    """
    Agrupa los eventos detectados por una dimensión temporal o por estación,
    y cuenta cuántos ocurren en cada grupo. Output ordenado descendente.

    dim disponibles:
      hora_del_dia, dia_semana, mes, anio, codigo, dz

    Requiere que `eventos` tenga columna 'datetime' y al menos 'codigo'.
    Para dim='dz' requiere también columna 'dz'.

    Retorna DataFrame: grupo · n_eventos · pct
    """
    if eventos.empty or "datetime" not in eventos.columns:
        return pd.DataFrame(columns=["grupo", "n_eventos", "pct"])

    dt = pd.to_datetime(eventos["datetime"])

    if dim == "hora_del_dia":
        grupos = dt.dt.hour
    elif dim == "dia_semana":
        grupos = dt.dt.dayofweek
    elif dim == "mes":
        grupos = dt.dt.month
    elif dim == "anio":
        grupos = dt.dt.year
    elif dim == "codigo":
        grupos = eventos["codigo"] if "codigo" in eventos.columns else None
    elif dim == "dz":
        grupos = eventos["dz"] if "dz" in eventos.columns else None
    else:
        grupos = None

    if grupos is None:
        return pd.DataFrame(columns=["grupo", "n_eventos", "pct"])

    cuenta = grupos.value_counts().sort_values(ascending=False)
    total = int(cuenta.sum())
    out = pd.DataFrame({
        "grupo":     cuenta.index,
        "n_eventos": cuenta.values,
        "pct":       (cuenta.values / total * 100).round(2),
    })
    return out


def co_ocurrencia_temporal(
    eventos: pd.DataFrame,
    ventana_horas: int = 1,
) -> pd.DataFrame:
    """
    Para detectar si varios eventos ocurren simultáneamente (en ventana ≤ N horas)
    en distintas estaciones — útil para distinguir falla de sensor vs
    fenómeno físico real (si todas las estaciones vecinas saltan a la vez,
    es probable que sea fenómeno; si solo una, es probable que sea sensor).

    Retorna DataFrame con columnas:
      ventana_inicio · n_estaciones · codigos · n_eventos
    """
    if eventos.empty or "datetime" not in eventos.columns or "codigo" not in eventos.columns:
        return pd.DataFrame()

    ev = eventos.sort_values("datetime").copy()
    ev["datetime"] = pd.to_datetime(ev["datetime"])
    ev["bucket"] = ev["datetime"].dt.floor(f"{ventana_horas}h")

    agg = ev.groupby("bucket").agg(
        n_eventos=("codigo", "size"),
        n_estaciones=("codigo", "nunique"),
        codigos=("codigo", lambda s: ", ".join(sorted(set(s)))),
    ).reset_index().rename(columns={"bucket": "ventana_inicio"})

    return agg.sort_values("n_estaciones", ascending=False).reset_index(drop=True)
