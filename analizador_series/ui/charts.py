"""
Builders de gráficos Plotly. Funciones puras: reciben datos, devuelven Figure.
Sin estado, sin Dash — testables aisladamente.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analizador_series.config import PALETA_ESTACIONES, COLOR_FLAG, COLOR_CC


# ══════════════════════════════════════════════════════════════════════════════
# Paleta consistente por estación
# ══════════════════════════════════════════════════════════════════════════════

def color_por_codigo(codigos: list[str]) -> dict[str, str]:
    """Asigna un color de la paleta a cada código de estación, ordenado."""
    codigos_ord = sorted(set(codigos))
    return {c: PALETA_ESTACIONES[i % len(PALETA_ESTACIONES)]
            for i, c in enumerate(codigos_ord)}


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 1: Serie cruda + serie(s) derivada(s) en panel apilado
# ══════════════════════════════════════════════════════════════════════════════

def serie_temporal_apilada(
    df_largo: pd.DataFrame,
    columna_cruda: str,
    derivadas: dict[str, pd.DataFrame],
    info_var: dict,
    percentiles_derivadas: dict[str, dict] | None = None,
    nombres: dict[str, str] | None = None,
) -> go.Figure:
    """
    Construye una figura con N+1 subplots verticales:
      panel 0: la serie cruda, coloreada por estación, con flags M marcados
      panel 1..N: cada serie derivada (una por panel)

    df_largo:           debe tener columnas codigo, datetime, columna_cruda,
                        flag_<columna_cruda>
    derivadas:          { id_serie -> DataFrame con codigo, datetime, id_serie }
                        (calculado por callbacks)
    info_var:           bloque YAML de la variable (display_name, unidad, etc.)
    percentiles_derivadas: { id_serie -> {p50, p95, p99, p99.5} } para overlay
                        de líneas horizontales en cada panel derivado
    """
    n_paneles = 1 + len(derivadas)
    alturas = [0.45] + [0.55 / max(1, len(derivadas))] * len(derivadas) if derivadas else [1.0]

    fig = make_subplots(
        rows=n_paneles, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=alturas,
        subplot_titles=[
            f"{info_var.get('display_name','')} ({info_var.get('unidad','')})"
        ] + [
            f"{spec_id}" for spec_id in derivadas.keys()
        ],
    )

    colores = color_por_codigo(df_largo["codigo"].tolist() if not df_largo.empty else [])
    nombres = nombres or {}

    def _label_para(cod: str) -> str:
        return nombres.get(cod, cod)

    # ── Panel cruda: una traza por estación ───────────────────────────────────
    # Estrategia: dropeamos NaN al plotear (no en los cálculos). Esto permite
    # ver líneas continuas incluso cuando el sensor reporta a cadencia menor
    # que la grilla del archivo (ej. humedad reportada cada 1h en archivo a
    # 10 min → la columna trae 5 NaN por cada valor válido, pero el plot debe
    # mostrar línea horaria limpia).
    flag_col = f"flag_{columna_cruda}"
    for cod, grp in df_largo.groupby("codigo"):
        grp = grp.sort_values("datetime")
        color = colores.get(cod, "#1f77b4")
        n_total   = len(grp)
        n_validos = grp[columna_cruda].notna().sum() if columna_cruda in grp.columns else 0
        pct_validos = (n_validos / n_total * 100) if n_total else 0
        nombre = _label_para(cod)
        label = f"{nombre} ({pct_validos:.0f}% válidos)"

        # Solo puntos válidos para el plot — las derivadas siguen calculadas en
        # la grilla original.
        grp_plot = grp[grp[columna_cruda].notna()] if columna_cruda in grp.columns else grp

        fig.add_trace(
            go.Scattergl(
                x=grp_plot["datetime"], y=grp_plot[columna_cruda],
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=1.2),
                marker=dict(color=color, size=3),
                legendgroup=cod,
                hovertemplate=(
                    f"<b>{nombre}</b> ({cod})<br>%{{x|%Y-%m-%d %H:%M}}<br>"
                    "Valor: %{y:.2f}<extra></extra>"
                ),
            ),
            row=1, col=1,
        )

        # Puntos con flag M sobre la serie cruda (sobre la grilla plot)
        if flag_col in grp.columns:
            malos = grp_plot[grp_plot[flag_col] == "M"]
            if not malos.empty:
                fig.add_trace(
                    go.Scatter(
                        x=malos["datetime"], y=malos[columna_cruda],
                        mode="markers",
                        name=f"{nombre} · M",
                        marker=dict(color=COLOR_FLAG["M"], size=6, symbol="x"),
                        legendgroup=cod, showlegend=False,
                        hovertemplate=(
                            f"<b>FLAG M · {nombre}</b><br>%{{x|%Y-%m-%d %H:%M}}<br>"
                            "Valor: %{y:.2f}<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )

        # Puntos DUDOSO/MALO del Control de Calidad propio (capa aparte del
        # flag de SIGMA de arriba) — mismo criterio visual que Vista Cruda
        # (ui.charts.panel_crudo_multivariable): color/símbolo distintos, sin
        # agregar más elementos que una serie de marcadores por severidad.
        cc_col = f"cc_{columna_cruda}"
        if cc_col in grp.columns:
            for severidad, simbolo in (("DUDOSO", "circle-open"), ("MALO", "triangle-up")):
                puntos_cc = grp_plot[grp_plot[cc_col] == severidad]
                if not puntos_cc.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=puntos_cc["datetime"], y=puntos_cc[columna_cruda],
                            mode="markers",
                            name=f"{nombre} · CC {severidad}",
                            marker=dict(color=COLOR_CC[severidad], size=7, symbol=simbolo,
                                        line=dict(width=1.2)),
                            legendgroup=cod, showlegend=False,
                            hovertemplate=(
                                f"<b>CC {severidad} · {nombre}</b><br>%{{x|%Y-%m-%d %H:%M}}<br>"
                                "Valor: %{y:.2f}<extra></extra>"
                            ),
                        ),
                        row=1, col=1,
                    )

    # ── Paneles derivados ──────────────────────────────────────────────────────
    for idx, (sid, df_der) in enumerate(derivadas.items(), start=2):
        if df_der.empty or sid not in df_der.columns:
            continue
        for cod, grp in df_der.groupby("codigo"):
            grp = grp.sort_values("datetime")
            # Dropea NaN para que la línea de la derivada se vea continua
            grp_plot = grp[grp[sid].notna()]
            color = colores.get(cod, "#1f77b4")
            nombre = _label_para(cod)
            fig.add_trace(
                go.Scattergl(
                    x=grp_plot["datetime"], y=grp_plot[sid],
                    mode="lines+markers",
                    name=nombre,
                    line=dict(color=color, width=1.0),
                    marker=dict(color=color, size=2.5),
                    legendgroup=cod, showlegend=False,
                    hovertemplate=(
                        f"<b>{nombre} · {sid}</b><br>%{{x|%Y-%m-%d %H:%M}}<br>"
                        "Valor: %{y:.2f}<extra></extra>"
                    ),
                ),
                row=idx, col=1,
            )

        # Líneas de percentiles si están disponibles
        if percentiles_derivadas and sid in percentiles_derivadas:
            pcts = percentiles_derivadas[sid]
            for p_label, valor in pcts.items():
                if valor is None or np.isnan(valor):
                    continue
                fig.add_hline(
                    y=valor, line_dash="dash", line_color="#999",
                    annotation_text=f"p{p_label}: {valor:.2f}",
                    annotation_position="right",
                    row=idx, col=1,
                )
                # Espejo para |Δ| y deltas con signo
                if sid.startswith("d") and not sid.startswith("absd"):
                    fig.add_hline(
                        y=-valor, line_dash="dash", line_color="#999",
                        row=idx, col=1,
                    )

    fig.update_layout(
        height=300 + 220 * max(1, n_paneles - 1),
        margin=dict(l=60, r=40, t=60, b=40),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        template="plotly_white",
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 2: Histograma de una serie derivada con líneas de percentil
# ══════════════════════════════════════════════════════════════════════════════

def histograma_con_percentiles(
    serie: pd.Series,
    titulo: str = "",
    percentiles: dict[float, float] | None = None,
    unidad: str = "",
) -> go.Figure:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    fig = go.Figure()
    if s.empty:
        fig.update_layout(title=titulo + "  (sin datos)", template="plotly_white")
        return fig

    fig.add_trace(go.Histogram(
        x=s, nbinsx=60, marker_color="#4682B4",
        opacity=0.85, name="distribución",
    ))

    if percentiles:
        for p, v in percentiles.items():
            if v is None or np.isnan(v):
                continue
            fig.add_vline(
                x=v, line_dash="dash", line_color="#d62728",
                annotation_text=f"p{p}: {v:.2f}",
                annotation_position="top",
            )

    xlabel = unidad if unidad else "valor"
    fig.update_layout(
        title=titulo,
        xaxis_title=xlabel,
        yaxis_title="frecuencia",
        template="plotly_white",
        margin=dict(l=50, r=30, t=50, b=40),
        height=320,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 3: Boxplot por mes / hora-del-día
# ══════════════════════════════════════════════════════════════════════════════

def boxplot_por_grupo(
    df_grupo_valor: pd.DataFrame,
    titulo: str = "",
    label_x: str = "",
) -> go.Figure:
    """
    df_grupo_valor: columnas 'grupo' y 'valor', producto de
                    core.distribuciones.boxplot_por().
    """
    fig = go.Figure()
    if df_grupo_valor.empty:
        fig.update_layout(title=titulo + "  (sin datos)", template="plotly_white")
        return fig

    for g in sorted(df_grupo_valor["grupo"].unique()):
        vals = df_grupo_valor.loc[df_grupo_valor["grupo"] == g, "valor"]
        fig.add_trace(go.Box(
            y=vals, name=str(g), boxpoints="outliers",
            marker_color="#4682B4",
        ))

    fig.update_layout(
        title=titulo,
        xaxis_title=label_x,
        yaxis_title="valor",
        showlegend=False,
        template="plotly_white",
        margin=dict(l=50, r=30, t=50, b=40),
        height=320,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 4: Heatmap mes × hora con frecuencia de eventos
# ══════════════════════════════════════════════════════════════════════════════

def heatmap_eventos_mes_hora(eventos: pd.DataFrame, titulo: str = "") -> go.Figure:
    """
    eventos: DataFrame con columna datetime (los eventos detectados).
    Muestra la frecuencia de eventos por (mes, hora-del-día).
    """
    fig = go.Figure()
    if eventos.empty or "datetime" not in eventos.columns:
        fig.update_layout(title=titulo + "  (sin eventos)", template="plotly_white")
        return fig

    dt = pd.to_datetime(eventos["datetime"])
    tabla = (
        pd.DataFrame({"mes": dt.dt.month, "hora": dt.dt.hour})
          .groupby(["mes", "hora"]).size().reset_index(name="n")
          .pivot(index="mes", columns="hora", values="n").fillna(0)
    )
    # Asegurar todas las horas 0-23
    for h in range(24):
        if h not in tabla.columns:
            tabla[h] = 0
    tabla = tabla[sorted(tabla.columns)]

    fig.add_trace(go.Heatmap(
        z=tabla.values,
        x=[f"{h:02d}h" for h in tabla.columns],
        y=[f"mes {m:02d}" for m in tabla.index],
        colorscale="OrRd",
        hovertemplate="%{y} · %{x}<br>eventos: %{z}<extra></extra>",
        colorbar=dict(title="eventos"),
    ))
    fig.update_layout(
        title=titulo,
        template="plotly_white",
        margin=dict(l=70, r=30, t=50, b=40),
        height=360,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 5: Panel alineado de Panorama — variables abiertas desde el índice
# de triaje, eje de tiempo compartido, altura FIJA por panel (R4: encoge al
# quitar variables en vez de estirar el panel restante).
# ══════════════════════════════════════════════════════════════════════════════

def _tramos_contiguos(idx) -> list[tuple]:
    """
    Agrupa un DatetimeIndex disperso (típico de AF-GAP intermitente) en
    tramos [inicio, fin] contiguos, usando el paso mínimo observado como
    cadencia de corte — evita pintar una sola banda que tape datos válidos
    entre huecos separados.
    """
    idx = pd.DatetimeIndex(sorted(idx))
    if len(idx) == 0:
        return []
    if len(idx) == 1:
        return [(idx[0], idx[0])]
    paso = idx.to_series().diff().dropna().min()
    tramos, inicio, prev = [], idx[0], idx[0]
    for t in idx[1:]:
        if (t - prev) > paso * 1.5:
            tramos.append((inicio, prev))
            inicio = t
        prev = t
    tramos.append((inicio, prev))
    return tramos


def _resaltar_firma(fig: go.Figure, firma: dict, serie: pd.Series, row: int) -> None:
    """Banda para firmas de racha (CST/GAP/MISS) o marcador puntual (OUT/NOIS/BIAS)."""
    idx = firma.get("indices_afectados")
    if idx is None or len(idx) == 0:
        return
    color = "rgba(214,39,40,0.18)" if firma.get("severidad") == "Alta" else "rgba(255,193,7,0.20)"
    if firma["tipo"] in ("AF-CST", "AF-GAP", "AF-MISS"):
        for x0, x1 in _tramos_contiguos(idx):
            fig.add_vrect(
                x0=x0, x1=x1, fillcolor=color, opacity=1.0, line_width=0,
                annotation_text=firma["tipo"], annotation_position="top left",
                row=row, col=1,
            )
    else:
        y = serie.reindex(pd.DatetimeIndex(idx))
        fig.add_trace(
            go.Scatter(
                x=pd.DatetimeIndex(idx), y=y.values, mode="markers",
                marker=dict(symbol="x", size=8,
                            color="#d62728" if firma.get("severidad") == "Alta" else "#e6a817"),
                name=firma["tipo"], showlegend=False,
                hovertemplate=(f"{firma['tipo']}<br>%{{x|%Y-%m-%d %H:%M}}<br>"
                               "%{y:.2f}<extra></extra>"),
            ),
            row=row, col=1,
        )


def panel_alineado_panorama(paneles: list[tuple], nombres: dict | None = None,
                             alto_panel: int = 170, alto_cabecera: int = 50) -> go.Figure:
    """
    paneles: list[(codigo, variable, pd.Series, list[dict-firma], info_var)].
    Un subplot por variable abierta, eje X compartido.
    """
    nombres = nombres or {}
    n = len(paneles)
    if n == 0:
        fig = go.Figure()
        fig.update_layout(
            title="Marca filas del índice para verlas aquí",
            template="plotly_white", height=180,
        )
        return fig

    fig = make_subplots(
        rows=n, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        subplot_titles=[
            f"{nombres.get(cod, cod)} · {info.get('display_name', var)}"
            for cod, var, _, _, info in paneles
        ],
    )
    for i, (cod, var, serie, firmas, info) in enumerate(paneles, start=1):
        s = serie.dropna()
        fig.add_trace(
            go.Scattergl(
                x=s.index, y=s.values, mode="lines+markers",
                line=dict(width=1.2, color="#1f77b4"), marker=dict(size=3),
                showlegend=False,
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
            ),
            row=i, col=1,
        )
        for firma in firmas:
            _resaltar_firma(fig, firma, serie, row=i)
        fig.update_yaxes(title_text=info.get("unidad", ""), row=i, col=1)

    fig.update_layout(
        height=alto_cabecera + n * alto_panel,
        template="plotly_white",
        margin=dict(l=60, r=30, t=50, b=30),
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 5b: Vista cruda multivariable — TODAS las variables propias de una
# estación, apiladas, sin firmas AF-* ni aparataje estadístico. Banda gris
# parcial (franja bajo el eje X de cada panel) marcando días NO efectivos.
# ══════════════════════════════════════════════════════════════════════════════

# Estaciones con caídas prolongadas (semanas/meses sin ningún dato) dejan un
# hueco enorme en el eje X: sin cortar la línea ahí, Plotly conecta con una
# recta el último punto antes del hueco con el primero después — un tramo
# diagonal engañoso. Umbral fijo, no configurable: por debajo de esto son
# caídas normales de una estación (ya señalizadas por el panel de "día
# efectivo"), no cortes de meses.
#
# Antes esto también colapsaba el hueco en el eje X (rangebreaks) para no
# desperdiciar ancho de gráfico en tramos vacíos — se sacó: Plotly.js
# desactiva en silencio (visible:false, sin error en consola visible al
# usuario) las trazas Scattergl en un eje con rangebreaks (confirmado en
# este entorno, Plotly 6.9.0), y volver a Scatter (SVG) para poder usar
# rangebreaks revive la lentitud original con series largas — justo la
# lentitud que este cambio existe para resolver. El hueco ahora se ve como
# un tramo en blanco de su ancho real en vez de comprimirse.
UMBRAL_HUECO = pd.Timedelta(days=7)


def _huecos_grandes(paneles: list[tuple], umbral: pd.Timedelta = UMBRAL_HUECO) -> list[tuple]:
    """
    [(inicio, fin), ...] — tramos donde NINGUNA variable de la estación tiene
    un solo dato válido (ej. la estación estuvo caída/desconectada), a partir
    de la unión de los índices (ya sin NaN) de todas las series en `paneles`.
    """
    idx = pd.DatetimeIndex([])
    for _, serie, _info, _flags, _cc, _motivo in paneles:
        idx = idx.union(serie.dropna().index)
    if len(idx) < 2:
        return []
    idx = idx.sort_values()
    diffs = idx.to_series().diff()
    return [
        (idx[i - 1], idx[i])
        for i in range(1, len(idx))
        if diffs.iloc[i] > umbral
    ]


def panel_crudo_multivariable(
    paneles: list[tuple], alto_panel: int = 170, alto_cabecera: int = 50,
) -> go.Figure:
    """
    paneles: list[(variable, pd.Series, info_var, flags_serie, cc_serie, motivo_serie)] —
    subconjunto de variables propias de UNA estación que el usuario eligió ver
    en detalle (el chequeo de día efectivo de TODAS las variables vive aparte,
    en panel_dias_efectivos, para no forzar una columna de N subgráficos por
    cada sensor de la estación).

    flags_serie: columna flag_<variable> de SIGMA alineada al mismo índice que
    serie, o None si no hay flags para pintar (ej. series derivadas sin flag
    propio) — los puntos "M" se resaltan en rojo, igual que en Estadística
    (ui.charts.serie_temporal_apilada).

    cc_serie: columna cc_<variable> del Control de Calidad PROPIO del
    Analizador (core.control_calidad), o None si esa variable no tiene regla
    de CC definida todavía (no todas la tienen). Puntos DUDOSO/MALO se
    resaltan con su propio color/símbolo (COLOR_CC), distinto del de SIGMA —
    capas independientes, un punto puede tener ambos marcadores a la vez.

    motivo_serie: texto por lectura de qué regla objeta el punto
    (core.control_calidad.resultado_motivos_cc_estacion), o None. Se muestra
    en el hover del marcador CC ("CC DUDOSO — prueba de paso (...)") en vez de
    agregar otro elemento visual — evita saturar el gráfico con más colores o
    símbolos, el detalle queda en el tooltip.
    """
    n = len(paneles)
    if n == 0:
        fig = go.Figure()
        fig.update_layout(
            title="Elige al menos una variable para graficar",
            template="plotly_white", height=180,
        )
        return fig

    huecos = _huecos_grandes(paneles)

    fig = make_subplots(
        rows=n, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        subplot_titles=[
            f"{info.get('display_name', var)} ({info.get('unidad', '')})"
            for var, _, info, _flags, _cc, _motivo in paneles
        ],
    )
    for i, (var, serie, info, flags, cc, motivo) in enumerate(paneles, start=1):
        s = serie.dropna()
        if huecos:
            # Un NaN a mitad de cada hueco corta la línea en vez de conectar
            # (Plotly no dibuja segmento a través de un y=NaN) — sin esto,
            # una caída prolongada se vería como una recta diagonal engañosa
            # entre el último dato antes y el primero después.
            medios = pd.DatetimeIndex([t0 + (t1 - t0) / 2 for t0, t1 in huecos])
            s = pd.concat([s, pd.Series(index=medios, dtype=float)]).sort_index()
        fig.add_trace(
            go.Scattergl(
                x=s.index, y=s.values, mode="lines+markers",
                line=dict(width=1.2, color="#1f77b4"), marker=dict(size=3),
                showlegend=False,
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
            ),
            row=i, col=1,
        )
        fig.update_yaxes(title_text=info.get("unidad", ""), row=i, col=1)

        if flags is not None:
            malos_idx = s.index.intersection(flags.index[flags == "M"])
            if len(malos_idx):
                fig.add_trace(
                    go.Scattergl(
                        x=malos_idx, y=s.loc[malos_idx].values,
                        mode="markers",
                        marker=dict(color=COLOR_FLAG["M"], size=6, symbol="x"),
                        showlegend=False,
                        hovertemplate="FLAG M<br>%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
                    ),
                    row=i, col=1,
                )

        if cc is not None:
            for severidad, simbolo in (("DUDOSO", "circle-open"), ("MALO", "triangle-up")):
                idx_cc = s.index.intersection(cc.index[cc == severidad])
                if len(idx_cc):
                    if motivo is not None:
                        textos = motivo.reindex(idx_cc).fillna("")
                        customdata = [
                            f"CC {severidad} — {m}" if m else f"CC {severidad}"
                            for m in textos
                        ]
                    else:
                        customdata = [f"CC {severidad}"] * len(idx_cc)
                    fig.add_trace(
                        go.Scattergl(
                            x=idx_cc, y=s.loc[idx_cc].values,
                            mode="markers",
                            marker=dict(color=COLOR_CC[severidad], size=7, symbol=simbolo,
                                        line=dict(width=1.2)),
                            showlegend=False,
                            customdata=customdata,
                            hovertemplate="%{customdata}<br>%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
                        ),
                        row=i, col=1,
                    )

    fig.update_layout(
        height=alto_cabecera + n * alto_panel,
        template="plotly_white",
        margin=dict(l=60, r=30, t=50, b=30),
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_xaxes(rangeslider_visible=True, rangeslider_thickness=0.06, row=n, col=1)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 5c: Día efectivo por sensor — un mapa de calor (una fila por
# variable, una columna por día), en vez de una banda por subgráfico. Cabe
# TODA la lista de sensores de la estación en un panel compacto, sin importar
# cuántas variables tenga (una estación puede tener 40+).
# ══════════════════════════════════════════════════════════════════════════════

def panel_dias_efectivos(
    resultado_de: dict[str, dict], info_por_var: dict[str, dict],
    alto_fila: int = 22, alto_cabecera: int = 70,
) -> go.Figure:
    """
    resultado_de: salida de core.dias_efectivos.construir_tabla_dias_efectivos
    ({variable -> {"tabla", "aplica", ...}}). Solo se pintan las variables con
    aplica=True (ver ese módulo: variables nativamente diarias se excluyen
    salvo que el usuario las incluya explícitamente).
    info_por_var: {variable -> info_variable(variable)} para el display_name.
    """
    filas = {v: r["tabla"] for v, r in resultado_de.items() if r["aplica"] and not r["tabla"].empty}
    if not filas:
        fig = go.Figure()
        fig.update_layout(
            title="Sin variables sub-diarias suficientes para calcular día efectivo",
            template="plotly_white", height=150,
        )
        return fig

    variables = list(filas)  # ya vienen en orden estable desde construir_tabla_dias_efectivos
    dias = pd.DatetimeIndex(sorted(set().union(*(set(t.index) for t in filas.values()))))

    # Sin array de texto por celda: con años de historia x 40+ variables eso
    # es F(filas x días) strings formateados en Python + un payload JSON de
    # varios MB — medido en un caso real (44 x 5915 días): pasaba de <1 MB a
    # ~5 MB y el navegador tardaba decenas de segundos en procesarlo. El
    # color ya comunica efectivo/no-efectivo; el hover solo ubica sensor+día.
    # El % exacto por variable (agregado) sigue disponible en la tabla-resumen.
    z = []
    for v in variables:
        tabla = filas[v].reindex(dias)
        z.append([
            None if pd.isna(efectivo) else (1.0 if efectivo else 0.0)
            for efectivo in tabla["efectivo"]
        ])

    # "display_name · variable": dos sensores pueden compartir display_name
    # (ej. dos instrumentos de temperatura instantánea) — el eje Y es
    # categórico, así que etiquetas repetidas colapsarían esas filas.
    nombres = [f"{info_por_var.get(v, {}).get('display_name', v)} · {v}" for v in variables]
    fig = go.Figure(go.Heatmap(
        z=z, x=dias, y=nombres,
        hovertemplate="<b>%{y}</b><br>%{x|%Y-%m-%d}<extra></extra>",
        colorscale=[[0, "#bdbdbd"], [1, "#2ca02c"]],
        zmin=0, zmax=1, showscale=False,
        xgap=0.5 if len(dias) < 400 else 0, ygap=2,
    ))
    fig.update_layout(
        title="Día efectivo por sensor (gris = no efectivo, &lt;75% de lecturas esperadas)",
        template="plotly_white",
        height=alto_cabecera + max(1, len(variables)) * alto_fila,
        margin=dict(l=160, r=20, t=50, b=30),
    )
    fig.update_yaxes(autorange="reversed")
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Gráfico 6: Overlay de 2 variables (Comparar) — doble eje Y si difieren
# unidades, marcadores de violación, series de apoyo opcionales.
# ══════════════════════════════════════════════════════════════════════════════

def overlay_multivar(df: pd.DataFrame, var1: str | None, var2: str | None,
                      info1: dict, info2: dict | None,
                      violacion=None, extra_series: list[dict] | None = None,
                      titulo: str = "") -> go.Figure:
    """
    df: indexado por datetime, con columnas var1/var2.
    violacion: índice de timestamps a resaltar sobre var1 (marcadores).
    extra_series: líneas de apoyo -> [{"nombre","serie","eje":"y1"|"y2","dash"}].
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if df is None or df.empty or not var1 or var1 not in df.columns:
        fig.update_layout(title=titulo or "Sin datos", template="plotly_white", height=440)
        return fig

    info2 = info2 or {}
    unidad1, unidad2 = info1.get("unidad", ""), info2.get("unidad", "")
    usar_eje2 = bool(var2) and var2 in df.columns and unidad1 != unidad2

    s1 = pd.to_numeric(df[var1], errors="coerce").dropna()
    fig.add_trace(
        go.Scattergl(
            x=s1.index, y=s1.values, name=info1.get("display_name", var1),
            line=dict(color="#1f77b4", width=1.3),
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
        ),
        secondary_y=False,
    )

    if var2 and var2 in df.columns:
        s2 = pd.to_numeric(df[var2], errors="coerce").dropna()
        fig.add_trace(
            go.Scattergl(
                x=s2.index, y=s2.values, name=info2.get("display_name", var2),
                line=dict(color="#ff7f0e", width=1.3),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
            ),
            secondary_y=usar_eje2,
        )

    for extra in (extra_series or []):
        s = pd.to_numeric(extra["serie"], errors="coerce").dropna()
        color = extra.get("color", "#2ca02c")
        modo = extra.get("modo", "lines")
        kwargs = dict(marker=dict(color=color, size=7)) if modo == "markers" \
            else dict(line=dict(color=color, width=1.0, dash=extra.get("dash", "dot")))
        fig.add_trace(
            go.Scattergl(
                x=s.index, y=s.values, name=extra.get("nombre", ""), mode=modo,
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.2f}<extra></extra>",
                **kwargs,
            ),
            secondary_y=(extra.get("eje") == "y2" and usar_eje2),
        )

    if violacion is not None and len(violacion) > 0:
        idx_v = pd.DatetimeIndex(violacion).intersection(s1.index)
        if len(idx_v):
            fig.add_trace(
                go.Scatter(
                    x=idx_v, y=s1.reindex(idx_v).values, mode="markers",
                    name="violación", marker=dict(color="#d62728", size=7, symbol="x"),
                    hovertemplate="violación<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
                ),
                secondary_y=False,
            )

    fig.update_yaxes(title_text=f"{info1.get('display_name','')} ({unidad1})", secondary_y=False)
    if usar_eje2:
        fig.update_yaxes(title_text=f"{info2.get('display_name','')} ({unidad2})", secondary_y=True)
    fig.update_layout(
        title=titulo, template="plotly_white", height=440,
        margin=dict(l=60, r=60, t=50, b=40), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig
