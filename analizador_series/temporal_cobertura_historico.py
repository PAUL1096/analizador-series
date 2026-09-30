# -*- coding: utf-8 -*-
"""
Analisis de cobertura historica de estaciones automaticas por DZ y semana.

Objetivo: evaluar si el historico de descargas semanales es lo suficientemente
consistente para calibrar umbrales estadisticos, o si hay DZs con descargas
incompletas que requieren re-descarga.

Metrica: n_estaciones = numero de codigos UNICOS en estaciones.csv por (DZ, semana).
Linea base por DZ: MEDIANA (robusta a las caidas que justamente queremos detectar).
"""
import os
import re
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = (r"C:/Users/drd06/Documents/SGR TEMPORALES/Desarrollos/"
        r"Dashboard-para-monitoreo-de-la-operatividad/DATA/automaticas/historico/csvs")
OUT_DIR = (r"C:/Users/drd06/Documents/SGR TEMPORALES/Desarrollos/"
           r"Dashboard-para-monitoreo-de-la-operatividad/analizador_series")

# Nombre de carpeta: DZ10_2024-01-05_2024-01-11
PAT = re.compile(r"^(DZ\d{1,2})_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$")


def leer_csv_robusto(path):
    """Lee CSV probando utf-8 (con BOM) y latin1 como fallback."""
    for enc in ("utf-8-sig", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, Exception):
            continue
    return None


def col_codigo(df):
    """Localiza la columna de codigo sin asumir tilde/capitalizacion."""
    for c in df.columns:
        cn = c.strip().lower().replace("ó", "o")
        if cn == "codigo":
            return c
    return None


