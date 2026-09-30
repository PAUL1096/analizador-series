"""
Pestaña Vecindad — overlay visual de una estación automática con su
convencional co-ubicada (<100m), para inspección rápida (¿cuentan la misma
historia?). Sin estadística de comparación (eso es PLIA, proyecto separado).
Ver docs/SPEC-vecindad.md.

Independiente del selector compartido (dd-codigos/dt-periodo arriba): el
dropdown de pares se puebla directo desde core.vecindad.calcular_pares_colocados,
y el periodo es propio de esta pestaña (dt-periodo-vecindad) — mismo motivo que
ya documentó ui/callbacks.renderizar_tab para Estadística/Comparar/Vista cruda
(evitar la carrera de callbacks contra dd-codigos).
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc


VARIABLE_OPTIONS = [
    {"label": "Temperatura", "value": "temperatura"},
    {"label": "Precipitación", "value": "precipitacion"},
]


def opciones_pares(pares: list[dict]) -> list[dict]:
    """[{"codigo_auto","codigo_conv","distancia_m"}] -> opciones de dcc.Dropdown,
    value codifica el par como "{codigo_auto}|{codigo_conv}"."""
    return [
        {
            "label": f"{p['codigo_auto']} ↔ {p['codigo_conv']} · {p['distancia_m']:.0f}m",
            "value": f"{p['codigo_auto']}|{p['codigo_conv']}",
        }
        for p in pares
    ]


def layout(pares_opts: list[dict] | None = None, par_value: str | None = None) -> html.Div:
    return html.Div([
        dbc.Card(
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("Par co-ubicado (automática ↔ convencional):",
                                   className="fw-bold"),
                        dcc.Dropdown(
                            id="dd-vecindad-par", options=pares_opts or [],
                            value=par_value, clearable=False, searchable=True,
                            placeholder="Elige un par por código o distancia…",
                        ),
                    ], md=5),
                    dbc.Col([
                        html.Label("Variable física:", className="fw-bold"),
                        dbc.RadioItems(
                            id="rb-vecindad-variable", options=VARIABLE_OPTIONS,
                            value="temperatura",
                            className="btn-group", inputClassName="btn-check",
                            labelClassName="btn btn-outline-primary btn-sm",
                            labelCheckedClassName="active",
                        ),
                    ], md=3),
                    dbc.Col([
                        html.Label("Periodo:", className="fw-bold"),
                        dcc.DatePickerRange(
                            id="dt-periodo-vecindad",
                            display_format="YYYY-MM-DD",
                            clearable=True,
                        ),
                    ], md=4),
                ], className="g-2 align-items-end"),

                dbc.Row([
                    dbc.Col([
                        html.Label("Control de calidad (CC) a incluir:", className="fw-bold"),
                        dcc.Checklist(
                            id="cl-cc-vecindad",
                            options=[
                                {"label": " BUENO",  "value": "BUENO"},
                                {"label": " DUDOSO", "value": "DUDOSO"},
                                {"label": " MALO",   "value": "MALO"},
                            ],
                            value=["BUENO", "DUDOSO", "MALO"],
                            inline=True,
                            labelStyle={"margin-right": "16px"},
                        ),
                    ], md=6),
                ], className="g-2 mt-2"),

                html.Div(id="div-vecindad-mensaje", className="text-muted small mt-2"),
            ]),
            className="shadow-sm mb-3",
        ),

        dbc.Card(
            dbc.CardBody([
                dcc.Loading(dcc.Graph(id="g-vecindad", config={"displaylogo": False})),
            ]),
            className="shadow-sm mb-3",
        ),
    ])
