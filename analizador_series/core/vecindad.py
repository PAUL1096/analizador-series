"""
Vecindad — pares co-ubicados automática↔convencional (<umbral_m) y equivalencia
de variables físicas entre ambas, para la pestaña "Vecindad" (inspección visual,
sin estadística de comparación — eso es PLIA, proyecto separado. Ver
docs/SPEC-vecindad.md).

Sin caché en disco: 413×681 combinaciones es trivial (<1s), no amerita el
patrón de invalidación por versión de lógica que sí usa control_calidad.py
sobre históricos completos de CSV.
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd

from analizador_series.config import CATALOGO_DB

R_TIERRA_M = 6371000.0

_PALETA_EXTRA_SERIES = ["#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]

EQUIVALENCIA_VARIABLES: dict[str, dict] = {
    "temperatura": {
        "automatica": "n_airtemp",
        "convencional": ["n_tm102", "n_tm103", "n_tm104", "n_tm105", "n_tm106"],
        "etiqueta": "Temperatura",
    },
    "precipitacion": {
        "automatica": "n_lluvia",
        "convencional": ["n_pt101", "n_pt102", "n_pt103"],
        "etiqueta": "Precipitación",
    },
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros sobre una Tierra esférica de radio R_TIERRA_M."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dlon / 2) ** 2
    return 2 * R_TIERRA_M * math.asin(math.sqrt(a))


def calcular_pares_colocados(umbral_m: float = 100.0, ruta_db=CATALOGO_DB) -> list[dict]:
    """
    [{"codigo_auto","codigo_conv","distancia_m"}], ordenado por distancia. Solo
    cruza AUTOMATICA con CONVENCIONAL (nunca misma categoría); una automática
    puede aparecer en varios pares si tiene varias candidatas dentro del
    umbral — no se queda solo con la más cercana, el spec pide la lista
    completa para que el usuario filtre en la UI.
    """
    con = sqlite3.connect(ruta_db)
    try:
        filas = con.execute(
            "SELECT codigo, categoria, latitud, longitud FROM estaciones "
            "WHERE latitud IS NOT NULL AND longitud IS NOT NULL"
        ).fetchall()
    finally:
        con.close()

    automaticas = [f for f in filas if (f[1] or "").upper() == "AUTOMATICA"]
    convencionales = [f for f in filas if (f[1] or "").upper() == "CONVENCIONAL"]

    pares = []
    for cod_auto, _, lat_a, lon_a in automaticas:
        for cod_conv, _, lat_c, lon_c in convencionales:
            distancia = _haversine_m(lat_a, lon_a, lat_c, lon_c)
            if distancia <= umbral_m:
                pares.append({
                    "codigo_auto": cod_auto,
                    "codigo_conv": cod_conv,
                    "distancia_m": distancia,
                })

    pares.sort(key=lambda p: p["distancia_m"])
    return pares


def columnas_convencionales_disponibles(variable_fisica: str, columnas_df: list[str]) -> list[str]:
    """
    Subconjunto de EQUIVALENCIA_VARIABLES[variable_fisica]["convencional"] que
    de hecho existe en columnas_df — una convencional puede no traer todas
    (ej. si solo mide n_tm102/103 y no 104-106), se omite sin error.
    """
    esperadas = EQUIVALENCIA_VARIABLES[variable_fisica]["convencional"]
    return [c for c in esperadas if c in columnas_df]


def armar_extra_series_convencional(df_conv: pd.DataFrame, variable_fisica: str) -> list[dict]:
    """
    extra_series para ui.charts.overlay_multivar: una entrada por columna
    convencional disponible para variable_fisica en df_conv, en modo
    "markers" (puntos, sin línea conectora falsa) y con color distinto por
    columna. Columnas de la equivalencia que no estén en df_conv se omiten
    sin error (una convencional puede no traer todas).
    """
    if df_conv.empty:
        return []
    columnas = columnas_convencionales_disponibles(variable_fisica, list(df_conv.columns))
    return [
        {
            "nombre": col,
            "serie": df_conv[col],
            "eje": "y1",
            "modo": "markers",
            "color": _PALETA_EXTRA_SERIES[i % len(_PALETA_EXTRA_SERIES)],
        }
        for i, col in enumerate(columnas)
    ]
