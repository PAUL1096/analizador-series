"""
Callbacks Dash del Analizador de Series.

Patrón general:
  - El usuario elige estaciones → se cargan los datos y se infieren variables
  - El usuario elige variable → se cargan las series derivadas disponibles del YAML
  - Cuando hay estaciones + variable + periodo + series tildadas → se calcula todo
"""
from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime

import numpy as np
import pandas as pd
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, no_update, dash_table, html, dcc

from analizador_series.config import COLOR_FLAG
from analizador_series.core import (
    control_calidad, data_loader, series_derivadas, distribuciones, detector_eventos,
    deteccion_afectaciones, consistencia, panorama, dias_efectivos, emplazamiento,
)
from analizador_series.ui import (
    charts, tab_estadistica, tab_panorama, tab_comparar, tab_crudo, tab_emplazamiento,
)


# ══════════════════════════════════════════════════════════════════════════════
# Caché de consulta para store-datos-crudos: dcc.Store viaja como JSON entre
# navegador y servidor en CADA callback que lo usa como Input/State — con
# series largas (años a 10 min, muchas variables) ese round-trip de TODO el
# dataset es en sí mismo lento, aparte de la lectura en disco. En vez de
# guardar los registros en el Store, se guarda una "receta" chica (códigos +
# periodo + flags) y el DataFrame real vive en este dict de servidor. Si la
# entrada fue desalojada (LRU) o el servidor se reinició, se recalcula sola
# — nunca puede devolver un resultado incorrecto, solo más lento esa vez.
# ══════════════════════════════════════════════════════════════════════════════

_CACHE_CONSULTAS: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
_CACHE_CONSULTAS_MAXSIZE = 12


def _clave_consulta(codigos, start_date, end_date, flags_incluidos, cc_incluidos) -> tuple:
    return (
        tuple(sorted(codigos)) if codigos else (),
        start_date, end_date,
        tuple(sorted(flags_incluidos)) if flags_incluidos else None,
        tuple(sorted(cc_incluidos)) if cc_incluidos else None,
    )


def _resolver_datos_crudos(receta: dict | None) -> pd.DataFrame:
    """
    receta: {"codigos", "start", "end", "flags", "cc"} — lo que hoy vive en
    store-datos-crudos. Retorna el DataFrame completo (codigo, datetime,
    variables), indexado 0..n, con 'datetime' ya como Timestamp.

    "flags" filtra por flag_n_* de SIGMA; "cc" filtra por cc_n_* del Control de
    Calidad propio del Analizador (core.control_calidad) — capas independientes
    y combinables, nunca la misma columna (ver docs/SPEC-control-calidad.md).
    """
    if not receta:
        return pd.DataFrame()

    clave = _clave_consulta(receta.get("codigos"), receta.get("start"),
                             receta.get("end"), receta.get("flags"), receta.get("cc"))
    df = _CACHE_CONSULTAS.get(clave)
    if df is not None:
        _CACHE_CONSULTAS.move_to_end(clave)
        return df

    fi = pd.to_datetime(receta.get("start")) if receta.get("start") else None
    ff = pd.to_datetime(receta.get("end")) if receta.get("end") else None
    df = data_loader.cargar_estaciones(receta.get("codigos") or [], fi, ff)
    if not df.empty:
        df = data_loader.filtrar_por_flags(df, receta.get("flags"))
        df = control_calidad.agregar_columnas_cc(df)
        df = data_loader.filtrar_por_flags(df, receta.get("cc"), prefijo_flag="cc_")
        # flag_*/cc_* SÍ se conservan (a diferencia de antes): Vista cruda las
        # usa para resaltar puntos sobre la serie — como el df ahora vive
        # cacheado en el servidor (ver _CACHE_CONSULTAS) y ya no viaja
        # completo por red en el Store, conservarlas no tiene costo de red.
        variables = data_loader.variables_disponibles(df)
        flag_cols = [c for c in df.columns if c.startswith("flag_") or c.startswith("cc_")]
        cols = ["codigo", "datetime"] + variables + flag_cols
        df = df[cols].copy()

    _CACHE_CONSULTAS[clave] = df
    _CACHE_CONSULTAS.move_to_end(clave)
    while len(_CACHE_CONSULTAS) > _CACHE_CONSULTAS_MAXSIZE:
        _CACHE_CONSULTAS.popitem(last=False)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# Poblar dropdown de estaciones (al iniciar y al pulsar "Actualizar lista")
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("dd-codigos", "options"),
    Output("dd-codigos", "placeholder"),
    Input("interval-inicio", "n_intervals"),
    Input("btn-refresh-estaciones", "n_clicks"),
    prevent_initial_call=False,
)
def actualizar_lista_estaciones(_n_interval, _n_clicks):
    df = data_loader.codigos_disponibles()
    if df.empty:
        return [], "Sin estaciones descargadas — ejecuta el script de descarga primero"
    opciones = []
    for _, row in df.iterrows():
        cod = row["codigo"]
        nom = row.get("nombre") or "—"
        dz  = row.get("dz") or "?"
        cat = (row.get("categoria") or "")[:4]
        opciones.append({"label": f"{cod}  ·  {nom}  ·  DZ{dz} {cat}", "value": cod})
    return opciones, f"Selecciona uno o más códigos… ({len(opciones)} disponibles)"


# ══════════════════════════════════════════════════════════════════════════════
# Helper compartido: opciones de dd-variable a partir de códigos elegidos.
# Lo usan tanto el callback de abajo (cuando la pestaña Estadística ya está
# montada) como el router de pestañas (para "hornear" el valor inicial al
# montar la pestaña — ver renderizar_tab más abajo).
# ══════════════════════════════════════════════════════════════════════════════

def _opciones_variable(codigos):
    if not codigos:
        return [], None
    df = data_loader.cargar_estaciones(codigos)
    if df.empty:
        return [], None
    vars_disp = data_loader.variables_disponibles(df)
    opts = [{"label": v, "value": v} for v in vars_disp]
    # Sugerir humedad por defecto si existe (motivación principal del tool)
    preferidas = ["n_humedad", "n_humedad_inst", "n_humre", "n_humrel",
                  "n_airtemp", "n_temp"]
    var_def = next((v for v in preferidas if v in vars_disp),
                   vars_disp[0] if vars_disp else None)
    return opts, var_def


# ══════════════════════════════════════════════════════════════════════════════
# Cuando cambian las estaciones: rango de fechas + mensaje (compartido, vive
# siempre montado en la raíz, fuera de cualquier pestaña).
# ══════════════════════════════════════════════════════════════════════════════

MESES_PERIODO_DEFAULT = 6


def _texto_cobertura(cobertura: dict[str, list[tuple]], fmin, fmax) -> str:
    """
    Texto de cobertura LOCAL (lo que ya descargamos a disco) para el mensaje
    compartido — se etiqueta explícito para no confundirlo con la
    disponibilidad real en la BD central de SIGMA, que puede tener más
    historial o distinto. Con 1 sola estación (el caso típico al elegir en
    el selector) muestra sus propios tramos y avisa si hay huecos de
    DESCARGA entre ellos — no confundir con huecos de datos AF-GAP/AF-MISS,
    que están DENTRO de un tramo ya descargado. Con varias estaciones
    seleccionadas muestra el rango combinado (cada una puede cubrir menos).
    Acompaña a _barra_cobertura(), que muestra lo mismo de forma visual —
    el texto se conserva porque el hueco de descarga es información
    operativa que conviene poder leer, no solo intuir de una barra.
    """
    etiqueta = "Descargado localmente (no es la disponibilidad en la BD central de SIGMA)"
    if len(cobertura) == 1:
        [tramos] = cobertura.values()
        rango = " y ".join(f"{fi:%Y-%m-%d}→{ff:%Y-%m-%d}" for fi, ff in tramos)
        if len(tramos) > 1:
            return f"{etiqueta}: {rango} ({len(tramos)} tramos — hay huecos de descarga entre ellos)."
        return f"{etiqueta}: {rango}."
    return f"{etiqueta}, rango combinado de {len(cobertura)} estaciones: {fmin:%Y-%m-%d} → {fmax:%Y-%m-%d}."


