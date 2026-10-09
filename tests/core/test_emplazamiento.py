"""
Tests de core.emplazamiento: pares co-ubicados (automática↔convencional, <umbral_m)
y diccionario de equivalencia de variables físicas. Ver docs/SPEC-emplazamiento-compartido.md
y tasks/todo.md Task 2.
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd
import pytest

from analizador_series.core import emplazamiento

R_TIERRA_M = 6371000.0  # mismo radio que usa emplazamiento._haversine_m


def _desplazar_latitud(lat: float, distancia_m: float) -> float:
    """
    Desplazamiento norte-sur puro: un meridiano es un círculo máximo, así que
    la distancia a lo largo de él es exactamente R*ángulo (sin aproximación),
    independiente de la fórmula de haversine que se está probando.
    """
    return lat + math.degrees(distancia_m / R_TIERRA_M)


def _crear_db(ruta_db, estaciones):
    """estaciones: lista de (codigo, categoria, latitud, longitud[, clasificacion])
    — latitud/longitud pueden ser None; clasificacion es opcional (NULL si falta)."""
    con = sqlite3.connect(ruta_db)
    con.execute(
        "CREATE TABLE estaciones (codigo TEXT PRIMARY KEY, categoria TEXT, "
        "latitud REAL, longitud REAL, clasificacion TEXT)"
    )
    con.executemany(
        "INSERT INTO estaciones (codigo, categoria, latitud, longitud, clasificacion) "
        "VALUES (?, ?, ?, ?, ?)",
        [tuple(e) + (None,) * (5 - len(e)) for e in estaciones],
    )
    con.commit()
    con.close()


class TestHaversineM:
    def test_mismo_punto_da_distancia_cero(self):
        assert emplazamiento._haversine_m(-5.0, -75.0, -5.0, -75.0) == pytest.approx(0.0, abs=1e-6)

    def test_un_grado_de_longitud_en_el_ecuador(self):
        # Circunferencia ecuatorial / 360, calculado directo (no vía haversine).
        esperado = (2 * math.pi * R_TIERRA_M) / 360
        obtenido = emplazamiento._haversine_m(0.0, 0.0, 0.0, 1.0)
        assert obtenido == pytest.approx(esperado, rel=1e-6)

    def test_desplazamiento_norte_sur_exacto(self):
        lat2 = _desplazar_latitud(-5.0, 250.0)
        assert emplazamiento._haversine_m(-5.0, -75.0, lat2, -75.0) == pytest.approx(250.0, rel=1e-6)


class TestCalcularParesColocados:
    def test_par_dentro_del_umbral_entra(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        lat_conv = _desplazar_latitud(-5.0, 99.0)
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", lat_conv, -75.0),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert len(pares) == 1
        assert pares[0]["codigo_auto"] == "AUTO1"
        assert pares[0]["codigo_conv"] == "CONV1"
        assert pares[0]["distancia_m"] == pytest.approx(99.0, rel=1e-3)

    def test_par_fuera_del_umbral_no_entra(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        lat_conv = _desplazar_latitud(-5.0, 101.0)
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", lat_conv, -75.0),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert pares == []

    def test_no_empareja_misma_categoria(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("AUTO2", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", -5.0, -75.0),
            ("CONV2", "CONVENCIONAL", -5.0, -75.0),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        codigos_auto = {p["codigo_auto"] for p in pares}
        codigos_conv = {p["codigo_conv"] for p in pares}
        assert codigos_auto == {"AUTO1", "AUTO2"}
        assert codigos_conv == {"CONV1", "CONV2"}
        assert len(pares) == 4  # 2 automáticas x 2 convencionales, todas a 0m

    def test_ordenado_por_distancia_ascendente(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        lat_lejos = _desplazar_latitud(-5.0, 80.0)
        lat_cerca = _desplazar_latitud(-5.0, 10.0)
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("CONV_LEJOS", "CONVENCIONAL", lat_lejos, -75.0),
            ("CONV_CERCA", "CONVENCIONAL", lat_cerca, -75.0),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert [p["codigo_conv"] for p in pares] == ["CONV_CERCA", "CONV_LEJOS"]

    def test_una_automatica_con_dos_candidatas_da_dos_pares(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        lat_a = _desplazar_latitud(-5.0, 20.0)
        lat_b = _desplazar_latitud(-5.0, 60.0)
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("CONV_A", "CONVENCIONAL", lat_a, -75.0),
            ("CONV_B", "CONVENCIONAL", lat_b, -75.0),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert len(pares) == 2
        assert {p["codigo_conv"] for p in pares} == {"CONV_A", "CONV_B"}

    def test_estacion_sin_coordenadas_se_excluye_sin_error(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", None, None),
            ("AUTO2", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", -5.0, -75.0),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert len(pares) == 1
        assert pares[0]["codigo_auto"] == "AUTO2"

    def test_excluye_hidrologicas_automaticas_y_convencionales(self, tmp_path):
        # EHA (automática hidrológica) y HLG/HLM (convencionales hidrológicas)
        # no se comparan — decisión del usuario 2026-10-09.
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [
            ("EHA1", "AUTOMATICA", -5.0, -75.0, "EHA"),
            ("EMA1", "AUTOMATICA", -6.0, -75.0, "EMA"),
            ("HLG1", "CONVENCIONAL", -5.0, -75.0, "HLG"),
            ("HLM1", "CONVENCIONAL", -6.0, -75.0, "HLM"),
            ("CO1", "CONVENCIONAL", -6.0, -75.0, "CO"),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert [(p["codigo_auto"], p["codigo_conv"]) for p in pares] == [("EMA1", "CO1")]

    def test_hidrometeorologica_automatica_se_mantiene(self, tmp_path):
        # EHMA sí mide variables meteorológicas: se compara con su convencional
        # meteorológica (ej. pluviométrica), no se excluye.
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [
            ("EHMA1", "AUTOMATICA", -5.0, -75.0, "EHMA"),
            ("PLU1", "CONVENCIONAL", -5.0, -75.0, "PLU"),
        ])
        pares = emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert [(p["codigo_auto"], p["codigo_conv"]) for p in pares] == [("EHMA1", "PLU1")]

    def test_sin_estaciones_da_lista_vacia(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [])
        assert emplazamiento.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db) == []


class TestEquivalenciaVariables:
    def test_temperatura_incluye_columnas_esperadas_y_excluye_bulbo_humedo(self):
        conv = emplazamiento.EQUIVALENCIA_VARIABLES["temperatura"]["convencional"]
        assert set(conv) == {"n_tm102", "n_tm103", "n_tm104", "n_tm105", "n_tm106"}
        assert "n_tm107" not in conv
        assert "n_tm108" not in conv
        assert "n_tm109" not in conv
        assert emplazamiento.EQUIVALENCIA_VARIABLES["temperatura"]["automatica"] == "n_airtemp"

    def test_precipitacion_incluye_columnas_esperadas(self):
        conv = emplazamiento.EQUIVALENCIA_VARIABLES["precipitacion"]["convencional"]
        assert set(conv) == {"n_pt101", "n_pt102", "n_pt103"}
        assert emplazamiento.EQUIVALENCIA_VARIABLES["precipitacion"]["automatica"] == "n_lluvia"


class TestColumnasConvencionalesDisponibles:
    def test_devuelve_solo_las_columnas_presentes(self):
        disponibles = emplazamiento.columnas_convencionales_disponibles(
            "temperatura", columnas_df=["n_tm102", "n_tm104", "n_pt101"]
        )
        assert disponibles == ["n_tm102", "n_tm104"]

    def test_ninguna_columna_presente_no_lanza_error(self):
        disponibles = emplazamiento.columnas_convencionales_disponibles(
            "temperatura", columnas_df=["n_humedad"]
        )
        assert disponibles == []


class TestArmarExtraSeriesConvencional:
    """
    Cada columna convencional tiene, según el catálogo oficial de SIGMA
    (confirmado en Análisis -> DataMonitor, ver tasks/todo.md), un "tipo":
    "diaria" (máx/mín/total del día, sin hora puntual) o "puntual" (lectura a
    una hora sinóptica exacta: 07h/13h/19h). Las puntuales se desplazan a su
    hora real para caer sobre el tramo correcto de la curva continua de la
    automática; las diarias se dejan al mediodía con un símbolo distinto
    (diamante) para no insinuar que son de una hora puntual.
    """

    def test_columna_puntual_se_desplaza_a_su_hora_real(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")  # medianoche
        df_conv = pd.DataFrame({"n_tm104": [10.0, 11.0]}, index=idx)  # 07h
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        assert len(extra) == 1
        assert extra[0]["modo"] == "markers"
        assert extra[0]["symbol"] == "circle"
        assert list(extra[0]["serie"].index) == [
            pd.Timestamp("2026-01-01 07:00:00"), pd.Timestamp("2026-01-02 07:00:00"),
        ]
        assert list(extra[0]["serie"].values) == [10.0, 11.0]

    def test_columna_diaria_se_deja_al_mediodia_con_simbolo_diamante(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="D")
        df_conv = pd.DataFrame({"n_tm102": [18.0]}, index=idx)  # máxima diaria
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        assert extra[0]["symbol"] == "diamond"
        assert list(extra[0]["serie"].index) == [pd.Timestamp("2026-01-01 12:00:00")]

    def test_nombre_usa_la_etiqueta_legible_no_el_codigo_crudo(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="D")
        df_conv = pd.DataFrame({"n_tm104": [10.0], "n_tm102": [18.0]}, index=idx)
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        nombres = {e["nombre"] for e in extra}
        assert nombres == {"07h", "Máxima diaria"}

    def test_conserva_el_codigo_crudo_de_columna_para_mapear_color(self):
        """Necesario para que el panel de diferencias use el mismo color que
        su punto correspondiente en el gráfico principal (ver callbacks.py)."""
        idx = pd.date_range("2026-01-01", periods=1, freq="D")
        df_conv = pd.DataFrame({"n_tm104": [10.0]}, index=idx)
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        assert extra[0]["columna"] == "n_tm104"

    def test_conserva_el_tipo_para_que_el_callback_separe_por_grafico(self):
        idx = pd.date_range("2026-01-01", periods=1, freq="D")
        df_conv = pd.DataFrame({"n_tm104": [10.0], "n_tm102": [18.0]}, index=idx)
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        tipos = {e["columna"]: e["tipo"] for e in extra}
        assert tipos == {"n_tm104": "puntual", "n_tm102": "diaria"}

    def test_columnas_faltantes_se_omiten_sin_error(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        df_conv = pd.DataFrame({"n_humedad": [50.0, 55.0]}, index=idx)
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        assert extra == []

    def test_columna_presente_pero_toda_vacia_se_omite(self):
        """Regresión: una columna que EXISTE pero no tiene ningún valor real
        (todo NaN en el periodo) no debe generar una traza fantasma en la
        leyenda sin puntos visibles — ver tasks/todo.md, feedback real sobre
        leyendas confusas."""
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        df_conv = pd.DataFrame({"n_tm102": [None, None], "n_tm103": [12.0, 13.0]}, index=idx)
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        columnas = {e["columna"] for e in extra}
        assert columnas == {"n_tm103"}

    def test_df_vacio_no_lanza_error(self):
        df_conv = pd.DataFrame()
        assert emplazamiento.armar_extra_series_convencional(df_conv, "temperatura") == []

    def test_colores_distintos_por_columna(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        df_conv = pd.DataFrame({
            "n_tm102": [1.0, 2.0], "n_tm103": [3.0, 4.0], "n_tm104": [5.0, 6.0],
        }, index=idx)
        extra = emplazamiento.armar_extra_series_convencional(df_conv, "temperatura")
        colores = [e["color"] for e in extra]
        assert len(set(colores)) == len(colores)


class TestCalcularDiferenciasPuntuales:
    """
    Diferencia (convencional - automática) SOLO para columnas "puntual" — para
    las "diaria" (máx/mín/total) calcular una diferencia exigiría que emplazamiento compartido
    compute su propio agregado diario de la automática, y esa rigurosidad queda
    fuera de esta herramienta (límite explícito de docs/SPEC-emplazamiento-compartido.md, confirmado con
    el usuario antes de agregar este panel).
    """

    def test_diferencia_en_el_instante_exacto_de_la_hora_puntual(self):
        idx_auto = pd.date_range("2026-01-01", periods=48, freq="h")
        serie_auto = pd.Series(20.0, index=idx_auto)  # constante, fácil de verificar
        serie_auto.loc["2026-01-01 07:00:00"] = 22.0
        idx_conv = pd.date_range("2026-01-01", periods=2, freq="D")
        df_conv = pd.DataFrame({"n_tm104": [20.5, 21.0]}, index=idx_conv)  # 07h

        diffs = emplazamiento.calcular_diferencias_puntuales(serie_auto, df_conv, "temperatura")
        assert list(diffs.keys()) == ["n_tm104"]
        assert diffs["n_tm104"].loc["2026-01-01 07:00:00"] == pytest.approx(20.5 - 22.0)

    def test_columnas_diarias_no_generan_diferencia(self):
        idx_auto = pd.date_range("2026-01-01", periods=24, freq="h")
        serie_auto = pd.Series(20.0, index=idx_auto)
        idx_conv = pd.date_range("2026-01-01", periods=1, freq="D")
        df_conv = pd.DataFrame({"n_tm102": [25.0], "n_tm104": [20.2]}, index=idx_conv)

        diffs = emplazamiento.calcular_diferencias_puntuales(serie_auto, df_conv, "temperatura")
        assert "n_tm102" not in diffs
        assert "n_tm104" in diffs

    def test_sin_dato_automatica_en_ese_instante_se_omite_sin_error(self):
        idx_auto = pd.date_range("2026-01-01", periods=5, freq="h")  # solo hasta las 04h
        serie_auto = pd.Series(20.0, index=idx_auto)
        idx_conv = pd.date_range("2026-01-01", periods=1, freq="D")
        df_conv = pd.DataFrame({"n_tm106": [18.0]}, index=idx_conv)  # 19h, sin dato auto

        diffs = emplazamiento.calcular_diferencias_puntuales(serie_auto, df_conv, "temperatura")
        assert diffs["n_tm106"].empty

    def test_df_conv_vacio_da_diccionario_vacio(self):
        serie_auto = pd.Series([20.0], index=pd.date_range("2026-01-01", periods=1, freq="h"))
        assert emplazamiento.calcular_diferencias_puntuales(serie_auto, pd.DataFrame(), "temperatura") == {}


class TestCalcularExtremosDiariosAutomatica:
    """
    Máxima/mínima diaria de la automática, en 3 niveles exactos (instrucción
    original del usuario, ver tasks/todo.md Ronda 2 — corregido tras un error
    real: la primera implementación calculaba desde n_airtemp, que el usuario
    NUNCA pidió, y además subestima picos intra-hora):

      1. n_maxat/n_minat REAL (diario, reportado por SIGMA) si existe.
      2. Si no, "el máximo/mínimo de los máximos/mínimos agregados"
         (n_maxath/n_minath, el pico/valle YA agregado por hora — verificado
         con datos reales en 104114: max(n_maxath) del día captura picos que
         max(n_airtemp) se pierde), marcado "calculado": True.
      3. Si tampoco existe eso, None — nunca se calcula desde n_airtemp.
    """

    def test_usa_n_maxat_n_minat_reales_si_existen(self):
        idx = pd.date_range("2026-01-01 07:00", periods=2, freq="D")
        df_auto = pd.DataFrame({"n_maxat": [30.0, 31.0], "n_minat": [18.0, 17.5]}, index=idx)
        res = emplazamiento.calcular_extremos_diarios_automatica(df_auto)
        assert res["maxima"]["calculado"] is False
        assert res["minima"]["calculado"] is False
        assert list(res["maxima"]["serie"].values) == [30.0, 31.0]

    def test_normaliza_al_mediodia_igual_que_la_convencional(self):
        idx = pd.date_range("2026-01-01 07:00", periods=1, freq="D")
        df_auto = pd.DataFrame({"n_maxat": [30.0], "n_minat": [18.0]}, index=idx)
        res = emplazamiento.calcular_extremos_diarios_automatica(df_auto)
        assert res["maxima"]["serie"].index[0] == pd.Timestamp("2026-01-01 12:00")

    def test_respaldo_usa_maximo_de_n_maxath_no_n_airtemp(self):
        idx = pd.date_range("2026-01-01 00:00", periods=48, freq="h")
        n_maxath = [20.0 + (i % 24) for i in range(48)]  # pico horario, sube de 20 a 43
        n_airtemp = [v - 2.0 for v in n_maxath]  # lectura puntual, siempre 2° por debajo del pico
        df_auto = pd.DataFrame({"n_maxath": n_maxath, "n_airtemp": n_airtemp}, index=idx)
        res = emplazamiento.calcular_extremos_diarios_automatica(df_auto)
        assert res["maxima"]["calculado"] is True
        # 43.0 (pico real de n_maxath), NO 41.0 (que daría max de n_airtemp)
        assert list(res["maxima"]["serie"].values) == [43.0, 43.0]

    def test_sin_n_maxat_ni_n_maxath_da_none_aunque_haya_n_airtemp(self):
        """Regresión: n_airtemp NUNCA debe usarse como respaldo — no fue lo
        que pidió el usuario, y subestima picos intra-hora (verificado con
        datos reales: 16.6°C de max(n_airtemp) vs. 18.8°C real de max(n_maxath)
        el mismo día, en 104114)."""
        idx = pd.date_range("2026-01-01 00:00", periods=24, freq="h")
        df_auto = pd.DataFrame({"n_airtemp": [20.0 + i for i in range(24)]}, index=idx)
        res = emplazamiento.calcular_extremos_diarios_automatica(df_auto)
        assert res["maxima"] is None
        assert res["minima"] is None

    def test_sin_ninguna_fuente_da_none(self):
        df_auto = pd.DataFrame({"n_humedad": [50.0]}, index=pd.date_range("2026-01-01", periods=1, freq="D"))
        res = emplazamiento.calcular_extremos_diarios_automatica(df_auto)
        assert res["maxima"] is None
        assert res["minima"] is None


class TestCalcularDiferenciasDiariasTemperatura:
    def test_diferencia_convencional_menos_automatica_real(self):
        idx = pd.date_range("2026-01-01 07:00", periods=2, freq="D")
        df_auto = pd.DataFrame({"n_maxat": [30.0, 31.0], "n_minat": [18.0, 17.0]}, index=idx)
        df_conv = pd.DataFrame({"n_tm102": [30.5, 30.0], "n_tm103": [18.2, 16.5]},
                                index=pd.date_range("2026-01-01", periods=2, freq="D"))
        diffs = emplazamiento.calcular_diferencias_diarias_temperatura(df_auto, df_conv)
        assert diffs["n_tm102"].iloc[0] == pytest.approx(0.5)
        assert diffs["n_tm103"].iloc[1] == pytest.approx(-0.5)

    def test_sin_extremos_automatica_no_genera_esa_columna(self):
        df_auto = pd.DataFrame({"n_humedad": [1.0]}, index=pd.date_range("2026-01-01", periods=1, freq="D"))
        df_conv = pd.DataFrame({"n_tm102": [30.0]}, index=pd.date_range("2026-01-01", periods=1, freq="D"))
        diffs = emplazamiento.calcular_diferencias_diarias_temperatura(df_auto, df_conv)
        assert diffs == {}


class TestCalcularAcumuladoDiarioAutomatica:
    """
    Acumulado diario REAL de la automática (n_dayrain), o respaldo sumando
    n_lluvia en la ventana 07h(D-1)->07h(D) — mismo "día meteorológico" que
    usa SIGMA para n_dayrain, verificado con datos reales (ver tasks/todo.md
    Ronda 2: 1.00 calculado vs. 1.1 reportado en 4728B11C, 2025-02-13).
    """

    def test_usa_n_dayrain_real_si_existe(self):
        idx = pd.date_range("2026-01-01 07:00", periods=2, freq="D")
        df_auto = pd.DataFrame({"n_dayrain": [0.5, 1.2]}, index=idx)
        res = emplazamiento.calcular_acumulado_diario_automatica(df_auto)
        assert res["calculado"] is False
        assert list(res["serie"].values) == [0.5, 1.2]
        # Etiquetado con el día que CIERRA (07:00 de ese mismo día), igual que SIGMA
        assert res["serie"].index[0] == pd.Timestamp("2026-01-01 07:00")

    def test_respaldo_suma_ventana_07_07_si_falta_n_dayrain(self):
        # Lecturas horarias de 0.1 cada una, desde 2026-01-01 08:00 hasta
        # 2026-01-02 07:00 (24 lecturas) -> ventana que cierra el día 02.
        idx = pd.date_range("2026-01-01 08:00", periods=24, freq="h")
        df_auto = pd.DataFrame({"n_lluvia": [0.1] * 24}, index=idx)
        res = emplazamiento.calcular_acumulado_diario_automatica(df_auto)
        assert res["calculado"] is True
        dia_cierre = pd.Timestamp("2026-01-02 07:00")
        assert dia_cierre in res["serie"].index
        assert res["serie"].loc[dia_cierre] == pytest.approx(2.4)

    def test_sin_ninguna_fuente_da_none(self):
        df_auto = pd.DataFrame({"n_humedad": [1.0]}, index=pd.date_range("2026-01-01", periods=1, freq="D"))
        assert emplazamiento.calcular_acumulado_diario_automatica(df_auto) is None


class TestCalcularDiferenciasPrecipitacionDiaria:
    def test_alinea_pt101_un_dia_adelante_antes_de_restar(self):
        # n_pt101 fechado "2026-01-01" representa el período que CIERRA el
        # 2026-01-02 (ver EQUIVALENCIA_VARIABLES, desfase_dias_cierre) — debe
        # compararse contra n_dayrain fechado 2026-01-02, no 2026-01-01.
        df_conv = pd.DataFrame({"n_pt101": [5.0]}, index=pd.date_range("2026-01-01", periods=1, freq="D"))
        df_auto = pd.DataFrame({"n_dayrain": [5.5]}, index=pd.date_range("2026-01-02 07:00", periods=1, freq="D"))
        diff = emplazamiento.calcular_diferencias_precipitacion_diaria(df_auto, df_conv)
        assert diff is not None
        assert diff.iloc[0] == pytest.approx(5.0 - 5.5)

    def test_sin_dato_automatica_da_none(self):
        df_conv = pd.DataFrame({"n_pt101": [5.0]}, index=pd.date_range("2026-01-01", periods=1, freq="D"))
        df_auto = pd.DataFrame({"n_humedad": [1.0]}, index=pd.date_range("2026-01-02", periods=1, freq="D"))
        assert emplazamiento.calcular_diferencias_precipitacion_diaria(df_auto, df_conv) is None


class TestCalcularVentaneoAutomatica:
    """
    Suma de n_lluvia en las ventanas nocturna (19:01->07:00) y diurna
    (07:01->19:00), para comparar contra n_pt102/n_pt103. Cálculo propio de
    emplazamiento compartido (no un estudio estadístico formal) — autorizado explícitamente por
    el usuario tras confirmar la física real del proceso de observación
    (ver tasks/todo.md, Ronda 2).
    """

    def test_ventana_diurna_suma_solo_07_a_19(self):
        idx = pd.date_range("2026-01-01 00:00", periods=24, freq="h")
        valores = [1.0] * 24  # una unidad por hora, todo el día
        df_auto = pd.DataFrame({"n_lluvia": valores}, index=idx)
        res = emplazamiento.calcular_ventaneo_automatica(df_auto)
        # 07:01-19:00 -> horas en punto 08,09,...,19 => 12 lecturas de 1.0
        assert res["diurna"].loc[pd.Timestamp("2026-01-01 19:00")] == pytest.approx(12.0)

    def test_ventana_nocturna_cruza_medianoche_y_cierra_en_el_dia_siguiente(self):
        idx = pd.date_range("2026-01-01 00:00", periods=48, freq="h")
        valores = [1.0] * 48
        df_auto = pd.DataFrame({"n_lluvia": valores}, index=idx)
        res = emplazamiento.calcular_ventaneo_automatica(df_auto)
        # 19:01(01) -> 07:00(02): horas en punto 20,21,22,23(01) + 00..07(02) = 12 lecturas
        assert res["nocturna"].loc[pd.Timestamp("2026-01-02 07:00")] == pytest.approx(12.0)

    def test_sin_n_lluvia_da_ventanas_vacias(self):
        df_auto = pd.DataFrame({"n_humedad": [1.0]}, index=pd.date_range("2026-01-01", periods=1, freq="h"))
        res = emplazamiento.calcular_ventaneo_automatica(df_auto)
        assert res["diurna"].empty and res["nocturna"].empty


class TestCalcularDiferenciasPrecipitacionVentaneo:
    def test_diferencia_por_ventana(self):
        idx_auto = pd.date_range("2026-01-01 00:00", periods=48, freq="h")
        df_auto = pd.DataFrame({"n_lluvia": [0.5] * 48}, index=idx_auto)
        df_conv = pd.DataFrame(
            {"n_pt102": [7.0], "n_pt103": [5.0]},
            index=pd.date_range("2026-01-02", periods=1, freq="D"),
        )
        diffs = emplazamiento.calcular_diferencias_precipitacion_ventaneo(df_auto, df_conv)
        # nocturna que cierra 2026-01-02 07:00 = 12 * 0.5 = 6.0 -> pt102(7.0) - 6.0 = 1.0
        assert diffs["n_pt102"].iloc[0] == pytest.approx(1.0)
        # diurna que cierra 2026-01-02 19:00 = 12 * 0.5 = 6.0 -> pt103(5.0) - 6.0 = -1.0
        assert diffs["n_pt103"].iloc[0] == pytest.approx(-1.0)
