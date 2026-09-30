"""
Pestaña Panorama — índice de triaje AF-* (dash-ag-grid) + panel alineado.

La tabla se llena desde core.panorama.construir_indice_triaje (ver
ui/callbacks.py: actualizar_tabla_panorama). Marcar filas (checkbox) abre su
tira en el panel de abajo (actualizar_panel_panorama), que reusa
ui.charts.panel_alineado_panorama con altura fija por panel.
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc
import dash_ag_grid as dag


COLUMN_DEFS = [
    {"field": "severidad", "headerName": "Severidad", "width": 120,
     "cellClassRules": {
         "text-danger fw-bold": "params.value == 'Alta'",
         "text-warning fw-bold": "params.value == 'Media'",
         "text-muted": "params.value == 'OK' || params.value == 'N/D'",
     }},
    {"field": "estacion", "headerName": "Estación", "flex": 1.1},
    {"field": "variable_label", "headerName": "Variable", "flex": 1.4},
    {"field": "firma", "headerName": "Firma AF-*", "flex": 1.6},
    {"field": "pct_validos", "headerName": "% válidos", "width": 110,
     "valueFormatter": {"function": "params.value != null ? params.value.toFixed(1) + '%' : '—'"}},
    {"field": "cadencia", "headerName": "Cadencia", "width": 110},
]

GRID_OPTIONS = {
    "rowSelection": {"mode": "multiRow", "checkboxes": True,
                      "headerCheckbox": True, "enableClickSelection": True},
    "domLayout": "autoHeight",
}


def layout() -> html.Div:
    return html.Div([
        dbc.Card(
            dbc.CardBody([
                dbc.Row([
                    dbc.Col(html.H6("Índice de triaje", className="text-muted mb-0"), width="auto"),
                    dbc.Col(
                        dbc.Checkbox(id="chk-incluir-bias",
                                     label="Incluir AF-BIAS (más lento)", value=False),
                        width="auto", className="ms-auto",
                    ),
                ], className="align-items-center mb-2", justify="between"),
                html.Div(id="div-panorama-mensaje", className="text-muted small mb-2"),
                dcc.Loading(dag.AgGrid(
                    id="tabla-panorama",
                    columnDefs=COLUMN_DEFS,
                    rowData=[],
                    dashGridOptions=GRID_OPTIONS,
                    defaultColDef={"resizable": True, "sortable": True, "filter": True},
                    getRowStyle={"styleConditions": [
                        {"condition": "params.data.severidad == 'Alta'",
                         "style": {"backgroundColor": "#fdecea"}},
                        {"condition": "params.data.severidad == 'Media'",
                         "style": {"backgroundColor": "#fff8e1"}},
                        {"condition": "params.data.severidad == 'N/D'",
                         "style": {"backgroundColor": "#f5f5f5", "color": "#999"}},
                    ]},
                    className="ag-theme-alpine",
                )),
            ]),
            className="shadow-sm mb-3",
        ),

        dbc.Card(
            dbc.CardBody([
                html.H6("Panel alineado — variables marcadas", className="text-muted mb-2"),
                html.Div(id="div-panel-panorama"),
            ]),
            className="shadow-sm mb-3",
        ),
    ])