MAX_ESTACIONES_BARRA_COBERTURA = 8
ANCHO_ETIQUETA_FILA = "84px"  # ancho fijo de la columna de código, compartido con la fila de ticks


def _ticks_temporales(lo: pd.Timestamp, hi: pd.Timestamp, max_ticks: int = 6) -> list[tuple[pd.Timestamp, str]]:
    """
    Pocos ticks (fecha, etiqueta) para orientar la barra por año o por mes,
    sin llenarla de texto — el detalle exacto ya está en el tooltip de cada
    segmento y en el texto de abajo. Por año si el rango pasa de ~13 meses,
    por mes si es más corto; en ambos casos se espacian para no superar
    `max_ticks` (no son exhaustivos, son orientación).
    """
    dias = (hi - lo).days or 1
    if dias > 400:
        anios = list(range(lo.year, hi.year + 1))
        paso = max(1, -(-len(anios) // max_ticks))  # techo de la división
        return [(pd.Timestamp(year=a, month=1, day=1), str(a)) for a in anios[::paso]]

    meses = pd.date_range(lo.normalize().replace(day=1), hi, freq="MS")
    if meses.empty:
        return []
    paso = max(1, -(-len(meses) // max_ticks))
    return [(m, f"{m:%b %Y}") for m in meses[::paso]]


def _barra_cobertura(cobertura: dict[str, list[tuple]], fmin, fmax) -> html.Div | None:
    """
    Franja horizontal por estación: un segmento verde por tramo descargado,
    hueco visible (gris) donde no hay CSV — refuerzo visual de lo que
    _texto_cobertura ya dice en palabras. Escala compartida
    [fmin, max(fmax, hoy)] para que un atraso de descarga (último dato
    anterior a hoy) también se vea, no solo los huecos internos.

    Con más de MAX_ESTACIONES_BARRA_COBERTURA estaciones se omite (queda
    solo el texto) — una fila por estación deja de ser legible mucho antes
    de que valga la pena seguir apilando.
    """
    if len(cobertura) > MAX_ESTACIONES_BARRA_COBERTURA:
        return None

    hoy = pd.Timestamp.now().normalize()
    lo, hi = fmin, max(fmax, hoy)
    total_seg = (hi - lo).total_seconds() or 1.0

    def pct(ts) -> float:
        return max(0.0, min(100.0, (ts - lo).total_seconds() / total_seg * 100))

    filas = []
    for cod, tramos in cobertura.items():
        segmentos, cursor = [], 0.0
        for fi, ff in tramos:
            ini_pct, fin_pct = pct(fi), pct(ff)
            if ini_pct > cursor:
                segmentos.append(html.Div(style={"width": f"{ini_pct - cursor:.3f}%"}))
            segmentos.append(html.Div(
                title=f"{fi:%Y-%m-%d} → {ff:%Y-%m-%d}",
                style={"width": f"{max(fin_pct - ini_pct, 0.3):.3f}%",
                       "background": COLOR_FLAG["C"], "height": "100%"},
            ))
            cursor = fin_pct
        if cursor < 100:
            segmentos.append(html.Div(style={"width": f"{100 - cursor:.3f}%"}))

        marca_hoy = []
        if fmax < hoy:
            marca_hoy = [html.Div(title=f"Hoy ({hoy:%Y-%m-%d})", style={
                "position": "absolute", "left": f"{pct(hoy):.3f}%", "top": 0,
                "bottom": 0, "width": "2px", "background": "#495057",
            })]

        filas.append(html.Div([
            html.Span(cod, className="text-muted", style={
                "width": ANCHO_ETIQUETA_FILA, "flex": "0 0 auto", "fontSize": "0.75rem",
                "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap",
            }),
            html.Div(segmentos + marca_hoy, style={
                "display": "flex", "flex": "1 1 auto", "height": "10px",
                "background": COLOR_FLAG["SD"], "borderRadius": "2px",
                "overflow": "hidden", "position": "relative",
            }),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "3px"}))

    # Eje de años/meses, UNA sola vez (la escala es compartida por todas las
    # filas) — se alinea con la columna de las barras dejando el mismo ancho
    # reservado que ocupa la etiqueta de código a la izquierda.
    ticks = html.Div([
        html.Span(style={"width": ANCHO_ETIQUETA_FILA, "flex": "0 0 auto"}),
        html.Div([
            html.Span(etiqueta, className="text-muted", style={
                "position": "absolute", "left": f"{pct(ts):.3f}%",
                "transform": "translateX(-50%)", "whiteSpace": "nowrap", "fontSize": "0.68rem",
            })
            for ts, etiqueta in _ticks_temporales(lo, hi)
        ], style={"position": "relative", "flex": "1 1 auto", "height": "14px"}),
    ], style={"display": "flex", "gap": "8px"})

    return html.Div(filas + [ticks], className="mt-1 mb-1")


@callback(
    Output("dt-periodo", "min_date_allowed"),
    Output("dt-periodo", "max_date_allowed"),
    Output("dt-periodo", "start_date"),
    Output("dt-periodo", "end_date"),
    Output("div-mensaje", "children"),
    Input("dd-codigos", "value"),
)
def actualizar_periodo_compartido(codigos):
    if not codigos:
        return None, None, None, None, ""

    # Cobertura barata: solo lee nombres de archivo, no abre ningún CSV —
    # instantáneo aunque haya historiales de varios años (ver
    # data_loader.tramos_descargados).
    cobertura = {cod: data_loader.tramos_descargados(cod) for cod in codigos}
    todos_los_tramos = [t for tramos in cobertura.values() for t in tramos]
    if not todos_los_tramos:
        return None, None, None, None, (
            f"Sin datos descargados para {codigos}. "
            "Ejecuta scripts/pipeline/Descargar_Datos_Meteo.bat primero."
        )

    fmin = min(fi for fi, _ in todos_los_tramos)
    fmax = max(ff for _, ff in todos_los_tramos)

    # Por defecto se pide solo un tramo reciente, no todo el histórico — con
    # series de varios años, graficar todo de entrada es lo que hacía lenta
    # la herramienta. min/max_date_allowed sí quedan en el rango completo:
    # el usuario puede ampliar el periodo a mano cuando lo necesite.
    inicio_default = fmax - pd.DateOffset(months=MESES_PERIODO_DEFAULT)
    if inicio_default < fmin:
        inicio_default = fmin

    df = data_loader.cargar_estaciones(codigos)
    vars_disp = data_loader.variables_disponibles(df)

    resumen = (f"{len(codigos)} estación(es), {len(df):,} registros, {len(vars_disp)} variables. "
               f"Mostrando los últimos {MESES_PERIODO_DEFAULT} meses por defecto — amplía el "
               "periodo arriba si necesitas más.")

    mensaje = html.Div([
        _barra_cobertura(cobertura, fmin, fmax),
        html.Div(_texto_cobertura(cobertura, fmin, fmax)),
        html.Div(resumen),
    ])

    return (fmin.date(), fmax.date(), inicio_default.date(), fmax.date(), mensaje)


# ══════════════════════════════════════════════════════════════════════════════
# Cuando cambian las estaciones y la pestaña Estadística está montada: poblar
# dd-variable. Si la pestaña activa es otra, este Output no existe en el DOM
# y el update se ignora (benigno) — al volver a Estadística, el router lo
# repuebla directamente (ver renderizar_tab).
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("dd-variable", "options"),
    Output("dd-variable", "value"),
    Input("dd-codigos", "value"),
)
def poblar_variable_estadistica(codigos):
    return _opciones_variable(codigos)


def _opciones_estacion_comparar(codigos):
    if not codigos:
        return [], None
    meta = data_loader.metadata_estaciones(codigos)
    if meta.empty:
        return [{"label": c, "value": c} for c in codigos], codigos[0]
    opts = [{"label": f"{row.codigo} · {row.nombre}", "value": row.codigo}
            for row in meta.itertuples()]
    return opts, codigos[0]


# ══════════════════════════════════════════════════════════════════════════════
# Router de pestañas: construye el contenido de la pestaña activa.
# Estadística/Comparar nacen con sus dropdowns ya poblados (State, no Input
# — evita una carrera con los callbacks que reaccionan al mismo evento).
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("div-tab-content", "children"),
    Input("tabs-principales", "active_tab"),
    State("dd-codigos", "value"),
)
def renderizar_tab(active_tab, codigos):
    if active_tab == "tab-panorama":
        return tab_panorama.layout()
    if active_tab == "tab-comparar":
        estacion_opts, estacion_value = _opciones_estacion_comparar(codigos)
        return tab_comparar.layout(estacion_opts=estacion_opts, estacion_value=estacion_value)
    if active_tab == "tab-crudo":
        estacion_opts, estacion_value = _opciones_estacion_comparar(codigos)
        return tab_crudo.layout(estacion_opts=estacion_opts, estacion_value=estacion_value)
    if active_tab == "tab-emplazamiento":
        pares = emplazamiento.calcular_pares_colocados()
        codigos_par = {c for p in pares for c in (p["codigo_auto"], p["codigo_conv"])}
        meta = data_loader.metadata_estaciones(list(codigos_par)) if codigos_par else pd.DataFrame()
        nombres = _mapa_nombre_clasificacion(meta)
        pares_opts = tab_emplazamiento.opciones_pares(pares, nombres)
        return tab_emplazamiento.layout(pares_opts=pares_opts)
    variable_opts, variable_value = _opciones_variable(codigos)
    return tab_estadistica.layout(variable_opts=variable_opts, variable_value=variable_value)


# ══════════════════════════════════════════════════════════════════════════════
# Cuando cambia la variable: actualizar checklist de series derivadas
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("cl-series-derivadas", "options"),
    Output("cl-series-derivadas", "value"),
    Output("dd-derivada-foco", "options"),
    Output("dd-derivada-foco", "value"),
    Input("dd-variable", "value"),
)
def actualizar_series_derivadas(variable):
    if not variable:
        return [], [], [], None
    specs = series_derivadas.series_disponibles(variable)
    opts = [{"label": sp.get("label", sp["id"]), "value": sp["id"]} for sp in specs]
    # Por defecto activar |Δ| horario si existe; si no, la primera
    ids = [sp["id"] for sp in specs]
    default = next((i for i in ids if i.startswith("absd")), ids[:1])
    default = default if isinstance(default, list) else [default]
    foco = default[0] if default else (ids[0] if ids else None)
    return opts, default, opts, foco


# ══════════════════════════════════════════════════════════════════════════════
# Cargar datos al store (recarga solo cuando cambia codigos/variable/periodo)
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("store-df-cargado", "data"),
    Input("dd-codigos", "value"),
    Input("dd-variable", "value"),
    Input("dt-periodo", "start_date"),
    Input("dt-periodo", "end_date"),
    Input("cl-flags", "value"),
    Input("cl-cc", "value"),
)
def cargar_al_store(codigos, variable, start_date, end_date, flags_incluidos, cc_incluidos):
    if not codigos or not variable:
        return None
    fi = pd.to_datetime(start_date) if start_date else None
    ff = pd.to_datetime(end_date) if end_date else None

    df = data_loader.cargar_estaciones(codigos, fi, ff)
    if df.empty or variable not in df.columns:
        return None
    df = control_calidad.agregar_columnas_cc(df)  # agrega cc_{variable} si hay regla definida

    flag_col = f"flag_{variable}"
    cc_col = f"cc_{variable}"
    cols_needed = ["codigo", "datetime", variable]
    if flag_col in df.columns:
        cols_needed.append(flag_col)
    if cc_col in df.columns:
        cols_needed.append(cc_col)
    df_min = df[cols_needed].copy()

    # ── Filtrar por flags de SIGMA ────────────────────────────────────────────
    # Los datos cuyo flag no esté en la lista se reemplazan por NaN.
    # Esto preserva el eje temporal (la fila no se elimina) pero hace que las
    # series derivadas, histogramas y detección de eventos los ignoren.
    if flag_col in df_min.columns and flags_incluidos is not None:
        if len(flags_incluidos) == 0:
            # Usuario destildó todos: todo se vuelve NaN
            df_min[variable] = np.nan
        else:
            flags_validos = set(flags_incluidos)
            # Normalizar: flag NaN/None se trata como "SD"
            flag_norm = df_min[flag_col].fillna("SD")
            mask_excluido = ~flag_norm.isin(flags_validos)
            df_min.loc[mask_excluido, variable] = np.nan

    # ── Filtrar por Control de Calidad propio (capa aparte del flag de SIGMA) ─
    df_min = data_loader.filtrar_por_flags(df_min, cc_incluidos, prefijo_flag="cc_")

    df_min["datetime"] = df_min["datetime"].astype(str)
    return df_min.to_dict(orient="records")


