"""
Tests de core.data_loader.tramos_descargados: cobertura LOCAL leída solo del
nombre de archivo ({codigo}_{fi}_{ff}.csv), sin abrir ningún CSV — clave para
que mostrar el periodo disponible en la UI sea instantáneo.
"""
from __future__ import annotations

import pandas as pd
import pytest

from analizador_series.core import data_loader


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    auto = tmp_path / "automaticas"
    conv = tmp_path / "convencionales"
    auto.mkdir()
    conv.mkdir()
    monkeypatch.setattr(data_loader, "DIR_AUTO", auto)
    monkeypatch.setattr(data_loader, "DIR_CONV", conv)
    return auto, conv


def _crear(carpeta, nombre):
    (carpeta / nombre).write_text("Fecha,Hora\n", encoding="utf-8")


class TestTramosDescargados:
    def test_sin_csv_da_lista_vacia(self, dirs):
        assert data_loader.tramos_descargados("ABC123") == []

    def test_un_solo_csv_da_un_tramo(self, dirs):
        auto, _ = dirs
        _crear(auto, "ABC123_2020-01-01_2020-12-31.csv")
        tramos = data_loader.tramos_descargados("ABC123")
        assert tramos == [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))]

    def test_tramos_solapados_se_fusionan(self, dirs):
        auto, _ = dirs
        _crear(auto, "ABC123_2020-01-01_2020-06-30.csv")
        _crear(auto, "ABC123_2020-05-01_2020-12-31.csv")
        tramos = data_loader.tramos_descargados("ABC123")
        assert tramos == [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))]

    def test_tramos_contiguos_a_un_dia_se_fusionan(self, dirs):
        auto, _ = dirs
        _crear(auto, "ABC123_2020-01-01_2020-06-30.csv")
        _crear(auto, "ABC123_2020-07-01_2020-12-31.csv")  # arranca justo al día siguiente
        tramos = data_loader.tramos_descargados("ABC123")
        assert tramos == [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))]

    def test_tramos_con_hueco_real_no_se_fusionan(self, dirs):
        auto, _ = dirs
        _crear(auto, "ABC123_2020-01-01_2020-03-31.csv")
        _crear(auto, "ABC123_2022-01-01_2022-12-31.csv")
        tramos = data_loader.tramos_descargados("ABC123")
        assert tramos == [
            (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31")),
            (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
        ]

    def test_junta_automaticas_y_convencionales(self, dirs):
        auto, conv = dirs
        _crear(auto, "ABC123_2020-01-01_2020-06-30.csv")
        _crear(conv, "ABC123_2020-07-01_2020-12-31.csv")
        tramos = data_loader.tramos_descargados("ABC123")
        assert tramos == [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))]

    def test_nombre_sin_rango_parseable_se_ignora(self, dirs):
        auto, _ = dirs
        _crear(auto, "ABC123_sin_rango.csv")
        assert data_loader.tramos_descargados("ABC123") == []

    def test_no_lee_contenido_del_csv(self, dirs, monkeypatch):
        """Si algo intentara abrir el archivo, esto lo detecta: se rompe el
        contenido a propósito y la función debe seguir funcionando igual,
        porque solo mira el nombre."""
        auto, _ = dirs
        p = auto / "ABC123_2020-01-01_2020-12-31.csv"
        p.write_bytes(b"\xff\xfe\x00contenido invalido no utf-8")
        tramos = data_loader.tramos_descargados("ABC123")
        assert tramos == [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))]

    def test_codigo_es_case_insensitive(self, dirs):
        auto, _ = dirs
        _crear(auto, "ABC123_2020-01-01_2020-12-31.csv")
        assert data_loader.tramos_descargados("abc123") == [
            (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))
        ]


