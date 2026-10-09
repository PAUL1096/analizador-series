"""
Tests de ui.charts.overlay_multivar: extensión para emplazamiento compartido (Task 3 de
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

    def test_symbol_por_defecto_es_circle(self):
        df = _df_base()
        extra_serie = pd.Series([1.0, 2.0], index=df.index[:2])
        fig = charts.overlay_multivar(
            df, "var1", None, {"display_name": "Var 1", "unidad": "u"}, None,
            extra_series=[{"nombre": "A", "serie": extra_serie, "eje": "y1", "modo": "markers"}],
        )
        assert fig.data[-1].marker.symbol == "circle"

    def test_symbol_explicito_diamond(self):
        df = _df_base()
        extra_serie = pd.Series([1.0, 2.0], index=df.index[:2])
        fig = charts.overlay_multivar(
            df, "var1", None, {"display_name": "Var 1", "unidad": "u"}, None,
            extra_series=[{"nombre": "A", "serie": extra_serie, "eje": "y1",
                            "modo": "markers", "symbol": "diamond"}],
        )
        assert fig.data[-1].marker.symbol == "diamond"


class TestPanelDiferenciasEmplazamiento:
    def test_una_traza_de_barras_por_entrada_con_su_color(self):
        idx = pd.date_range("2026-01-01", periods=3, freq="D")
        serie = pd.Series([0.5, -0.3, 1.1], index=idx)
        fig = charts.panel_diferencias_emplazamiento(
            [{"nombre": "07h", "serie": serie, "color": "#d62728"}]
        )
        assert fig.data[0].type == "bar"
        assert fig.data[0].marker.color == "#d62728"
        assert list(fig.data[0].y) == [0.5, -0.3, 1.1]

    def test_varias_entradas_dan_varias_trazas(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        s1 = pd.Series([1.0, 2.0], index=idx)
        s2 = pd.Series([-1.0, -2.0], index=idx)
        fig = charts.panel_diferencias_emplazamiento([
            {"nombre": "07h", "serie": s1, "color": "#111111"},
            {"nombre": "19h", "serie": s2, "color": "#222222"},
        ])
        assert len(fig.data) == 2

    def test_lista_vacia_no_lanza_error(self):
        fig = charts.panel_diferencias_emplazamiento([])
        assert fig is not None


class TestSeriePuntosDiarios:
    """Gráfico genérico para comparar N series diarias (máx/mín temperatura,
    acumulado precipitación) sin una curva continua de base — a diferencia de
    overlay_multivar, acá ninguna serie es "la principal"."""

    def test_una_traza_por_entrada_con_su_color_y_simbolo(self):
        idx = pd.date_range("2026-01-01", periods=3, freq="D")
        serie = pd.Series([30.0, 31.0, 29.0], index=idx)
        fig = charts.serie_puntos_diarios(
            [{"nombre": "Máxima (auto)", "serie": serie, "color": "#d62728", "symbol": "diamond"}]
        )
        assert fig.data[0].mode == "markers"
        assert fig.data[0].marker.color == "#d62728"
        assert fig.data[0].marker.symbol == "diamond"
        assert list(fig.data[0].y) == [30.0, 31.0, 29.0]

    def test_modo_lines_markers_conecta_la_serie(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        serie = pd.Series([1.0, 2.0], index=idx)
        fig = charts.serie_puntos_diarios(
            [{"nombre": "A", "serie": serie, "color": "#111", "modo": "lines+markers"}]
        )
        assert fig.data[0].mode == "lines+markers"

    def test_varias_entradas_dan_varias_trazas(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        s1 = pd.Series([1.0, 2.0], index=idx)
        s2 = pd.Series([3.0, 4.0], index=idx)
        fig = charts.serie_puntos_diarios([
            {"nombre": "A", "serie": s1, "color": "#111"},
            {"nombre": "B", "serie": s2, "color": "#222"},
        ])
        assert len(fig.data) == 2

    def test_lista_vacia_no_lanza_error(self):
        assert charts.serie_puntos_diarios([]) is not None