# ══════════════════════════════════════════════════════════════════════════════
# Calcular series derivadas al store
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("store-derivadas", "data"),
    Input("store-df-cargado", "data"),
    Input("cl-series-derivadas", "value"),
    State("dd-variable", "value"),
)
def calcular_derivadas_al_store(df_data, ids_seleccionados, variable):
    if not df_data or not ids_seleccionados or not variable:
        return None

    df = pd.DataFrame(df_data)
    df["datetime"] = pd.to_datetime(df["datetime"])
    flag_col = f"flag_{variable}"

    salida = {sid: [] for sid in ids_seleccionados}
    for cod, grp in df.groupby("codigo"):
        grp = grp.sort_values("datetime").set_index("datetime")
        derivs = series_derivadas.calcular_lote(grp[variable], ids_seleccionados, variable)
        for sid, s in derivs.items():
            df_d = pd.DataFrame({sid: s.values}, index=s.index).reset_index()
            df_d.insert(0, "codigo", cod)
            df_d["datetime"] = df_d["datetime"].astype(str)
            salida[sid].extend(df_d.to_dict(orient="records"))

    return salida


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico principal: serie cruda + derivadas apiladas
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("g-series", "figure"),
    Input("store-df-cargado", "data"),
    Input("store-derivadas", "data"),
    Input("sl-percentil", "value"),
    State("dd-variable", "value"),
)
def actualizar_grafico_series(df_data, derivadas_data, percentil, variable):
    if not df_data or not variable:
        return charts.serie_temporal_apilada(
            pd.DataFrame(columns=["codigo", "datetime", variable or "x"]),
            variable or "x", {}, {"display_name": "", "unidad": ""}, {},
        )
    df = pd.DataFrame(df_data)
    df["datetime"] = pd.to_datetime(df["datetime"])

    info_var = series_derivadas.info_variable(variable)

    # Mapa codigo -> nombre para etiquetas de leyenda
    codigos_presentes = sorted(df["codigo"].unique().tolist())
    meta = data_loader.metadata_estaciones(codigos_presentes)
    nombres = _mapa_nombre_clasificacion(meta)

    # Construir dict de DataFrames de derivadas
    derivadas: dict[str, pd.DataFrame] = {}
    pct_der: dict[str, dict] = {}
    if derivadas_data:
        for sid, registros in derivadas_data.items():
            if not registros:
                continue
            df_d = pd.DataFrame(registros)
            df_d["datetime"] = pd.to_datetime(df_d["datetime"])
            derivadas[sid] = df_d
            # Calcular percentiles globales para el panel
            valores = pd.to_numeric(df_d[sid], errors="coerce").dropna()
            if len(valores) > 5:
                pct_der[sid] = distribuciones.percentiles(valores, [percentil])

    return charts.serie_temporal_apilada(
        df, variable, derivadas, info_var, pct_der, nombres=nombres
    )


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico histograma + resumen estadístico
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("g-hist", "figure"),
    Output("div-resumen-stat", "children"),
    Input("store-derivadas", "data"),
    Input("dd-derivada-foco", "value"),
    Input("sl-percentil", "value"),
    State("dd-variable", "value"),
)
def actualizar_histograma(derivadas_data, sid_foco, percentil, variable):
    if not derivadas_data or not sid_foco or sid_foco not in derivadas_data:
        return charts.histograma_con_percentiles(pd.Series(dtype=float)), ""

    registros = derivadas_data[sid_foco]
    df = pd.DataFrame(registros)
    if df.empty or sid_foco not in df.columns:
        return charts.histograma_con_percentiles(pd.Series(dtype=float)), ""

    s = pd.to_numeric(df[sid_foco], errors="coerce").dropna()
    info_var = series_derivadas.info_variable(variable)
    unidad = info_var.get("unidad", "")

    pcts = distribuciones.percentiles(s, [50, 95, 99, percentil])
    fig = charts.histograma_con_percentiles(
        s, titulo=f"{sid_foco}  (n = {len(s):,})", percentiles=pcts, unidad=unidad,
    )

    res = distribuciones.resumen(s)
    detalle = html.Div([
        html.Div([html.Strong("n: "), f"{res['n_validos']:,}  "],),
        html.Div([html.Strong("media: "), f"{res['media']:.2f}  ",
                  html.Strong("std: "),   f"{res['std']:.2f}"]),
        html.Div([html.Strong("p50: "),  f"{res['p50']:.2f}  ",
                  html.Strong("p95: "),  f"{res['p95']:.2f}  ",
                  html.Strong("p99: "),  f"{res['p99']:.2f}  ",
                  html.Strong("p99.5: "), f"{res['p99_5']:.2f}"]),
    ])
    return fig, detalle


