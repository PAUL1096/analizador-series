"""
Tests de descarga.descargar_datos_meteo_sigma._construir_csv.

Bug real encontrado probando la pestaña vecindad (2026-09-30): SIGMA usa
nombres de campo de fecha DISTINTOS según la familia de datos —
"d_fecha_reg"/"v_hora_reg" para automáticas e hidrológicas, pero "FECHA"
(mayúsculas, sin hora) para meteorológicas convencionales diarias
(temperatura n_tm*/precipitación n_pt*, justo las que necesita vecindad).
_construir_csv solo buscaba "d_fecha_reg" — para las de familia "FECHA" el
campo quedaba vacío en todas las filas, y el deduplicado por (fecha, hora)
colapsaba TODO el período a una sola fila corrupta. Reproducido real contra
la API con 106077 (CHUGUR) y 100043 (FONAGRO): ambas bajaron 1 sola fila sin
Fecha/Hora en vez de 31/30 filas reales.
"""
from __future__ import annotations

from descarga import descargar_datos_meteo_sigma as dl


def _fila_automatica(fecha, hora, valor):
    return {"d_fecha_reg": fecha, "v_hora_reg": hora, "n_airtemp": valor, "flag_n_airtemp": "C"}


def _fila_convencional_mayusculas(fecha, valor):
    """Forma real devuelta por SIGMA para n_tm*/n_pt* — sin v_hora_reg."""
    return {"FECHA": fecha, "n_tm102": valor, "flag_n_tm102": "C"}


class TestConstruirCsvFamiliaFechaMinuscula:
    def test_automatica_con_d_fecha_reg_y_hora_no_colapsa(self):
        datos = [
            _fila_automatica("2026-05-01", "00:00:00", 10.5),
            _fila_automatica("2026-05-01", "01:00:00", 10.6),
            _fila_automatica("2026-05-02", "00:00:00", 11.0),
        ]
        csv = dl._construir_csv(datos)
        filas = csv.strip().split("\n")
        assert len(filas) == 1 + 3  # header + 3 registros reales, ninguno colapsado


class TestConstruirCsvFamiliaFechaMayuscula:
    def test_convencional_con_FECHA_no_colapsa_a_una_fila(self):
        datos = [
            _fila_convencional_mayusculas("2026-06-01", 25.4),
            _fila_convencional_mayusculas("2026-06-02", 25.0),
            _fila_convencional_mayusculas("2026-06-03", 22.2),
        ]
        csv = dl._construir_csv(datos)
        filas = csv.strip().split("\n")
        assert len(filas) == 1 + 3, (
            "Las 3 fechas distintas deben quedar como 3 filas — si colapsa a 1, "
            "revivió el bug de 'FECHA' vs 'd_fecha_reg'"
        )

    def test_convencional_con_FECHA_usa_00_00_como_hora(self):
        datos = [_fila_convencional_mayusculas("2026-06-01", 25.4)]
        csv = dl._construir_csv(datos)
        fila = csv.strip().split("\n")[1]
        assert fila.startswith("2026-06-01,00:00,")

    def test_fechas_distintas_producen_filas_distintas_no_vacias(self):
        datos = [
            _fila_convencional_mayusculas("2026-06-01", 25.4),
            _fila_convencional_mayusculas("2026-06-02", 25.0),
        ]
        csv = dl._construir_csv(datos)
        filas = csv.strip().split("\n")[1:]
        fechas = [f.split(",")[0] for f in filas]
        assert fechas == ["2026-06-01", "2026-06-02"]
        assert "" not in fechas
