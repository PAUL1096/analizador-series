"""
Tests de core.control_calidad — CC local del Analizador (ver docs/SPEC-control-calidad.md).
Casos límite exactos de las subreglas citadas en config/control_calidad.yaml.
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
import pytest

from analizador_series.core import control_calidad as cc


def _serie(valores, freq="1h", inicio="2026-01-01"):
    idx = pd.date_range(inicio, periods=len(valores), freq=freq)
    return pd.Series(list(valores), index=idx, dtype=float)


class TestEvaluarLimitesDurosAutomatica:
    def test_dentro_de_rango_es_bueno(self):
        s = _serie([20.0, 25.0, -10.0])  # n_airtemp: -40 a 50
        r = cc.evaluar_limites_duros_automatica(s, "n_airtemp")
        assert (r == cc.BUENO).all()

    def test_fuera_de_rango_es_malo(self):
        s = _serie([20.0, 55.0, -45.0])  # ambos fuera de -40/50
        r = cc.evaluar_limites_duros_automatica(s, "n_airtemp")
        assert r.iloc[0] == cc.BUENO
        assert r.iloc[1] == cc.MALO
        assert r.iloc[2] == cc.MALO

    def test_borde_exacto_es_bueno(self):
        s = _serie([-40.0, 50.0])
        r = cc.evaluar_limites_duros_automatica(s, "n_airtemp")
        assert (r == cc.BUENO).all()

    def test_precipitacion_horaria_usa_el_mas_estricto_401_no_500(self):
        # n_lluvia: MT-DRD-002 (401) es más estricto que MT-DRD-001 (500)
        s = _serie([300.0, 450.0])
        r = cc.evaluar_limites_duros_automatica(s, "n_lluvia")
        assert r.iloc[0] == cc.BUENO
        assert r.iloc[1] == cc.MALO

    def test_intensidad_lluvia_cero_es_bueno_no_malo(self):
        # min real es 0, no el 0.02 de MT-DRD-001 (ese es umbral de detección
        # del sensor con lluvia activa, no un piso físico) -- la mayoría de
        # lecturas son "no llueve" (0) y no deben marcarse MALO.
        s = _serie([0.0, 0.0, 0.0])
        r = cc.evaluar_limites_duros_automatica(s, "n_int_lluvia")
        assert (r == cc.BUENO).all()

    def test_precipitacion_diaria_acumulada_508_es_el_limite(self):
        s = _serie([500.0, 510.0], freq="1D")
        r = cc.evaluar_limites_duros_automatica(s, "n_dayrain")
        assert r.iloc[0] == cc.BUENO
        assert r.iloc[1] == cc.MALO

    def test_variable_sin_config_es_siempre_bueno(self):
        s = _serie([9999.0, -9999.0])
        r = cc.evaluar_limites_duros_automatica(s, "n_variable_inexistente")
        assert (r == cc.BUENO).all()


class TestEvaluarPruebaPaso:
    def test_temperatura_salto_exacto_4_es_bueno(self):
        s = _serie([20.0, 24.0])  # delta 1h = 4.0, límite subregla 31a
        r = cc.evaluar_prueba_paso(s, "n_airtemp")
        assert r.iloc[1] == cc.BUENO

    def test_temperatura_salto_4_01_es_dudoso(self):
        s = _serie([20.0, 24.01])
        r = cc.evaluar_prueba_paso(s, "n_airtemp")
        assert r.iloc[1] == cc.DUDOSO

    def test_humedad_salto_45_es_bueno_45_01_es_dudoso(self):
        s_ok = _serie([50.0, 95.0])
        s_mal = _serie([50.0, 95.01])
        assert cc.evaluar_prueba_paso(s_ok, "n_humedad").iloc[1] == cc.BUENO
        assert cc.evaluar_prueba_paso(s_mal, "n_humedad").iloc[1] == cc.DUDOSO

    def test_velviento_es_estricto_10_0_ya_es_dudoso(self):
        # subregla 38 usa "<" estricto: exactamente 10.0 NO pasa
        s_borde = _serie([5.0, 15.0])   # delta = 10.0
        s_bajo = _serie([5.0, 14.99])   # delta = 9.99
        assert cc.evaluar_prueba_paso(s_borde, "n_velviento").iloc[1] == cc.DUDOSO
        assert cc.evaluar_prueba_paso(s_bajo, "n_velviento").iloc[1] == cc.BUENO

    def test_dirviento_distancia_circular(self):
        # min(|Δ|, 360-|Δ|) < 150 pasa (subregla 39). 350 -> 10 (350, 10) circular = 10, pasa.
        s_ok = _serie([0.0, 350.0])
        r_ok = cc.evaluar_prueba_paso(s_ok, "n_dirviento")
        assert r_ok.iloc[1] == cc.BUENO
        # 170 -> distancia circular min(170, 190) = 170 >= 150 -> dudoso
        s_mal = _serie([0.0, 170.0])
        r_mal = cc.evaluar_prueba_paso(s_mal, "n_dirviento")
        assert r_mal.iloc[1] == cc.DUDOSO

    def test_radsolar_salto_555_es_bueno_555_01_es_dudoso(self):
        s_ok = _serie([0.0, 555.0])
        s_mal = _serie([0.0, 555.01])
        assert cc.evaluar_prueba_paso(s_ok, "n_radsolar").iloc[1] == cc.BUENO
        assert cc.evaluar_prueba_paso(s_mal, "n_radsolar").iloc[1] == cc.DUDOSO

    def test_variable_sin_regla_de_paso_es_siempre_bueno(self):
        # n_nivelagua y n_lluvia no tienen prueba de paso documentada (MT-DRD-002 p.16)
        s = _serie([0.0, 9999.0])
        assert (cc.evaluar_prueba_paso(s, "n_nivelagua") == cc.BUENO).all()
        assert (cc.evaluar_prueba_paso(s, "n_lluvia") == cc.BUENO).all()

    def test_sin_cadencia_valida_es_bueno_sin_crashear(self):
        s = _serie([20.0])  # 1 solo dato -> cadencia_inferida da None
        r = cc.evaluar_prueba_paso(s, "n_airtemp")
        assert (r == cc.BUENO).all()

    def test_cadencia_no_horaria_convierte_pasos_correctamente(self):
        # cadencia 10min -> "1h" son 6 pasos
        s = _serie([20.0] * 7, freq="10min")
        s.iloc[6] = 25.0  # salto de 5°C a las 6 lecturas (=1h) -> viola subregla 31a (4°C)
        r = cc.evaluar_prueba_paso(s, "n_airtemp")
        assert r.iloc[6] == cc.DUDOSO


class TestEvaluarPersistencia:
    def test_4_horas_identicas_marca_las_4(self):
        s = _serie([20.0, 20.0, 20.0, 20.0, 21.0, 22.0])
        r = cc.evaluar_persistencia(s, "n_airtemp")
        assert (r.iloc[:4] == cc.DUDOSO).all()
        assert r.iloc[4] == cc.BUENO
        assert r.iloc[5] == cc.BUENO

    def test_solo_3_horas_identicas_no_dispara(self):
        s = _serie([20.0, 20.0, 20.0, 21.0])
        r = cc.evaluar_persistencia(s, "n_airtemp")
        assert (r == cc.BUENO).all()

    def test_precipitacion_excluida_no_dispara_aunque_se_repita(self):
        s = _serie([0.0, 0.0, 0.0, 0.0, 0.0])
        r = cc.evaluar_persistencia(s, "n_lluvia")
        assert (r == cc.BUENO).all()

    def test_nivel_agua_excluido_no_dispara(self):
        s = _serie([5.0, 5.0, 5.0, 5.0])
        r = cc.evaluar_persistencia(s, "n_nivelagua")
        assert (r == cc.BUENO).all()


class TestEvaluarAutomatica:
    def test_combina_peor_banderin_gana(self):
        # índice 1: dentro de límite duro (BUENO) pero salto de paso viola (DUDOSO)
        # índice 2: fuera de límite duro (MALO) Y viola paso -> debe ganar MALO
        s = _serie([20.0, 24.01, 60.0])
        r = cc.evaluar_automatica(s, "n_airtemp")
        assert r.iloc[1] == cc.DUDOSO
        assert r.iloc[2] == cc.MALO

    def test_todo_bueno_si_nada_se_viola(self):
        s = _serie([20.0, 21.0, 22.0, 23.0])
        r = cc.evaluar_automatica(s, "n_airtemp")
        assert (r == cc.BUENO).all()


class TestEvaluarLimitesDurosConvencional:
    def test_dentro_de_rango_es_bueno(self):
        s = _serie([20.0, -20.0, 40.0], freq="1D")
        r = cc.evaluar_limites_duros_convencional(s, "n_tm102")
        assert (r == cc.BUENO).all()

    def test_fuera_del_duro_es_malo(self):
        s = _serie([50.0, -35.0], freq="1D")
        r = cc.evaluar_limites_duros_convencional(s, "n_tm102")
        assert (r == cc.MALO).all()

    def test_banda_baja_dudosa(self):
        s = _serie([-29.0], freq="1D")  # entre -30 y -28
        r = cc.evaluar_limites_duros_convencional(s, "n_tm103")
        assert r.iloc[0] == cc.DUDOSO

    def test_banda_alta_dudosa(self):
        s = _serie([44.0], freq="1D")  # entre 43 y 45
        r = cc.evaluar_limites_duros_convencional(s, "n_tm104")
        assert r.iloc[0] == cc.DUDOSO

    def test_variable_no_temperatura_es_siempre_bueno(self):
        s = _serie([9999.0], freq="1D")
        r = cc.evaluar_limites_duros_convencional(s, "n_pt102")
        assert r.iloc[0] == cc.BUENO


class TestEvaluarCoherenciaInterna:
    def _df(self, **columnas):
        idx = pd.date_range("2026-01-01", periods=len(next(iter(columnas.values()))), freq="1D")
        return pd.DataFrame(columnas, index=idx)

    def test_max_menor_o_igual_a_min_es_malo_en_ambas(self):
        df = self._df(n_tm102=[15.0], n_tm103=[20.0])  # max < min, invalido
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm102"].iloc[0] == cc.MALO
        assert r["n_tm103"].iloc[0] == cc.MALO

    def test_max_igual_a_min_tambien_es_malo(self):
        df = self._df(n_tm102=[18.0], n_tm103=[18.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm102"].iloc[0] == cc.MALO

    def test_max_coherente_es_bueno(self):
        df = self._df(n_tm102=[25.0], n_tm103=[10.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm102"].iloc[0] == cc.BUENO
        assert r["n_tm103"].iloc[0] == cc.BUENO

    def test_max_menor_que_instantanea_seco_es_malo(self):
        df = self._df(n_tm102=[15.0], n_tm104=[20.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm102"].iloc[0] == cc.MALO
        assert r["n_tm104"].iloc[0] == cc.MALO

    def test_max_menor_que_instantanea_humedo_es_malo(self):
        df = self._df(n_tm102=[15.0], n_tm107=[20.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm102"].iloc[0] == cc.MALO

    def test_min_mayor_que_instantanea_seco_es_malo(self):
        df = self._df(n_tm103=[25.0], n_tm104=[10.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm103"].iloc[0] == cc.MALO

    def test_min_no_se_compara_con_bulbo_humedo(self):
        # el manual (2.C) solo compara mínima contra bulbo SECO, no húmedo
        df = self._df(n_tm103=[25.0], n_tm107=[10.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm103"].iloc[0] == cc.BUENO

    def test_seco_menor_que_humedo_mismo_horario_es_malo(self):
        df = self._df(n_tm104=[10.0], n_tm107=[15.0])
        r = cc.evaluar_coherencia_interna(df)
        assert r["n_tm104"].iloc[0] == cc.MALO
        assert r["n_tm107"].iloc[0] == cc.MALO

    def test_variable_ausente_se_omite_sin_error(self):
        df = self._df(n_tm102=[25.0])  # sin n_tm103 ni ninguna instantánea
        r = cc.evaluar_coherencia_interna(df)
        assert set(r.keys()) == {"n_tm102"}
        assert r["n_tm102"].iloc[0] == cc.BUENO


class TestEvaluarVariacionDiaria:
    def test_costa_baja_altitud_umbral_5(self):
        s = _serie([20.0, 26.0], freq="1D")  # delta 6 > 5
        r = cc.evaluar_variacion_diaria(s, "Costa", altitud=100)
        assert r.iloc[1] == cc.DUDOSO

    def test_costa_baja_altitud_dentro_del_umbral(self):
        s = _serie([20.0, 24.0], freq="1D")  # delta 4 <= 5
        r = cc.evaluar_variacion_diaria(s, "Costa", altitud=100)
        assert r.iloc[1] == cc.BUENO

    def test_sierra_baja_altitud_umbral_10(self):
        s = _serie([20.0, 31.0], freq="1D")  # delta 11 > 10
        r = cc.evaluar_variacion_diaria(s, "Sierra", altitud=2000)
        assert r.iloc[1] == cc.DUDOSO

    def test_sierra_alta_altitud_umbral_15(self):
        s = _serie([20.0, 36.0], freq="1D")  # delta 16 > 15
        r = cc.evaluar_variacion_diaria(s, "Sierra", altitud=4000)
        assert r.iloc[1] == cc.DUDOSO
        s_ok = _serie([20.0, 34.0], freq="1D")  # delta 14 <= 15
        r_ok = cc.evaluar_variacion_diaria(s_ok, "Sierra", altitud=4000)
        assert r_ok.iloc[1] == cc.BUENO

    def test_sin_metadata_no_evalua_y_no_crashea(self):
        s = _serie([20.0, 9999.0], freq="1D")
        assert (cc.evaluar_variacion_diaria(s, None, 100) == cc.BUENO).all()
        assert (cc.evaluar_variacion_diaria(s, "Costa", None) == cc.BUENO).all()


class TestEvaluarConvencional:
    def test_combina_las_tres_reglas_por_variable(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="1D")
        df = pd.DataFrame({
            "n_tm102": [25.0, 26.0],   # coherente, dentro de todo
            "n_tm103": [10.0, 60.0],   # segundo dato fuera del límite duro -> MALO
        }, index=idx)
        r = cc.evaluar_convencional(df, region_natural="Costa", altitud=100)
        assert r["n_tm103"].iloc[1] == cc.MALO
        assert set(r.keys()) == {"n_tm102", "n_tm103"}

    def test_variable_no_convencional_no_aparece_en_resultado(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1D")
        df = pd.DataFrame({"n_pt102": [5.0]}, index=idx)
        r = cc.evaluar_convencional(df, region_natural="Costa", altitud=100)
        assert r == {}


class TestEvaluarTodas:
    def test_automatica_usa_reglas_de_automatica(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="1h")
        df = pd.DataFrame({"n_airtemp": [20.0, 60.0]}, index=idx)  # 2do fuera del duro
        r = cc.evaluar_todas(df, categoria="AUTOMATICA")
        assert r["n_airtemp"].iloc[1] == cc.MALO

    def test_convencional_usa_reglas_de_convencional(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="1D")
        df = pd.DataFrame({"n_tm102": [20.0, 60.0]}, index=idx)  # fuera del duro convencional
        r = cc.evaluar_todas(df, categoria="CONVENCIONAL", region_natural="Costa", altitud=100)
        assert r["n_tm102"].iloc[1] == cc.MALO

    def test_categoria_minuscula_funciona_igual(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1h")
        df = pd.DataFrame({"n_airtemp": [20.0]}, index=idx)
        r = cc.evaluar_todas(df, categoria="automatica")
        assert "n_airtemp" in r

    def test_categoria_desconocida_da_diccionario_vacio_sin_crashear(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1h")
        df = pd.DataFrame({"n_airtemp": [20.0]}, index=idx)
        assert cc.evaluar_todas(df, categoria="OTRA_COSA") == {}

    def test_variable_sin_regla_definida_no_aparece(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1h")
        df = pd.DataFrame({"n_airtemp": [20.0], "n_variable_rara": [1.0]}, index=idx)
        r = cc.evaluar_todas(df, categoria="AUTOMATICA")
        assert "n_variable_rara" not in r
        assert "n_airtemp" in r


class TestExplicarMotivoAutomatica:
    def test_bueno_da_motivo_vacio(self):
        s = _serie([20.0, 21.0, 22.0, 23.0])
        m = cc.explicar_motivo_automatica(s, "n_airtemp")
        assert (m == "").all()

    def test_limite_duro_nombra_el_rango(self):
        s = _serie([20.0, 60.0])
        m = cc.explicar_motivo_automatica(s, "n_airtemp")
        assert m.iloc[0] == ""
        assert "límite duro" in m.iloc[1]
        assert "-40" in m.iloc[1] and "50" in m.iloc[1]

    def test_dos_reglas_a_la_vez_se_unen_con_punto_y_coma(self):
        # fuera del límite duro Y con salto de paso en el mismo punto
        s = _serie([20.0, 60.0])
        m = cc.explicar_motivo_automatica(s, "n_airtemp")
        assert "límite duro" in m.iloc[1]
        assert "prueba de paso" in m.iloc[1]
        assert "; " in m.iloc[1]

    def test_persistencia_nombrada(self):
        s = _serie([20.0, 20.0, 20.0, 20.0])
        m = cc.explicar_motivo_automatica(s, "n_airtemp")
        assert all("persistencia" in x for x in m)


class TestExplicarMotivoConvencional:
    def test_coherencia_interna_nombrada(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1D")
        df = pd.DataFrame({"n_tm102": [15.0], "n_tm103": [20.0]}, index=idx)
        m = cc.explicar_motivo_convencional(df, region_natural=None, altitud=None)
        assert "coherencia interna" in m["n_tm102"].iloc[0]
        assert "coherencia interna" in m["n_tm103"].iloc[0]

    def test_variacion_diaria_nombrada(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="1D")
        df = pd.DataFrame({"n_tm102": [20.0, 30.0]}, index=idx)  # delta 10 > 5 (Costa)
        m = cc.explicar_motivo_convencional(df, region_natural="Costa", altitud=100)
        assert "variación diaria" in m["n_tm102"].iloc[1]


class TestExplicarMotivos:
    def test_automatica_delega_correctamente(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1h")
        df = pd.DataFrame({"n_airtemp": [60.0]}, index=idx)
        m = cc.explicar_motivos(df, categoria="AUTOMATICA")
        assert "límite duro" in m["n_airtemp"].iloc[0]

    def test_convencional_delega_correctamente(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1D")
        df = pd.DataFrame({"n_tm102": [60.0]}, index=idx)
        m = cc.explicar_motivos(df, categoria="CONVENCIONAL")
        assert "límite duro" in m["n_tm102"].iloc[0]

    def test_categoria_desconocida_da_vacio(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="1h")
        df = pd.DataFrame({"n_airtemp": [60.0]}, index=idx)
        assert cc.explicar_motivos(df, categoria="OTRA") == {}


class TestCacheMotivosCCEstacion:
    def test_reusa_cache_sin_recalcular(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cc, "DIR_CACHE_CONTROL_CALIDAD", tmp_path)
        monkeypatch.setattr(cc.data_loader, "firma_estacion", lambda codigo: [("x.csv", 1, 2)])
        llamadas = []

        def _fake(codigo):
            llamadas.append(codigo)
            return {"n_airtemp": pd.Series([""])}

        monkeypatch.setattr(cc, "_calcular_motivos_estacion", _fake)

        cc.resultado_motivos_cc_estacion("104112")
        cc.resultado_motivos_cc_estacion("104112")

        assert len(llamadas) == 1

    def test_no_colisiona_con_el_cache_de_severidad(self, tmp_path, monkeypatch):
        # Mismo codigo, misma carpeta -- deben ser archivos DISTINTOS.
        monkeypatch.setattr(cc, "DIR_CACHE_CONTROL_CALIDAD", tmp_path)
        monkeypatch.setattr(cc.data_loader, "firma_estacion", lambda codigo: [("x.csv", 1, 2)])
        monkeypatch.setattr(cc, "_calcular_resultado_estacion", lambda codigo: {"n_airtemp": pd.Series([cc.MALO])})
        monkeypatch.setattr(cc, "_calcular_motivos_estacion", lambda codigo: {"n_airtemp": pd.Series(["límite duro"])})

        severidad = cc.resultado_control_calidad_estacion("104112")
        motivo = cc.resultado_motivos_cc_estacion("104112")

        assert severidad["n_airtemp"].iloc[0] == cc.MALO
        assert motivo["n_airtemp"].iloc[0] == "límite duro"
        assert (tmp_path / "104112.pkl").exists()
        assert (tmp_path / "104112_motivos.pkl").exists()


class TestTieneReglaCC:
    def test_automatica_con_regla(self):
        assert cc.tiene_regla_cc("n_airtemp", "AUTOMATICA") is True

    def test_automatica_sin_regla(self):
        assert cc.tiene_regla_cc("n_bateria", "AUTOMATICA") is False

    def test_convencional_con_regla(self):
        assert cc.tiene_regla_cc("n_tm102", "CONVENCIONAL") is True

    def test_convencional_sin_regla(self):
        assert cc.tiene_regla_cc("n_pt102", "CONVENCIONAL") is False

    def test_categoria_desconocida_es_false(self):
        assert cc.tiene_regla_cc("n_airtemp", "OTRA_COSA") is False

    def test_categoria_minuscula_funciona_igual(self):
        assert cc.tiene_regla_cc("n_airtemp", "automatica") is True


class TestVersionLogicaCache:
    def test_incluye_bytes_del_yaml_de_config(self, tmp_path, monkeypatch):
        # Si cambia el YAML de umbrales (no el .py), el hash tiene que cambiar
        # tambien -- si no, un cambio de umbral no invalidaria el cache (paso
        # real de esta sesion: el fix de n_radsolar en el YAML no invalidaba
        # nada hasta que _RUTA_CONFIG.read_bytes() se sumo al hash).
        ruta_falsa = tmp_path / "control_calidad.yaml"
        ruta_falsa.write_text("a: 1\n", encoding="utf-8")
        monkeypatch.setattr(cc, "_RUTA_CONFIG", ruta_falsa)
        version_a = cc._version_logica_cache()

        ruta_falsa.write_text("a: 2\n", encoding="utf-8")
        version_b = cc._version_logica_cache()

        assert version_a != version_b


class TestCacheControlCalidadEstacion:
    """
    Mismo mecanismo que TestCacheDiasEfectivosEstacion en test_dias_efectivos.py —
    el caché no debe quedar "válido" solo porque los CSV no cambiaron si la LÓGICA
    del CC cambió.
    """

    def _preparar(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cc, "DIR_CACHE_CONTROL_CALIDAD", tmp_path)
        monkeypatch.setattr(cc.data_loader, "firma_estacion", lambda codigo: [("x.csv", 1, 2)])
        llamadas = []

        def _fake_calculo(codigo):
            llamadas.append(codigo)
            return {"n_airtemp": pd.Series([cc.BUENO])}

        monkeypatch.setattr(cc, "_calcular_resultado_estacion", _fake_calculo)
        return llamadas

    def test_segunda_consulta_reusa_cache_sin_recalcular(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)

        cc.resultado_control_calidad_estacion("104112")
        cc.resultado_control_calidad_estacion("104112")

        assert len(llamadas) == 1

    def test_cambio_de_version_logica_fuerza_recalculo_aunque_no_cambien_csv(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)

        cc.resultado_control_calidad_estacion("104112")
        monkeypatch.setattr(cc, "_VERSION_LOGICA_CACHE", "version-simulada-distinta")
        cc.resultado_control_calidad_estacion("104112")

        assert len(llamadas) == 2

    def test_cache_pre_existente_sin_llave_version_logica_no_crashea_y_recalcula(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)
        ruta = tmp_path / "104112.pkl"
        with open(ruta, "wb") as f:
            pickle.dump({"firma": [("x.csv", 1, 2)], "resultado": {"viejo": True}}, f)

        resultado = cc.resultado_control_calidad_estacion("104112")

        assert len(llamadas) == 1
        assert list(resultado.keys()) == ["n_airtemp"]


class TestAgregarColumnasCC:
    def test_agrega_columna_cc_alineada_por_codigo_y_fecha(self, monkeypatch):
        idx_completo = pd.date_range("2026-01-01", periods=5, freq="1h")
        cacheado = {
            "104112": {"n_airtemp": pd.Series(
                [cc.BUENO, cc.DUDOSO, cc.MALO, cc.BUENO, cc.BUENO], index=idx_completo,
            )},
        }
        monkeypatch.setattr(cc, "resultado_control_calidad_estacion", lambda codigo: cacheado[codigo])

        # df solo trae un RECORTE del histórico (horas 1 y 3, no todas)
        df = pd.DataFrame({
            "codigo": ["104112", "104112"],
            "datetime": [idx_completo[1], idx_completo[3]],
            "n_airtemp": [21.0, 23.0],
        })
        r = cc.agregar_columnas_cc(df)
        assert r["cc_n_airtemp"].tolist() == [cc.DUDOSO, cc.BUENO]

    def test_df_vacio_no_rompe(self):
        df = pd.DataFrame(columns=["codigo", "datetime"])
        r = cc.agregar_columnas_cc(df)
        assert r.empty

    def test_estacion_sin_variables_evaluadas_no_agrega_columnas(self, monkeypatch):
        monkeypatch.setattr(cc, "resultado_control_calidad_estacion", lambda codigo: {})
        df = pd.DataFrame({
            "codigo": ["999999"], "datetime": [pd.Timestamp("2026-01-01")], "n_airtemp": [20.0],
        })
        r = cc.agregar_columnas_cc(df)
        assert "cc_n_airtemp" not in r.columns
