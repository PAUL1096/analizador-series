"""
Emplazamiento compartido — pares co-ubicados automática↔convencional (<umbral_m) y equivalencia
de variables físicas entre ambas, para la pestaña "Emplazamiento compartido" (inspección visual,
sin estadística de comparación — fuera del alcance de esta herramienta. Ver
docs/SPEC-emplazamiento-compartido.md).

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

_OFFSET_DIARIA = pd.Timedelta(hours=12)

# Clasificaciones hidrológicas (columna `clasificacion` de estaciones.db): no se
# comparan — decisión del usuario 2026-10-09. EHMA (hidrometeorológica
# automática) NO está acá a propósito: mide variables meteorológicas y se
# compara con su convencional meteorológica (ej. PLU).
CLASIFICACIONES_EXCLUIDAS = frozenset({"EHA", "HLG", "HLM"})

# Catálogo oficial de SIGMA (confirmado en Análisis -> DataMonitor, 2026-09-30,
# ver tasks/todo.md) — cada columna convencional es "diaria" (máx/mín/total del
# día, sin hora puntual real) o "puntual" (lectura exacta a una hora sinóptica:
# 07h/13h/19h). La distinción importa para dónde se dibuja el punto (Task de
# alineación temporal) y para qué columnas admiten diferencia contra la
# automática (solo "puntual" — ver calcular_diferencias_puntuales).
EQUIVALENCIA_VARIABLES: dict[str, dict] = {
    "temperatura": {
        "automatica": "n_airtemp",
        # Extremos diarios REALES de la automática (no calculados por emplazamiento compartido)
        # — mismo espíritu que n_tm102/103 de la convencional. Si faltan, hay
        # respaldo calculado desde n_airtemp (ver calcular_extremos_diarios_automatica).
        "automatica_extremos_diarios": {"maxima": "n_maxat", "minima": "n_minat"},
        # Respaldo si falta lo diario: "el máximo/mínimo de los
        # máximos/mínimos agregados" (instrucción literal del usuario) — el
        # pico/valle que la automática ya agrega POR HORA (n_maxath/n_minath),
        # tomando el extremo de esos valores a lo largo del día. Verificado
        # con datos reales en 104114 (que tiene n_maxath pero no n_maxat):
        # max(n_maxath) del día = 18.8°C, capta un pico real que
        # max(n_airtemp) = 16.6°C se pierde — por eso NUNCA se usa n_airtemp
        # como respaldo, aunque sea tentador, no es lo que se pidió.
        "automatica_extremos_horarios_agregados": {"maxima": "n_maxath", "minima": "n_minath"},
        "convencional": {
            "n_tm102": {"etiqueta": "Máxima diaria", "tipo": "diaria", "extremo": "maxima"},
            "n_tm103": {"etiqueta": "Mínima diaria", "tipo": "diaria", "extremo": "minima"},
            "n_tm104": {"etiqueta": "07h", "tipo": "puntual", "hora": "07:00"},
            "n_tm105": {"etiqueta": "13h", "tipo": "puntual", "hora": "13:00"},
            "n_tm106": {"etiqueta": "19h", "tipo": "puntual", "hora": "19:00"},
        },
        "etiqueta": "Temperatura",
    },
    "precipitacion": {
        "automatica": "n_lluvia",
        # Acumulado diario REAL de la automática (día meteorológico 07h->07h,
        # mismo cierre que usa SIGMA para n_pt101/n_dayrain — verificado con
        # datos reales, ver tasks/todo.md). Si falta, respaldo calculado
        # sumando n_lluvia en esa ventana (ver calcular_acumulado_diario_automatica).
        "automatica_diaria": "n_dayrain",
        "convencional": {
            # OJO — n_pt101 tiene un desfase de etiqueta real, verificado con
            # datos reales (21/21 casos en 106077): SIGMA lo fecha con el día
            # que EMPIEZA la ventana nocturna (pt103[D] + pt102[D+1] = pt101[D]),
            # no el que la cierra. n_dayrain de la automática, en cambio, se
            # fecha con el día que CIERRA (07:00 de ese día). Para comparar el
            # mismo período físico hay que correr pt101 un día hacia adelante
            # (ver calcular_diferencias_precipitacion_diaria).
            "n_pt101": {"etiqueta": "Total diaria", "tipo": "diaria", "desfase_dias_cierre": 1},
            "n_pt102": {"etiqueta": "07h (nocturna 19h→07h)", "tipo": "puntual",
                        "hora": "07:00", "ventana": "nocturna"},
            "n_pt103": {"etiqueta": "19h (diurna 07h→19h)", "tipo": "puntual",
                        "hora": "19:00", "ventana": "diurna"},
        },
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
    completa para que el usuario filtre en la UI. Excluye estaciones
    hidrológicas (ver CLASIFICACIONES_EXCLUIDAS).
    """
    con = sqlite3.connect(ruta_db)
    try:
        filas = con.execute(
            "SELECT codigo, categoria, latitud, longitud, clasificacion FROM estaciones "
            "WHERE latitud IS NOT NULL AND longitud IS NOT NULL"
        ).fetchall()
    finally:
        con.close()

    filas = [f[:4] for f in filas if (f[4] or "").upper() not in CLASIFICACIONES_EXCLUIDAS]
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

    Cada punto se desplaza de medianoche (como viene el CSV, un registro por
    día) a la hora real que representa: "puntual" -> su hora sinóptica exacta
    (cae sobre el tramo correcto de la curva continua de la automática);
    "diaria" -> mediodía, con símbolo distinto (diamante) para no insinuar que
    es una lectura de una hora puntual.
    """
    if df_conv.empty:
        return []
    columnas = columnas_convencionales_disponibles(variable_fisica, list(df_conv.columns))
    # No alcanza con que la columna EXISTA — si está pero sin ningún valor
    # real en el periodo, no debe quedar una traza fantasma en la leyenda sin
    # puntos visibles (feedback real del usuario, ver tasks/todo.md).
    columnas = [c for c in columnas if df_conv[c].notna().any()]
    metadata = EQUIVALENCIA_VARIABLES[variable_fisica]["convencional"]
    extra = []
    for i, col in enumerate(columnas):
        meta = metadata[col]
        serie = df_conv[col].copy()
        if meta["tipo"] == "puntual":
            serie.index = serie.index + pd.to_timedelta(meta["hora"] + ":00")
            symbol = "circle"
        else:
            serie.index = serie.index + _OFFSET_DIARIA
            symbol = "diamond"
        extra.append({
            "nombre": meta["etiqueta"],
            "columna": col,
            "tipo": meta["tipo"],
            "serie": serie,
            "eje": "y1",
            "modo": "markers",
            "color": _PALETA_EXTRA_SERIES[i % len(_PALETA_EXTRA_SERIES)],
            "symbol": symbol,
        })
    return extra


def calcular_diferencias_puntuales(
    serie_automatica: pd.Series, df_conv: pd.DataFrame, variable_fisica: str
) -> dict[str, pd.Series]:
    """
    {columna: pd.Series[convencional - automática]} SOLO para columnas
    "puntual" (07h/13h/19h) — el instante exacto de esa hora tiene un valor
    real de la automática con el que comparar directo, sin calcular nada.

    Las "diaria" (máx/mín/total) NUNCA generan diferencia acá: eso exigiría
    que emplazamiento compartido calculara su propio agregado diario de la automática, y esa
    rigurosidad queda fuera de esta herramienta (límite explícito de
    docs/SPEC-emplazamiento-compartido.md, confirmado con el usuario).
    """
    if df_conv.empty or serie_automatica.empty:
        return {}
    columnas = columnas_convencionales_disponibles(variable_fisica, list(df_conv.columns))
    metadata = EQUIVALENCIA_VARIABLES[variable_fisica]["convencional"]
    resultado = {}
    for col in columnas:
        meta = metadata[col]
        if meta["tipo"] != "puntual":
            continue
        idx_desplazado = df_conv.index + pd.to_timedelta(meta["hora"] + ":00")
        valores_conv = pd.Series(df_conv[col].to_numpy(), index=idx_desplazado)
        valores_auto = serie_automatica.reindex(idx_desplazado)
        resultado[col] = (valores_conv - valores_auto).dropna()
    return resultado


def _serie_diaria_normalizada(serie_cruda: pd.Series) -> pd.Series:
    """Un valor por día calendario (el primero si hay más de uno), índice
    normalizado a mediodía — mismo punto de referencia que usa la convencional
    para sus columnas "diaria" (ver armar_extra_series_convencional)."""
    s = serie_cruda.dropna()
    por_dia = s.groupby(s.index.normalize()).first()
    return pd.Series(por_dia.to_numpy(), index=por_dia.index + _OFFSET_DIARIA)


def calcular_extremos_diarios_automatica(df_auto: pd.DataFrame) -> dict:
    """
    {"maxima": {"serie","calculado"} | None, "minima": {...} | None} — 3
    niveles exactos (instrucción literal del usuario, ver tasks/todo.md
    Ronda 2):
      1. n_maxat/n_minat REAL (diario, reportado por SIGMA) si existe.
      2. Si no, "el máximo/mínimo de los máximos/mínimos agregados":
         n_maxath/n_minath (el pico/valle que la automática ya agrega POR
         HORA), tomando el extremo de esos valores a lo largo del día —
         marcado "calculado": True.
      3. Si tampoco existe eso, None. NUNCA se calcula desde n_airtemp (esa
         lectura puntual subestima picos intra-hora — ver docstring del
         diccionario EQUIVALENCIA_VARIABLES, verificado con datos reales).
    """
    reales = EQUIVALENCIA_VARIABLES["temperatura"]["automatica_extremos_diarios"]
    horarios_agregados = EQUIVALENCIA_VARIABLES["temperatura"]["automatica_extremos_horarios_agregados"]
    resultado = {}
    for clave, col_real in reales.items():
        if col_real in df_auto.columns and df_auto[col_real].notna().any():
            resultado[clave] = {"serie": _serie_diaria_normalizada(df_auto[col_real]), "calculado": False}
            continue
        col_horario = horarios_agregados[clave]
        if col_horario in df_auto.columns and df_auto[col_horario].notna().any():
            agg = "max" if clave == "maxima" else "min"
            diario = df_auto[col_horario].dropna().resample("D").agg(agg).dropna()
            diario.index = diario.index + _OFFSET_DIARIA
            resultado[clave] = {"serie": diario, "calculado": True}
        else:
            resultado[clave] = None
    return resultado


def calcular_diferencias_diarias_temperatura(
    df_auto: pd.DataFrame, df_conv: pd.DataFrame
) -> dict[str, pd.Series]:
    """
    {"n_tm102": serie, "n_tm103": serie} — convencional menos automática, por
    día calendario. Usa la misma fuente (real o calculada) que
    calcular_extremos_diarios_automatica; si esa fuente no existe para algún
    extremo, esa columna simplemente no aparece (sin error).
    """
    if df_conv.empty or df_auto.empty:
        return {}
    extremos = calcular_extremos_diarios_automatica(df_auto)
    metadata = EQUIVALENCIA_VARIABLES["temperatura"]["convencional"]
    resultado = {}
    for col, meta in metadata.items():
        if meta["tipo"] != "diaria" or col not in df_conv.columns:
            continue
        fuente = extremos.get(meta["extremo"])
        if fuente is None:
            continue
        serie_conv = _serie_diaria_normalizada(df_conv[col])
        serie_auto = fuente["serie"].reindex(serie_conv.index)
        diff = (serie_conv - serie_auto).dropna()
        if not diff.empty:
            resultado[col] = diff
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# Precipitación — acumulado diario y ventaneo 07h/19h.
#
# Hallazgo real (verificado con datos reales, 21/21 casos en 106077): SIGMA
# fecha n_pt101 con el día que EMPIEZA la ventana nocturna
# (n_pt103[D] + n_pt102[D+1] = n_pt101[D]), pero n_dayrain de la automática se
# fecha con el día que la CIERRA (07:00 de ese día). Para comparar el mismo
# período físico hay que correr n_pt101 un día hacia adelante antes de restar
# — ver "desfase_dias_cierre" en EQUIVALENCIA_VARIABLES.
# ══════════════════════════════════════════════════════════════════════════════

def _sumar_ventana_07_07(serie_horaria: pd.Series) -> pd.Series:
    """
    Suma serie_horaria en ventanas de 24h que cierran a las 07:00 de cada
    día — el mismo "día meteorológico" que usa SIGMA para n_dayrain (ver
    tasks/todo.md, Ronda 2: verificado 1.00 calculado vs. 1.1 reportado).
    Lecturas en punto representan la hora anterior.
    """
    s = serie_horaria.dropna()
    if s.empty:
        return s
    pertenece_al_dia_siguiente = s.index.hour >= 8
    claves = pd.Series(s.index.normalize(), index=s.index)
    claves[pertenece_al_dia_siguiente] += pd.Timedelta(days=1)
    claves = claves + pd.Timedelta(hours=7)
    return s.groupby(claves.to_numpy()).sum()


def _sumar_ventana_diurna(serie_horaria: pd.Series) -> pd.Series:
    """Suma 07:01->19:00 del mismo día (no cruza medianoche)."""
    s = serie_horaria.dropna()
    if s.empty:
        return s
    dentro = (s.index.hour >= 8) & (s.index.hour <= 19)
    ventana = s[dentro]
    claves = ventana.index.normalize() + pd.Timedelta(hours=19)
    return ventana.groupby(claves).sum()


def _sumar_ventana_nocturna(serie_horaria: pd.Series) -> pd.Series:
    """Suma 19:01(D)->07:00(D+1), etiquetada con la fecha+07:00 de cierre."""
    s = serie_horaria.dropna()
    if s.empty:
        return s
    dentro = (s.index.hour >= 20) | (s.index.hour <= 7)
    ventana = s[dentro]
    pertenece_al_dia_siguiente = ventana.index.hour >= 20
    claves = pd.Series(ventana.index.normalize(), index=ventana.index)
    claves[pertenece_al_dia_siguiente] += pd.Timedelta(days=1)
    claves = claves + pd.Timedelta(hours=7)
    return ventana.groupby(claves.to_numpy()).sum()


def calcular_acumulado_diario_automatica(df_auto: pd.DataFrame) -> dict | None:
    """
    {"serie","calculado"} — acumulado diario de la automática (día
    meteorológico 07h->07h). Usa n_dayrain REAL (reportado por SIGMA) si
    existe; si falta, respaldo sumando n_lluvia en esa misma ventana, marcado
    "calculado": True (excepción acotada, ver calcular_extremos_diarios_automatica).
    """
    col_real = EQUIVALENCIA_VARIABLES["precipitacion"]["automatica_diaria"]
    if col_real in df_auto.columns and df_auto[col_real].notna().any():
        crudo = df_auto[col_real].dropna()
        crudo = crudo[~crudo.index.normalize().duplicated()]
        return {"serie": crudo, "calculado": False}
    col_horaria = EQUIVALENCIA_VARIABLES["precipitacion"]["automatica"]
    if col_horaria in df_auto.columns and df_auto[col_horaria].notna().any():
        return {"serie": _sumar_ventana_07_07(df_auto[col_horaria]), "calculado": True}
    return None


def calcular_diferencias_precipitacion_diaria(
    df_auto: pd.DataFrame, df_conv: pd.DataFrame
) -> pd.Series | None:
    """
    pd.Series[convencional - automática], acumulado diario — corrige el
    desfase de fecha de n_pt101 (ver docstring de esta sección) antes de
    restar contra el acumulado real/calculado de la automática.
    """
    if "n_pt101" not in df_conv.columns:
        return None
    acumulado = calcular_acumulado_diario_automatica(df_auto)
    if acumulado is None:
        return None

    desfase = EQUIVALENCIA_VARIABLES["precipitacion"]["convencional"]["n_pt101"]["desfase_dias_cierre"]
    crudo_conv = df_conv["n_pt101"].dropna()
    crudo_conv = crudo_conv[~crudo_conv.index.normalize().duplicated()]
    idx_alineado = crudo_conv.index.normalize() + pd.Timedelta(days=desfase)
    valores_conv = pd.Series(crudo_conv.to_numpy(), index=idx_alineado)

    serie_auto = acumulado["serie"]
    valores_auto = pd.Series(serie_auto.to_numpy(), index=serie_auto.index.normalize())

    diff = (valores_conv - valores_auto.reindex(valores_conv.index)).dropna()
    return diff if not diff.empty else None


def calcular_ventaneo_automatica(df_auto: pd.DataFrame) -> dict[str, pd.Series]:
    """
    {"diurna": serie, "nocturna": serie} — sumas de n_lluvia en las ventanas
    07h->19h y 19h->07h, para comparar contra n_pt103/n_pt102. Cálculo propio
    del Analizador (no un estudio estadístico formal) —
    autorizado explícitamente por el usuario tras confirmar la física real
    del proceso de observación convencional (ver tasks/todo.md, Ronda 2).
    """
    col = EQUIVALENCIA_VARIABLES["precipitacion"]["automatica"]
    if col not in df_auto.columns:
        vacio = pd.Series(dtype=float)
        return {"diurna": vacio, "nocturna": vacio}
    serie = df_auto[col]
    return {"diurna": _sumar_ventana_diurna(serie), "nocturna": _sumar_ventana_nocturna(serie)}


def calcular_diferencias_precipitacion_ventaneo(
    df_auto: pd.DataFrame, df_conv: pd.DataFrame
) -> dict[str, pd.Series]:
    """{"n_pt102": serie, "n_pt103": serie} — convencional menos la suma de
    la automática en la ventana correspondiente (ver calcular_ventaneo_automatica)."""
    if df_conv.empty:
        return {}
    ventaneo = calcular_ventaneo_automatica(df_auto)
    metadata = EQUIVALENCIA_VARIABLES["precipitacion"]["convencional"]
    resultado = {}
    for col, meta in metadata.items():
        ventana = meta.get("ventana")
        if ventana is None or col not in df_conv.columns:
            continue
        serie_auto = ventaneo.get(ventana)
        if serie_auto is None or serie_auto.empty:
            continue
        idx_desplazado = df_conv.index + pd.to_timedelta(meta["hora"] + ":00")
        valores_conv = pd.Series(df_conv[col].to_numpy(), index=idx_desplazado)
        diff = (valores_conv - serie_auto.reindex(idx_desplazado)).dropna()
        if not diff.empty:
            resultado[col] = diff
    return resultado
