"""
Detección de firmas de afectación AF-* sobre una serie individual.

Funciones puras: cada detector recibe una pd.Series con DatetimeIndex (ya
filtrada por flags, igual que el resto del proyecto) y devuelve un dict
{tipo, severidad, parametros, indices_afectados} o {} si no hay firma.

Principio rector del spec (docs/2026-07-13-rediseno-fase1-design.md): esto
SUGIERE, no dictamina — el AF-* final lo confirma el analista.

Las duraciones se configuran en minutos reales (config/afectaciones.yaml) y
se convierten a "pasos" usando la cadencia inferida EMPÍRICAMENTE de cada
serie (moda del Δt entre lecturas válidas consecutivas). Así no hace falta
adivinar si una variable es 10-min/horaria/diaria — eso varía por estación
y depende del catálogo SIGMA (ver spec §10.1, R5: no adivinar).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import yaml

from analizador_series.config import AFECTACIONES_YAML


# ══════════════════════════════════════════════════════════════════════════════
# Configuración (mismo patrón que series_derivadas._cargar_config)
# ══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _cargar_config() -> dict:
    if not AFECTACIONES_YAML.exists():
        return {}
    with open(AFECTACIONES_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def info_afectaciones(variable: str) -> dict:
    """
    Bloque de umbrales para una variable, con cada sub-bloque (cst/gap/miss/
    out/nois/bias) completado desde `_default` si la variable no define
    alguna clave.
    """
    cfg = _cargar_config()
    default = cfg.get("_default", {})
    bloque = cfg.get(variable, {})
    return {
        clave: {**default.get(clave, {}), **bloque.get(clave, {})}
        for clave in ("cst", "gap", "miss", "out", "nois", "bias")
    }


# ══════════════════════════════════════════════════════════════════════════════
# Utilidades: cadencia empírica y rachas booleanas
# ══════════════════════════════════════════════════════════════════════════════

def cadencia_inferida(serie: pd.Series) -> pd.Timedelta | None:
    """
    Moda del Δt entre lecturas VÁLIDAS consecutivas (ignora NaN). A
    diferencia de data_loader.frecuencia_inferida (que opera sobre toda una
    estación), esto se calcula por variable — una variable horaria en un
    archivo a 10 min debe inferir 1h, no 10min.
    """
    s = serie.dropna()
    if len(s) < 2:
        return None
    deltas = s.index.to_series().diff().dropna()
    if deltas.empty:
        return None
    moda = deltas.mode()
    return moda.iloc[0] if not moda.empty else None


def pct_lecturas_esperadas(serie: pd.Series) -> float:
    """
    % de lecturas recibidas frente a las esperadas según la frecuencia propia
    de la variable (cadencia_inferida), dentro de la ventana que cubre la
    serie (su índice completo, incluidas las filas vacías). Contar contra
    todas las filas del archivo daba 16,7 % a una variable horaria en una
    estación que también trae variables de 10 min (5 de cada 6 filas vacías).
    """
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if s.empty:
        return 0.0
    cad = cadencia_inferida(s)
    if cad is None or cad.total_seconds() <= 0:
        return 100.0
    ventana = serie.index.max() - serie.index.min()
    esperadas = int(ventana / cad) + 1
    return round(min(100.0, len(s) / esperadas * 100), 1)


def _duracion_a_pasos(duracion_min: float, cadencia: pd.Timedelta | None) -> int:
    """Convierte una duración en minutos a nº de pasos según la cadencia."""
    if cadencia is None or cadencia.total_seconds() <= 0:
        return 2
    pasos = duracion_min / (cadencia.total_seconds() / 60.0)
    return max(2, round(pasos))


def _racha_booleana_maxima(mask: pd.Series) -> tuple[int, pd.Index]:
    """Longitud e índice de la racha más larga de True consecutivos en `mask`."""
    if mask.empty or not mask.any():
        return 0, mask.index[:0]
    grupo_id = (mask != mask.shift()).cumsum()
    solo_true = grupo_id[mask]
    tam = solo_true.value_counts()
    mejor = tam.idxmax()
    idx = solo_true[solo_true == mejor].index
    return int(tam.max()), idx


# ══════════════════════════════════════════════════════════════════════════════
# AF-CST — racha de valores ~iguales sostenida (flatline / congelado)
# ══════════════════════════════════════════════════════════════════════════════

def detectar_cst(serie: pd.Series, duracion_min: float, duracion_alta_min: float,
                  tol: float = 0.0) -> dict:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if len(s) < 2:
        return {}
    cadencia = cadencia_inferida(serie)
    pasos_min = _duracion_a_pasos(duracion_min, cadencia)
    pasos_alta = _duracion_a_pasos(duracion_alta_min, cadencia)

    plano = s.diff().abs() <= tol   # primer elemento: diff NaN -> False
    largo, idx = _racha_booleana_maxima(plano)
    if largo < pasos_min:
        return {}

    severidad = "Alta" if largo >= pasos_alta else "Media"
    return {
        "tipo": "AF-CST",
        "severidad": severidad,
        "parametros": {
            "racha_pasos": largo,
            "cadencia_min": cadencia.total_seconds() / 60 if cadencia else None,
            "tol": tol,
        },
        "indices_afectados": idx,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AF-GAP / AF-MISS — huecos sobre la grilla ESPERADA de la propia variable
# ══════════════════════════════════════════════════════════════════════════════

def _grilla_esperada(serie: pd.Series, cadencia: pd.Timedelta) -> pd.DatetimeIndex:
    """
    Grilla que cubre todo el rango de `serie` (para no perder huecos al
    inicio/final — ej. estación que dejó de reportar antes del fin del
    periodo pedido), pero anclada en la FASE de las lecturas válidas, no en
    serie.index.min() crudo. Ese índice puede venir desfasado por otra
    variable con timestamps más finos en la misma fila fusionada (ej. una
    variable horaria mezclada en un archivo a 10 min cuyo primer timestamp de
    OTRA columna cae en :10/:20) — anclar mal la fase hace que TODOS los
    puntos válidos "no calcen" con la grilla y dispara GAP/MISS falsos sobre
    datos completos.
    """
    s_validos = serie.dropna()
    if s_validos.empty:
        return pd.DatetimeIndex([])
    ancla = s_validos.index.min()
    inicio_serie = serie.index.min()
    if inicio_serie < ancla:
        n_pasos_atras = int(np.ceil((ancla - inicio_serie) / cadencia))
        inicio_grilla = ancla - n_pasos_atras * cadencia
    else:
        inicio_grilla = ancla
    return pd.date_range(inicio_grilla, serie.index.max(), freq=cadencia)


def detectar_gap(serie: pd.Series, umbral_frac: float, umbral_alta_frac: float,
                  excluir_indices: pd.Index | None = None,
                  cadencia: pd.Timedelta | None = None) -> dict:
    s_validos = pd.to_numeric(serie, errors="coerce").dropna()
    if len(s_validos) < 2:
        return {}
    cadencia = cadencia if cadencia is not None else cadencia_inferida(serie)
    if cadencia is None or cadencia.total_seconds() <= 0:
        return {}

    grilla = _grilla_esperada(serie, cadencia)
    if excluir_indices is not None and len(excluir_indices):
        grilla = grilla.difference(pd.DatetimeIndex(excluir_indices))
    if len(grilla) == 0:
        return {}

    faltantes = grilla.difference(s_validos.index)
    frac = len(faltantes) / len(grilla)
    if frac < umbral_frac:
        return {}

    severidad = "Alta" if frac >= umbral_alta_frac else "Media"
    return {
        "tipo": "AF-GAP",
        "severidad": severidad,
        "parametros": {"frac_nan": float(frac), "cadencia_min": cadencia.total_seconds() / 60},
        "indices_afectados": faltantes,
    }


def detectar_miss(serie: pd.Series, umbral_pct: float, racha_min_horas: float,
                   cadencia: pd.Timedelta | None = None) -> dict:
    s_validos = pd.to_numeric(serie, errors="coerce").dropna()
    if s_validos.empty:
        return {
            "tipo": "AF-MISS", "severidad": "Alta",
            "parametros": {"frac_nan_total": 1.0, "racha_horas": None},
            "indices_afectados": serie.index,
        }
    if len(s_validos) < 2:
        return {}

    cadencia = cadencia if cadencia is not None else cadencia_inferida(serie)
    if cadencia is None or cadencia.total_seconds() <= 0:
        return {}

    grilla = _grilla_esperada(serie, cadencia)
    if len(grilla) == 0:
        return {}
    faltante_mask = pd.Series(~grilla.isin(s_validos.index), index=grilla)
    frac = faltante_mask.sum() / len(grilla)

    largo_pasos, idx_racha = _racha_booleana_maxima(faltante_mask)
    racha_horas = 0.0
    if largo_pasos > 0:
        racha_horas = (idx_racha.max() - idx_racha.min()).total_seconds() / 3600.0
        racha_horas += cadencia.total_seconds() / 3600.0   # incluir el último paso faltante

    if frac < umbral_pct and racha_horas < racha_min_horas:
        return {}

    indices_afectados = idx_racha if racha_horas >= racha_min_horas else grilla[faltante_mask]
    return {
        "tipo": "AF-MISS",
        "severidad": "Alta",
        "parametros": {"frac_nan_total": float(frac), "racha_horas": float(racha_horas)},
        "indices_afectados": indices_afectados,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AF-OUT — fuera de rango físico o salto excesivo entre lecturas
# ══════════════════════════════════════════════════════════════════════════════

def detectar_out(serie: pd.Series, rango_fisico: tuple | list | None = None,
                  delta_max: float | None = None) -> dict:
    s = pd.to_numeric(serie, errors="coerce")
    if s.dropna().empty:
        return {}

    fuera_rango = pd.Series(False, index=s.index)
    lo, hi = (rango_fisico or (None, None))
    if lo is not None:
        fuera_rango |= s < lo
    if hi is not None:
        fuera_rango |= s > hi
    fuera_rango &= s.notna()
    idx_rango = s.index[fuera_rango]

    idx_salto = pd.Index([])
    if delta_max is not None:
        s_validos = s.dropna()
        deltas = s_validos.diff().abs()
        idx_salto = deltas[deltas > delta_max].index

    if len(idx_rango) == 0 and len(idx_salto) == 0:
        return {}

    severidad = "Alta" if len(idx_rango) > 0 else "Media"
    idx_afectados = idx_rango.union(idx_salto)
    return {
        "tipo": "AF-OUT",
        "severidad": severidad,
        "parametros": {
            "n_fuera_rango": int(len(idx_rango)),
            "n_saltos": int(len(idx_salto)),
            "delta_max": delta_max,
        },
        "indices_afectados": idx_afectados,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AF-NOIS — dispersión anómala (z-score del rolling-std)
# ══════════════════════════════════════════════════════════════════════════════

def detectar_nois(serie: pd.Series, ventana_min: float, z_umbral: float,
                   z_umbral_alta: float, cadencia: pd.Timedelta | None = None) -> dict:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if len(s) < 6:
        return {}

    cadencia = cadencia if cadencia is not None else cadencia_inferida(serie)
    pasos = max(3, _duracion_a_pasos(ventana_min, cadencia))

    roll_std = s.rolling(pasos, min_periods=max(2, pasos // 2)).std()
    mu, sigma = roll_std.mean(), roll_std.std()
    if sigma is None or np.isnan(sigma) or sigma == 0:
        return {}

    z = (roll_std - mu) / sigma
    idx_alta = z[z >= z_umbral_alta].index
    idx_media = z[(z >= z_umbral) & (z < z_umbral_alta)].index
    if len(idx_alta) == 0 and len(idx_media) == 0:
        return {}

    severidad = "Alta" if len(idx_alta) > 0 else "Media"
    idx_afectados = idx_alta if severidad == "Alta" else idx_media
    return {
        "tipo": "AF-NOIS",
        "severidad": severidad,
        "parametros": {"z_max": float(z.max()), "ventana_pasos": pasos},
        "indices_afectados": idx_afectados,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AF-BIAS — change-point de nivel/tendencia (ruptures.Pelt)
# ══════════════════════════════════════════════════════════════════════════════

def detectar_bias(serie: pd.Series, penalizacion: float = 10.0,
                   min_size_min: float = 180, salto_alta: float | None = None,
                   cadencia: pd.Timedelta | None = None) -> dict:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    cadencia = cadencia if cadencia is not None else cadencia_inferida(serie)
    if cadencia is None or cadencia.total_seconds() <= 0:
        return {}

    min_size_pasos = _duracion_a_pasos(min_size_min, cadencia)
    if len(s) < 2 * min_size_pasos:
        return {}

    import ruptures as rpt
    algo = rpt.Pelt(model="rbf", min_size=min_size_pasos).fit(s.values)
    bkps = algo.predict(pen=penalizacion)
    bkps_reales = bkps[:-1]   # el último elemento de predict() es siempre len(s)
    if not bkps_reales:
        return {}

    idx_puntos = s.index[bkps_reales]
    segmentos = np.split(s.values, bkps_reales)
    medias = [seg.mean() for seg in segmentos if len(seg) > 0]
    saltos = [abs(medias[i + 1] - medias[i]) for i in range(len(medias) - 1)]
    salto_max = float(max(saltos)) if saltos else 0.0

    severidad = "Alta" if (salto_alta is not None and salto_max >= salto_alta) else "Media"
    return {
        "tipo": "AF-BIAS",
        "severidad": severidad,
        "parametros": {"n_puntos_cambio": len(bkps_reales), "salto_max": salto_max},
        "indices_afectados": idx_puntos,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Agregador
# ══════════════════════════════════════════════════════════════════════════════

def detectar_todas(serie: pd.Series, variable: str,
                    rango_fisico: tuple | list | None = None,
                    incluir_bias: bool = False) -> list[dict]:
    """
    Corre las 5 firmas baratas siempre (MISS primero, excluyendo sus índices
    del cálculo de GAP para no reportar dos firmas sobre el mismo hueco).
    AF-BIAS (ruptures) solo si incluir_bias=True — es la cara del grupo.
    """
    cfg = info_afectaciones(variable)
    cadencia = cadencia_inferida(serie)
    resultados = []

    r_miss = detectar_miss(serie, cadencia=cadencia, **cfg["miss"])
    if r_miss:
        resultados.append(r_miss)

    excluir = r_miss.get("indices_afectados") if r_miss else None
    r_gap = detectar_gap(serie, cadencia=cadencia, excluir_indices=excluir, **cfg["gap"])
    if r_gap:
        resultados.append(r_gap)

    r_cst = detectar_cst(serie, **cfg["cst"])
    if r_cst:
        resultados.append(r_cst)

    r_out = detectar_out(serie, rango_fisico=rango_fisico, delta_max=cfg["out"].get("delta_max"))
    if r_out:
        resultados.append(r_out)

    r_nois = detectar_nois(serie, cadencia=cadencia, **cfg["nois"])
    if r_nois:
        resultados.append(r_nois)

    if incluir_bias:
        r_bias = detectar_bias(serie, cadencia=cadencia, **cfg["bias"])
        if r_bias:
            resultados.append(r_bias)

    return resultados
