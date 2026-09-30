"""
Tests de core.consistencia: punto_de_rocio contra valores de referencia
conocidos + un caso con violación y un caso coherente por cada chequeo
cruzado (T-rocío, HR-lluvia, veleta trabada, Tmax/Tmin/T).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analizador_series.core import consistencia as co


def _serie(valores, freq="1h", inicio="2026-01-01"):
    idx = pd.date_range(inicio, periods=len(valores), freq=freq)
    return pd.Series(list(valores), index=idx, dtype=float)


# ══════════════════════════════════════════════════════════════════════════════
# punto_de_rocio (Magnus) — valores de referencia calculados independientemente
# ══════════════════════════════════════════════════════════════════════════════

class TestPuntoDeRocio:
    def test_valores_referencia(self):
        assert abs(co.punto_de_rocio(25.0, 50.0) - 13.85) < 0.05
        assert abs(co.punto_de_rocio(20.0, 100.0) - 20.0) < 0.05
        assert abs(co.punto_de_rocio(30.0, 80.0) - 26.17) < 0.05
        assert abs(co.punto_de_rocio(15.0, 40.0) - 1.49) < 0.05

    def test_acepta_series(self):
        t = pd.Series([25.0, 20.0])
        hr = pd.Series([50.0, 100.0])
        td = co.punto_de_rocio(t, hr)
        assert abs(td[0] - 13.85) < 0.05
        assert abs(td[1] - 20.0) < 0.05


# ══════════════════════════════════════════════════════════════════════════════
# Preset T vs T-rocío
# ══════════════════════════════════════════════════════════════════════════════

class TestChequeoTempRocio:
    def test_td_mayor_a_t_dispara(self):
        # HR imposiblemente alta relativa a T (dato corrupto): Td calculado > T
        t = _serie([20.0] * 10)
        hr = _serie([150.0] * 10)   # HR fuera de [0,100] -> Magnus da Td > T
        r = co.chequeo_temp_rocio(t, hr)
        assert r["pct_violacion"] > 0

    def test_coherente_no_dispara(self):
        rng = np.random.default_rng(20)
        t = _serie(rng.normal(25, 3, 30))
        hr = _serie(rng.uniform(40, 90, 30))
        r = co.chequeo_temp_rocio(t, hr)
        assert r["pct_violacion"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Preset HR vs Lluvia
# ══════════════════════════════════════════════════════════════════════════════

class TestChequeoHrLluvia:
    def test_hr_saturada_sin_lluvia_dispara(self):
        hr = _serie([99.0] * 20)
        lluvia = _serie([0.0] * 20)
        r = co.chequeo_hr_lluvia(hr, lluvia)
        assert r["n_hr_saturada_sin_lluvia"] == 20

    def test_lluvia_con_hr_baja_dispara(self):
        hr = _serie([30.0] * 10)
        lluvia = _serie([5.0] * 10)
        r = co.chequeo_hr_lluvia(hr, lluvia)
        assert r["n_lluvia_con_hr_baja"] == 10

    def test_coherente_no_dispara(self):
        hr = _serie([70.0] * 10)
        lluvia = _serie([0.0] * 10)
        r = co.chequeo_hr_lluvia(hr, lluvia)
        assert r["pct_violacion"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Preset veleta trabada
# ══════════════════════════════════════════════════════════════════════════════

class TestChequeoVeletaTrabada:
    def test_direccion_constante_con_viento_dispara(self):
        direccion = _serie([180.0] * 20)
        velocidad = _serie([5.0] * 20)
        r = co.chequeo_veleta_trabada(direccion, velocidad, duracion_min=180, duracion_alta_min=720)
        assert r["pct_violacion"] > 0

    def test_direccion_constante_viento_calmo_no_dispara(self):
        direccion = _serie([180.0] * 20)
        velocidad = _serie([0.0] * 20)
        r = co.chequeo_veleta_trabada(direccion, velocidad, duracion_min=180, duracion_alta_min=720)
        assert r["pct_violacion"] == 0.0

    def test_direccion_variable_no_dispara(self):
        rng = np.random.default_rng(21)
        direccion = _serie(rng.uniform(0, 360, 20))
        velocidad = _serie(rng.uniform(1, 10, 20))
        r = co.chequeo_veleta_trabada(direccion, velocidad, duracion_min=180, duracion_alta_min=720)
        assert r["pct_violacion"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Preset Tmax/Tmin/T
# ══════════════════════════════════════════════════════════════════════════════

class TestChequeoTmaxTminT:
    def test_t_fuera_de_rango_diario_dispara(self):
        idx = pd.date_range("2026-01-01", periods=24, freq="1h")
        t = pd.Series([25.0] * 24, index=idx)
        t.iloc[12] = 40.0   # excede Tmax del día
        dia = pd.Timestamp("2026-01-01")
        tmax = pd.Series([30.0], index=[dia])
        tmin = pd.Series([15.0], index=[dia])
        r = co.chequeo_tmax_tmin_t(t, tmax, tmin)
        assert r["pct_violacion"] > 0

    def test_tmax_menor_tmin_dispara_inconsistencia(self):
        idx = pd.date_range("2026-01-01", periods=24, freq="1h")
        t = pd.Series([20.0] * 24, index=idx)
        dia = pd.Timestamp("2026-01-01")
        tmax = pd.Series([10.0], index=[dia])   # invertido
        tmin = pd.Series([15.0], index=[dia])
        r = co.chequeo_tmax_tmin_t(t, tmax, tmin)
        assert r["dias_tmax_menor_tmin"] == 1

    def test_coherente_no_dispara(self):
        idx = pd.date_range("2026-01-01", periods=24, freq="1h")
        rng = np.random.default_rng(22)
        t = pd.Series(20 + rng.normal(0, 1, 24), index=idx)
        dia = pd.Timestamp("2026-01-01")
        tmax = pd.Series([float(t.max() + 1)], index=[dia])
        tmin = pd.Series([float(t.min() - 1)], index=[dia])
        r = co.chequeo_tmax_tmin_t(t, tmax, tmin)
        assert r["pct_violacion"] == 0.0
        assert r["dias_tmax_menor_tmin"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Presets de Comparar
# ══════════════════════════════════════════════════════════════════════════════

class TestResolverVariables:
    def test_prefiere_variable_sin_sufijo_inst_cuando_ambas_presentes(self):
        # Deliberado: si algún día esto se revierte, que sea a propósito
        # (ver nota junto a PRESETS en consistencia.py) y no un accidente al
        # reordenar la lista de candidatos. "hr" acá solo tiene el candidato
        # "_inst" disponible -> debe caer a ese, no quedar sin resolver.
        cols = {"n_airtemp_inst", "n_airtemp", "n_humedad_inst"}
        r = co.resolver_variables("temp_rocio", cols)
        assert r == {"t": "n_airtemp", "hr": "n_humedad_inst"}

    def test_cae_al_segundo_candidato(self):
        cols = {"n_airtemp", "n_humedad"}
        r = co.resolver_variables("temp_rocio", cols)
        assert r == {"t": "n_airtemp", "hr": "n_humedad"}

    def test_ningun_candidato_presente(self):
        cols = {"n_lluvia"}
        r = co.resolver_variables("temp_rocio", cols)
        assert r == {"t": None, "hr": None}

    def test_no_mezcla_maxat_con_maxath(self):
        # n_maxath es máx/mín HORARIA, no debe resolver el rol "tmax" (diaria)
        cols = {"n_airtemp", "n_maxath", "n_minath"}
        r = co.resolver_variables("tmax_tmin", cols)
        assert r["tmax"] is None
        assert r["tmin"] is None

    def test_roles_faltantes(self):
        resueltas = {"t": "n_airtemp", "tmax": None, "tmin": None}
        assert set(co.roles_faltantes(resueltas)) == {"tmax", "tmin"}

    def test_sin_faltantes(self):
        resueltas = {"t": "n_airtemp", "hr": "n_humedad"}
        assert co.roles_faltantes(resueltas) == []


class TestEjecutarPreset:
    def test_temp_rocio_despacha_correctamente(self):
        t = _serie([20.0] * 10)
        hr = _serie([150.0] * 10)
        r = co.ejecutar_preset("temp_rocio", {"t": t, "hr": hr})
        assert r["pct_violacion"] > 0

    def test_tmax_tmin_despacha_correctamente(self):
        idx = pd.date_range("2026-01-01", periods=24, freq="1h")
        t = pd.Series([40.0] * 24, index=idx)
        dia = pd.Timestamp("2026-01-01")
        tmax = pd.Series([30.0], index=[dia])
        tmin = pd.Series([15.0], index=[dia])
        r = co.ejecutar_preset("tmax_tmin", {"t": t, "tmax": tmax, "tmin": tmin})
        assert r["pct_violacion"] > 0

    def test_preset_desconocido_retorna_vacio(self):
        assert co.ejecutar_preset("no_existe", {}) == {}