# ══════════════════════════════════════════════════════════════════════════════
# Boxplot por mes / hora / año
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("g-boxplot", "figure"),
    Input("store-derivadas", "data"),
    Input("dd-derivada-foco", "value"),
    Input("rb-boxplot-dim", "value"),
)
def actualizar_boxplot(derivadas_data, sid_foco, dim):
    if not derivadas_data or not sid_foco or sid_foco not in derivadas_data:
        return charts.boxplot_por_grupo(pd.DataFrame())

    df = pd.DataFrame(derivadas_data[sid_foco])
    if df.empty:
        return charts.boxplot_por_grupo(pd.DataFrame())
    df["datetime"] = pd.to_datetime(df["datetime"])
    s = df.set_index("datetime")[sid_foco]

    df_grupo = distribuciones.boxplot_por(s, dim=dim)
    label_x = {"mes": "mes", "hora": "hora del día", "anio": "año"}.get(dim, dim)
    return charts.boxplot_por_grupo(df_grupo, titulo=f"{sid_foco} agrupado", label_x=label_x)


# ══════════════════════════════════════════════════════════════════════════════
# Heatmap mes x hora con eventos detectados
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("g-heatmap", "figure"),
    Output("div-tabla-eventos", "children"),
    Output("div-resumen-eventos", "children"),
    Input("store-derivadas", "data"),
    Input("dd-derivada-foco", "value"),
    Input("sl-percentil", "value"),
)
def actualizar_eventos(derivadas_data, sid_foco, percentil):
    if not derivadas_data or not sid_foco or sid_foco not in derivadas_data:
        return charts.heatmap_eventos_mes_hora(pd.DataFrame()), "", ""

    df = pd.DataFrame(derivadas_data[sid_foco])
    if df.empty:
        return charts.heatmap_eventos_mes_hora(pd.DataFrame()), "", ""
    df["datetime"] = pd.to_datetime(df["datetime"])

    eventos = detector_eventos.detectar_excedencias(
        df, sid_foco, percentil=percentil, direccion="ambos",
    )
    if eventos.empty:
        return (charts.heatmap_eventos_mes_hora(pd.DataFrame()),
                html.Div("No se detectaron eventos.", className="text-muted"),
                "")

    fig = charts.heatmap_eventos_mes_hora(eventos, titulo=f"Eventos {sid_foco}")

    # Patrones agregados (texto-resumen)
    pat_hora = detector_eventos.patron_recurrencia(eventos, dim="hora_del_dia")
    pat_mes  = detector_eventos.patron_recurrencia(eventos, dim="mes")
    pat_cod  = detector_eventos.patron_recurrencia(eventos, dim="codigo")

    umbral = eventos["umbral_usado"].iloc[0]
    txt_resumen = (f"{len(eventos):,} eventos · umbral p{percentil} = {umbral:.2f} · "
                   f"top hora: {pat_hora.iloc[0]['grupo'] if not pat_hora.empty else '—'}h "
                   f"({pat_hora.iloc[0]['pct'] if not pat_hora.empty else 0:.0f}%) · "
                   f"top mes: {pat_mes.iloc[0]['grupo'] if not pat_mes.empty else '—'} · "
                   f"top estación: {pat_cod.iloc[0]['grupo'] if not pat_cod.empty else '—'}")

    # Tabla de eventos (limitada a top 200 por |valor|)
    ev_show = (eventos.sort_values("abs_valor", ascending=False)
                       .head(200)
                       .copy())
    ev_show["datetime"] = ev_show["datetime"].dt.strftime("%Y-%m-%d %H:%M")
    cols = ["datetime", "codigo", sid_foco, "abs_valor", "umbral_usado"]
    cols = [c for c in cols if c in ev_show.columns]
    ev_show = ev_show[cols]

    tabla = dash_table.DataTable(
        data=ev_show.to_dict(orient="records"),
        columns=[{"name": c, "id": c} for c in cols],
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "monospace", "fontSize": "12px", "padding": "4px 8px"},
        style_header={"backgroundColor": "#f4f4f4", "fontWeight": "bold"},
    )

    return fig, tabla, txt_resumen


# ══════════════════════════════════════════════════════════════════════════════
# store-datos-crudos: todas las variables de las estaciones/periodo elegidos,
# para Panorama/Comparar. No toca cargar_al_store (Estadística sigue igual).
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("store-datos-crudos", "data"),
    Input("dd-codigos", "value"),
    Input("dt-periodo", "start_date"),
    Input("dt-periodo", "end_date"),
    Input("cl-flags", "value"),
    Input("cl-cc", "value"),
)
def cargar_datos_crudos_al_store(codigos, start_date, end_date, flags_incluidos, cc_incluidos):
    if not codigos:
        return None
    receta = {
        "codigos": codigos, "start": start_date, "end": end_date,
        "flags": flags_incluidos, "cc": cc_incluidos,
    }
    if _resolver_datos_crudos(receta).empty:
        return None
    # El Store guarda solo esta receta chica (no el dataset) — ver
    # _resolver_datos_crudos: el DataFrame real vive cacheado en el servidor.
    return receta


# ══════════════════════════════════════════════════════════════════════════════
# Panorama: índice de triaje + panel alineado
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("tabla-panorama", "rowData"),
    Output("div-panorama-mensaje", "children"),
    Input("store-datos-crudos", "data"),
    Input("chk-incluir-bias", "value"),
)
def actualizar_tabla_panorama(datos_crudos, incluir_bias):
    if not datos_crudos:
        return [], "Selecciona estación(es) y periodo arriba para ver el índice de triaje."

    df = _resolver_datos_crudos(datos_crudos)
    if df.empty:
        return [], "Selecciona estación(es) y periodo arriba para ver el índice de triaje."
    variables = data_loader.variables_disponibles(df)
    codigos = sorted(df["codigo"].unique().tolist())

    meta = data_loader.metadata_estaciones(codigos)
    nombres = _mapa_nombre_clasificacion(meta)
    propias = {c: data_loader.variables_propias_estacion(c) for c in codigos}
    rangos = {v: series_derivadas.info_variable(v).get("rango_fisico") for v in variables}
    display_names = {v: series_derivadas.info_variable(v).get("display_name", v) for v in variables}

    filas = panorama.construir_indice_triaje(
        df, variables, rangos, display_names, nombres, propias,
        incluir_bias=bool(incluir_bias),
    )
    n_alta = sum(1 for f in filas if f["severidad"] == "Alta")
    n_media = sum(1 for f in filas if f["severidad"] == "Media")
    msg = f"{len(filas)} fila(s) · {n_alta} Alta · {n_media} Media"
    if incluir_bias:
        msg += " · AF-BIAS incluido"
    return filas, msg


