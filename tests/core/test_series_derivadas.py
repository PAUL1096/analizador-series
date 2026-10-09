"""
Tests de los nombres legibles de variables (series_derivadas.info_variable /
etiqueta_variable): ninguna pantalla debe mostrar el código crudo de SIGMA
como si fuera un nombre cuando hay uno conocido.
"""
from __future__ import annotations

from analizador_series.core import series_derivadas as sd


class TestNombresVariables:
    def test_variable_con_bloque_propio_usa_su_nombre(self):
        assert sd.info_variable("n_airtemp")["display_name"] == "Temperatura del aire"
        assert sd.info_variable("n_airtemp")["unidad"] == "°C"

    def test_variable_sin_bloque_usa_nombres_variables(self):
        info = sd.info_variable("n_bateria")
        assert info["display_name"] == "Voltaje de batería"
        assert info["unidad"] == "V"

    def test_convencional_toma_el_nombre_del_catalogo(self):
        assert sd.info_variable("n_pt101")["display_name"] == "Precipitación total diaria"
        assert sd.info_variable("n_tm105")["display_name"] == "Temperatura de bulbo seco a las 13 h"

    def test_maxrh_es_diaria_y_maxrhh_horaria(self):
        assert sd.info_variable("n_maxrh")["display_name"] == "Humedad relativa máxima diaria"
        assert sd.info_variable("n_maxrhh")["display_name"] == "Humedad relativa máxima horaria"

    def test_desconocida_cae_al_codigo(self):
        info = sd.info_variable("n_inventada_xyz")
        assert info["display_name"] == "n_inventada_xyz"
        assert info["unidad"] == ""


class TestEtiquetaVariable:
    def test_sin_codigo_es_solo_el_nombre(self):
        assert sd.etiqueta_variable("n_bateria") == "Voltaje de batería"

    def test_con_codigo_agrega_el_codigo(self):
        assert sd.etiqueta_variable("n_bateria", con_codigo=True) == "Voltaje de batería · n_bateria"

    def test_con_codigo_no_lo_duplica_si_el_nombre_ya_lo_trae(self):
        assert sd.etiqueta_variable("n_airtemp_10m", con_codigo=True) == "Temperatura del aire (n_airtemp_10m)"

    def test_desconocida_con_codigo_no_se_repite(self):
        assert sd.etiqueta_variable("n_inventada_xyz", con_codigo=True) == "n_inventada_xyz"


class TestEtiquetaDerivada:
    def test_traduce_el_id_interno(self):
        assert sd.etiqueta_derivada("n_humedad", "absdHR_1h") == "Cambio absoluto en 1 h · Humedad relativa"

    def test_id_desconocido_se_devuelve_tal_cual(self):
        assert sd.etiqueta_derivada("n_humedad", "xyz") == "xyz"
