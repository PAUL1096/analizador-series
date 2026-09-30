"""
Chequeos de consistencia cruzada entre variables (pestaña Comparar del
spec — docs/2026-07-13-rediseno-fase1-design.md §4.2).

Funciones puras: reciben pd.Series (con DatetimeIndex, ya filtradas por
flags) y devuelven {violacion, pct_violacion, veredicto, ...}. Sugieren
incoherencias — el AF-* final lo confirma el analista, igual que en
core.deteccion_afectaciones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analizador_series.core.deteccion_afectaciones import detectar_cst


# ══════════════════════════════════════════════════════════════════════════════
# Punto de rocío (Magnus, WMO — equivale a Bolton-1980 de MetPy)
# ══════════════════════════════════════════════════════════════════════════════

def punto_de_rocio(t, hr):
    """
    Td (°C) a partir de T (°C) y HR (%). Acepta escalares o pd.Series.
    g = ln(hr/100) + 17.62*t/(243.12+t) ; Td = 243.12*g/(17.62-g)
    """
    t = np.asarray(t, dtype=float) if not isinstance(t, pd.Series) else t.astype(float)
    hr = np.asarray(hr, dtype=float) if not isinstance(hr, pd.Series) else hr.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.log(hr / 100.0) + 17.62 * t / (243.12 + t)
        td = 243.12 * g / (17.62 - g)
    return td


# ══════════════════════════════════════════════════════════════════════════════
# Preset: T vs T-rocío — Td > T es físicamente imposible
# ══════════════════════════════════════════════════════════════════════════════

def chequeo_temp_rocio(t: pd.Series, hr: pd.Series, tol: float = 0.5) -> dict:
    t_n = pd.to_numeric(t, errors="coerce")
    hr_n = pd.to_numeric(hr, errors="coerce")
    validos = t_n.notna() & hr_n.notna()
    if not validos.any():
        return {"violacion": t_n.index[:0], "pct_violacion": 0.0, "veredicto": "Sin datos suficientes"}

    td = pd.Series(punto_de_rocio(t_n, hr_n), index=t_n.index)
    violacion_mask = validos & (td > (t_n + tol))
    n_validos = int(validos.sum())
    pct = float(violacion_mask.sum() / n_validos * 100) if n_validos else 0.0
    veredicto = (
        f"{pct:.1f}% de puntos con T-rocío > T (físicamente imposible) — sugiere AF-OUT/AF-BIAS"
        if pct > 0 else "Sin violaciones: T-rocío ≤ T en todos los puntos válidos"
    )
    return {"violacion": t_n.index[violacion_mask], "pct_violacion": pct, "veredicto": veredicto}


# ══════════════════════════════════════════════════════════════════════════════
# Preset: HR vs Lluvia — HR saturada sin lluvia / lluvia con HR baja
# ══════════════════════════════════════════════════════════════════════════════

def chequeo_hr_lluvia(hr: pd.Series, lluvia: pd.Series,
                       umbral_hr_saturado: float = 98.0,
                       umbral_hr_bajo: float = 60.0) -> dict:
    hr_n = pd.to_numeric(hr, errors="coerce")
    ll_n = pd.to_numeric(lluvia, errors="coerce")
    validos = hr_n.notna() & ll_n.notna()
    if not validos.any():
        return {"violacion": hr_n.index[:0], "pct_violacion": 0.0, "veredicto": "Sin datos suficientes"}

    hr_saturada_sin_lluvia = validos & (hr_n >= umbral_hr_saturado) & (ll_n <= 0)
    lluvia_con_hr_baja = validos & (ll_n > 0) & (hr_n < umbral_hr_bajo)
    violacion_mask = hr_saturada_sin_lluvia | lluvia_con_hr_baja

    n_validos = int(validos.sum())
    pct = float(violacion_mask.sum() / n_validos * 100) if n_validos else 0.0
    n_sat = int(hr_saturada_sin_lluvia.sum())
    n_baja = int(lluvia_con_hr_baja.sum())
    veredicto = (
        f"HR≥{umbral_hr_saturado:.0f}% sin lluvia: {n_sat} puntos (posible AF-CST en HR) · "
        f"lluvia con HR<{umbral_hr_bajo:.0f}%: {n_baja} puntos (incoherencia)"
        if (n_sat or n_baja) else "Sin incoherencias HR/lluvia detectadas"
    )
    return {
        "violacion": hr_n.index[violacion_mask], "pct_violacion": pct, "veredicto": veredicto,
        "n_hr_saturada_sin_lluvia": n_sat, "n_lluvia_con_hr_baja": n_baja,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Preset: Viento vel/dir — veleta trabada (dirección constante con viento)
# ══════════════════════════════════════════════════════════════════════════════

def chequeo_veleta_trabada(direccion: pd.Series, velocidad: pd.Series,
                            duracion_min: float = 60, duracion_alta_min: float = 360,
                            vel_min: float = 0.5, tol_direccion: float = 0.0) -> dict:
    resultado_cst = detectar_cst(direccion, duracion_min=duracion_min,
                                  duracion_alta_min=duracion_alta_min, tol=tol_direccion)
    if not resultado_cst:
        return {"violacion": direccion.index[:0], "pct_violacion": 0.0,
                "veredicto": "Sin racha de dirección constante"}

    idx_racha = resultado_cst["indices_afectados"]
    vel_n = pd.to_numeric(velocidad, errors="coerce")
    vel_en_racha = vel_n.reindex(idx_racha)
    idx_con_viento = vel_en_racha[vel_en_racha > vel_min].index

    if len(idx_con_viento) == 0:
        return {"violacion": direccion.index[:0], "pct_violacion": 0.0,
                "veredicto": "Dirección constante pero con viento calmo — no es veleta trabada"}

    pct = float(len(idx_con_viento) / resultado_cst["parametros"]["racha_pasos"] * 100)
    veredicto = (
        f"Dirección constante ({resultado_cst['severidad']}) con viento > {vel_min} m/s en "
        f"{len(idx_con_viento)} puntos — sugiere veleta trabada (AF-CST en dirección)"
    )
    return {"violacion": idx_con_viento, "pct_violacion": pct, "veredicto": veredicto,
            "severidad_direccion": resultado_cst["severidad"]}


# ══════════════════════════════════════════════════════════════════════════════
# Preset: Tmax/Tmin/T — T fuera del rango diario, o Tmax < Tmin
# ══════════════════════════════════════════════════════════════════════════════

def chequeo_tmax_tmin_t(t: pd.Series, tmax_diario: pd.Series, tmin_diario: pd.Series,
                         tol: float = 0.3) -> dict:
    t_n = pd.to_numeric(t, errors="coerce").dropna()
    if t_n.empty:
        return {"violacion": t_n.index[:0], "pct_violacion": 0.0,
                "veredicto": "Sin datos suficientes", "dias_tmax_menor_tmin": 0}

    tmax_por_dia = pd.to_numeric(tmax_diario, errors="coerce").dropna()
    tmin_por_dia = pd.to_numeric(tmin_diario, errors="coerce").dropna()
    tmax_por_dia.index = tmax_por_dia.index.normalize()
    tmin_por_dia.index = tmin_por_dia.index.normalize()
    tmax_por_dia = tmax_por_dia.groupby(level=0).first()
    tmin_por_dia = tmin_por_dia.groupby(level=0).first()

    dias_t = pd.Series(t_n.index.normalize(), index=t_n.index)
    tmax_asignado = dias_t.map(tmax_por_dia)
    tmin_asignado = dias_t.map(tmin_por_dia)

    excede_max = (t_n > (tmax_asignado + tol)).fillna(False)
    excede_min = (t_n < (tmin_asignado - tol)).fillna(False)
    violacion_mask = excede_max | excede_min

    validos = tmax_asignado.notna() | tmin_asignado.notna()
    n_validos = int(validos.sum())
    pct = float(violacion_mask[validos].sum() / n_validos * 100) if n_validos else 0.0

    comunes = tmax_por_dia.index.intersection(tmin_por_dia.index)
    dias_invertidos = int((tmax_por_dia.loc[comunes] < tmin_por_dia.loc[comunes]).sum())

    partes = []
    if pct > 0:
        partes.append(f"{pct:.1f}% de T fuera de [Tmin,Tmax] del día (± {tol})")
    if dias_invertidos > 0:
        partes.append(f"{dias_invertidos} día(s) con Tmax < Tmin (reporte inconsistente)")
    veredicto = " · ".join(partes) if partes else "T dentro de [Tmin, Tmax] en todos los días"

    return {
        "violacion": t_n.index[violacion_mask], "pct_violacion": pct, "veredicto": veredicto,
        "dias_tmax_menor_tmin": dias_invertidos,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Presets de la pestaña Comparar: rol -> candidatos de columna, por preferencia.
# Se toma el primero presente en las columnas de la estación elegida; si
# ninguno está, el rol queda sin resolver (mensaje claro en la UI, no error).
# NO se mezcla n_maxat/n_minat (Tmax/Tmin DIARIA) con n_maxath/n_minath
# (máx/mín HORARIA — magnitud distinta, confirmado contra datos reales).
#
# t/hr: se prefiere la variable SIN sufijo (n_airtemp, n_humedad) sobre su
# par "_inst" — al revés de como estaba antes. Motivo: no es una elección de
# cadencia (ambas llegan horarias, verificado con datos reales de varias
# estaciones — ver nota en config/series_disponibles.yaml junto a
# n_airtemp) sino de cuál conviene para un chequeo de consistencia. Evidencia
# a favor de la variable sin sufijo, re-derivada de datos reales (no
# asumida): en 3 de 4 estaciones probadas (103068, 104114, y HR en 472FB328)
# es la más "suave" (menor std de la diferencia paso-a-paso) — consistente
# con ser la agregada/promedio, más apta para un chequeo de consistencia
# porque diluye ruido de instrumento en vez de amplificarlo. Esto coincide
# con la práctica general de QC meteorológico (comparar contra el valor
# archivado/oficial, no contra la lectura puntual más ruidosa — ver
# docs/referencias_qc_comunidad.md). SIGUE PENDIENTE la confirmación
# definitiva del equipo que mantiene el catálogo SIGMA (R5, sin resolver por
# código) — si ese catálogo dice lo contrario, invertir de nuevo.
# ══════════════════════════════════════════════════════════════════════════════

PRESETS = {
    "temp_rocio": {
        "label": "T vs T-rocío",
        "fn": "chequeo_temp_rocio",
        "roles": {
            "t": ["n_airtemp", "n_airtemp_inst"],
            "hr": ["n_humedad", "n_humedad_inst"],
        },
    },
    "hr_lluvia": {
        "label": "HR vs Lluvia",
        "fn": "chequeo_hr_lluvia",
        "roles": {
            "hr": ["n_humedad", "n_humedad_inst"],
            "lluvia": ["n_lluvia", "n_rain_10m"],
        },
    },
    "veleta": {
        "label": "Viento vel/dir",
        "fn": "chequeo_veleta_trabada",
        "roles": {
            "direccion": ["n_dirviento", "n_dirviento_inst"],
            "velocidad": ["n_velviento", "n_velviento_inst"],
        },
    },
    "tmax_tmin": {
        "label": "Tmax/Tmin/T",
        "fn": "chequeo_tmax_tmin_t",
        "roles": {
            "t": ["n_airtemp", "n_airtemp_inst"],
            "tmax": ["n_maxat"],
            "tmin": ["n_minat"],
        },
    },
}


def resolver_variables(preset_id: str, columnas_disponibles: set[str]) -> dict[str, str | None]:
    """Para cada rol del preset, la primera columna candidata presente en `columnas_disponibles`."""
    spec = PRESETS.get(preset_id, {})
    return {
        rol: next((c for c in candidatos if c in columnas_disponibles), None)
        for rol, candidatos in spec.get("roles", {}).items()
    }


def roles_faltantes(resueltas: dict[str, str | None]) -> list[str]:
    return [rol for rol, col in resueltas.items() if col is None]


def ejecutar_preset(preset_id: str, series: dict[str, pd.Series]) -> dict:
    """Despacha a la función de chequeo correspondiente con las series ya resueltas por rol."""
    spec = PRESETS.get(preset_id)
    if not spec:
        return {}
    fn = globals()[spec["fn"]]
    if preset_id == "temp_rocio":
        return fn(series["t"], series["hr"])
    if preset_id == "hr_lluvia":
        return fn(series["hr"], series["lluvia"])
    if preset_id == "veleta":
        return fn(series["direccion"], series["velocidad"])
    if preset_id == "tmax_tmin":
        return fn(series["t"], series["tmax"], series["tmin"])
    return {}
