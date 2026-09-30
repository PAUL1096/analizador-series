"""
Tests de core.vecindad: pares co-ubicados (automática↔convencional, <umbral_m)
y diccionario de equivalencia de variables físicas. Ver docs/SPEC-vecindad.md
y tasks/todo.md Task 2.
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd
import pytest

from analizador_series.core import vecindad

R_TIERRA_M = 6371000.0  # mismo radio que usa vecindad._haversine_m


def _desplazar_latitud(lat: float, distancia_m: float) -> float:
    """
    Desplazamiento norte-sur puro: un meridiano es un círculo máximo, así que
    la distancia a lo largo de él es exactamente R*ángulo (sin aproximación),
    independiente de la fórmula de haversine que se está probando.
    """
    return lat + math.degrees(distancia_m / R_TIERRA_M)


def _crear_db(ruta_db, estaciones):
    """estaciones: lista de (codigo, categoria, latitud, longitud) — latitud/
    longitud pueden ser None."""
    con = sqlite3.connect(ruta_db)
    con.execute(
        "CREATE TABLE estaciones (codigo TEXT PRIMARY KEY, categoria TEXT, "
        "latitud REAL, longitud REAL)"
    )
    con.executemany(
        "INSERT INTO estaciones (codigo, categoria, latitud, longitud) VALUES (?, ?, ?, ?)",
        estaciones,
    )
    con.commit()
    con.close()


class TestHaversineM:
    def test_mismo_punto_da_distancia_cero(self):
        assert vecindad._haversine_m(-5.0, -75.0, -5.0, -75.0) == pytest.approx(0.0, abs=1e-6)

    def test_un_grado_de_longitud_en_el_ecuador(self):
        # Circunferencia ecuatorial / 360, calculado directo (no vía haversine).
        esperado = (2 * math.pi * R_TIERRA_M) / 360
        obtenido = vecindad._haversine_m(0.0, 0.0, 0.0, 1.0)
        assert obtenido == pytest.approx(esperado, rel=1e-6)

    def test_desplazamiento_norte_sur_exacto(self):
        lat2 = _desplazar_latitud(-5.0, 250.0)
        assert vecindad._haversine_m(-5.0, -75.0, lat2, -75.0) == pytest.approx(250.0, rel=1e-6)


class TestCalcularParesColocados:
    def test_par_dentro_del_umbral_entra(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        lat_conv = _desplazar_latitud(-5.0, 99.0)
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", lat_conv, -75.0),
        ])
        pares = vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
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
        pares = vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert pares == []

    def test_no_empareja_misma_categoria(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", -5.0, -75.0),
            ("AUTO2", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", -5.0, -75.0),
            ("CONV2", "CONVENCIONAL", -5.0, -75.0),
        ])
        pares = vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
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
        pares = vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
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
        pares = vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert len(pares) == 2
        assert {p["codigo_conv"] for p in pares} == {"CONV_A", "CONV_B"}

    def test_estacion_sin_coordenadas_se_excluye_sin_error(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [
            ("AUTO1", "AUTOMATICA", None, None),
            ("AUTO2", "AUTOMATICA", -5.0, -75.0),
            ("CONV1", "CONVENCIONAL", -5.0, -75.0),
        ])
        pares = vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db)
        assert len(pares) == 1
        assert pares[0]["codigo_auto"] == "AUTO2"

    def test_sin_estaciones_da_lista_vacia(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        _crear_db(ruta_db, [])
        assert vecindad.calcular_pares_colocados(umbral_m=100.0, ruta_db=ruta_db) == []


class TestEquivalenciaVariables:
    def test_temperatura_incluye_columnas_esperadas_y_excluye_bulbo_humedo(self):
        conv = vecindad.EQUIVALENCIA_VARIABLES["temperatura"]["convencional"]
        assert set(conv) == {"n_tm102", "n_tm103", "n_tm104", "n_tm105", "n_tm106"}
        assert "n_tm107" not in conv
        assert "n_tm108" not in conv
        assert "n_tm109" not in conv
        assert vecindad.EQUIVALENCIA_VARIABLES["temperatura"]["automatica"] == "n_airtemp"

    def test_precipitacion_incluye_columnas_esperadas(self):
        conv = vecindad.EQUIVALENCIA_VARIABLES["precipitacion"]["convencional"]
        assert set(conv) == {"n_pt101", "n_pt102", "n_pt103"}
        assert vecindad.EQUIVALENCIA_VARIABLES["precipitacion"]["automatica"] == "n_lluvia"


class TestColumnasConvencionalesDisponibles:
    def test_devuelve_solo_las_columnas_presentes(self):
        disponibles = vecindad.columnas_convencionales_disponibles(
            "temperatura", columnas_df=["n_tm102", "n_tm104", "n_pt101"]
        )
        assert disponibles == ["n_tm102", "n_tm104"]

    def test_ninguna_columna_presente_no_lanza_error(self):
        disponibles = vecindad.columnas_convencionales_disponibles(
            "temperatura", columnas_df=["n_humedad"]
        )
        assert disponibles == []


class TestArmarExtraSeriesConvencional:
    def test_una_serie_por_columna_disponible_en_modo_markers(self):
        idx = pd.date_range("2026-01-01", periods=3, freq="D")
        df_conv = pd.DataFrame({"n_tm102": [10.0, 11.0, 12.0], "n_pt101": [0.0, 1.0, 0.0]}, index=idx)
        extra = vecindad.armar_extra_series_convencional(df_conv, "temperatura")
        assert len(extra) == 1
        assert extra[0]["nombre"] == "n_tm102"
        assert extra[0]["modo"] == "markers"
        assert list(extra[0]["serie"].values) == [10.0, 11.0, 12.0]

    def test_columnas_faltantes_se_omiten_sin_error(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        df_conv = pd.DataFrame({"n_humedad": [50.0, 55.0]}, index=idx)
        extra = vecindad.armar_extra_series_convencional(df_conv, "temperatura")
        assert extra == []

    def test_df_vacio_no_lanza_error(self):
        df_conv = pd.DataFrame()
        assert vecindad.armar_extra_series_convencional(df_conv, "temperatura") == []

    def test_colores_distintos_por_columna(self):
        idx = pd.date_range("2026-01-01", periods=2, freq="D")
        df_conv = pd.DataFrame({
            "n_tm102": [1.0, 2.0], "n_tm103": [3.0, 4.0], "n_tm104": [5.0, 6.0],
        }, index=idx)
        extra = vecindad.armar_extra_series_convencional(df_conv, "temperatura")
        colores = [e["color"] for e in extra]
        assert len(set(colores)) == len(colores)
