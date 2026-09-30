"""
Carga de datos meteorológicos desde DATA/datos_meteo/.

Cada CSV se llama {CODIGO}_{fi}_{ff}.csv y vive en automaticas/ o convencionales/.
Este módulo:
  - escanea ambas carpetas buscando todos los CSVs de los códigos pedidos
  - los concatena (manejando rangos solapados con dedupe)
  - parsea Fecha+Hora a datetime
  - filtra por rango de fechas pedido
  - se cruza con el catálogo de estaciones (data_ref/estaciones.db) para nombre/DZ/categoría
"""
from __future__ import annotations

import functools
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from analizador_series.config import DIR_AUTO, DIR_CONV, CATALOGO_DB


# ══════════════════════════════════════════════════════════════════════════════
# Metadata de estaciones (catálogo data_ref/estaciones.db)
# ══════════════════════════════════════════════════════════════════════════════

def metadata_estaciones(codigos: list[str] | None = None) -> pd.DataFrame:
    """
    Retorna DataFrame con codigo, nombre, dz, categoria, activa, altitud,
    region_natural de las estaciones pedidas. Si codigos es None retorna todas las
    activas. altitud/region_natural pueden venir NULL si data_ref/actualizar_geodatos.py
    no se corrió todavía para esa estación (core.control_calidad las trata como
    metadata faltante, no como error).
    """
    columnas_vacias = ["codigo", "nombre", "dz", "categoria", "activa", "altitud", "region_natural"]
    if not CATALOGO_DB.exists():
        return pd.DataFrame(columns=columnas_vacias)

    if codigos:
        codigos = [c.upper() for c in codigos]
        placeholders = ",".join("?" * len(codigos))
        q = f"""
            SELECT codigo, nombre, dz, categoria, activa, altitud, region_natural
            FROM estaciones
            WHERE codigo IN ({placeholders})
        """
        params = codigos
    else:
        q = """
            SELECT codigo, nombre, dz, categoria, activa, altitud, region_natural
            FROM estaciones
            WHERE activa = 1
            ORDER BY dz, categoria, nombre
        """
        params = []

    with sqlite3.connect(str(CATALOGO_DB)) as con:
        return pd.read_sql_query(q, con, params=params)


