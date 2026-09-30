"""
Agregación del índice de triaje de la pestaña Panorama.

Por cada (estación, variable) corre core.deteccion_afectaciones.detectar_todas
y resume en una fila de tabla. Distingue "variable no medida por la estación"
(N/D — no se llama al detector) de "medida pero sin firma" (OK) o "medida con
firma real" (Media/Alta). Funciones puras, sin Dash.
"""
from __future__ import annotations

import pandas as pd

from analizador_series.core import deteccion_afectaciones


_RANK_SEVERIDAD = {"Alta": 0, "Media": 1, "OK": 2, "N/D": 3}


def _texto_cadencia(cadencia: pd.Timedelta | None) -> str:
    if cadencia is None:
        return "—"
    mins = cadencia.total_seconds() / 60
    if mins < 60:
        return f"{mins:.0f} min"
    if mins < 1440:
        return f"{mins / 60:.0f} h"
    return f"{mins / 1440:.0f} d"


def resumen_fila(serie: pd.Series, variable: str,
                  rango_fisico: tuple | list | None = None,
                  incluir_bias: bool = False) -> dict:
    """Fila del índice para una variable que la estación SÍ mide."""
    n_total = len(serie)
    n_validos = int(pd.to_numeric(serie, errors="coerce").notna().sum())
    pct_validos = round(n_validos / n_total * 100, 1) if n_total else 0.0

    firmas = deteccion_afectaciones.detectar_todas(
        serie, variable, rango_fisico=rango_fisico, incluir_bias=incluir_bias,
    )
    if firmas:
        peor = min(firmas, key=lambda f: _RANK_SEVERIDAD.get(f["severidad"], 2))
        severidad = peor["severidad"]
        firma_txt = " · ".join(f["tipo"] for f in firmas)
    else:
        severidad, firma_txt = "OK", "sin firma"

    return {
        "severidad": severidad,
        "severidad_rank": _RANK_SEVERIDAD[severidad],
        "firma": firma_txt,
        "pct_validos": pct_validos,
        "cadencia": _texto_cadencia(deteccion_afectaciones.cadencia_inferida(serie)),
    }


def fila_no_medida() -> dict:
    """Fila del índice para una variable que la estación NO mide (no confundir con MISS)."""
    return {
        "severidad": "N/D",
        "severidad_rank": _RANK_SEVERIDAD["N/D"],
        "firma": "variable no medida por esta estación",
        "pct_validos": None,
        "cadencia": "—",
    }


def construir_indice_triaje(df_crudo: pd.DataFrame, variables: list[str],
                             rangos_fisicos: dict, display_names: dict,
                             nombres_estacion: dict, variables_propias: dict,
                             incluir_bias: bool = False) -> list[dict]:
    """
    Una fila por (estación, variable) presente en df_crudo (indexado por
    'codigo' + 'datetime'). Pre-ordenada por severidad (Alta<Media<OK<N/D).
    """
    filas = []
    for cod, grp in df_crudo.groupby("codigo"):
        grp = grp.sort_values("datetime").set_index("datetime")
        propias = variables_propias.get(cod, set())
        for var in variables:
            if var not in grp.columns:
                continue
            if var in propias:
                resumen = resumen_fila(grp[var], var, rangos_fisicos.get(var), incluir_bias)
            else:
                resumen = fila_no_medida()
            resumen.update({
                "codigo": cod,
                "estacion": nombres_estacion.get(cod, cod),
                "variable": var,
                "variable_label": display_names.get(var, var),
            })
            filas.append(resumen)

    filas.sort(key=lambda f: (f["severidad_rank"], f["variable_label"], f["estacion"]))
    return filas