@callback(
    Output("div-panel-panorama", "children"),
    Input("tabla-panorama", "selectedRows"),
    State("store-datos-crudos", "data"),
    State("chk-incluir-bias", "value"),
)
def actualizar_panel_panorama(seleccionadas, datos_crudos, incluir_bias):
    if not seleccionadas or not datos_crudos:
        return dbc.Alert("Marca filas del índice (checkbox) para verlas aquí.",
                          color="light", className="text-muted mb-0")

    df = _resolver_datos_crudos(datos_crudos)
    if df.empty:
        return dbc.Alert("Marca filas del índice (checkbox) para verlas aquí.",
                          color="light", className="text-muted mb-0")

    limitadas = seleccionadas[:8]
    paneles = []
    for fila in limitadas:
        cod, var = fila.get("codigo"), fila.get("variable")
        if not cod or not var or var not in df.columns:
            continue
        serie = df[df["codigo"] == cod].sort_values("datetime").set_index("datetime")[var]
        info_var = series_derivadas.info_variable(var)
        firmas = deteccion_afectaciones.detectar_todas(
            serie, var, rango_fisico=info_var.get("rango_fisico"),
            incluir_bias=bool(incluir_bias),
        )
        paneles.append((cod, var, serie, firmas, info_var))

    if not paneles:
        return dbc.Alert("No se pudo resolver la selección.", color="warning", className="mb-0")

    meta = data_loader.metadata_estaciones(sorted({p[0] for p in paneles}))
    nombres = _mapa_nombre_clasificacion(meta)
    hijos = [dcc.Graph(figure=charts.panel_alineado_panorama(paneles, nombres=nombres),
                        config={"displaylogo": False})]
    if len(seleccionadas) > 8:
        hijos.insert(0, dbc.Alert(
            f"Mostrando 8 de {len(seleccionadas)} filas marcadas — desmarca algunas para ver otras.",
            color="warning", className="small"))
    return html.Div(hijos)


# ══════════════════════════════════════════════════════════════════════════════
# Comparar: presets + modo libre
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("dd-comparar-estacion", "options"),
    Output("dd-comparar-estacion", "value"),
    Input("dd-codigos", "value"),
)
def poblar_estacion_comparar(codigos):
    return _opciones_estacion_comparar(codigos)


@callback(
    Output("dd-comparar-var1", "options"),
    Output("dd-comparar-var2", "options"),
    Input("dd-comparar-estacion", "value"),
)
def poblar_variables_libres_comparar(estacion):
    if not estacion:
        return [], []
    opts = [{"label": v, "value": v}
            for v in sorted(data_loader.variables_propias_estacion(estacion))]
    return opts, opts


@callback(
    Output("div-comparar-libre", "style"),
    Output("div-comparar-preset-info", "children"),
    Input("rb-comparar-preset", "value"),
)
def toggle_modo_comparar(preset_id):
    if preset_id == "libre":
        return {"display": "block"}, ""
    spec = consistencia.PRESETS.get(preset_id, {})
    return {"display": "none"}, dbc.Alert(
        f"Preset «{spec.get('label', preset_id)}»: resuelve automáticamente las variables "
        "según los candidatos configurados para esta estación.",
        color="light", className="small mb-0",
    )


@callback(
    Output("g-comparar", "figure"),
    Output("div-comparar-veredicto", "children"),
    Output("div-comparar-mensaje", "children"),
    Input("rb-comparar-preset", "value"),
    Input("dd-comparar-estacion", "value"),
    Input("dd-comparar-var1", "value"),
    Input("dd-comparar-var2", "value"),
    State("store-datos-crudos", "data"),
)
def actualizar_comparar(preset_id, estacion, var1, var2, datos_crudos):
    vacio = charts.overlay_multivar(pd.DataFrame(), None, None, {}, {})
    if not estacion or not datos_crudos:
        return vacio, "", "Elige estación y periodo arriba."

    df = _resolver_datos_crudos(datos_crudos)
    grp = df[df["codigo"] == estacion].sort_values("datetime").set_index("datetime") if not df.empty else df
    if grp.empty:
        return vacio, "", f"Sin datos para {estacion} en el periodo elegido."
    columnas = set(grp.columns)

    if preset_id == "libre":
        if not var1 or not var2:
            return vacio, "", "Modo libre: elige dos variables."
        if var1 not in columnas or var2 not in columnas:
            return vacio, "", "Alguna variable elegida no está disponible en esta estación."
        info1, info2 = series_derivadas.info_variable(var1), series_derivadas.info_variable(var2)
        return charts.overlay_multivar(grp, var1, var2, info1, info2), "", ""

    resueltas = consistencia.resolver_variables(preset_id, columnas)
    faltan = consistencia.roles_faltantes(resueltas)
    spec = consistencia.PRESETS[preset_id]
    if faltan:
        return vacio, "", (f"No se pudo resolver «{spec['label']}»: falta variable para "
                            f"rol(es) {', '.join(faltan)} en esta estación.")

    series = {rol: grp[col] for rol, col in resueltas.items()}
    resultado = consistencia.ejecutar_preset(preset_id, series)

    if preset_id == "temp_rocio":
        # El spec compara T contra el T-rocío CALCULADO (Magnus), no T contra
        # HR crudo — Td se agrega como serie de apoyo en el mismo eje (°C).
        td = pd.Series(consistencia.punto_de_rocio(series["t"], series["hr"]),
                        index=series["t"].index)
        info1 = series_derivadas.info_variable(resueltas["t"])
        fig = charts.overlay_multivar(
            grp, resueltas["t"], None, info1, {},
            violacion=resultado.get("violacion"),
            extra_series=[{"nombre": "T-rocío (calc.)", "serie": td, "eje": "y1", "dash": "dash"}],
        )
    elif preset_id == "tmax_tmin":
        col1, col2 = resueltas["t"], resueltas["tmax"]
        info1 = series_derivadas.info_variable(col1)
        # Tmax comparte unidad con T (°C) pero no está en series_disponibles.yaml
        # -> info_variable cae a _default (unidad=""); forzar para no abrir un
        # eje secundario innecesario.
        info2 = {**series_derivadas.info_variable(col2), "unidad": info1.get("unidad", "")}
        extra = [{"nombre": "Tmin diaria", "serie": series["tmin"], "eje": "y1", "dash": "dot"}]
        fig = charts.overlay_multivar(grp, col1, col2, info1, info2,
                                       violacion=resultado.get("violacion"), extra_series=extra)
    else:
        col1, col2 = resueltas[list(resueltas)[0]], resueltas[list(resueltas)[1]]
        info1, info2 = series_derivadas.info_variable(col1), series_derivadas.info_variable(col2)
        fig = charts.overlay_multivar(grp, col1, col2, info1, info2,
                                       violacion=resultado.get("violacion"))

    veredicto = dbc.Alert(
        resultado.get("veredicto", ""),
        color="danger" if resultado.get("pct_violacion", 0) > 0 else "success",
        className="mb-0",
    )
    return fig, veredicto, ""


