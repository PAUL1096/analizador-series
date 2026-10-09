"""
Tests de ui.tab_emplazamiento: formateo de opciones del dropdown de pares y que el
layout renderice sin excepción vacío o poblado. Ver tasks/todo.md Task 4.
"""
from __future__ import annotations

from analizador_series.ui import tab_emplazamiento


class TestOpcionesPares:
    def test_formatea_label_y_value(self):
        pares = [{"codigo_auto": "101004", "codigo_conv": "101098", "distancia_m": 0.0}]
        opts = tab_emplazamiento.opciones_pares(pares)
        assert opts == [{"label": "101004 ↔ 101098 · 0m", "value": "101004|101098"}]

    def test_redondea_distancia_a_entero(self):
        pares = [{"codigo_auto": "101004", "codigo_conv": "101098", "distancia_m": 42.6}]
        opts = tab_emplazamiento.opciones_pares(pares)
        assert opts[0]["label"] == "101004 ↔ 101098 · 43m"

    def test_lista_vacia_da_opciones_vacias(self):
        assert tab_emplazamiento.opciones_pares([]) == []


class TestLayout:
    def test_renderiza_sin_pares(self):
        layout = tab_emplazamiento.layout(pares_opts=[])
        assert layout is not None

    def test_renderiza_con_pares_poblados(self):
        opts = [{"label": "101004 ↔ 101098 · 0m", "value": "101004|101098"}]
        layout = tab_emplazamiento.layout(pares_opts=opts, par_value="101004|101098")
        assert layout is not None