def main():
    registros = []
    columnas_vistas = None
    fila_ejemplo = None
    errores = []

    carpetas = []
    for anio in ("2023", "2024", "2025", "2026"):
        d = os.path.join(BASE, anio)
        if not os.path.isdir(d):
            continue
        for nombre in os.listdir(d):
            ruta = os.path.join(d, nombre)
            if os.path.isdir(ruta):
                carpetas.append((anio, nombre, ruta))

    for anio, nombre, ruta in carpetas:
        m = PAT.match(nombre)
        if not m:
            errores.append(f"nombre no parseable: {anio}/{nombre}")
            continue
        dz, fi, ff = m.group(1), m.group(2), m.group(3)
        est_path = os.path.join(ruta, "estaciones.csv")
        if not os.path.isfile(est_path):
            errores.append(f"sin estaciones.csv: {anio}/{nombre}")
            continue
        df = leer_csv_robusto(est_path)
        if df is None or df.empty:
            errores.append(f"vacio/ilegible: {anio}/{nombre}")
            continue

        if columnas_vistas is None:
            columnas_vistas = list(df.columns)
            fila_ejemplo = df.iloc[0].to_dict()

        cc = col_codigo(df)
        n_unicas = df[cc].nunique() if cc else len(df)
        n_filas = len(df)

        registros.append({
            "anio": int(anio),
            "DZ": dz,
            "dz_num": int(dz.replace("DZ", "")),
            "fecha_inicio": pd.to_datetime(fi),
            "fecha_fin": pd.to_datetime(ff),
            "n_estaciones": int(n_unicas),
            "n_filas": int(n_filas),
        })

    df = pd.DataFrame(registros).sort_values(["dz_num", "fecha_inicio"]).reset_index(drop=True)

    print("=" * 78)
    print("PASO 1 - PERFILADO")
    print("=" * 78)
    print(f"Carpetas validas leidas : {len(df)}")
    print(f"Errores/omisiones        : {len(errores)}")
    print(f"\nColumnas de estaciones.csv ({len(columnas_vistas)}):")
    for c in columnas_vistas:
        print(f"  - {c}")
    print("\nFila de ejemplo:")
    for k, v in fila_ejemplo.items():
        print(f"  {k!r}: {v!r}")
    dup = (df["n_filas"] - df["n_estaciones"])
    print(f"\nFilas con duplicados de Codigo (filas>unicos): {(dup > 0).sum()} "
          f"(max exceso={int(dup.max())})")
    if errores[:10]:
        print("\nPrimeros errores/omisiones:")
        for e in errores[:10]:
            print("  *", e)

    # -------- PASO 2A: cobertura temporal (semanas por DZ por anio) --------
    print("\n" + "=" * 78)
    print("PASO 2A - SEMANAS DISPONIBLES POR DZ Y ANIO")
    print("=" * 78)
    piv = df.pivot_table(index="DZ", columns="anio", values="fecha_inicio",
                         aggfunc="count", fill_value=0)
    piv = piv.reindex(sorted(piv.index, key=lambda x: int(x.replace("DZ", ""))))
    piv["TOTAL"] = piv.sum(axis=1)
    print(piv.to_string())

    # -------- PASO 2B: estadisticos de n_estaciones por DZ --------
    print("\n" + "=" * 78)
    print("PASO 2B - DISTRIBUCION DE n_estaciones POR DZ")
    print("=" * 78)
    g = df.groupby("DZ")["n_estaciones"]
    stats = pd.DataFrame({
        "n_semanas": g.count(),
        "min": g.min(),
        "max": g.max(),
        "mediana": g.median(),
        "std": g.std().round(2),
    })
    stats["cv_%"] = (g.std() / g.mean() * 100).round(1)        # coef. variacion
    stats["min_vs_med_%"] = (stats["min"] / stats["mediana"] * 100).round(1)
    stats = stats.reindex(sorted(stats.index, key=lambda x: int(x.replace("DZ", ""))))
    print(stats.to_string())

    print("\nDZs con ALTA variabilidad (CV>10% o min<70% de su mediana):")
    sospechosas = stats[(stats["cv_%"] > 10) | (stats["min_vs_med_%"] < 70)]
    if sospechosas.empty:
        print("  (ninguna)")
    else:
        print(sospechosas.to_string())

    # -------- PASO 3: semanas bajo el 70% de la mediana de su DZ --------
    print("\n" + "=" * 78)
    print("PASO 3 - SEMANAS CON n_estaciones < 70% DE LA MEDIANA DE SU DZ")
    print("=" * 78)
    med = g.median()
    df["mediana_dz"] = df["DZ"].map(med)
    df["pct_vs_mediana"] = (df["n_estaciones"] / df["mediana_dz"] * 100).round(1)
    alertas = df[df["pct_vs_mediana"] < 70].copy()

    if alertas.empty:
        print("  No hay semanas por debajo del 70% de la mediana.")
    else:
        print(f"Total de semanas en alerta: {len(alertas)}\n")
        resumen = (alertas.groupby("DZ")
                   .agg(n_semanas_alerta=("fecha_inicio", "count"),
                        peor_pct=("pct_vs_mediana", "min"),
                        mediana_dz=("mediana_dz", "first"))
                   .reindex(sorted(alertas["DZ"].unique(),
                                   key=lambda x: int(x.replace("DZ", "")))))
        print("Resumen por DZ (problema puntual vs sistematico):")
        print(resumen.to_string())
        print("\nDetalle de semanas en alerta:")
        det = alertas[["DZ", "anio", "fecha_inicio", "n_estaciones",
                       "mediana_dz", "pct_vs_mediana"]].copy()
        det["fecha_inicio"] = det["fecha_inicio"].dt.strftime("%Y-%m-%d")
        det["mediana_dz"] = det["mediana_dz"].astype(int)
        with pd.option_context("display.max_rows", None):
            print(det.to_string(index=False))

    # -------- GRAFICO: evolucion mensual de n_estaciones por DZ --------
    df["mes"] = df["fecha_inicio"].dt.to_period("M").dt.to_timestamp()
    serie_mes = (df.groupby(["DZ", "mes"])["n_estaciones"].mean().reset_index())

    fig, ax = plt.subplots(figsize=(15, 8))
    cmap = plt.get_cmap("tab20")
    dzs_ord = sorted(df["DZ"].unique(), key=lambda x: int(x.replace("DZ", "")))
    for i, dz in enumerate(dzs_ord):
        s = serie_mes[serie_mes["DZ"] == dz]
        ax.plot(s["mes"], s["n_estaciones"], marker="o", ms=3,
                lw=1.3, color=cmap(i % 20), label=dz)
    ax.set_title("Evolucion mensual de n_estaciones unicas por DZ "
                 "(promedio de semanas del mes)", fontsize=13)
    ax.set_xlabel("Mes")
    ax.set_ylabel("n_estaciones (promedio mensual)")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=2, fontsize=8, loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout()
    out_png = os.path.join(OUT_DIR, "cobertura_historico_por_dz.png")
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    print(f"\n[grafico guardado] {out_png}")


if __name__ == "__main__":
    main()
