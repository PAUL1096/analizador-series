"""
Test de integración de los callbacks de Emplazamiento compartido, con CSVs sintéticos reales
(no el store server-side de Comparar/Panorama, que no aplica aquí — Emplazamiento compartido
carga directo con data_loader.cargar_estaciones).

Necesario porque, al momento de escribir esto, el único CSV convencional real
descargado localmente tenía bugs pre-existentes del loader (ver tasks/todo.md,
notas de verificación de Task 5 y Ronda 2) — no siempre sirve para probar el
camino feliz completo end-to-end.

Diseño de 4 gráficos + mensaje (Ronda 2, ver docs/SPEC-emplazamiento-compartido.md):
  Temperatura:   [1] horaria + horas sinópticas · [2] máx/mín diaria
                 [diff-1] dif. horas sinópticas · [diff-2] dif. diaria
  Precipitación: [1] acumulado diario           · [2] ventaneo 07h/19h
                 [diff-1] dif. acumulado diario · [diff-2] dif. ventaneo
"""
from __future__ import annotations

import dash
import pandas as pd
import pytest

from analizador_series.config import DIR_AUTO
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
        "Fecha,Hora,n_airtemp,n_lluvia,n_maxat,n_minat,n_dayrain\n"
        "2026-01-01,00:00,18.0,0.1,,,\n"
        "2026-01-01,07:00,15.5,0.1,,,\n"
        "2026-01-01,13:00,22.0,0.0,,,\n"
        "2026-01-01,19:00,17.0,0.0,,,\n"
        "2026-01-02,00:00,18.5,0.1,,,\n"
        "2026-01-02,07:00,16.0,0.1,30.0,14.0,0.5\n"
        "2026-01-03,00:00,19.0,0.0,,,\n",
        encoding="utf-8",
    )
    (dir_conv / "CONVTEST_2026-01-01_2026-01-05.csv").write_text(
        "Fecha,Hora,n_tm102,n_tm103,n_tm104,n_pt101,n_pt102,n_pt103\n"
        "2026-01-01,00:00,17.8,12.1,16.0,0.0,0.3,0.0\n"
        "2026-01-02,00:00,18.2,12.4,16.5,0.0,0.2,0.1\n"
        "2026-01-03,00:00,18.9,12.9,17.0,,,\n",
        encoding="utf-8",
    )
    # dash.Dash(__name__) para que @callback tenga un app context válido al
    # invocar la función directamente.
    dash.Dash(__name__)
    return dir_auto, dir_conv


CC_TODAS = ["BUENO", "DUDOSO", "MALO"]


class TestActualizarEmplazamientoTemperatura:
    def test_grafico1_horaria_mas_horas_sinopticas(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "temperatura", None, None, CC_TODAS
        )
        nombres = [t.name for t in fig1.data]
        assert "Temperatura del Aire" in nombres
        assert "07h" in nombres
        # Las diarias (máx/mín) NO van en este gráfico, quedan en el 2
        assert "Máxima diaria" not in nombres
        assert "Mínima diaria" not in nombres

    def test_grafico2_maxima_minima_diaria_incluye_automatica_real(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "temperatura", None, None, CC_TODAS
        )
        nombres = [t.name for t in fig2.data]
        assert "Máxima diaria" in nombres
        assert "Mínima diaria" in nombres
        # n_maxat/n_minat reales existen en el fixture -> sin nota de "calculado"
        assert any("Máxima (auto)" == n for n in nombres)
        assert not any("calculado por el Analizador" in n for n in nombres)
        simbolos = {t.name: t.marker.symbol for t in fig2.data}
        assert simbolos["Máxima diaria"] == "diamond"
        assert simbolos["Máxima (auto)"] == "diamond"

    def test_diff1_solo_horas_sinopticas(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "temperatura", None, None, CC_TODAS
        )
        nombres_diff1 = [t.name for t in diff1.data]
        assert nombres_diff1 == ["07h"]
        assert diff1.data[0].y[0] == pytest.approx(16.0 - 15.5)  # conv(07h) - auto(07h), día 1

    def test_diff2_solo_diarias(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "temperatura", None, None, CC_TODAS
        )
        nombres_diff2 = {t.name for t in diff2.data}
        assert nombres_diff2 == {"Máxima diaria", "Mínima diaria"}


