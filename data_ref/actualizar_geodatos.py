"""
Refresca data_ref/estaciones.db con altitud, región natural (Costa/Sierra/Selva)
y coordenadas (latitud/longitud) por estación, a partir de un export
"Georeferencias" de SIGMA.

data_ref/estaciones.db es un snapshot extraído una vez de sgo.db (ver
docs/ESTADO_MIGRACION_Y_PENDIENTES.md §"Fase A") y nunca tuvo coordenadas ni
altitud/región. Las reglas de control_calidad.py para estaciones convencionales
(MT-DRD-003 §6.3.2, variación día a día por región+altitud) necesitan altitud/
región; core/vecindad.py (docs/SPEC-vecindad.md) necesita latitud/longitud para
calcular pares co-ubicados. Este script agrega/refresca las cuatro columnas,
re-ejecutable sin duplicar filas (UPDATE por código, no INSERT).

Uso:
    python actualizar_geodatos.py <ruta_a_georeferencias.xlsx>
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analizador_series.config import CATALOGO_DB  # noqa: E402

COLUMNAS_REQUERIDAS = {"Código", "Latitud", "Longitud", "Altitud (m)", "Región Natural"}
REGIONES_VALIDAS = {"Costa", "Sierra", "Selva"}


def _leer_georeferencias(ruta_excel: Path) -> pd.DataFrame:
    df = pd.read_excel(ruta_excel, sheet_name="Georeferencias")
    faltantes = COLUMNAS_REQUERIDAS - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas en {ruta_excel.name}: {faltantes}")

    df = df[["Código", "Latitud", "Longitud", "Altitud (m)", "Región Natural"]].rename(columns={
        "Código": "codigo",
        "Latitud": "latitud",
        "Longitud": "longitud",
        "Altitud (m)": "altitud",
        "Región Natural": "region_natural",
    })
    df["codigo"] = df["codigo"].astype(str).str.strip()
    df = df.dropna(subset=["codigo"])

    invalidas = set(df["region_natural"].dropna()) - REGIONES_VALIDAS
    if invalidas:
        raise ValueError(
            f"Región Natural con valores no esperados (se esperaba {REGIONES_VALIDAS}): {invalidas}"
        )
    return df


def _asegurar_columnas(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(estaciones)")}
    if "altitud" not in cols:
        con.execute("ALTER TABLE estaciones ADD COLUMN altitud REAL")
    if "region_natural" not in cols:
        con.execute("ALTER TABLE estaciones ADD COLUMN region_natural TEXT")
    if "latitud" not in cols:
        con.execute("ALTER TABLE estaciones ADD COLUMN latitud REAL")
    if "longitud" not in cols:
        con.execute("ALTER TABLE estaciones ADD COLUMN longitud REAL")


def actualizar(ruta_excel: Path, ruta_db: Path = CATALOGO_DB) -> dict:
    df = _leer_georeferencias(ruta_excel)

    con = sqlite3.connect(ruta_db)
    try:
        _asegurar_columnas(con)
        codigos_db = {row[0] for row in con.execute("SELECT codigo FROM estaciones")}

        actualizadas = 0
        sin_match = 0
        for _, fila in df.iterrows():
            if fila["codigo"] not in codigos_db:
                sin_match += 1
                continue
            con.execute(
                "UPDATE estaciones SET altitud = ?, region_natural = ?, latitud = ?, longitud = ? "
                "WHERE codigo = ?",
                (float(fila["altitud"]) if pd.notna(fila["altitud"]) else None,
                 fila["region_natural"] if pd.notna(fila["region_natural"]) else None,
                 float(fila["latitud"]) if pd.notna(fila["latitud"]) else None,
                 float(fila["longitud"]) if pd.notna(fila["longitud"]) else None,
                 fila["codigo"]),
            )
            actualizadas += 1
        con.commit()
    finally:
        con.close()

    return {"actualizadas": actualizadas, "sin_match_en_db": sin_match, "filas_excel": len(df)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruta_excel", type=Path, help="Export 'Georeferencias' (.xlsx) de SIGMA")
    args = parser.parse_args()

    if not args.ruta_excel.exists():
        print(f"[!] No existe: {args.ruta_excel}", file=sys.stderr)
        return 1

    resultado = actualizar(args.ruta_excel)
    print(f"[OK] {resultado['actualizadas']} estaciones actualizadas en {CATALOGO_DB.name}")
    if resultado["sin_match_en_db"]:
        print(f"[!] {resultado['sin_match_en_db']} códigos del Excel no existen en estaciones.db (ignorados)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
