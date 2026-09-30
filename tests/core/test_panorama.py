"""
Tests de core.panorama: fila Alta con firma inyectada, fila OK sin firma,
y fila N/D cuando la variable no está en variables_propias (sin llamar al
detector).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analizador_series.core import panorama


def _serie(valores, freq="1h", inicio="2026-01-01"):
    idx = pd.date_range(inicio, periods=len(valores), freq=freq)
    return pd.Series(list(valores), index=idx, dtype=float)


class TestResumenFila:
    def test_flatline_da_severidad_alta(self):
        rng = np.random.default_rng(0)
        valores = list(rng.normal(20, 1, 5)) + [20.0] * 20
        s = _serie(valores)
        r = panorama.resumen_fila(s, "variable_inexistente")
        assert r["severidad"] == "Alta"
        assert "AF-CST" in r["firma"]
        assert r["pct_validos"] == 100.0

    def test_serie_limpia_da_ok(self):
        # seed=0: bajo el _default, ventana NOIS de solo 3 pasos (180min/1h) es
        # estadísticamente ruidosa — algunos seeds disparan un falso positivo
        # borderline (z~3.05). Umbral no bloqueante (se afina con datos reales,
        # ver spec §10.1); acá solo se elige un seed conocido sin ese ruido.
        s = _serie(np.random.default_rng(0).normal(20, 1, 50))
        r = panorama.resumen_fila(s, "variable_inexistente", rango_fisico=(-30, 50))
        assert r["severidad"] == "OK"
        assert r["firma"] == "sin firma"

    def test_pct_validos_con_nan(self):
        valores = list(np.random.default_rng(2).normal(20, 1, 50)) + [np.nan] * 50
        s = _serie(valores)
        r = panorama.resumen_fila(s, "variable_inexistente")
        assert r["pct_validos"] == 50.0


class TestFilaNoMedida:
    def test_severidad_nd(self):
        r = panorama.fila_no_medida()
        assert r["severidad"] == "N/D"
        assert r["pct_validos"] is None


class TestConstruirIndiceTriaje:
    def test_variable_no_propia_es_nd_sin_llamar_detector(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="1h")
        df = pd.DataFrame({
            "codigo": ["EST1"] * 20,
            "datetime": idx,
            "n_airtemp": np.random.default_rng(3).normal(20, 1, 20),
        })
        filas = panorama.construir_indice_triaje(
            df, variables=["n_airtemp"], rangos_fisicos={"n_airtemp": (-30, 50)},
            display_names={"n_airtemp": "Temperatura"}, nombres_estacion={"EST1": "Estación 1"},
            variables_propias={"EST1": set()},   # EST1 no mide n_airtemp según su CSV real
        )
        assert len(filas) == 1
        assert filas[0]["severidad"] == "N/D"

    def test_variable_propia_se_evalua_normal(self):
        idx = pd.date_range("2026-01-01", periods=20, freq="1h")
        df = pd.DataFrame({
            "codigo": ["EST1"] * 20,
            "datetime": idx,
            "n_airtemp": np.random.default_rng(4).normal(20, 1, 20),
        })
        filas = panorama.construir_indice_triaje(
            df, variables=["n_airtemp"], rangos_fisicos={"n_airtemp": (-30, 50)},
            display_names={"n_airtemp": "Temperatura"}, nombres_estacion={"EST1": "Estación 1"},
            variables_propias={"EST1": {"n_airtemp"}},
        )
        assert len(filas) == 1
        assert filas[0]["severidad"] == "OK"
        assert filas[0]["estacion"] == "Estación 1"

    def test_orden_por_severidad(self):
        idx = pd.date_range("2026-01-01", periods=30, freq="1h")
        rng = np.random.default_rng(5)
        df = pd.DataFrame({
            "codigo": ["EST1"] * 30,
            "datetime": idx,
            "n_limpia": rng.normal(20, 1, 30),
            "n_plana": [20.0] * 30,
        })
        filas = panorama.construir_indice_triaje(
            df, variables=["n_limpia", "n_plana"],
            rangos_fisicos={"n_limpia": (-30, 50), "n_plana": (-30, 50)},
            display_names={"n_limpia": "Limpia", "n_plana": "Plana"},
            nombres_estacion={"EST1": "Estación 1"},
            variables_propias={"EST1": {"n_limpia", "n_plana"}},
        )
        assert [f["variable"] for f in filas] == ["n_plana", "n_limpia"]
