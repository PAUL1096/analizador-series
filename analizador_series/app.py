"""
Analizador de Series — Entry point Dash.

Ejecutar desde la raíz del proyecto:
    python -m analizador_series.app

O usar el .bat:
    scripts/visualizadores/Iniciar_Analizador_Series.bat
"""
from __future__ import annotations

import sys
from pathlib import Path

# Forzar UTF-8 en stdout para Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Asegurar que la raíz del proyecto esté en sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dash
import dash_bootstrap_components as dbc

from analizador_series.config import DASH_HOST, DASH_PORT, DASH_DEBUG
from analizador_series.ui.layout import layout_principal
from analizador_series.ui import callbacks  # noqa: F401  registra los callbacks


app = dash.Dash(
    __name__,
    title="Analizador de Series — SGR",
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
)

app.layout = layout_principal()
server = app.server


def main():
    print("─" * 60)
    print(f"  Analizador de Series — SGR/SENAMHI")
    print(f"  http://localhost:{DASH_PORT}")
    print(f"  Datos leídos de: DATA/datos_meteo/")
    print(f"  Ctrl+C para detener")
    print("─" * 60)
    app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG)


if __name__ == "__main__":
    main()
