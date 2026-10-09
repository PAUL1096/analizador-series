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


MARCA_CC = "⚑"

# Lo que antes era un solo párrafo largo, en viñetas y dentro de una sección
# plegable: se conserva todo el contenido, pero no ocupa la pantalla.
COMO_LEER = [
    "Las series respetan el Periodo, la calificación de SIGMA y el control de calidad "
    "elegidos arriba.",
    "Panel «Días completos» (derecha): verde = llegó al menos el 75 % de las lecturas "
    "esperadas para esa variable según su frecuencia; gris = menos que eso (un promedio "
    "diario ya no sería representativo); blanco = sin datos.",
    "Ese panel muestra siempre TODO el historial de la estación, solo con datos "
    "Correctos (C) de SIGMA, sin importar el periodo elegido. Se calcula una vez y se "
    "guarda.",
    "«Día» se toma como día calendario (00 h a 00 h). Es una simplificación para "
    "explorar; falta confirmarla contra la convención meteorológica institucional.",
    "Las variables que ya vienen como valor diario (Tmáx/Tmín, precipitación diaria) "
    "no entran en «días completos» salvo que actives la casilla de arriba.",
    "«% coincidencia del valor diario» compara cada valor diario contra las 24 h de "
    "datos horarios que lo preceden; no depende de la simplificación del día calendario.",
    f"Las variables marcadas con {MARCA_CC} tienen reglas del control de calidad del "
    "Analizador (no todas las tienen todavía). Sus valores Dudoso y Malo se resaltan en "
    "naranja y rojo oscuro.",
]


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
                            label="Incluir en «días completos» las variables que ya vienen como "
                                  "valor diario (Tmáx/Tmín, precipitación diaria)",
                            value=False,
                        ),
                        md="auto", className="align-self-end",
                    ),
                ], className="g-2 align-items-end"),

                html.Div(
                    "Series tal como llegan de SIGMA, una debajo de otra. A la derecha, qué días "
                    "llegaron completos y un resumen por variable.",
                    className="small text-muted mt-2",
                ),
                dbc.Accordion([
                    dbc.AccordionItem(
                        html.Ul([html.Li(t) for t in COMO_LEER], className="small mb-0"),
                        title="¿Cómo leer esta pestaña?",
                    ),
                ], start_collapsed=True, flush=True, id="div-crudo-disclaimer", className="mt-2 mb-2"),
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
                            className="small mb-1",
                        ),
                        html.Div(
                            f"{MARCA_CC} = la variable tiene reglas del control de calidad del "
                            "Analizador: sus valores Dudoso/Malo se resaltan en el gráfico (pasa el "
                            "mouse para ver qué regla los objeta).",
                            className="text-muted mb-2", style={"fontSize": "0.75rem"},
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
                        html.H6("Resumen por variable", className="text-muted mb-2"),
                        html.Div(id="div-crudo-resumen"),
                    ]),
                    className="shadow-sm mb-3",
                ),
            ], md=5),
        ], className="g-3"),
    ])