def codigos_disponibles() -> pd.DataFrame:
    """
    Inspecciona DATA/datos_meteo/ y retorna lista de códigos que tienen al
    menos un CSV descargado, con nombre/DZ/categoría desde sgo.db.
    """
    codigos = set()
    for carpeta in (DIR_AUTO, DIR_CONV):
        if not carpeta.exists():
            continue
        for f in carpeta.glob("*.csv"):
            cod = f.name.split("_", 1)[0]
            codigos.add(cod)
    if not codigos:
        return pd.DataFrame(columns=["codigo", "nombre", "dz", "categoria"])
    meta = metadata_estaciones(list(codigos))
    return meta.sort_values(["dz", "categoria", "nombre"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# Lectura de CSVs por estación
# ══════════════════════════════════════════════════════════════════════════════

def _csvs_de_codigo(codigo: str) -> list[Path]:
    """Lista todos los CSVs descargados para un código, en cualquier carpeta."""
    codigo = codigo.upper()
    archivos = []
    for carpeta in (DIR_AUTO, DIR_CONV):
        if carpeta.exists():
            archivos.extend(carpeta.glob(f"{codigo}_*.csv"))
    return sorted(archivos)


def firma_estacion(codigo: str) -> list[tuple]:
    """
    [(nombre, mtime, size), ...] de todos los CSV de una estación — huella
    barata (solo stat(), sin leer contenido) para saber si "algo cambió en
    disco" desde la última vez. La usa core.dias_efectivos para invalidar su
    caché de "día efectivo" solo cuando corresponde, no en cada consulta.
    """
    return sorted((p.name, p.stat().st_mtime, p.stat().st_size) for p in _csvs_de_codigo(codigo))


def _leer_csv_estacion(path: Path) -> pd.DataFrame:
    """
    Lee un CSV individual y normaliza:
      - construye columna 'datetime' combinando Fecha + Hora
      - mantiene columnas n_* y flag_n_*
      - omite filas marcador 'sin_datos'
    """
    # Marcador de "sin datos en periodo"
    try:
        primera_linea = path.read_text(encoding="utf-8").split("\n", 1)[0]
        if primera_linea.strip() == "sin_datos":
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    if df.empty or "Fecha" not in df.columns:
        return pd.DataFrame()

    # Combinar Fecha + Hora -> datetime
    df["datetime"] = pd.to_datetime(
        df["Fecha"] + " " + df["Hora"].astype(str),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    df = df.dropna(subset=["datetime"]).drop(columns=["Fecha", "Hora"])

    # Convertir n_* a numérico (vacíos -> NaN)
    for col in df.columns:
        if col.startswith("n_") and not col.startswith("flag_"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


_RE_RANGO_ARCHIVO = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")


def _rango_de_archivo(path: Path) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """(fi, ff) codificados en el nombre {codigo}_{fi}_{ff}.csv, o None si no matchea."""
    m = _RE_RANGO_ARCHIVO.search(path.name)
    if not m:
        return None
    try:
        return pd.Timestamp(m.group(1)), pd.Timestamp(m.group(2))
    except ValueError:
        return None


def _archivo_en_rango(path: Path, fecha_inicio, fecha_fin) -> bool:
    """
    True si el rango codificado en el nombre del archivo intersecta
    [fecha_inicio, fecha_fin] (bordes None = sin límite). Evita leer/parsear
    CSVs que quedan completamente fuera del periodo pedido — con estaciones
    que acumulan varias descargas históricas solapadas (algunas de +10 años),
    esto es lo que evita releer todo el histórico para pedir solo un mes.
    Si el nombre no trae rango parseable, se incluye igual (mejor leer de más
    que perderse datos por un nombre atípico).
    """
    rango = _rango_de_archivo(path)
    if rango is None:
        return True
    fi_archivo, ff_archivo = rango
    if fecha_fin is not None and fi_archivo > pd.Timestamp(fecha_fin):
        return False
    if fecha_inicio is not None and ff_archivo < pd.Timestamp(fecha_inicio):
        return False
    return True


@functools.lru_cache(maxsize=256)
def _leer_csv_estacion_cacheado(path_str: str, _mtime: float, _size: int) -> pd.DataFrame:
    return _leer_csv_estacion(Path(path_str))


def _leer_csv_estacion_actual(path: Path) -> pd.DataFrame:
    """
    Envuelve _leer_csv_estacion con caché en memoria (clave: ruta + mtime +
    tamaño) — un CSV ya descargado no cambia entre una interacción de la UI y
    la siguiente (cambiar periodo, tildar un flag, etc. re-dispara el
    callback pero no los archivos en disco), así que releerlo y reparsearlo
    cada vez es puro desperdicio. Si el archivo se vuelve a descargar, el
    mtime cambia y la caché se refresca sola.
    """
    stat = path.stat()
    return _leer_csv_estacion_cacheado(str(path), stat.st_mtime, stat.st_size)


def cargar_estaciones(
    codigos: list[str],
    fecha_inicio: datetime | None = None,
    fecha_fin: datetime | None = None,
) -> pd.DataFrame:
    """
    Carga datos de varias estaciones, concatenados con columna 'codigo'.
    Si una estación tiene varios CSVs con rangos solapados, deduplica por
    (codigo, datetime).

    Retorna DataFrame con columnas:  codigo · datetime · n_* · flag_n_*

    El DataFrame puede tener variables distintas entre estaciones; las que no
    existen para una estación aparecen como NaN.
    """
    if not codigos:
        return pd.DataFrame()

    dfs = []
    for cod in codigos:
        for path in _csvs_de_codigo(cod):
            if not _archivo_en_rango(path, fecha_inicio, fecha_fin):
                continue
            df = _leer_csv_estacion_actual(path)
            if df.empty:
                continue
            df = df.copy()  # la versión cacheada es compartida; no mutarla
            df.insert(0, "codigo", cod.upper())
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df_all = pd.concat(dfs, ignore_index=True, sort=False)
    df_all = df_all.drop_duplicates(subset=["codigo", "datetime"], keep="first")

    if fecha_inicio is not None:
        df_all = df_all[df_all["datetime"] >= pd.Timestamp(fecha_inicio)]
    if fecha_fin is not None:
        # Inclusivo hasta el final del día
        df_all = df_all[df_all["datetime"] <= pd.Timestamp(fecha_fin) + pd.Timedelta(hours=23, minutes=59)]

    return df_all.sort_values(["codigo", "datetime"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# Inspección
# ══════════════════════════════════════════════════════════════════════════════

def variables_disponibles(df: pd.DataFrame) -> list[str]:
    """Retorna lista ordenada de variables n_* presentes (no flag_)."""
    return sorted(c for c in df.columns
                  if c.startswith("n_") and not c.startswith("flag_"))


def rango_fechas(df: pd.DataFrame) -> tuple[datetime, datetime] | tuple[None, None]:
    """Retorna (min, max) del campo datetime, o (None, None) si está vacío."""
    if df.empty or "datetime" not in df.columns:
        return (None, None)
    return (df["datetime"].min(), df["datetime"].max())


def tramos_descargados(codigo: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """
    Tramos [(fi, ff), ...] que YA TENEMOS EN DISCO para esta estación — leídos
    SOLO del nombre de cada CSV (vía _rango_de_archivo), sin abrir ni parsear
    su contenido. Por eso es prácticamente instantáneo incluso con
    historiales de varios años, a diferencia de rango_fechas(df) (que exige
    haber cargado y parseado los datos primero).

    Representa lo que este proyecto YA DESCARGÓ a disco, no la disponibilidad
    real en la BD central de SIGMA (que puede tener más historial, o
    distinto, si nunca se pidió esa parte). Tampoco garantiza cero huecos
    DENTRO de un tramo (eso lo evalúa la detección AF-GAP/AF-MISS sobre el
    contenido real) — es la cobertura de lo descargado, no de los datos.

    Tramos solapados o contiguos (a ≤1 día de distancia) se fusionan.
    Archivos cuyo nombre no trae un rango parseable (atípico) se ignoran acá
    — no aportan un tramo confiable, aunque una consulta real sí los lee
    igual (ver _archivo_en_rango). Resultado ordenado cronológicamente.
    """
    rangos = sorted(
        r for r in (_rango_de_archivo(p) for p in _csvs_de_codigo(codigo))
        if r is not None
    )
    if not rangos:
        return []

    fusionados = [list(rangos[0])]
    for fi, ff in rangos[1:]:
        if fi <= fusionados[-1][1] + pd.Timedelta(days=1):
            fusionados[-1][1] = max(fusionados[-1][1], ff)
        else:
            fusionados.append([fi, ff])
    return [(fi, ff) for fi, ff in fusionados]


def frecuencia_inferida(df: pd.DataFrame, codigo: str | None = None) -> pd.Timedelta | None:
    """
    Infiere la frecuencia (Δt típico) de la serie para una estación.
    Útil para saber si es 10-min, horaria, diaria.
    """
    if df.empty or "datetime" not in df.columns:
        return None
    sub = df if codigo is None else df[df["codigo"] == codigo.upper()]
    if len(sub) < 2:
        return None
    deltas = sub["datetime"].diff().dropna()
    if deltas.empty:
        return None
    return deltas.mode().iloc[0]


# ══════════════════════════════════════════════════════════════════════════════
# Filtro de flags generalizado (Panorama/Comparar) y variables propias
# ══════════════════════════════════════════════════════════════════════════════

def filtrar_por_flags(
    df: pd.DataFrame, flags_incluidos: list[str] | None, prefijo_flag: str = "flag_",
) -> pd.DataFrame:
    """
    Generaliza a TODAS las columnas n_* el filtro que hoy vive inline en
    ui.callbacks.cargar_al_store (ahí queda intacto, solo para 1 variable).
    Los valores cuyo {prefijo_flag}{variable} no esté en flags_incluidos se
    reemplazan por NaN (no se elimina la fila: preserva el eje temporal). Flag
    NaN/None se trata como "SD". flags_incluidos=None => sin filtro. Retorna copia.

    prefijo_flag: por defecto "flag_" (el de SIGMA, columnas flag_n_*). Pasar "cc_"
    filtra por el Control de Calidad propio del Analizador (core.control_calidad,
    columnas cc_n_*) en vez del flag de SIGMA — son capas independientes.
    """
    if df.empty or flags_incluidos is None:
        return df.copy()
    df2 = df.copy()
    flags_validos = set(flags_incluidos)
    for var in variables_disponibles(df2):
        flag_col = f"{prefijo_flag}{var}"
        if flag_col not in df2.columns:
            continue
        if not flags_validos:
            df2[var] = np.nan
            continue
        flag_norm = df2[flag_col].fillna("SD")
        df2.loc[~flag_norm.isin(flags_validos), var] = np.nan
    return df2


def variables_propias_estacion(codigo: str) -> set[str]:
    """
    Columnas n_* que existen NATIVAMENTE en los CSV de esta estación — a
    diferencia de variables_disponibles(df) sobre un merge multi-estación,
    donde una variable que solo aporta OTRA estación aparece igual (columna
    toda-NaN). Distingue "esta estación no mide X" (fila N/D en Panorama) de
    "la mide pero con MISS real". Solo lee la primera línea (encabezados) de
    cada CSV, no parsea filas.
    """
    variables = set()
    for path in _csvs_de_codigo(codigo):
        try:
            primera = path.read_text(encoding="utf-8").split("\n", 1)[0]
        except Exception:
            continue
        if primera.strip() == "sin_datos":
            continue
        for col in primera.split(","):
            col = col.strip()
            if col.startswith("n_") and not col.startswith("flag_"):
                variables.add(col)
    return variables
