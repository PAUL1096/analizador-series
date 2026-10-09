"""
Configuración del Analizador de Series.
Paths, puerto, defaults — todo lo que el resto del código necesita saber.
"""
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────────────
ROOT_PROYECTO = Path(__file__).resolve().parent.parent

DIR_DATOS_METEO = ROOT_PROYECTO / "DATA" / "datos_meteo"
DIR_AUTO        = DIR_DATOS_METEO / "automaticas"
DIR_CONV        = DIR_DATOS_METEO / "convencionales"
CATALOGO_DB     = ROOT_PROYECTO / "data_ref" / "estaciones.db"

# Caché en disco de "día efectivo" por estación (ver core/dias_efectivos.py) —
# se recalcula solo si cambiaron los CSV de la estación, no en cada consulta.
DIR_CACHE_DIAS_EFECTIVOS = ROOT_PROYECTO / "DATA" / "cache_dias_efectivos"

# Caché en disco del Control de Calidad (CC) LOCAL por estación (ver
# core/control_calidad.py) — mismo mecanismo que DIR_CACHE_DIAS_EFECTIVOS. Nunca
# sale de esta máquina (docs/SPEC-control-calidad.md).
DIR_CACHE_CONTROL_CALIDAD = ROOT_PROYECTO / "DATA" / "cache_control_calidad"

DIR_CONFIG       = Path(__file__).resolve().parent / "config"
SERIES_YAML      = DIR_CONFIG / "series_disponibles.yaml"
NOMBRES_YAML     = DIR_CONFIG / "nombres_variables.yaml"
AFECTACIONES_YAML = DIR_CONFIG / "afectaciones.yaml"

# ── Afectaciones AF-* (nombre corto para pantalla) ──────────────────────────
# Definiciones de docs/2026-07-13-rediseno-fase1-design.md. La herramienta
# solo SUGIERE la afectación; la confirma el analista.
AF_NOMBRES = {
    "AF-MISS": "Sin datos",
    "AF-GAP":  "Huecos intermitentes",
    "AF-OUT":  "Valor fuera de rango",
    "AF-NOIS": "Ruido anómalo",
    "AF-BIAS": "Sesgo o salto de nivel",
    "AF-CST":  "Valor congelado",
    "AF-REP":  "Pérdida de representatividad",
}


def af_legible(codigo: str) -> str:
    """'AF-CST' -> 'Valor constante (congelado) (AF-CST)'; desconocido -> tal cual."""
    nombre = AF_NOMBRES.get(codigo)
    return f"{nombre} ({codigo})" if nombre else codigo


# ── Servidor Dash ─────────────────────────────────────────────────────────────
DASH_HOST = "0.0.0.0"
DASH_PORT = 8054
DASH_DEBUG = False

# ── Defaults UI ───────────────────────────────────────────────────────────────
PERCENTILES_DEFAULT = [50, 95, 99, 99.5]
ROLLING_WINDOW_DEFAULT = 24       # horas
PALETA_ESTACIONES = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf",
]
COLOR_FLAG = {
    "C":  "#2ca02c",  # verde
    "M":  "#d62728",  # rojo
    "SD": "#bdbdbd",  # gris
}

# Colores para resaltar puntos por el Control de Calidad propio (core.control_calidad)
# — capa aparte de COLOR_FLAG (que es de SIGMA). BUENO no se resalta (es la línea
# normal, sin marcador extra).
COLOR_CC = {
    "DUDOSO": "#ff7f0e",  # naranja
    "MALO":   "#8b0000",  # rojo oscuro — distinto del rojo de flag M para no confundirse
}