class TestFiltrarPorFlags:
    def _df(self):
        return pd.DataFrame({
            "n_airtemp": [20.0, 21.0, 22.0],
            "flag_n_airtemp": ["C", "M", "C"],
            "cc_n_airtemp": ["BUENO", "BUENO", "MALO"],
        })

    def test_flags_incluidos_none_no_filtra(self):
        r = data_loader.filtrar_por_flags(self._df(), None)
        assert r["n_airtemp"].tolist() == [20.0, 21.0, 22.0]

    def test_filtra_por_flag_de_sigma_por_defecto(self):
        r = data_loader.filtrar_por_flags(self._df(), ["C"])
        assert r["n_airtemp"].iloc[0] == 20.0
        assert pd.isna(r["n_airtemp"].iloc[1])  # M excluido
        assert r["n_airtemp"].iloc[2] == 22.0

    def test_prefijo_flag_permite_filtrar_por_cc_propio(self):
        r = data_loader.filtrar_por_flags(self._df(), ["BUENO"], prefijo_flag="cc_")
        assert r["n_airtemp"].iloc[0] == 20.0
        assert r["n_airtemp"].iloc[1] == 21.0
        assert pd.isna(r["n_airtemp"].iloc[2])  # MALO excluido

    def test_ambos_filtros_son_independientes_y_combinables(self):
        # Filtrar primero por SIGMA (excluye índice 1), después por CC (excluye índice 2)
        df = self._df()
        paso1 = data_loader.filtrar_por_flags(df, ["C"])
        paso2 = data_loader.filtrar_por_flags(paso1, ["BUENO"], prefijo_flag="cc_")
        assert paso2["n_airtemp"].iloc[0] == 20.0
        assert pd.isna(paso2["n_airtemp"].iloc[1])
        assert pd.isna(paso2["n_airtemp"].iloc[2])

    def test_columna_de_flag_ausente_no_rompe(self):
        df = pd.DataFrame({"n_airtemp": [20.0]})  # sin flag_n_airtemp ni cc_n_airtemp
        r = data_loader.filtrar_por_flags(df, ["C"])
        assert r["n_airtemp"].iloc[0] == 20.0


def _df_dias(codigo, dias_con_valor, dias_sin_valor=()):
    """Una fila diaria por fecha; n_x con valor en dias_con_valor y NaN en dias_sin_valor."""
    filas = [(codigo, pd.Timestamp(d), 1.0) for d in dias_con_valor]
    filas += [(codigo, pd.Timestamp(d), float("nan")) for d in dias_sin_valor]
    return pd.DataFrame(filas, columns=["codigo", "datetime", "n_x"])


class TestTramosConDatos:
    """Cobertura REAL (días con al menos un valor medido), no la del nombre del CSV:
    un archivo pedido para ene→sep puede traer solo jun y ago (caso real 114066)."""

    def test_dos_meses_separados_dan_dos_tramos(self):
        dias = list(pd.date_range("2026-06-01", "2026-06-30")) + list(pd.date_range("2026-08-01", "2026-08-31"))
        tramos = data_loader.tramos_con_datos(_df_dias("114066", dias), "114066")
        assert tramos == [
            (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-06-30")),
            (pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31")),
        ]

    def test_filas_sin_ningun_valor_no_cuentan(self):
        df = _df_dias("A", ["2026-01-01", "2026-01-02"], dias_sin_valor=["2026-01-03", "2026-01-04"])
        assert data_loader.tramos_con_datos(df, "A") == [
            (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")),
        ]

    def test_varios_registros_el_mismo_dia_cuentan_una_vez(self):
        df = pd.DataFrame({
            "codigo": ["A"] * 3,
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 10:00", "2026-01-02 05:00"]),
            "n_x": [1.0, 2.0, 3.0],
        })
        assert data_loader.tramos_con_datos(df, "A") == [
            (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")),
        ]

    def test_solo_considera_la_estacion_pedida(self):
        df = pd.concat([_df_dias("A", ["2026-01-01"]), _df_dias("B", ["2026-05-01"])])
        assert data_loader.tramos_con_datos(df, "a") == [
            (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-01")),
        ]

    def test_df_vacio_o_sin_valores_da_lista_vacia(self):
        assert data_loader.tramos_con_datos(pd.DataFrame(), "A") == []
        assert data_loader.tramos_con_datos(_df_dias("A", [], ["2026-01-01"]), "A") == []
