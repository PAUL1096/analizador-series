"""
Tests de ui.charts.overlay_multivar: extensión para vecindad (Task 3 de
tasks/todo.md) — extra_series gana "modo" (markers|lines) y "color" por
entrada, sin romper el uso actual en Comparar (callbacks.py:865, que no pasa
ninguna de las dos claves nuevas).
"""
from __future__ import annotations

import pandas as pd

from analizador_series.ui import charts


def _df_base():
    idx = pd.date_range("2026-01-01", periods=5, freq="h")
    return pd.DataFrame({"var1": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=idx)


class TestOverlayMultivarExtraSeriesSinRegresion:
    def test_extra_series_sin_modo_ni_color_se_ve_igual_que_antes(self):
        df = _df_base()
        extra_serie = pd.Series([1.0, 2.0], index=df.index[:2])
        fig = charts.overlay_multivar(
            df, "var1", None, {"display_name": "Var 1", "unidad": "u"}, None,
            extra_series=[{"nombre": "T-rocío (calc.)", "serie": extra_serie,
                            "eje": "y1", "dash": "dash"}],
        )
        traza_extra = fig.data[-1]
        assert traza_extra.mode in (None, "lines")
        assert traza_extra.line.color == "#2ca02c"


class TestOverlayMultivarModoMarkers:
    def test_modo_markers_no_dibuja_linea_conectora(self):
        df = _df_base()
        extra_serie = pd.Series([1.0, 2.0, 3.0], index=df.index[:3])
        fig = charts.overlay_multivar(
            df, "var1", None, {"display_name": "Var 1", "unidad": "u"}, None,
            extra_series=[{"nombre": "Convencional", "serie": extra_serie,
                            "eje": "y1", "modo": "markers", "color": "#111111"}],
        )
        traza_extra = fig.data[-1]
        assert traza_extra.mode == "markers"
        assert traza_extra.marker.color == "#111111"

    def test_color_distinto_por_entrada(self):
        df = _df_base()
        s1 = pd.Series([1.0, 2.0], index=df.index[:2])
        s2 = pd.Series([3.0, 4.0], index=df.index[:2])
        fig = charts.overlay_multivar(
            df, "var1", None, {"display_name": "Var 1", "unidad": "u"}, None,
            extra_series=[
                {"nombre": "A", "serie": s1, "eje": "y1", "modo": "markers", "color": "#111111"},
                {"nombre": "B", "serie": s2, "eje": "y1", "modo": "markers", "color": "#222222"},
            ],
        )
        colores = [t.marker.color for t in fig.data[-2:]]
        assert colores == ["#111111", "#222222"]
