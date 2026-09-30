"""
Test de integración de los callbacks de Vecindad (Task 5/6 de tasks/todo.md),
con CSVs sintéticos reales (no el store server-side de Comparar/Panorama,
que no aplica aquí — Vecindad carga directo con data_loader.cargar_estaciones).

Necesario porque, al momento de escribir esto, el único CSV convencional
real descargado localmente (104097) tiene el bug pre-existente documentado en
tasks/todo.md de control-calidad (Fecha/Hora inválidos) — no sirve para probar
el camino feliz completo (ver tasks/todo.md Task 5, nota de verificación).
"""
from __future__ import annotations

import dash
import pandas as pd
import pytest

from analizador_series.core import data_loader
from analizador_series.ui import callbacks


@pytest.fixture
def estaciones_sinteticas(tmp_path, monkeypatch):
    dir_auto = tmp_path / "automaticas"
    dir_conv = tmp_path / "convencionales"
    dir_auto.mkdir()
    dir_conv.mkdir()
    monkeypatch.setattr(data_loader, "DIR_AUTO", dir_auto)
    monkeypatch.setattr(data_loader, "DIR_CONV", dir_conv)

    (dir_auto / "AUTOTEST_2026-01-01_2026-01-05.csv").write_text(
        "Fecha,Hora,n_airtemp\n"
        "2026-01-01,00:00,18.0\n"
        "2026-01-02,00:00,18.5\n"
        "2026-01-03,00:00,19.0\n",
        encoding="utf-8",
    )
    (dir_conv / "CONVTEST_2026-01-01_2026-01-05.csv").write_text(
        "Fecha,Hora,n_tm102,n_tm103\n"
        "2026-01-01,00:00,17.8,12.1\n"
        "2026-01-02,00:00,18.2,12.4\n"
        "2026-01-03,00:00,18.9,12.9\n",
        encoding="utf-8",
    )
    # dash.Dash(__name__) para que @callback tenga un app context válido al
    # invocar la función directamente (mismo patrón usado en el smoke test
    # manual de Task 4/5).
    dash.Dash(__name__)
    return dir_auto, dir_conv


CC_TODAS = ["BUENO", "DUDOSO", "MALO"]


class TestActualizarVecindadCaminoFeliz:
    def test_grafica_linea_automatica_mas_puntos_convencional(self, estaciones_sinteticas):
        fig, mensaje = callbacks.actualizar_vecindad(
            "AUTOTEST|CONVTEST", "temperatura", None, None, CC_TODAS
        )
        assert mensaje == ""
        nombres_trazas = [t.name for t in fig.data]
        assert "n_tm102" in nombres_trazas
        assert "n_tm103" in nombres_trazas
        modos = {t.name: t.mode for t in fig.data if t.name in ("n_tm102", "n_tm103")}
        assert modos == {"n_tm102": "markers", "n_tm103": "markers"}

    def test_variable_fisica_precipitacion_sin_columnas_dispara_mensaje(self, estaciones_sinteticas):
        fig, mensaje = callbacks.actualizar_vecindad(
            "AUTOTEST|CONVTEST", "precipitacion", None, None, CC_TODAS
        )
        assert "no tiene" in mensaje.lower()


class TestChecklistCCVecindad:
    """
    Verificación por backend con una estación REAL (101004, ya conocida por
    tener DUDOSO/MALO reales en n_airtemp — ver memoria del proyecto y
    tasks/todo.md de control-calidad), mismo patrón que las Tasks 9/10 de
    control-calidad (`_resolver_datos_crudos` con distinto `cc=[...]`). La
    convencional se fija a un código sin ningún CSV descargado (999999) para
    aislar el efecto del toggle sobre la automática sin tropezar con el bug
    pre-existente del único CSV convencional real (ver Task 5, nota de
    verificación).
    """

    def test_solo_bueno_excluye_los_dudoso_y_malo_reales(self):
        fig_todas, _ = callbacks.actualizar_vecindad(
            "101004|999999", "temperatura", None, None, ["BUENO", "DUDOSO", "MALO"]
        )
        fig_solo_bueno, _ = callbacks.actualizar_vecindad(
            "101004|999999", "temperatura", None, None, ["BUENO"]
        )
        n_todas = pd.notna(fig_todas.data[0].y).sum()
        n_solo_bueno = pd.notna(fig_solo_bueno.data[0].y).sum()
        # 30 DUDOSO + 19 MALO conocidos (ver resultado_control_calidad_estacion
        # de 101004) deben desaparecer al filtrar solo BUENO.
        assert n_todas - n_solo_bueno == 49


class TestActualizarPeriodoVecindad:
    def test_calcula_min_max_start_end_de_ambas_estaciones(self, estaciones_sinteticas):
        fmin, fmax, inicio, fin = callbacks.actualizar_periodo_vecindad("AUTOTEST|CONVTEST")
        assert fmin is not None and fmax is not None
        assert fin == fmax

    def test_sin_par_da_todo_none(self, estaciones_sinteticas):
        assert callbacks.actualizar_periodo_vecindad(None) == (None, None, None, None)