# ══════════════════════════════════════════════════════════════════════════════
# Emplazamiento compartido: overlay automática↔convencional co-ubicada, independiente del
# selector compartido (dd-codigos/dt-periodo) — carga directo las 2 estaciones
# del par elegido, con su propio periodo (dt-periodo-emplazamiento).
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("div-emplazamiento-disclaimer", "children"),
    Input("rb-emplazamiento-variable", "value"),
)
def actualizar_disclaimer_emplazamiento(variable_fisica):
    md = (tab_emplazamiento.DISCLAIMER_PRECIPITACION_MD if variable_fisica == "precipitacion"
          else tab_emplazamiento.DISCLAIMER_TEMPERATURA_MD)
    return dcc.Markdown(md, className="small text-muted mb-0")


def _dividir_par_emplazamiento(par_value: str | None) -> tuple[str | None, str | None]:
    if not par_value or "|" not in par_value:
        return None, None
    cod_auto, cod_conv = par_value.split("|", 1)
    return cod_auto, cod_conv


def _mapa_nombre_clasificacion(meta: pd.DataFrame) -> dict[str, str]:
    """{codigo: "Nombre · CLASIF"} a partir de metadata_estaciones() — CLASIF es
    el código operativo real (EMA/EAA/EHA/EHMA/PE/PLU para automáticas;
    CO/CP/HLG/HLM/MAP/PE/PLU para convencionales, ver data_ref/estaciones.db),
    no el `categoria` genérico (solo AUTOMATICA/CONVENCIONAL) — pedido explícito
    del usuario 2026-10-01: el código de estación solo no se reconoce rápido, y
    tampoco alcanza con saber si es automática o convencional, hace falta el
    tipo específico "tal como dice la maestra"."""
    if meta.empty:
        return {}
    resultado = {}
    for row in meta.itertuples():
        clasif = getattr(row, "clasificacion", None)
        resultado[row.codigo] = f"{row.nombre} · {clasif}" if clasif else row.nombre
    return resultado


def _etiqueta_estacion(codigo: str, nombres: dict[str, str]) -> str:
    """"CODIGO · Nombre · CLASIF" — el código solo no se reconoce rápido a simple
    vista (pedido del usuario, 2026-10-01); mismo patrón ya usado en
    _opciones_estacion_comparar() para Comparar/Vista cruda. `nombres` viene de
    _mapa_nombre_clasificacion(), ya trae nombre+clasificación combinados."""
    nombre = nombres.get(codigo)
    return f"{codigo} · {nombre}" if nombre else codigo


def _titulo_par_emplazamiento(cod_auto: str, cod_conv: str, nombres: dict[str, str]) -> str:
    return f"{_etiqueta_estacion(cod_auto, nombres)} ↔ {_etiqueta_estacion(cod_conv, nombres)}"


@callback(
    Output("dt-periodo-emplazamiento", "min_date_allowed"),
    Output("dt-periodo-emplazamiento", "max_date_allowed"),
    Output("dt-periodo-emplazamiento", "start_date"),
    Output("dt-periodo-emplazamiento", "end_date"),
    Input("dd-emplazamiento-par", "value"),
)
def actualizar_periodo_emplazamiento(par_value):
    cod_auto, cod_conv = _dividir_par_emplazamiento(par_value)
    if not cod_auto:
        return None, None, None, None

    tramos = data_loader.tramos_descargados(cod_auto) + data_loader.tramos_descargados(cod_conv)
    if not tramos:
        return None, None, None, None

    fmin = min(fi for fi, _ in tramos)
    fmax = max(ff for _, ff in tramos)
    inicio_default = fmax - pd.DateOffset(months=MESES_PERIODO_DEFAULT)
    if inicio_default < fmin:
        inicio_default = fmin
    return fmin, fmax, inicio_default, fmax


_COLOR_EXTREMO_MAXIMA = "#1f77b4"
_COLOR_EXTREMO_MINIMA = "#ff7f0e"
_COLOR_VENTANA_NOCTURNA = "#1f77b4"
_COLOR_VENTANA_DIURNA = "#ff7f0e"
_NOTA_CALCULADO = " (calculada)"


def _figuras_emplazamiento_temperatura(cod_auto, cod_conv, df_auto, df_conv, vacio, vacio_diff, nombres):
    mensajes = []
    titulo_par = _titulo_par_emplazamiento(cod_auto, cod_conv, nombres)
    metadata = emplazamiento.EQUIVALENCIA_VARIABLES["temperatura"]["convencional"]
    var_auto = emplazamiento.EQUIVALENCIA_VARIABLES["temperatura"]["automatica"]
    extra_todas = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
    colores_por_columna = {e["columna"]: e["color"] for e in extra_todas}

    # Gráfico 1: horaria continua + horas sinópticas (07h/13h/19h)
    if var_auto not in df_auto.columns:
        fig1 = vacio
        mensajes.append(f"{cod_auto} no tiene {var_auto} descargada en este periodo.")
    else:
        extra_puntual = [e for e in extra_todas if e["tipo"] == "puntual"]
        info_auto = series_derivadas.info_variable(var_auto)
        fig1 = charts.overlay_multivar(
            df_auto, var_auto, None, info_auto, {}, extra_series=extra_puntual,
            titulo=f"{titulo_par} · Horaria",
        )
        if df_conv.empty:
            mensajes.append(f"{cod_conv} no tiene datos descargados en este periodo.")
        elif not extra_puntual:
            mensajes.append(f"{cod_conv} no tiene horas sinópticas de temperatura disponibles.")

    # Gráfico 2: máxima/mínima diaria — real de la automática (n_maxat/n_minat,
    # respaldo n_maxath/n_minath) y de la convencional (n_tm102/n_tm103). Si
    # falta de cualquiera de los dos lados, se menciona explícitamente (no se
    # omite en silencio).
    extremos = emplazamiento.calcular_extremos_diarios_automatica(df_auto)
    puntos2 = [e for e in extra_todas if e["tipo"] == "diaria"]
    for col, meta in metadata.items():
        if meta["tipo"] == "diaria" and not (col in df_conv.columns and df_conv[col].notna().any()):
            mensajes.append(f"{cod_conv} no tiene {meta['etiqueta'].lower()} disponible.")
    for clave, etiqueta, color in (
        ("maxima", "Máxima (auto)", _COLOR_EXTREMO_MAXIMA),
        ("minima", "Mínima (auto)", _COLOR_EXTREMO_MINIMA),
    ):
        fuente = extremos.get(clave)
        if fuente is None:
            col_real = emplazamiento.EQUIVALENCIA_VARIABLES["temperatura"]["automatica_extremos_diarios"][clave]
            col_horario = emplazamiento.EQUIVALENCIA_VARIABLES["temperatura"]["automatica_extremos_horarios_agregados"][clave]
            mensajes.append(f"{cod_auto} no tiene {etiqueta.split(' ')[0].lower()} diaria disponible "
                             f"(ni {col_real} ni {col_horario}).")
            continue
        nombre = etiqueta + (_NOTA_CALCULADO if fuente["calculado"] else "")
        puntos2.append({"nombre": nombre, "serie": fuente["serie"], "color": color, "symbol": "diamond"})
        if fuente["calculado"]:
            mensajes.append(f"Nota: {nombre}.")
    fig2 = charts.serie_puntos_diarios(
        puntos2, titulo=f"{titulo_par} · Máx/mín diaria", yaxis_title="Temperatura (°C)",
    )

    # Diferencias (convencional − automática)
    serie_auto_cont = df_auto[var_auto] if var_auto in df_auto.columns else pd.Series(dtype=float)
    dif_puntual = emplazamiento.calcular_diferencias_puntuales(serie_auto_cont, df_conv, "temperatura")
    lista_diff1 = [
        {"nombre": metadata[col]["etiqueta"], "serie": s, "color": colores_por_columna.get(col, "#2ca02c")}
        for col, s in dif_puntual.items() if not s.empty
    ]
    fig_diff1 = charts.panel_diferencias_emplazamiento(lista_diff1, titulo="Dif. horas sinópticas (conv.−auto.)")

    dif_diaria = emplazamiento.calcular_diferencias_diarias_temperatura(df_auto, df_conv)
    lista_diff2 = [
        {"nombre": metadata[col]["etiqueta"], "serie": s, "color": colores_por_columna.get(col, "#2ca02c")}
        for col, s in dif_diaria.items() if not s.empty
    ]
    fig_diff2 = charts.panel_diferencias_emplazamiento(lista_diff2, titulo="Dif. máx/mín diaria (conv.−auto.)")

    return fig1, fig2, fig_diff1, fig_diff2, " ".join(mensajes)


