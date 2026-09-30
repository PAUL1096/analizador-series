"""
Pestaña Estadística — series derivadas, distribuciones y patrones.

Contenido idéntico al layout original (pre-pestañas): mismos ids, mismos
callbacks (ui/callbacks.py), solo reubicado aquí. `layout()` recibe las
opciones de `dd-variable` ya resueltas por el router de pestañas
(ui/callbacks.renderizar_tab), para que el dropdown nazca poblado en el
instante en que la pestaña se monta — no depende de que otro callback
llegue a tiempo tras el remount.
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc


# ══════════════════════════════════════════════════════════════════════════════
# Selectores propios de Estadística (variable, series derivadas, percentil)
# ══════════════════════════════════════════════════════════════════════════════

def selectores_estadistica(variable_opts: list[dict] | None = None,
                            variable_value: str | None = None) -> html.Div:
    return dbc.Card(
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Variable:", className="fw-bold"),
                    dcc.Dropdown(
                        id="dd-variable",
                        options=variable_opts or [],
                        value=variable_value,
                        placeholder="Primero elige estación(es)…",
                    ),
                ], md=3),

                dbc.Col([
                    html.Label("Series derivadas a calcular:", className="fw-bold"),
                    dcc.Checklist(
                        id="cl-series-derivadas",
                        options=[],
                        value=[],
                        inline=True,
                        labelStyle={"margin-right": "16px"},
                    ),
                ], md=6),

                dbc.Col([
                    html.Label("Percentil para detectar eventos:", className="fw-bold"),
                    dcc.Slider(
                        id="sl-percentil", min=90, max=99.9, step=0.1, value=99,
                        marks={90: "p90", 95: "p95", 99: "p99", 99.5: "p99.5"},
                    ),
                ], md=3),
            ], className="g-2"),
        ]),
        className="shadow-sm mb-3",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Series + Distribuciones
# ══════════════════════════════════════════════════════════════════════════════

def panel_series_y_distrib() -> html.Div:
    return dbc.Row([
        dbc.Col([
            dbc.Card(
                dbc.CardBody([
                    html.H6("Serie temporal y derivadas", className="text-muted mb-2"),
                    dcc.Loading(dcc.Graph(id="g-series", config={"displaylogo": False})),
                ]),
                className="shadow-sm",
            ),
        ], md=8),

        dbc.Col([
            dbc.Card(
                dbc.CardBody([
                    html.H6("Distribución de la serie derivada", className="text-muted mb-2"),
                    dcc.Dropdown(
                        id="dd-derivada-foco",
                        placeholder="Elige qué serie derivada examinar…",
                        clearable=False,
                    ),
                    dcc.Loading(dcc.Graph(id="g-hist", config={"displaylogo": False})),
                    html.Div(id="div-resumen-stat", className="small mt-2"),
                ]),
                className="shadow-sm",
            ),
        ], md=4),
    ], className="mb-3 g-2")


# ══════════════════════════════════════════════════════════════════════════════
# Patrones y eventos
# ══════════════════════════════════════════════════════════════════════════════

def panel_patrones() -> html.Div:
    return dbc.Row([
        dbc.Col([
            dbc.Card(
                dbc.CardBody([
                    html.H6("Distribución por mes / hora-del-día", className="text-muted mb-2"),
                    dbc.RadioItems(
                        id="rb-boxplot-dim",
                        options=[
                            {"label": "Por mes",          "value": "mes"},
                            {"label": "Por hora del día", "value": "hora"},
                            {"label": "Por año",          "value": "anio"},
                        ],
                        value="mes", inline=True, className="mb-2",
                    ),
                    dcc.Loading(dcc.Graph(id="g-boxplot", config={"displaylogo": False})),
                ]),
                className="shadow-sm",
            ),
        ], md=6),

        dbc.Col([
            dbc.Card(
                dbc.CardBody([
                    html.H6("Heatmap de eventos: mes × hora-del-día", className="text-muted mb-2"),
                    dcc.Loading(dcc.Graph(id="g-heatmap", config={"displaylogo": False})),
                ]),
                className="shadow-sm",
            ),
        ], md=6),
    ], className="mb-3 g-2")


def panel_eventos() -> html.Div:
    return dbc.Card(
        dbc.CardBody([
            html.H6("Eventos detectados — series derivadas que exceden el percentil elegido",
                    className="text-muted mb-2"),
            html.Div(id="div-resumen-eventos", className="small mb-2 text-muted"),
            dcc.Loading(html.Div(id="div-tabla-eventos")),
        ]),
        className="shadow-sm mb-3",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Layout de la pestaña
# ══════════════════════════════════════════════════════════════════════════════

def layout(variable_opts: list[dict] | None = None, variable_value: str | None = None) -> html.Div:
    return html.Div([
        selectores_estadistica(variable_opts, variable_value),
        panel_series_y_distrib(),
        panel_patrones(),
        panel_eventos(),
    ])
