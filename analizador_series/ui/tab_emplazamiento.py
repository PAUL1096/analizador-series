"""
Pestaña Emplazamiento compartido — overlay visual de una estación automática con su
convencional co-ubicada (<100m), para inspección rápida (¿cuentan la misma
historia?). Sin estadística de comparación (fuera del alcance de esta herramienta).
Ver docs/SPEC-emplazamiento-compartido.md.

Independiente del selector compartido (dd-codigos/dt-periodo arriba): el
dropdown de pares se puebla directo desde core.emplazamiento.calcular_pares_colocados,
y el periodo es propio de esta pestaña (dt-periodo-emplazamiento) — mismo motivo que
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

# D = día calendario; t = instante horario. "real" = dato que SIGMA ya calculó
# y reporta (no lo calcula el Analizador); "calculado" = lo arma el Analizador
# solo cuando falta el real, siempre rotulado así también en la leyenda del
# gráfico. Ver core.emplazamiento y docs/SPEC-emplazamiento-compartido.md para el detalle completo.
# Versión corta (vive al lado del selector de periodo) — cambia según la
# variable física elegida, ver ui.callbacks.actualizar_disclaimer_emplazamiento.
DISCLAIMER_TEMPERATURA_MD = """
ℹ️ **Máx/mín diaria:** real (`n_maxat`/`n_minat`) o, si falta, el extremo de
los valores ya agregados por hora (`n_maxath`/`n_minath`) — nunca `n_airtemp`:
`Máx_calc(D) = máx{n_maxath(t): t∈D}`

**Horas sinópticas:** valor real en su hora exacta, sin cálculo.

**Diferencia** = Convencional − Automática.
"""

DISCLAIMER_PRECIPITACION_MD = """
ℹ️ **Acumulado diario:** real (`n_dayrain`) o, si falta:
`Acum_calc(D) = Σn_lluvia, t∈(07h D−1, 07h D]`
(`n_pt101` se muestra +1 día vs. su fecha cruda de SIGMA)

**Ventaneo 07h/19h:** siempre calculado:
`Noct(D)=Σn_lluvia(19h D−1→07h D)` · `Día(D)=Σn_lluvia(07h D→19h D)`

**Diferencia** = Convencional − Automática.
"""


def opciones_pares(pares: list[dict], nombres: dict[str, str] | None = None) -> list[dict]:
    """[{"codigo_auto","codigo_conv","distancia_m"}] -> opciones de dcc.Dropdown,
    value codifica el par como "{codigo_auto}|{codigo_conv}". `nombres` (opcional,
    {codigo: nombre}) agrega el nombre de cada estación a la etiqueta — el código
    solo no se reconoce rápido a simple vista (pedido del usuario, 2026-10-01)."""
    nombres = nombres or {}

    def _etq(codigo: str) -> str:
        nombre = nombres.get(codigo)
        return f"{codigo} · {nombre}" if nombre else codigo

    return [
        {
            "label": f"{_etq(p['codigo_auto'])} ↔ {_etq(p['codigo_conv'])} · {p['distancia_m']:.0f}m",
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
                            id="dd-emplazamiento-par", options=pares_opts or [],
                            value=par_value, clearable=False, searchable=True,
                            placeholder="Elige un par por código o distancia…",
                        ),
                    ], md=5),
                    dbc.Col([
                        html.Label("Variable física:", className="fw-bold"),
                        dbc.RadioItems(
                            id="rb-emplazamiento-variable", options=VARIABLE_OPTIONS,
                            value="temperatura",
                            className="btn-group", inputClassName="btn-check",
                            labelClassName="btn btn-outline-primary btn-sm",
                            labelCheckedClassName="active",
                        ),
                    ], md=3),
                    dbc.Col([
                        html.Label("Periodo:", className="fw-bold"),
                        dcc.DatePickerRange(
                            id="dt-periodo-emplazamiento",
                            display_format="YYYY-MM-DD",
                            clearable=True,
                        ),
                    ], md=4),
                ], className="g-2 align-items-start"),

                # Disclaimer en su propia fila, ancho completo — antes vivía apretado
                # dentro de la columna de Periodo (md=4) y esa columna, al ser la más
                # alta del Row (texto de 3-4 líneas vs. un dropdown/toggle de 1 línea
                # en las otras dos), dejaba un hueco en blanco debajo de "Par
                # co-ubicado" y "Variable física" (el Row completo toma la altura del
                # hijo más alto). Separarlo en su propia fila evita el hueco Y le da
                # más ancho real al texto técnico.
                dbc.Row([
                    dbc.Col(
                        html.Div(
                            dcc.Markdown(DISCLAIMER_TEMPERATURA_MD, className="small text-muted mb-0"),
                            id="div-emplazamiento-disclaimer", className="emplazamiento-disclaimer",
                        ),
                    ),
                ], className="g-2 mt-1"),

                dbc.Row([
                    dbc.Col([
                        html.Label("Control de calidad (CC) a incluir:", className="fw-bold"),
                        dcc.Checklist(
                            id="cl-cc-emplazamiento",
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

                html.Div(id="div-emplazamiento-mensaje", className="text-muted small mt-2"),
            ]),
            className="shadow-sm mb-3",
        ),

        # 4 gráficos genéricos — el callback decide qué va en cada uno según
        # la variable física elegida (Ronda 2, ver docs/SPEC-emplazamiento-compartido.md):
        #   Temperatura:   [1] horaria + horas sinópticas · [2] máx/mín diaria
        #                  [diff-1] dif. horas sinópticas · [diff-2] dif. diaria
        #   Precipitación: [1] acumulado diario           · [2] ventaneo 07h/19h
        #                  [diff-1] dif. acumulado diario · [diff-2] dif. ventaneo
        dbc.Card(
            dbc.CardBody([dcc.Loading(dcc.Graph(id="g-emplazamiento-1", config={"displaylogo": False}))]),
            className="shadow-sm mb-3",
        ),
        dbc.Card(
            dbc.CardBody([dcc.Loading(dcc.Graph(id="g-emplazamiento-2", config={"displaylogo": False}))]),
            className="shadow-sm mb-3",
        ),
        dbc.Row([
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([dcc.Loading(dcc.Graph(id="g-emplazamiento-diff-1", config={"displaylogo": False}))]),
                    className="shadow-sm mb-3",
                ),
                md=6,
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([dcc.Loading(dcc.Graph(id="g-emplazamiento-diff-2", config={"displaylogo": False}))]),
                    className="shadow-sm mb-3",
                ),
                md=6,
            ),
        ]),
    ])
