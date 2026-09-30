"""
Pestaña Comparar — overlay de 2 variables con presets de consistencia
cruzada (core.consistencia.PRESETS) + modo libre.

Opera sobre UNA estación a la vez (selector propio, poblado desde las
estaciones ya elegidas arriba) — evita el lío visual de doble-eje +
multi-estación. Ver ui/callbacks.py: actualizar_comparar.
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc


PRESET_OPTIONS = [
    {"label": "T vs T-rocío", "value": "temp_rocio"},
    {"label": "HR vs Lluvia", "value": "hr_lluvia"},
    {"label": "Viento vel/dir", "value": "veleta"},
    {"label": "Tmax/Tmin/T", "value": "tmax_tmin"},
    {"label": "Libre", "value": "libre"},
]


def layout(estacion_opts: list[dict] | None = None, estacion_value: str | None = None) -> html.Div:
    return html.Div([
        dbc.Card(
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("Estación a comparar:", className="fw-bold"),
                        dcc.Dropdown(
                            id="dd-comparar-estacion", options=estacion_opts or [],
                            value=estacion_value, clearable=False,
                            placeholder="Elige una de las estaciones seleccionadas arriba…",
                        ),
                    ], md=3),
                    dbc.Col([
                        html.Label("Chequeo:", className="fw-bold"),
                        dbc.RadioItems(
                            id="rb-comparar-preset", options=PRESET_OPTIONS, value="libre",
                            className="btn-group flex-wrap", inputClassName="btn-check",
                            labelClassName="btn btn-outline-primary btn-sm",
                            labelCheckedClassName="active",
                        ),
                    ], md=7),
                ], className="g-2 align-items-end"),

                html.Div(id="div-comparar-preset-info", className="small mt-2"),

                html.Div(
                    dbc.Row([
                        dbc.Col([
                            html.Label("Variable 1:", className="fw-bold small"),
                            dcc.Dropdown(id="dd-comparar-var1", options=[]),
                        ], md=4),
                        dbc.Col([
                            html.Label("Variable 2:", className="fw-bold small"),
                            dcc.Dropdown(id="dd-comparar-var2", options=[]),
                        ], md=4),
                    ], className="g-2 mt-2"),
                    id="div-comparar-libre", style={"display": "block"},
                ),

                html.Div(id="div-comparar-mensaje", className="text-muted small mt-2"),
            ]),
            className="shadow-sm mb-3",
        ),

        dbc.Card(
            dbc.CardBody([
                dcc.Loading(dcc.Graph(id="g-comparar", config={"displaylogo": False})),
                html.Div(id="div-comparar-veredicto", className="mt-2"),
            ]),
            className="shadow-sm mb-3",
        ),
    ])
