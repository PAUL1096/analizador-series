"""
Layout raíz del Analizador de Series.

selectores_compartidos(): estaciones, periodo, flags — visibles siempre,
arriba de las 3 pestañas. El contenido de cada pestaña se renderiza
dinámicamente vía callback (ui/callbacks.renderizar_tab), en vez de vivir
como children estáticos de dbc.Tab: las pestañas tendrán dcc.Graph/ag-grid,
y un dcc.Graph montado dentro de un panel oculto (display:none) mide ancho
0 y queda deformado hasta un resize manual — el swap dinámico evita eso.

Los 3 dcc.Store + el dcc.Interval viven en la raíz, fuera de cualquier
pestaña, para que sobrevivan a cualquier cambio de pestaña sin perder
estado ni dejar de dispararse.
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc


# ══════════════════════════════════════════════════════════════════════════════
# Selectores compartidos (estaciones, periodo, flags)
# ══════════════════════════════════════════════════════════════════════════════

def selectores_compartidos() -> html.Div:
    return dbc.Card(
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Row([
                        dbc.Col(
                            html.Label("Estaciones (puedes seleccionar varias):", className="fw-bold"),
                            className="align-self-center",
                        ),
                        dbc.Col(
                            dbc.Button(
                                "↺ Actualizar lista",
                                id="btn-refresh-estaciones",
                                size="sm",
                                color="secondary",
                                outline=True,
                                className="float-end",
                            ),
                            width="auto",
                        ),
                    ], className="g-1 mb-1"),
                    dcc.Dropdown(
                        id="dd-codigos",
                        options=[],
                        multi=True,
                        placeholder="Cargando estaciones…",
                    ),
                ], md=6),

                dbc.Col([
                    html.Label("Periodo:", className="fw-bold"),
                    dcc.DatePickerRange(
                        id="dt-periodo",
                        display_format="YYYY-MM-DD",
                        clearable=True,
                    ),
                ], md=3),

                dbc.Col([
                    html.Label("Flags a incluir en el análisis:", className="fw-bold"),
                    dcc.Checklist(
                        id="cl-flags",
                        options=[
                            {"label": " C (correctos)",  "value": "C"},
                            {"label": " M (malos)",      "value": "M"},
                            {"label": " SD (sin dato)",  "value": "SD"},
                        ],
                        value=["C"],         # ← por defecto, solo correctos
                        inline=True,
                        labelStyle={"margin-right": "16px"},
                    ),
                ], md=3),
            ], className="g-2"),

            # Control de calidad (CC) propio del Analizador — capa aparte del flag
            # de SIGMA de arriba (cl-flags). Nunca sale de esta máquina (ver
            # docs/SPEC-control-calidad.md). Label explícito para no repetir la
            # confusión de "esto es CC de SGD" que ya pasó una vez en este proyecto.
            dbc.Row([
                dbc.Col([
                    html.Label("Control de calidad (CC) a incluir:", className="fw-bold"),
                    dcc.Checklist(
                        id="cl-cc",
                        options=[
                            {"label": " BUENO",  "value": "BUENO"},
                            {"label": " DUDOSO", "value": "DUDOSO"},
                            {"label": " MALO",   "value": "MALO"},
                        ],
                        value=["BUENO", "DUDOSO", "MALO"],   # por defecto, no filtra nada
                        inline=True,
                        labelStyle={"margin-right": "16px"},
                    ),
                ], md=6),
            ], className="g-2 mt-1"),

            html.Div(id="div-mensaje", className="mt-2 text-muted small"),
        ]),
        className="shadow-sm mb-3",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Pestañas
# ══════════════════════════════════════════════════════════════════════════════

def tabs_principales() -> dbc.Tabs:
    return dbc.Tabs(
        id="tabs-principales",
        active_tab="tab-estadistica",
        children=[
            dbc.Tab(label="Panorama", tab_id="tab-panorama"),
            dbc.Tab(label="Comparar", tab_id="tab-comparar"),
            dbc.Tab(label="Vista cruda", tab_id="tab-crudo"),
            dbc.Tab(label="Vecindad", tab_id="tab-vecindad"),
            dbc.Tab(label="Estadística", tab_id="tab-estadistica"),
        ],
        className="mb-3",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Layout principal
# ══════════════════════════════════════════════════════════════════════════════

def layout_principal() -> html.Div:
    return dbc.Container([
        html.Div([
            html.H4("Analizador de Series — Aseguramiento de Datos",
                    className="mt-3 mb-0"),
            html.P("SGR · SENAMHI · Explora series crudas y derivadas para descubrir "
                   "patrones operativos y umbrales empíricos de anomalía.",
                   className="text-muted small mb-3"),
        ]),
        selectores_compartidos(),
        tabs_principales(),
        dcc.Loading(html.Div(id="div-tab-content")),
        # Stores compartidos entre callbacks — en la raíz: sobreviven cualquier
        # cambio de pestaña sin recalcular.
        dcc.Store(id="store-df-cargado"),       # Estadística: una sola variable, filtrada por flags
        dcc.Store(id="store-derivadas"),        # Estadística: series derivadas de esa variable
        # Panorama/Comparar/Vista cruda: guarda solo la "receta" (códigos/periodo/
        # flags) — el DataFrame real se cachea en el servidor (ver
        # ui.callbacks._resolver_datos_crudos) para no viajar completo por red.
        dcc.Store(id="store-datos-crudos"),
        # Dispara una vez al cargar la página para poblar el dropdown de estaciones
        dcc.Interval(id="interval-inicio", interval=300, n_intervals=0, max_intervals=1),
        html.Footer(
            "Servicio Nacional de Meteorología e Hidrología del Perú — SENAMHI",
            className="text-muted small text-center mt-4 pt-3 border-top",
        ),
    ], fluid=True, className="px-3 pb-4")
