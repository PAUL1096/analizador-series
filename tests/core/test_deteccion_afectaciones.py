"""
Tests de core.deteccion_afectaciones sobre series sintéticas con firma
conocida. Un test por firma positiva + un test de serie limpia (sin firma,
guarda contra falsos positivos) por detector.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analizador_series.core import deteccion_afectaciones as da


def _serie(valores, freq="1h", inicio="2026-01-01"):
    idx = pd.date_range(inicio, periods=len(valores), freq=freq)
    return pd.Series(list(valores), index=idx, dtype=float)


# ══════════════════════════════════════════════════════════════════════════════
# cadencia_inferida
# ══════════════════════════════════════════════════════════════════════════════

class TestCadenciaInferida:
    def test_hourly(self):
        s = _serie(np.arange(10))
        assert da.cadencia_inferida(s) == pd.Timedelta(hours=1)

    def test_insuficiente(self):
        assert da.cadencia_inferida(_serie([1.0])) is None

    def test_serie_vacia(self):
        assert da.cadencia_inferida(pd.Series(dtype=float)) is None


# ══════════════════════════════════════════════════════════════════════════════
# AF-CST
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarCst:
    def test_flatline_dispara_alta(self):
        rng = np.random.default_rng(0)
        valores = list(rng.normal(20, 1, 5)) + [20.0] * 15
        s = _serie(valores)
        r = da.detectar_cst(s, duracion_min=180, duracion_alta_min=720)
        assert r and r["tipo"] == "AF-CST"
        assert r["severidad"] == "Alta"
        assert r["parametros"]["racha_pasos"] >= 14

    def test_meseta_corta_severidad_media(self):
        rng = np.random.default_rng(6)
        valores = list(rng.normal(20, 1, 10)) + [20.0] * 5 + list(rng.normal(20, 1, 10))
        s = _serie(valores)
        r = da.detectar_cst(s, duracion_min=180, duracion_alta_min=720)
        assert r and r["severidad"] == "Media"

    def test_serie_limpia_no_dispara(self):
        rng = np.random.default_rng(1)
        s = _serie(20 + rng.normal(0, 2, 48))
        assert da.detectar_cst(s, duracion_min=180, duracion_alta_min=720) == {}


# ══════════════════════════════════════════════════════════════════════════════
# AF-GAP
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarGap:
    def test_hueco_intermitente_dispara(self):
        idx_full = pd.date_range("2026-01-01", periods=100, freq="1h")
        mask = np.ones(100, dtype=bool)
        mask[40:52] = False   # 12 horas faltantes de 100 = 12%
        rng = np.random.default_rng(2)
        s = pd.Series(rng.normal(20, 1, mask.sum()), index=idx_full[mask])
        r = da.detectar_gap(s, umbral_frac=0.10, umbral_alta_frac=0.40)
        assert r and r["tipo"] == "AF-GAP"
        assert r["severidad"] == "Media"

    def test_no_dispara_por_cadencia_no_por_falla(self):
        # Variable horaria transmitida en archivo a 10 min: 5/6 de las filas
        # son NaN por construcción de grilla, no por falla. No debe disparar.
        idx_10m = pd.date_range("2026-01-01", periods=600, freq="10min")
        s = pd.Series(np.nan, index=idx_10m)
        rng = np.random.default_rng(3)
        s.iloc[::6] = rng.normal(50, 5, len(s.iloc[::6]))
        assert da.detectar_gap(s, umbral_frac=0.10, umbral_alta_frac=0.40) == {}

    def test_sin_huecos_no_dispara(self):
        s = _serie(np.random.default_rng(4).normal(20, 1, 50))
        assert da.detectar_gap(s, umbral_frac=0.10, umbral_alta_frac=0.40) == {}

    def test_no_dispara_por_desfase_de_fase_con_otra_variable(self):
        # Reproduce el bug real encontrado con datos de Puerto Pizarro: el
        # índice CRUDO de la serie (antes de dropna) puede empezar en un
        # timestamp que no es múltiplo de la cadencia real de ESTA variable
        # (viene de otra columna con grilla más fina fusionada en la misma
        # fila). Si la grilla esperada se ancla en serie.index.min() crudo en
        # vez de en la fase de los datos válidos, TODO punto válido "no calza"
        # con la grilla y dispara GAP/MISS falso sobre una serie horaria 100%
        # completa.
        idx_crudo = pd.date_range("2026-01-01 10:40", periods=180, freq="10min")
        s = pd.Series(np.nan, index=idx_crudo)
        marcas_horarias = idx_crudo[idx_crudo.minute == 0]
        rng = np.random.default_rng(9)
        s.loc[marcas_horarias] = rng.normal(70, 5, len(marcas_horarias))
        assert da.detectar_gap(s, umbral_frac=0.10, umbral_alta_frac=0.40) == {}
        assert da.detectar_miss(s, umbral_pct=0.80, racha_min_horas=24) == {}


# ══════════════════════════════════════════════════════════════════════════════
# AF-MISS
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarMiss:
    def test_racha_larga_dispara(self):
        rng = np.random.default_rng(5)
        valores = list(rng.normal(20, 1, 70)) + [np.nan] * 30
        s = _serie(valores)
        r = da.detectar_miss(s, umbral_pct=0.80, racha_min_horas=24)
        assert r and r["tipo"] == "AF-MISS" and r["severidad"] == "Alta"

    def test_completamente_vacia_dispara(self):
        s = _serie([np.nan] * 20)
        r = da.detectar_miss(s, umbral_pct=0.80, racha_min_horas=24)
        assert r and r["parametros"]["frac_nan_total"] == 1.0

    def test_huecos_dispersos_pequenos_no_disparan(self):
        rng = np.random.default_rng(7)
        valores = rng.normal(20, 1, 100)
        valores[::20] = np.nan   # 5% disperso, sin racha larga
        s = _serie(valores)
        assert da.detectar_miss(s, umbral_pct=0.80, racha_min_horas=24) == {}


# ══════════════════════════════════════════════════════════════════════════════
# AF-OUT
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarOut:
    def test_fuera_de_rango_fisico_dispara_alta(self):
        rng = np.random.default_rng(8)
        valores = rng.normal(50, 5, 20)
        valores[10] = 999.0
        s = _serie(valores)
        r = da.detectar_out(s, rango_fisico=(0, 100))
        assert r and r["severidad"] == "Alta" and r["parametros"]["n_fuera_rango"] == 1

    def test_salto_excesivo_sin_salir_de_rango_severidad_media(self):
        rng = np.random.default_rng(9)
        valores = list(rng.normal(20, 1, 20))
        valores[10] += 50
        s = _serie(valores)
        r = da.detectar_out(s, rango_fisico=(-100, 100), delta_max=10)
        assert r and r["severidad"] == "Media" and r["parametros"]["n_saltos"] >= 1

    def test_serie_limpia_no_dispara(self):
        s = _serie(np.random.default_rng(10).normal(20, 1, 30))
        assert da.detectar_out(s, rango_fisico=(-30, 50), delta_max=15) == {}


# ══════════════════════════════════════════════════════════════════════════════
# AF-NOIS
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarNois:
    def test_dispersion_anomala_dispara(self):
        rng = np.random.default_rng(11)
        base = rng.normal(20, 0.1, 60)
        ruido = rng.normal(20, 8, 20)
        valores = np.concatenate([base, ruido, base])
        s = _serie(valores)
        r = da.detectar_nois(s, ventana_min=600, z_umbral=3.0, z_umbral_alta=6.0)
        assert r and r["tipo"] == "AF-NOIS"

    def test_ruido_homogeneo_no_dispara(self):
        s = _serie(np.random.default_rng(12).normal(20, 1, 200))
        r = da.detectar_nois(s, ventana_min=600, z_umbral=4.0, z_umbral_alta=7.0)
        assert r == {}


# ══════════════════════════════════════════════════════════════════════════════
# AF-BIAS
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarBias:
    def test_escalon_dispara(self):
        rng = np.random.default_rng(13)
        seg1 = rng.normal(20, 0.5, 60)
        seg2 = rng.normal(30, 0.5, 60)
        s = _serie(np.concatenate([seg1, seg2]))
        r = da.detectar_bias(s, penalizacion=5, min_size_min=600)
        assert r and r["tipo"] == "AF-BIAS"
        assert r["parametros"]["salto_max"] > 5

    def test_serie_corta_no_lanza_excepcion(self):
        s = _serie(np.random.default_rng(14).normal(20, 1, 4))
        assert da.detectar_bias(s, min_size_min=600) == {}

    def test_serie_casi_todo_nan_no_lanza_excepcion(self):
        idx = pd.date_range("2026-01-01", periods=100, freq="1h")
        valores = [np.nan] * 100
        valores[0] = 20.0
        s = pd.Series(valores, index=idx)
        assert da.detectar_bias(s, min_size_min=600) == {}

    def test_serie_estable_no_dispara(self):
        s = _serie(np.random.default_rng(15).normal(20, 0.5, 120))
        assert da.detectar_bias(s, penalizacion=15, min_size_min=600) == {}


# ══════════════════════════════════════════════════════════════════════════════
# detectar_todas — agregador
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectarTodas:
    def test_variable_desconocida_usa_default(self):
        rng = np.random.default_rng(16)
        valores = list(rng.normal(20, 1, 5)) + [20.0] * 15
        s = _serie(valores)
        resultados = da.detectar_todas(s, "variable_inexistente", rango_fisico=(-30, 50))
        tipos = {r["tipo"] for r in resultados}
        assert "AF-CST" in tipos

    def test_incluir_bias_false_por_defecto(self):
        rng = np.random.default_rng(17)
        seg1 = rng.normal(20, 0.5, 60)
        seg2 = rng.normal(30, 0.5, 60)
        s = _serie(np.concatenate([seg1, seg2]))
        resultados = da.detectar_todas(s, "n_airtemp", rango_fisico=(-30, 50))
        assert all(r["tipo"] != "AF-BIAS" for r in resultados)

    def test_miss_excluye_indices_de_gap(self):
        rng = np.random.default_rng(18)
        valores = list(rng.normal(20, 1, 60)) + [np.nan] * 40
        s = _serie(valores)
        resultados = da.detectar_todas(s, "variable_inexistente", rango_fisico=(-30, 50))
        by_tipo = {r["tipo"]: r for r in resultados}
        assert "AF-MISS" in by_tipo
        if "AF-GAP" in by_tipo:
            idx_miss = set(by_tipo["AF-MISS"]["indices_afectados"])
            idx_gap = set(by_tipo["AF-GAP"]["indices_afectados"])
            assert not (idx_miss & idx_gap)
