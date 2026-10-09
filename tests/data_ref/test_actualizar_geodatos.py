"""
Tests de data_ref.actualizar_geodatos: agrega/refresca altitud, región natural
y (Task 1 de docs/SPEC-emplazamiento-compartido.md) latitud/longitud en estaciones.db a partir
del export "Georeferencias" de SIGMA. Ver tasks/todo.md Task 1.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from data_ref import actualizar_geodatos


def _crear_db(ruta_db, codigos):
    con = sqlite3.connect(ruta_db)
    con.execute(
        "CREATE TABLE estaciones (codigo TEXT PRIMARY KEY, nombre TEXT, categoria TEXT)"
    )
    for cod in codigos:
        con.execute("INSERT INTO estaciones (codigo, nombre, categoria) VALUES (?, ?, ?)",
                     (cod, f"Estación {cod}", "AUTOMATICA"))
    con.commit()
    con.close()


def _crear_excel(ruta_excel, filas):
    df = pd.DataFrame(filas, columns=[
        "Código", "Latitud", "Longitud", "Altitud (m)", "Región Natural",
    ])
    with pd.ExcelWriter(ruta_excel, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Georeferencias", index=False)


class TestLeerGeoreferenciasConLatLon:
    def test_incluye_latitud_y_longitud(self, tmp_path):
        ruta_excel = tmp_path / "georef.xlsx"
        _crear_excel(ruta_excel, [
            ("101004", -0.4667, -75.4833, 220.0, "Selva"),
        ])
        df = actualizar_geodatos._leer_georeferencias(ruta_excel)
        assert "latitud" in df.columns
        assert "longitud" in df.columns
        assert df.loc[0, "latitud"] == pytest.approx(-0.4667)
        assert df.loc[0, "longitud"] == pytest.approx(-75.4833)


class TestActualizarConLatLon:
    def test_puebla_latitud_longitud_para_estaciones_con_match(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        ruta_excel = tmp_path / "georef.xlsx"
        _crear_db(ruta_db, ["101004"])
        _crear_excel(ruta_excel, [
            ("101004", -0.4667, -75.4833, 220.0, "Selva"),
        ])

        actualizar_geodatos.actualizar(ruta_excel, ruta_db=ruta_db)

        con = sqlite3.connect(ruta_db)
        fila = con.execute(
            "SELECT latitud, longitud FROM estaciones WHERE codigo = '101004'"
        ).fetchone()
        con.close()
        assert fila == pytest.approx((-0.4667, -75.4833))

    def test_estacion_sin_match_en_excel_queda_en_null(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        ruta_excel = tmp_path / "georef.xlsx"
        _crear_db(ruta_db, ["101004", "999999"])
        _crear_excel(ruta_excel, [
            ("101004", -0.4667, -75.4833, 220.0, "Selva"),
        ])

        actualizar_geodatos.actualizar(ruta_excel, ruta_db=ruta_db)

        con = sqlite3.connect(ruta_db)
        fila = con.execute(
            "SELECT latitud, longitud FROM estaciones WHERE codigo = '999999'"
        ).fetchone()
        con.close()
        assert fila == (None, None)

    def test_reejecutar_no_duplica_filas(self, tmp_path):
        ruta_db = tmp_path / "estaciones.db"
        ruta_excel = tmp_path / "georef.xlsx"
        _crear_db(ruta_db, ["101004"])
        _crear_excel(ruta_excel, [
            ("101004", -0.4667, -75.4833, 220.0, "Selva"),
        ])

        actualizar_geodatos.actualizar(ruta_excel, ruta_db=ruta_db)
        actualizar_geodatos.actualizar(ruta_excel, ruta_db=ruta_db)

        con = sqlite3.connect(ruta_db)
        total = con.execute("SELECT COUNT(*) FROM estaciones").fetchone()[0]
        con.close()
        assert total == 1