def _figuras_emplazamiento_precipitacion(cod_auto, cod_conv, df_auto, df_conv, vacio, vacio_diff, nombres):
    mensajes = []
    titulo_par = _titulo_par_emplazamiento(cod_auto, cod_conv, nombres)
    metadata = emplazamiento.EQUIVALENCIA_VARIABLES["precipitacion"]["convencional"]
    extra_todas = emplazamiento.armar_extra_series_convencional(df_conv, "precipitacion")
    colores_por_columna = {e["columna"]: e["color"] for e in extra_todas}

    # Gráfico 1: acumulado diario — n_pt101 realineado +1 día (ver
    # core.emplazamiento, desfase_dias_cierre) junto al acumulado real/calculado
    # de la automática (n_dayrain).
    puntos1 = []
    for e in extra_todas:
        if e["columna"] != "n_pt101":
            continue
        p = dict(e)
        s = p["serie"].copy()
        s.index = s.index.normalize() + pd.Timedelta(days=1, hours=12)
        p["serie"] = s
        puntos1.append(p)
    if "n_pt101" not in df_conv.columns or not df_conv["n_pt101"].notna().any():
        mensajes.append(f"{cod_conv} no tiene {metadata['n_pt101']['etiqueta'].lower()} disponible.")
    acumulado = emplazamiento.calcular_acumulado_diario_automatica(df_auto)
    if acumulado is not None:
        nombre = "Acumulado diario (auto)" + (_NOTA_CALCULADO if acumulado["calculado"] else "")
        puntos1.append({"nombre": nombre, "serie": acumulado["serie"], "color": _COLOR_EXTREMO_MAXIMA,
                         "symbol": "diamond"})
        if acumulado["calculado"]:
            mensajes.append(f"Nota: {nombre}.")
    else:
        mensajes.append(f"{cod_auto} no tiene acumulado diario disponible (ni n_dayrain ni n_lluvia).")
    fig1 = charts.serie_puntos_diarios(
        puntos1, titulo=f"{titulo_par} · Acumulado diario", yaxis_title="Precipitación (mm)",
    )

    # Gráfico 2: ventaneo 07h/19h — cálculo propio de emplazamiento compartido (autorizado
    # explícitamente por el usuario, ver docs/SPEC-emplazamiento-compartido.md Ronda 2).
    ventaneo = emplazamiento.calcular_ventaneo_automatica(df_auto)
    puntos2 = [e for e in extra_todas if e["tipo"] == "puntual"]
    columnas_puntual_presentes = {e["columna"] for e in puntos2}
    for col, meta in metadata.items():
        if meta["tipo"] == "puntual" and col not in columnas_puntual_presentes:
            mensajes.append(f"{cod_conv} no tiene {meta['etiqueta'].lower()} disponible.")
    for clave, etiqueta, color in (
        ("nocturna", "Nocturna 19h→07h (auto, calculado)", _COLOR_VENTANA_NOCTURNA),
        ("diurna", "Diurna 07h→19h (auto, calculado)", _COLOR_VENTANA_DIURNA),
    ):
        serie = ventaneo.get(clave)
        if serie is None or serie.empty:
            mensajes.append(f"{cod_auto} no tiene n_lluvia disponible para calcular la ventana {clave}.")
            continue
        puntos2.append({"nombre": etiqueta, "serie": serie, "color": color, "symbol": "diamond"})
    fig2 = charts.serie_puntos_diarios(
        puntos2, titulo=f"{titulo_par} · Ventaneo 07h/19h", yaxis_title="Precipitación (mm)",
    )

    # Diferencias (convencional − automática)
    dif_diaria = emplazamiento.calcular_diferencias_precipitacion_diaria(df_auto, df_conv)
    lista_diff1 = []
    if dif_diaria is not None and not dif_diaria.empty:
        lista_diff1.append({"nombre": "Total diaria", "serie": dif_diaria,
                             "color": colores_por_columna.get("n_pt101", "#2ca02c")})
    fig_diff1 = charts.panel_diferencias_emplazamiento(lista_diff1, titulo="Dif. acumulado diario (conv.−auto.)")

    dif_ventaneo = emplazamiento.calcular_diferencias_precipitacion_ventaneo(df_auto, df_conv)
    lista_diff2 = [
        {"nombre": metadata[col]["etiqueta"], "serie": s, "color": colores_por_columna.get(col, "#2ca02c")}
        for col, s in dif_ventaneo.items() if not s.empty
    ]
    fig_diff2 = charts.panel_diferencias_emplazamiento(lista_diff2, titulo="Dif. ventaneo 07h/19h (conv.−auto.)")

    return fig1, fig2, fig_diff1, fig_diff2, " ".join(mensajes)


@callback(
    Output("g-emplazamiento-1", "figure"),
    Output("g-emplazamiento-2", "figure"),
    Output("g-emplazamiento-diff-1", "figure"),
    Output("g-emplazamiento-diff-2", "figure"),
    Output("div-emplazamiento-mensaje", "children"),
    Input("dd-emplazamiento-par", "value"),
    Input("rb-emplazamiento-variable", "value"),
    Input("dt-periodo-emplazamiento", "start_date"),
    Input("dt-periodo-emplazamiento", "end_date"),
    Input("cl-cc-emplazamiento", "value"),
)
def actualizar_emplazamiento(par_value, variable_fisica, fecha_inicio, fecha_fin, cc_incluidos):
    vacio = charts.overlay_multivar(pd.DataFrame(), None, None, {}, {})
    vacio_diff = charts.panel_diferencias_emplazamiento([])
    cod_auto, cod_conv = _dividir_par_emplazamiento(par_value)
    if not cod_auto:
        return vacio, vacio, vacio_diff, vacio_diff, "Elige un par arriba."

    df = data_loader.cargar_estaciones([cod_auto, cod_conv], fecha_inicio, fecha_fin)
    if df.empty:
        msg = f"Sin datos descargados para {cod_auto}/{cod_conv} en el periodo elegido."
        return vacio, vacio, vacio_diff, vacio_diff, msg

    # CC propio del Analizador (cc_n_*) — capa independiente del flag de SIGMA,
    # se aplica a ambas estaciones del par por igual (ver docs/SPEC-emplazamiento-compartido.md).
    df = control_calidad.agregar_columnas_cc(df)
    df = data_loader.filtrar_por_flags(df, cc_incluidos, prefijo_flag="cc_")

    df_auto = df[df["codigo"] == cod_auto.upper()].sort_values("datetime").set_index("datetime")
    df_conv = df[df["codigo"] == cod_conv.upper()].sort_values("datetime").set_index("datetime")

    meta = data_loader.metadata_estaciones([cod_auto, cod_conv])
    nombres = _mapa_nombre_clasificacion(meta)

    if variable_fisica == "temperatura":
        return _figuras_emplazamiento_temperatura(cod_auto, cod_conv, df_auto, df_conv, vacio, vacio_diff, nombres)
    return _figuras_emplazamiento_precipitacion(cod_auto, cod_conv, df_auto, df_conv, vacio, vacio_diff, nombres)


# ══════════════════════════════════════════════════════════════════════════════
# Vista cruda: todas las variables propias de una estación, sin aparataje
# estadístico, con banda de día efectivo + tabla de concordancia.
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("dd-crudo-estacion", "options"),
    Output("dd-crudo-estacion", "value"),
    Input("dd-codigos", "value"),
)
def poblar_estacion_crudo(codigos):
    return _opciones_estacion_comparar(codigos)