class TestActualizarEmplazamientoPrecipitacion:
    def test_grafico1_acumulado_diario_incluye_ambas_fuentes(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "precipitacion", None, None, CC_TODAS
        )
        nombres = [t.name for t in fig1.data]
        assert "Total diaria" in nombres
        assert any(n.startswith("Acumulado diario (auto)") for n in nombres)
        # n_dayrain real existe en el fixture -> sin nota de "calculado"
        assert not any("calculado por el Analizador" in n for n in nombres)

    def test_grafico2_ventaneo_incluye_puntuales_y_ventanas_automatica(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "precipitacion", None, None, CC_TODAS
        )
        nombres = [t.name for t in fig2.data]
        assert "07h (nocturna 19h→07h)" in nombres
        assert "19h (diurna 07h→19h)" in nombres
        assert any("Nocturna" in n for n in nombres)
        assert any("Diurna" in n for n in nombres)

    def test_diff1_y_diff2_no_lanzan_error(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "AUTOTEST|CONVTEST", "precipitacion", None, None, CC_TODAS
        )
        assert diff1 is not None and diff2 is not None


class TestActualizarEmplazamientoCasosVacios:
    def test_sin_par_da_los_5_valores_vacios(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            None, "temperatura", None, None, CC_TODAS
        )
        assert mensaje == "Elige un par arriba."
        assert fig1 is not None and fig2 is not None and diff1 is not None and diff2 is not None

    def test_sin_datos_descargados_da_mensaje_claro(self, estaciones_sinteticas):
        fig1, fig2, diff1, diff2, mensaje = callbacks.actualizar_emplazamiento(
            "999999|888888", "temperatura", None, None, CC_TODAS
        )
        assert "sin datos descargados" in mensaje.lower()


@pytest.mark.skipif(
    not any(DIR_AUTO.glob("101004_*.csv")),
    reason="requiere el CSV real de 101004 en DATA/ (no versionado; ej. clon recién hecho)",
)
class TestChecklistCCEmplazamiento:
    """
    Verificación por backend con una estación REAL (101004, ya conocida por
    tener DUDOSO/MALO reales en n_airtemp), mismo patrón que las Tasks 9/10 de
    control-calidad. La convencional se fija a un código sin ningún CSV
    descargado (999999) para aislar el efecto del toggle sobre la automática.
    """

    def test_solo_bueno_excluye_los_dudoso_y_malo_reales(self):
        fig_todas, _, _, _, _ = callbacks.actualizar_emplazamiento(
            "101004|999999", "temperatura", None, None, ["BUENO", "DUDOSO", "MALO"]
        )
        fig_solo_bueno, _, _, _, _ = callbacks.actualizar_emplazamiento(
            "101004|999999", "temperatura", None, None, ["BUENO"]
        )
        n_todas = pd.notna(fig_todas.data[0].y).sum()
        n_solo_bueno = pd.notna(fig_solo_bueno.data[0].y).sum()
        # 30 DUDOSO + 19 MALO conocidos (ver resultado_control_calidad_estacion
        # de 101004) deben desaparecer al filtrar solo BUENO.
        assert n_todas - n_solo_bueno == 49


class TestActualizarPeriodoEmplazamiento:
    def test_calcula_min_max_start_end_de_ambas_estaciones(self, estaciones_sinteticas):
        fmin, fmax, inicio, fin = callbacks.actualizar_periodo_emplazamiento("AUTOTEST|CONVTEST")
        assert fmin is not None and fmax is not None
        assert fin == fmax

    def test_sin_par_da_todo_none(self, estaciones_sinteticas):
        assert callbacks.actualizar_periodo_emplazamiento(None) == (None, None, None, None)
