"""
Tests de core.dias_efectivos: banda genérica de día efectivo (día calendario,
simplificación documentada) y concordancia (ventana anclada en el timestamp
real del valor diario nativo, sin asumir convención de día).
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
import pytest

from analizador_series.core import dias_efectivos as de


def _serie(valores, freq="1h", inicio="2026-01-01"):
    idx = pd.date_range(inicio, periods=len(valores), freq=freq)
    return pd.Series(list(valores), index=idx, dtype=float)


class TestEsVariableDiaria:
    def test_cadencia_horaria_no_es_diaria(self):
        assert de.es_variable_diaria(pd.Timedelta(hours=1)) is False

    def test_cadencia_24h_es_diaria(self):
        assert de.es_variable_diaria(pd.Timedelta(hours=24)) is True

    def test_cadencia_none_no_es_diaria(self):
        assert de.es_variable_diaria(None) is False


class TestEvaluarDiasEfectivos:
    def test_dias_completos_todos_efectivos(self):
        s = _serie([20.0] * 72)   # 3 días horarios, sin huecos
        tabla = de.evaluar_dias_efectivos(s)
        assert len(tabla) == 3
        assert tabla["efectivo"].all()
        assert tabla["pct_recibido"].round(3).eq(1.0).all()
        assert tabla["n_esperado"].round(3).eq(24.0).all()

    def test_borde_exacto_75_pct_es_efectivo(self):
        valores = [20.0] * 72
        # Día 2 (horas 24-47): dejar solo 18 de 24 válidas -> 75.0% exacto
        for h in range(24, 24 + 6):
            valores[h] = np.nan
        s = _serie(valores)
        tabla = de.evaluar_dias_efectivos(s)
        fila_dia2 = tabla.iloc[1]
        assert fila_dia2["n_recibido"] == 18
        assert fila_dia2["pct_recibido"] == pytest.approx(0.75)
        assert fila_dia2["efectivo"] == True  # noqa: E712 (bool numpy)

    def test_bajo_75_pct_no_es_efectivo(self):
        valores = [20.0] * 72
        # Día 2: dejar solo 17 de 24 válidas -> 70.8%
        for h in range(24, 24 + 7):
            valores[h] = np.nan
        s = _serie(valores)
        tabla = de.evaluar_dias_efectivos(s)
        fila_dia2 = tabla.iloc[1]
        assert fila_dia2["n_recibido"] == 17
        assert fila_dia2["efectivo"] == False  # noqa: E712

    def test_dia_totalmente_ausente_del_indice_cuenta_como_no_efectivo(self):
        dia1 = pd.date_range("2026-01-01 00:00", periods=24, freq="1h")
        dia3 = pd.date_range("2026-01-03 00:00", periods=24, freq="1h")
        idx = dia1.append(dia3)   # día 2 no existe en absoluto en el índice
        s = pd.Series([20.0] * len(idx), index=idx)

        tabla = de.evaluar_dias_efectivos(s)
        assert len(tabla) == 3   # dias 1, 2 y 3 -- el 2 sale del rango, no del groupby
        fila_dia2 = tabla.loc["2026-01-02"]
        assert fila_dia2["n_recibido"] == 0
        assert fila_dia2["efectivo"] == False  # noqa: E712

    def test_cadencia_no_divisor_exacto_no_se_redondea(self):
        s = _serie([20.0] * 10, freq="7h")
        tabla = de.evaluar_dias_efectivos(s)
        assert tabla["n_esperado"].tolist() == pytest.approx([24 / 7] * len(tabla))

    def test_cadencia_explicita_no_recalcula(self):
        s = _serie([20.0] * 48)   # cadencia real 1h -> se ignora
        tabla = de.evaluar_dias_efectivos(s, cadencia=pd.Timedelta(hours=2))
        assert tabla["n_esperado"].tolist() == pytest.approx([12.0] * len(tabla))

    def test_menos_de_2_validos_da_vacio(self):
        s = _serie([20.0, np.nan, np.nan])
        assert de.evaluar_dias_efectivos(s).empty

    def test_serie_vacia_da_vacio(self):
        assert de.evaluar_dias_efectivos(pd.Series(dtype=float)).empty


class TestConstruirTablaDiasEfectivos:
    def _df_estacion(self):
        idx_horaria = pd.date_range("2026-01-01", periods=72, freq="1h")
        idx_diaria = pd.date_range("2026-01-01 07:00", periods=3, freq="24h")
        df = pd.DataFrame(index=idx_horaria.union(idx_diaria))
        df["n_horaria"] = pd.Series(20.0, index=idx_horaria)
        df["n_tmax"] = pd.Series([30.0, 31.0, 29.0], index=idx_diaria)
        return df

    def test_diaria_excluida_por_defecto(self):
        df = self._df_estacion()
        resultado = de.construir_tabla_dias_efectivos(df, ["n_horaria", "n_tmax"])
        assert resultado["n_horaria"]["aplica"] is True
        assert resultado["n_tmax"]["es_diaria"] is True
        assert resultado["n_tmax"]["aplica"] is False

    def test_diaria_incluida_con_toggle(self):
        df = self._df_estacion()
        resultado = de.construir_tabla_dias_efectivos(df, ["n_tmax"], incluir_diarias=True)
        assert resultado["n_tmax"]["aplica"] is True

    def test_variable_ausente_se_omite_sin_error(self):
        df = self._df_estacion()
        resultado = de.construir_tabla_dias_efectivos(df, ["n_horaria", "n_inexistente"])
        assert "n_inexistente" not in resultado
        assert "n_horaria" in resultado


class TestEvaluarConcordanciaDiaria:
    def test_ventana_completa_es_respaldada(self):
        subdiaria = _serie([20.0] * 73)  # día1 00:00 .. día4 00:00, horaria
        diaria = pd.Series(
            [30.0, 31.0],
            index=pd.to_datetime(["2026-01-02 07:00", "2026-01-03 07:00"]),
        )
        tabla = de.evaluar_concordancia_diaria(diaria, subdiaria)
        assert len(tabla) == 2
        assert (tabla["n_recibido"] == 24).all()
        assert tabla["pct_recibido"].tolist() == pytest.approx([1.0, 1.0])
        assert tabla["respaldado"].all()

    def test_ventana_insuficiente_no_es_respaldada(self):
        idx = pd.date_range("2026-01-01", periods=73, freq="1h")
        valores = [20.0] * len(idx)
        s = pd.Series(valores, index=idx)
        # Vaciar la ventana (2026-01-02 07:00, 2026-01-03 07:00] casi entera,
        # dejar solo 5 lecturas válidas -> por debajo del 75%.
        ventana = (s.index > pd.Timestamp("2026-01-02 07:00")) & (s.index <= pd.Timestamp("2026-01-03 07:00"))
        posiciones = np.where(ventana)[0][5:]   # deja las primeras 5, NaNea el resto
        s.iloc[posiciones] = np.nan

        diaria = pd.Series([31.0], index=pd.to_datetime(["2026-01-03 07:00"]))
        tabla = de.evaluar_concordancia_diaria(diaria, s)
        fila = tabla.iloc[0]
        assert fila["n_recibido"] == 5
        assert fila["respaldado"] == False  # noqa: E712

    def test_ventana_es_abierta_al_inicio_y_cerrada_al_final(self):
        ts = pd.Timestamp("2026-01-02 07:00")
        # 26 horas: ts-25h .. ts. ts-24h debe EXCLUIRSE (límite abierto),
        # ts debe INCLUIRSE (límite cerrado) -> n_recibido debe dar 24, no 25.
        idx = pd.date_range(ts - pd.Timedelta(hours=25), ts, freq="1h")
        subdiaria = pd.Series(20.0, index=idx)
        diaria = pd.Series([30.0], index=[ts])

        tabla = de.evaluar_concordancia_diaria(diaria, subdiaria)
        assert tabla.iloc[0]["n_recibido"] == 24
        assert tabla.iloc[0]["pct_recibido"] == pytest.approx(1.0)

    def test_serie_diaria_vacia_da_vacio(self):
        subdiaria = _serie([20.0] * 48)
        diaria = pd.Series(dtype=float)
        assert de.evaluar_concordancia_diaria(diaria, subdiaria).empty

    def test_sin_cadencia_subdiaria_da_vacio(self):
        subdiaria = pd.Series([20.0], index=[pd.Timestamp("2026-01-01")])
        diaria = pd.Series([30.0], index=[pd.Timestamp("2026-01-02 07:00")])
        assert de.evaluar_concordancia_diaria(diaria, subdiaria).empty


class TestConstruirTablaConcordancia:
    def test_usa_primera_candidata_presente(self):
        idx_h = pd.date_range("2026-01-01", periods=49, freq="1h")
        df = pd.DataFrame(index=idx_h)
        df["n_airtemp_inst"] = 20.0
        df["n_maxat"] = np.nan
        df.loc["2026-01-02 07:00", "n_maxat"] = 30.0

        resultado = de.construir_tabla_concordancia(df)
        assert resultado["n_maxat"]["variable_subdiaria"] == "n_airtemp_inst"

    def test_candidata_ausente_omite_la_variable(self):
        idx_h = pd.date_range("2026-01-01", periods=49, freq="1h")
        df = pd.DataFrame(index=idx_h)
        df["n_dayrain"] = np.nan
        df.loc["2026-01-02 07:00", "n_dayrain"] = 0.4
        # ni n_lluvia ni n_rain_10m presentes en columnas

        resultado = de.construir_tabla_concordancia(df)
        assert "n_dayrain" not in resultado


class TestCacheDiasEfectivosEstacion:
    """
    resultado_dias_efectivos_estacion() no debe quedar "válido" solo porque
    los CSV de la estación no cambiaron -- si la LÓGICA cambió (el propio
    código de este archivo, o cadencia_inferida), el caché en disco tiene
    que invalidarse solo. Ver _version_logica_cache().
    """

    def _preparar(self, tmp_path, monkeypatch):
        monkeypatch.setattr(de, "DIR_CACHE_DIAS_EFECTIVOS", tmp_path)
        monkeypatch.setattr(de.data_loader, "firma_estacion", lambda codigo: [("x.csv", 1, 2)])
        llamadas = []

        def _fake_calculo(codigo, umbral_pct, flags_cc=None):
            llamadas.append((codigo, umbral_pct, flags_cc))
            return {"resultado_de": {}, "resultado_conc": {}}

        monkeypatch.setattr(de, "_calcular_resultado_estacion", _fake_calculo)
        return llamadas

    def test_segunda_consulta_reusa_cache_sin_recalcular(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)

        de.resultado_dias_efectivos_estacion("104112")
        de.resultado_dias_efectivos_estacion("104112")

        assert len(llamadas) == 1

    def test_cambio_de_version_logica_fuerza_recalculo_aunque_no_cambien_csv(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)

        de.resultado_dias_efectivos_estacion("104112")
        monkeypatch.setattr(de, "_VERSION_LOGICA_CACHE", "version-simulada-distinta")
        de.resultado_dias_efectivos_estacion("104112")

        assert len(llamadas) == 2

    def test_cache_pre_existente_sin_llave_version_logica_no_crashea_y_recalcula(self, tmp_path, monkeypatch):
        # Simula un .pkl escrito ANTES de que existiera este mecanismo.
        llamadas = self._preparar(tmp_path, monkeypatch)
        ruta = tmp_path / "104112.pkl"
        with open(ruta, "wb") as f:
            pickle.dump(
                {"firma": [("x.csv", 1, 2)], "umbral_pct": de.UMBRAL_DIA_EFECTIVO, "resultado": {"viejo": True}},
                f,
            )

        resultado = de.resultado_dias_efectivos_estacion("104112")

        assert len(llamadas) == 1

    def test_flags_cc_distinto_no_reusa_cache_del_otro(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)

        de.resultado_dias_efectivos_estacion("104112", flags_cc=None)
        de.resultado_dias_efectivos_estacion("104112", flags_cc=["BUENO"])

        assert len(llamadas) == 2

    def test_mismo_flags_cc_reusa_cache(self, tmp_path, monkeypatch):
        llamadas = self._preparar(tmp_path, monkeypatch)

        de.resultado_dias_efectivos_estacion("104112", flags_cc=["BUENO", "DUDOSO"])
        de.resultado_dias_efectivos_estacion("104112", flags_cc=["DUDOSO", "BUENO"])  # mismo set, otro orden

        assert len(llamadas) == 1

    def test_cache_viejo_sin_llave_flags_cc_sigue_siendo_valido_para_flags_cc_none(self, tmp_path, monkeypatch):
        # Un .pkl escrito ANTES de que existiera flags_cc no debe forzar
        # recálculo cuando se consulta con el default (None) — es exactamente
        # el mismo resultado que ya tenía cacheado.
        llamadas = self._preparar(tmp_path, monkeypatch)
        ruta = tmp_path / "104112.pkl"
        with open(ruta, "wb") as f:
            pickle.dump({
                "firma": [("x.csv", 1, 2)],
                "umbral_pct": de.UMBRAL_DIA_EFECTIVO,
                "version_logica": de._VERSION_LOGICA_CACHE,
                "resultado": {"resultado_de": {}, "resultado_conc": {}},
            }, f)

        resultado = de.resultado_dias_efectivos_estacion("104112")

        assert len(llamadas) == 0
        assert resultado == {"resultado_de": {}, "resultado_conc": {}}
