"""
Pestaña Vista cruda — layout mitad/mitad:
  - Izquierda (más ancha): series de tiempo crudas de las variables que el
    usuario tilda en el selector — sin el aparataje estadístico de la
    pestaña Estadística (sin derivadas, sin histogramas, sin percentiles).
  - Derecha: "día efectivo" de TODAS las variables propias de la estación
    (no solo las tildadas a la izquierda), como mapa de calor compacto —
    una estación puede tener 40+ sensores; apilar uno-un-subgráfico-por-
    variable ahí sería una columna larguísima, así que ese chequeo vive
    aparte, en una fila por sensor en vez de un panel completo por sensor.

Dos chequeos de core.dias_efectivos (ver docstring del módulo para el
porqué de la separación):
  - "Día efectivo": mapa de calor a la derecha (día calendario, simplificación
    documentada — no la convención meteorológica exacta).
  - "Concordancia": si un valor diario nativo (Tmax/Tmin/precipitación
    diaria) tiene <75% de respaldo horario detrás, se lista aparte, en la
    tabla-resumen bajo el mapa de calor.

Ver ui/callbacks.py: actualizar_grafico_crudo, poblar_variables_crudo.
"""
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc


DISCLAIMER = (
    "Un día se marca NO efectivo (banda gris) si se recibió menos del 75% de las lecturas "
    "esperadas para esa variable, según su cadencia real — bajo ese umbral un promedio diario "
    "no es representativo. Variables nativamente diarias (Tmax/Tmin, precipitación diaria "
    "acumulada) se excluyen por defecto de este cálculo — actívalas con el switch de abajo. "
    "\"Día\" se define acá como día calendario (medianoche a medianoche): es una simplificación "
    "para exploración visual, pendiente de confirmar contra la convención meteorológica "
    "institucional exacta. El chequeo de concordancia (tabla de abajo) no depende de esa "
    "simplificación: compara cada valor diario nativo contra las 24h reales que le preceden. "
    "El panel de día efectivo (derecha) es independiente del \"Periodo\" y los \"Flags a incluir\" "
    "elegidos arriba: siempre muestra el histórico completo de la estación calculado sobre datos "
    "correctos (C), precalculado y guardado — cambiar el periodo no lo recalcula. "
    "Las variables marcadas \"(CC)\" en el selector de abajo tienen reglas de Control de Calidad "
    "definidas (no todas las tienen todavía): sus puntos DUDOSO/MALO se resaltan en el "
    "gráfico (naranja/rojo oscuro, pasar el mouse muestra qué regla lo objeta), y el toggle "
    "\"Control de calidad (CC)\" de arriba filtra sobre ellas — es una capa aparte del flag de SIGMA."
)


def layout(estacion_opts: list[dict] | None = None, estacion_value: str | None = None) -> html.Div:
    return html.Div([
        dbc.Card(
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("Estación:", className="fw-bold"),
                        dcc.Dropdown(
                            id="dd-crudo-estacion", options=estacion_opts or [],
                            value=estacion_value, clearable=False,
                            placeholder="Elige una de las estaciones seleccionadas arriba…",
                        ),
                    ], md=3),
                    dbc.Col(
                        dbc.Checkbox(
                            id="chk-crudo-incluir-diarias",
                            label="Incluir variables diarias nativas (Tmax/Tmin/precipitación diaria)",
                            value=False,
                        ),
                        md="auto", className="align-self-end",
                    ),
                ], className="g-2 align-items-end"),

                dbc.Alert(DISCLAIMER, id="div-crudo-disclaimer", color="light",
                          className="small mt-3 mb-2"),
                html.Div(id="div-crudo-mensaje", className="text-muted small mb-2"),
            ]),
            className="shadow-sm mb-3",
        ),

        dbc.Row([
            # ── Izquierda (más ancha): series de las variables tildadas ────────
            dbc.Col([
                dbc.Card(
                    dbc.CardBody([
                        html.Label("Variables a graficar:", className="fw-bold small mb-1"),
                        dcc.Checklist(
                            id="cl-crudo-variables", options=[], value=[],
                            inline=True, labelStyle={"margin-right": "14px"},
                            className="small mb-2",
                        ),
                        dcc.Loading(dcc.Graph(id="g-crudo", config={"displaylogo": False})),
                    ]),
                    className="shadow-sm mb-3",
                ),
            ], md=7),

            # ── Derecha (más angosta): día efectivo de TODOS los sensores ─────
            dbc.Col([
                dbc.Card(
                    dbc.CardBody([
                        dcc.Loading(dcc.Graph(id="g-crudo-dias-efectivos",
                                               config={"displaylogo": False})),
                        html.Div(id="div-crudo-dias-efectivos-mensaje",
                                 className="text-muted small"),
                    ]),
                    className="shadow-sm mb-3",
                ),
                dbc.Card(
                    dbc.CardBody([
                        html.H6("Resumen por variable (sensor/instrumento)",
                                className="text-muted mb-2"),
                        html.Div(id="div-crudo-resumen"),
                    ]),
                    className="shadow-sm mb-3",
                ),
            ], md=5),
        ], className="g-3"),
    ])