@callback(
    Output("cl-crudo-variables", "options"),
    Output("cl-crudo-variables", "value"),
    Input("dd-crudo-estacion", "value"),
)
def poblar_variables_crudo(estacion):
    """
    Checklist de variables a graficar como serie (columna izquierda). Aparte
    de esto, TODAS las variables propias de la estación se evalúan igual en
    el panel de día efectivo (columna derecha) — este selector solo decide
    qué se dibuja como línea de tiempo en detalle, no qué se audita.

    No todas las variables tienen una regla de CC propio definida todavía
    (ver control_calidad.tiene_regla_cc) — las que sí la tienen se marcan acá
    con "(CC)" en el label, para que el usuario sepa de entrada cuáles se
    evalúan y cuáles se muestran solo crudas (pedido explícito del usuario
    tras probar la pestaña: "no todas las variables tendrán ese CC").
    """
    if not estacion:
        return [], []
    variables = sorted(data_loader.variables_propias_estacion(estacion))
    meta = data_loader.metadata_estaciones([estacion])
    categoria = meta.iloc[0]["categoria"] if not meta.empty else ""
    opts = [
        {
            "label": series_derivadas.info_variable(v).get("display_name", v)
            + (" (CC)" if control_calidad.tiene_regla_cc(v, categoria) else ""),
            "value": v,
        }
        for v in variables
    ]
    # Arranca con un subconjunto chico (no las ~40 de golpe) — el usuario
    # tilda más si quiere; evita forzar una columna larguísima por defecto.
    return opts, variables[:6]


def _tabla_resumen_crudo(resultado_de: dict, resultado_conc: dict) -> html.Div:
    """
    Una fila por variable, todo agregado (nada de listar cada día sospechoso
    aparte): con muchos años de historial, un valor diario nativo con
    respaldo horario imperfecto puede acumular decenas de miles de días
    "sospechosos" — listarlos de a uno (como antes) es ilegible además de
    carísimo de renderizar. La columna "valores sospechosos" es solo un
    conteo; el detalle día a día se ve en la tabla de concordancia si hace
    falta drill-down (no construida acá).
    """
    filas = []
    for var, r in resultado_de.items():
        tabla = r["tabla"]
        pct_efectivo = f"{tabla['efectivo'].mean() * 100:.1f}%" if not tabla.empty else "—"
        conc = resultado_conc.get(var)
        pct_conc = "—"
        n_sospechosos = "—"
        if conc is not None and not conc["tabla"].empty:
            pct_conc = f"{conc['tabla']['respaldado'].mean() * 100:.1f}% (vs. {conc['variable_subdiaria']})"
            n_sospechosos = f"{int((~conc['tabla']['respaldado']).sum()):,}"
        filas.append(html.Tr([
            html.Td(series_derivadas.info_variable(var).get("display_name", var)),
            html.Td(pct_efectivo),
            html.Td(pct_conc),
            html.Td(n_sospechosos),
        ]))

    tabla_html = dbc.Table([
        html.Thead(html.Tr([html.Th("Variable"), html.Th("% días efectivos"),
                             html.Th("% concordancia diaria"), html.Th("Valores sospechosos")])),
        html.Tbody(filas),
    ], bordered=True, hover=True, size="sm", className="mb-0")
    return html.Div([tabla_html])


@callback(
    Output("g-crudo", "figure"),
    Output("div-crudo-mensaje", "children"),
    Input("store-datos-crudos", "data"),
    Input("dd-crudo-estacion", "value"),
    Input("cl-crudo-variables", "value"),
)
def actualizar_grafico_crudo(datos_crudos, estacion, variables_seleccionadas):
    """
    Solo la columna izquierda (series crudas) — depende del Periodo y los
    Flags elegidos arriba. El panel de día efectivo (derecha) vive en
    actualizar_dias_efectivos_crudo, deliberadamente SIN estas dependencias:
    ver ese callback para el porqué.
    """
    vacio = charts.panel_crudo_multivariable([])
    if not estacion or not datos_crudos:
        return vacio, "Elige estación arriba."

    df = _resolver_datos_crudos(datos_crudos)
    grp = df[df["codigo"] == estacion].sort_values("datetime").set_index("datetime") if not df.empty else df
    if grp.empty:
        return vacio, f"Sin datos para {estacion} en el periodo elegido."

    propias = data_loader.variables_propias_estacion(estacion)
    variables = sorted(v for v in propias if v in grp.columns)
    if not variables:
        return vacio, "Sin variables propias de esta estación en el periodo cargado."

    seleccionadas = [v for v in (variables_seleccionadas or []) if v in variables]
    # Motivo del CC: sobre el HISTÓRICO COMPLETO (mismo criterio que la severidad
    # cacheada en cc_{v}), no sobre el recorte de periodo — si no, el motivo de
    # los puntos cerca del borde del periodo elegido quedaría inconsistente con
    # la severidad ya mostrada (prueba de paso/persistencia necesitan lo que
    # vino ANTES, que un recorte de periodo puede no contener).
    motivos_cc = control_calidad.resultado_motivos_cc_estacion(estacion)
    paneles = [
        (
            v, grp[v], series_derivadas.info_variable(v), grp.get(f"flag_{v}"), grp.get(f"cc_{v}"),
            motivos_cc[v].reindex(grp.index) if v in motivos_cc else None,
        )
        for v in seleccionadas
    ]
    fig = charts.panel_crudo_multivariable(paneles)

    msg = f"{len(seleccionadas)} de {len(variables)} variable(s) propia(s) en el gráfico de series."
    return fig, msg


@callback(
    Output("g-crudo-dias-efectivos", "figure"),
    Output("div-crudo-resumen", "children"),
    Output("div-crudo-dias-efectivos-mensaje", "children"),
    Input("dd-crudo-estacion", "value"),
    Input("chk-crudo-incluir-diarias", "value"),
    Input("cl-cc", "value"),
)
def actualizar_dias_efectivos_crudo(estacion, incluir_diarias, cc_incluidos):
    """
    Deliberadamente SIN Input a store-datos-crudos/Periodo/Flags (de SIGMA):
    "día efectivo" es un chequeo de calidad sobre el HISTÓRICO COMPLETO de la
    estación (ver core.dias_efectivos.resultado_dias_efectivos_estacion),
    precalculado y cacheado en disco — cambiar el periodo consultado arriba
    no debe volver a calcularlo. SÍ tiene Input al CC propio (cl-cc), a
    pedido explícito del usuario — cambiarlo fuerza un recálculo sobre el
    histórico completo (mismo costo ya aceptado para el umbral_pct).
    """
    vacio_de = charts.panel_dias_efectivos({}, {})
    if not estacion:
        return vacio_de, None, ""

    cache = dias_efectivos.resultado_dias_efectivos_estacion(estacion, flags_cc=cc_incluidos)
    resultado_de_completo = cache["resultado_de"]
    resultado_conc = cache["resultado_conc"]
    if not resultado_de_completo:
        return vacio_de, None, "Sin datos para esta estación."

    # La caché guarda aplica=True para todas las variables (independiente del
    # switch); el switch se aplica acá, en vivo, sin recalcular nada.
    incluir_diarias = bool(incluir_diarias)
    resultado_de = {
        v: {**r, "aplica": (not r["es_diaria"]) or incluir_diarias}
        for v, r in resultado_de_completo.items()
    }

    info_por_var = {v: series_derivadas.info_variable(v) for v in resultado_de}
    fig_de = charts.panel_dias_efectivos(resultado_de, info_por_var)

    excluidas = [v for v, r in resultado_de.items() if r["es_diaria"] and not r["aplica"]]
    msg = "Histórico completo de la estación (independiente del periodo elegido arriba)."
    if excluidas:
        nombres = ", ".join(series_derivadas.info_variable(v).get("display_name", v) for v in excluidas)
        msg += f" {len(excluidas)} diaria(s) excluida(s) del cálculo: {nombres}."

    return fig_de, _tabla_resumen_crudo(resultado_de, resultado_conc), msg
