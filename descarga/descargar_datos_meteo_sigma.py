"""
descargar_datos_meteo_sigma.py
-------------------------------
Descarga datos meteorológicos (series de tiempo) por estación individual
desde la API de SIGMA-DRD.

A diferencia de descargar_csv_sigma.py —que descarga reportes de operatividad
por DZ— este script descarga los datos crudos de cada estación:
  Columnas: Fecha, Hora, n_variable, flag_n_variable, ...
  Resolución: 10 min / horaria / diaria según la estación y variable
  Fuente: POST /api-sigma-dev/api/operatividad/consultar

Estrategia:
  1. Selenium para login → captura JWT de localStorage (navegador se cierra)
  2. requests.Session para todos los llamados de datos (sin browser)
  3. Auto-refresh del token cuando está por vencer (re-login Selenium)

Salida:
  DATA/datos_meteo/automaticas/{CODIGO}_{fi}_{ff}.csv
  DATA/datos_meteo/convencionales/{CODIGO}_{fi}_{ff}.csv

Nota sobre CONVENCIONAL: por defecto se excluyen del CSV las variables de
nubosidad/visibilidad (N_NB*/N_VI*) — observación visual directa del
observador, sin instrumento detrás, irrelevante para evaluar operatividad de
sensores. Usar --incluir-observadas para el volcado completo.

Uso:
    python descargar_datos_meteo_sigma.py
    python descargar_datos_meteo_sigma.py --categoria automatica
    python descargar_datos_meteo_sigma.py --dz 1 4 8 --categoria automatica
    python descargar_datos_meteo_sigma.py --fecha-inicio 2026-05-01 --fecha-fin 2026-05-08
    python descargar_datos_meteo_sigma.py --headless --no-omitir
    python descargar_datos_meteo_sigma.py --categoria convencional --incluir-observadas
"""

import argparse
import base64
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Forzar UTF-8 en stdout para evitar UnicodeEncodeError en Windows (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ── Rutas ──────────────────────────────────────────────────────────────────────
ROOT_PIPELINE  = Path(__file__).resolve().parent
ROOT_PROYECTO  = ROOT_PIPELINE.parent   # descarga/ está 1 nivel bajo la raíz Analizador-Series/
SIGMA_ROOT     = ROOT_PROYECTO / "sigma"
DIR_AUTO       = ROOT_PROYECTO / "DATA" / "datos_meteo" / "automaticas"
DIR_CONV       = ROOT_PROYECTO / "DATA" / "datos_meteo" / "convencionales"
SGO_DB         = ROOT_PROYECTO / "data_ref" / "estaciones.db"   # catálogo extraído (solo tabla estaciones)

DIR_AUTO.mkdir(parents=True, exist_ok=True)
DIR_CONV.mkdir(parents=True, exist_ok=True)

# ── Credenciales y URLs ────────────────────────────────────────────────────────
load_dotenv(SIGMA_ROOT / ".env")
SIGMA_URL      = os.getenv("SIGMA_URL",      "https://www.senamhi.gob.pe/sigma-dev")
SIGMA_API_BASE = SIGMA_URL.replace("sigma-dev", "api-sigma-dev") + "/api"
SIGMA_USUARIO  = os.getenv("SIGMA_USUARIO",  "")
SIGMA_PASSWORD = os.getenv("SIGMA_PASSWORD", "")

# ── Timeouts ───────────────────────────────────────────────────────────────────
T_LOGIN           = 25
T_REQUEST         = 90     # timeout por llamado API (90s cubre chunks densos)
DELAY_ESTACIONES  = 0.4    # segundos entre estaciones (no saturar servidor)
DELAY_CHUNKS      = 0.8    # segundos entre chunks del mismo período
MARGEN_REFRESH    = 300    # refrescar token si vence en menos de 5 min

# ── Límite de SIGMA ────────────────────────────────────────────────────────────
MAX_DIAS_CHUNK = 90        # SIGMA no responde bien para períodos > 3 meses

# ── Logging ────────────────────────────────────────────────────────────────────
_ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_dir = ROOT_PROYECTO / "DATA" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / f"datos_meteo_{_ts}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)
_T0: float = 0.0


def t() -> str:
    return f"[+{time.time() - _T0:.1f}s]"


# ══════════════════════════════════════════════════════════════════════════════
# JWT helpers
# ══════════════════════════════════════════════════════════════════════════════

def _jwt_payload(token: str) -> dict:
    """Decodifica el payload del JWT sin verificar firma."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.b64decode(payload))
    except Exception:
        return {}


def _token_por_vencer(token: str) -> bool:
    """True si el token expira en menos de MARGEN_REFRESH segundos."""
    exp = _jwt_payload(token).get("exp", 0)
    return time.time() >= (exp - MARGEN_REFRESH)


# ══════════════════════════════════════════════════════════════════════════════
# Login con Selenium → obtiene JWT (cierra browser al terminar)
# ══════════════════════════════════════════════════════════════════════════════

def _set_react_value(driver, element, value: str) -> None:
    driver.execute_script("""
        var el = arguments[0], val = arguments[1];
        var proto = el.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    """, element, value)


def _crear_driver(headless: bool) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1200,800")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--log-level=3")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=opts)


def obtener_token(headless: bool = False) -> str:
    """
    Abre Chrome, hace login en SIGMA y extrae el JWT de localStorage.
    Cierra Chrome al terminar. Lanza RuntimeError si falla.
    """
    log.info(f"Login Selenium -> obteniendo JWT... {t()}")
    driver = _crear_driver(headless)
    try:
        driver.get(f"{SIGMA_URL}/login")
        WebDriverWait(driver, T_LOGIN).until(
            EC.presence_of_element_located((By.ID, "username"))
        )

        _set_react_value(driver, driver.find_element(By.ID, "username"), SIGMA_USUARIO)
        _set_react_value(driver, driver.find_element(By.ID, "password"), SIGMA_PASSWORD)

        for b in driver.find_elements(By.TAG_NAME, "button"):
            if b.text.strip() == "Ingresar" and b.is_displayed():
                b.click()
                break

        WebDriverWait(driver, T_LOGIN).until(lambda d: "/login" not in d.current_url)
        time.sleep(1.5)  # esperar que localStorage se escriba

        token = driver.execute_script("return localStorage.getItem('drd_access_token');")
        if not token:
            raise RuntimeError("drd_access_token no encontrado en localStorage")

        exp = datetime.fromtimestamp(_jwt_payload(token).get("exp", 0))
        log.info(f"  Token OK. Expira: {exp.strftime('%Y-%m-%d %H:%M:%S')} {t()}")
        return token

    finally:
        driver.quit()


# ══════════════════════════════════════════════════════════════════════════════
# Carga de estaciones desde sgo.db
# ══════════════════════════════════════════════════════════════════════════════

def cargar_estaciones(
    dzs: list | None = None,
    categorias: list | None = None,
    codigos: list | None = None,
) -> list:
    """
    Lee estaciones activas de sgo.db.
    Retorna lista de dicts: {codigo, nombre, dz, categoria}

    Si se pasan codigos, ignora dzs/categorias y busca directamente por código.
    """
    if not SGO_DB.exists():
        log.error(f"sgo.db no encontrado en: {SGO_DB}")
        return []

    if codigos:
        # Búsqueda directa por código — sin filtro de DZ ni categoría
        codigos_upper = [c.upper() for c in codigos]
        q = f"""
            SELECT codigo, nombre, dz, categoria
            FROM estaciones
            WHERE codigo IN ({','.join('?'*len(codigos_upper))})
            ORDER BY dz, categoria, nombre
        """
        with sqlite3.connect(str(SGO_DB)) as con:
            rows = con.execute(q, codigos_upper).fetchall()
        # Advertir si algún código no se encontró
        encontrados = {r[0] for r in rows}
        for c in codigos_upper:
            if c not in encontrados:
                log.warning(f"  Codigo no encontrado en sgo.db: {c}")
        return [{"codigo": r[0], "nombre": r[1], "dz": r[2], "categoria": r[3]} for r in rows]

    cats = [c.upper() for c in (categorias or ["AUTOMATICA", "CONVENCIONAL"])]
    q = f"""
        SELECT codigo, nombre, dz, categoria
        FROM estaciones
        WHERE activa = 1
          AND categoria IN ({','.join('?'*len(cats))})
    """
    params = list(cats)

    if dzs:
        q += f" AND dz IN ({','.join('?'*len(dzs))})"
        params.extend(dzs)

    q += " ORDER BY dz, categoria, nombre"

    with sqlite3.connect(str(SGO_DB)) as con:
        rows = con.execute(q, params).fetchall()

    return [{"codigo": r[0], "nombre": r[1], "dz": r[2], "categoria": r[3]} for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# Chunking de períodos largos
# ══════════════════════════════════════════════════════════════════════════════

def _partir_rango(
    fecha_ini: datetime, fecha_fin: datetime
) -> list[tuple[datetime, datetime]]:
    """Divide [fecha_ini, fecha_fin] en ventanas de MAX_DIAS_CHUNK días."""
    chunks = []
    cur = fecha_ini
    while cur <= fecha_fin:
        end = min(cur + timedelta(days=MAX_DIAS_CHUNK - 1), fecha_fin)
        chunks.append((cur, end))
        cur = end + timedelta(days=1)
    return chunks


def _consultar_chunk(
    session: requests.Session,
    token: str,
    codigo: str,
    cat_api: str,
    fecha_ini: datetime,
    fecha_fin: datetime,
) -> tuple[str, list]:
    """
    POST único para un rango ≤ MAX_DIAS_CHUNK días.
    Retorna (status, datos):  status ∈ {"ok", "vacio", "401", "error"}
    """
    fi_str = fecha_ini.strftime("%Y-%m-%d")
    ff_str = fecha_fin.strftime("%Y-%m-%d")
    try:
        resp = session.post(
            f"{SIGMA_API_BASE}/operatividad/consultar",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"codigo": codigo, "categoria": cat_api,
                  "fecha_inicio": fi_str, "fecha_fin": ff_str},
            timeout=T_REQUEST,
        )
        if resp.status_code == 401:
            return "401", []
        if resp.status_code != 200:
            log.warning(f"  {codigo} [{fi_str}→{ff_str}]: HTTP {resp.status_code} — {resp.text[:120]}")
            return "error", []
        datos = resp.json().get("data", {}).get("datos") or []
        return ("ok" if datos else "vacio"), datos
    except requests.exceptions.Timeout:
        log.warning(f"  {codigo} [{fi_str}→{ff_str}]: Timeout ({T_REQUEST}s)")
        return "error", []
    except Exception as exc:
        log.warning(f"  {codigo} [{fi_str}→{ff_str}]: {exc}")
        return "error", []


# ══════════════════════════════════════════════════════════════════════════════
# Construcción del CSV con valores + flags intercalados
# ══════════════════════════════════════════════════════════════════════════════

# Variables convencionales sin instrumento (observación visual directa del
# observador): nubosidad (cantidad/altura, N_NB*) y visibilidad (N_VI*).
# Catálogo oficial: variables-instrumento-convencionales.xlsx (proyecto
# Dashboard-para-monitoreo-de-la-operatividad), agrupadas como "VARIABLES
# OBSERVADAS" en la regla de negocio RN-41 — todo código con esos prefijos
# pertenece exclusivamente a ese grupo, ninguna otra variable los usa.
# Las categóricas V_NB*/V_VT* (forma de nubes, dirección de viento) ya quedan
# fuera porque abajo solo se toman columnas "n_".
_PATRON_VAR_OBSERVADA = re.compile(r"^n_(nb|vi)\d+$")


def _fecha_hora(row: dict) -> tuple[str, str]:
    """
    SIGMA nombra el campo de fecha distinto según la familia de datos:
    automáticas e hidrológicas -> "d_fecha_reg" (a veces con hora y timezone
    completos, tipo ISO) + "v_hora_reg"; meteorológicas convencionales diarias
    (temperatura n_tm*/precipitación n_pt*) -> "FECHA" (mayúsculas, sin ningún
    campo de hora — son diarias). Sin este fallback, todas las filas de esta
    segunda familia quedaban con fecha vacía y el deduplicado de abajo las
    colapsaba a una sola fila (bug real reproducido con 106077/100043 al
    probar la pestaña emplazamiento compartido — ver tests/descarga/).
    """
    fecha = (row.get("d_fecha_reg") or row.get("FECHA") or "")[:10]
    hora = (row.get("v_hora_reg") or "")[:5] or "00:00"
    return fecha, hora


def _construir_csv(datos: list, excluir_observadas: bool = False) -> str:
    """
    Construye CSV a partir de la respuesta JSON del API.
    Columnas: Fecha, Hora, n_var1, flag_n_var1, n_var2, flag_n_var2, ...
    Nulos se representan con cadena vacía (más limpio que "-" para pandas).
    Las filas se ordenan cronológicamente y se deduplicado por (Fecha, Hora).

    excluir_observadas: descarta N_NB*/N_VI* (nubosidad/visibilidad) — variables
    convencionales sin instrumento detrás, irrelevantes para evaluar operatividad
    de sensores.
    """
    if not datos:
        return ""

    # Ordenar y deduplicar por (fecha, hora) — necesario al concatenar chunks
    try:
        datos = sorted(datos, key=_fecha_hora)
        seen = set()
        datos_dedup = []
        for r in datos:
            key = _fecha_hora(r)
            if key not in seen:
                seen.add(key)
                datos_dedup.append(r)
        datos = datos_dedup
    except Exception:
        pass

    primera = datos[0]
    vars_n = sorted(k for k in primera if k.startswith("n_"))
    if excluir_observadas:
        vars_n = [v for v in vars_n if not _PATRON_VAR_OBSERVADA.match(v)]

    headers = ["Fecha", "Hora"]
    for v in vars_n:
        headers += [v, f"flag_{v}"]

    lines = [",".join(headers)]
    for row in datos:
        fecha, hora = _fecha_hora(row)
        vals = [fecha, hora]
        for v in vars_n:
            val  = row.get(v)
            flag = row.get(f"flag_{v}") or ""
            vals += ["" if val is None else str(val), flag]
        lines.append(",".join(vals))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Descarga de datos por estación
# ══════════════════════════════════════════════════════════════════════════════

_CAT_API = {"AUTOMATICA": "automatica", "CONVENCIONAL": "convencional"}
_DIR_OUT = {"AUTOMATICA": DIR_AUTO, "CONVENCIONAL": DIR_CONV}


def descargar_estacion(
    session: requests.Session,
    token: str,
    est: dict,
    fecha_ini: datetime,
    fecha_fin: datetime,
    omitir_existentes: bool,
    incluir_observadas: bool = False,
) -> str:
    """
    Descarga datos de una estación y guarda un único CSV para el período completo.

    Divide automáticamente en ventanas de MAX_DIAS_CHUNK días si el período
    supera ese límite (SIGMA no responde bien para >3 meses).

    incluir_observadas: si es False (default), las estaciones CONVENCIONAL
    excluyen del CSV las variables de nubosidad/visibilidad (sin instrumento).
    No afecta a AUTOMATICA, que no reporta esos códigos.

    Retorna:
      "ok"    → descargado exitosamente
      "skip"  → ya existía y se omitió
      "vacio" → sin datos en el período (CSV marcador guardado)
      "error" → falló (al menos un chunk sin datos parciales previos)
      "401"   → token inválido (señal para refrescar en main)
    """
    codigo = est["codigo"]
    cat_db = est["categoria"].upper()
    fi_str = fecha_ini.strftime("%Y-%m-%d")
    ff_str = fecha_fin.strftime("%Y-%m-%d")
    cat_api = _CAT_API.get(cat_db, "automatica")

    dir_out  = _DIR_OUT.get(cat_db, DIR_AUTO)
    csv_path = dir_out / f"{codigo}_{fi_str}_{ff_str}.csv"

    if omitir_existentes and csv_path.exists() and csv_path.stat().st_size > 10:
        return "skip"

    chunks   = _partir_rango(fecha_ini, fecha_fin)
    n_chunks = len(chunks)
    if n_chunks > 1:
        dias_total = (fecha_fin - fecha_ini).days + 1
        log.info(f"  {codigo}: {dias_total} días → {n_chunks} chunks de ≤{MAX_DIAS_CHUNK} días")

    todos_los_datos: list = []
    for i, (ch_ini, ch_fin) in enumerate(chunks, 1):
        if n_chunks > 1:
            log.info(f"    [{i}/{n_chunks}] {ch_ini.strftime('%Y-%m-%d')} → {ch_fin.strftime('%Y-%m-%d')}")

        status, datos = _consultar_chunk(session, token, codigo, cat_api, ch_ini, ch_fin)

        if status == "401":
            return "401"

        if status == "error":
            if todos_los_datos:
                log.warning(f"  {codigo}: chunk {i}/{n_chunks} falló — guardando datos parciales")
            else:
                return "error"
            break

        todos_los_datos.extend(datos)

        if n_chunks > 1 and i < n_chunks:
            time.sleep(DELAY_CHUNKS)

    if not todos_los_datos:
        csv_path.write_text("sin_datos\n", encoding="utf-8")
        log.info(f"  {codigo}: sin datos en el período")
        return "vacio"

    excluir_observadas = cat_db == "CONVENCIONAL" and not incluir_observadas
    csv_path.write_text(_construir_csv(todos_los_datos, excluir_observadas), encoding="utf-8")
    log.info(
        f"  OK {codigo} — {est['nombre'][:28]:28s} "
        f"DZ{est['dz']} {cat_db[:4]} — {len(todos_los_datos)} filas"
        + (f" ({n_chunks} chunks)" if n_chunks > 1 else "")
    )
    return "ok"


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def _calcular_rango(fecha_inicio=None, fecha_fin=None, dias=7):
    if fecha_inicio and fecha_fin:
        return fecha_inicio, fecha_fin
    if fecha_fin is None:
        hoy = datetime.now()
        dias_al_jueves = (hoy.weekday() - 3) % 7
        if dias_al_jueves == 0 and hoy.hour < 12:
            dias_al_jueves = 7
        fecha_fin = hoy - timedelta(days=dias_al_jueves)
    fecha_inicio = fecha_fin - timedelta(days=dias - 1)
    return fecha_inicio, fecha_fin


_PLACEHOLDERS_ENV = {"", "tu_usuario_sigma", "tu_password_aqui"}


def _problema_credenciales(usuario: str, password: str) -> str | None:
    """Mensaje de error si las credenciales de sigma/.env faltan o siguen con los
    valores de ejemplo de .env.example; None si están completas. Evita que el
    login de Selenium falle con un TimeoutException sin explicación."""
    if usuario in _PLACEHOLDERS_ENV or password in _PLACEHOLDERS_ENV:
        return (
            f"Faltan credenciales de SIGMA en {SIGMA_ROOT / '.env'}. "
            "Copia sigma/.env.example como sigma/.env y completa "
            "SIGMA_USUARIO y SIGMA_PASSWORD con tu usuario de SIGMA."
        )
    return None


def main():
    global _T0
    _T0 = time.time()

    parser = argparse.ArgumentParser(
        description="Descarga datos meteorológicos por estación desde SIGMA-DRD"
    )
    parser.add_argument("--codigo",     nargs="+", type=str,
                        help="Códigos de estaciones específicas (ej: 47E0D438 104114). "
                             "Si se usa, ignora --dz y --categoria.")
    parser.add_argument("--dz",         nargs="+", type=int,
                        help="DZs a procesar (default: todas). Ignorado si se usa --codigo.")
    parser.add_argument("--categoria",  choices=["automatica", "convencional", "ambas"],
                        default="ambas",
                        help="Categoría de estaciones (default: ambas). Ignorado si se usa --codigo.")
    parser.add_argument("--fecha-inicio", type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
                        help="Fecha inicio YYYY-MM-DD (default: semana anterior)")
    parser.add_argument("--fecha-fin",    type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
                        help="Fecha fin YYYY-MM-DD")
    parser.add_argument("--headless",   action="store_true",
                        help="Chrome sin ventana para el login")
    parser.add_argument("--no-omitir",  dest="omitir_existentes", action="store_false",
                        default=True,
                        help="Re-descarga aunque el CSV ya exista")
    parser.add_argument("--incluir-observadas", action="store_true", default=False,
                        help="No excluir nubosidad/visibilidad (N_NB*/N_VI*) en "
                             "estaciones CONVENCIONAL. Por defecto se excluyen "
                             "por no depender de instrumento.")
    args = parser.parse_args()

    problema = _problema_credenciales(SIGMA_USUARIO, SIGMA_PASSWORD)
    if problema:
        log.error(problema)
        sys.exit(1)

    fecha_ini, fecha_fin = _calcular_rango(args.fecha_inicio, args.fecha_fin)
    log.info(f"Periodo: {fecha_ini.strftime('%Y-%m-%d')} -> {fecha_fin.strftime('%Y-%m-%d')}")

    if args.codigo:
        # Modo puntual: busca directamente por código, sin filtros de DZ/categoría
        estaciones = cargar_estaciones(codigos=args.codigo)
    else:
        if args.categoria == "automatica":
            cats = ["AUTOMATICA"]
        elif args.categoria == "convencional":
            cats = ["CONVENCIONAL"]
        else:
            cats = ["AUTOMATICA", "CONVENCIONAL"]
        estaciones = cargar_estaciones(dzs=args.dz, categorias=cats)
    if not estaciones:
        log.error("Sin estaciones. ¿sgo.db accesible y con registros activos?")
        sys.exit(1)

    log.info(f"Estaciones: {len(estaciones)} "
             f"(auto={sum(1 for e in estaciones if e['categoria']=='AUTOMATICA')}, "
             f"conv={sum(1 for e in estaciones if e['categoria']=='CONVENCIONAL')})")

    # ── Login inicial ──────────────────────────────────────────────────────────
    token   = obtener_token(headless=args.headless)
    session = requests.Session()

    conteo  = {"ok": 0, "skip": 0, "vacio": 0, "error": 0}
    errores = []

    for i, est in enumerate(estaciones, 1):
        log.info(f"[{i:4d}/{len(estaciones)}] {est['codigo']} {t()}")

        # Refrescar token si está por vencer
        if _token_por_vencer(token):
            log.info("Token por vencer — renovando...")
            try:
                token = obtener_token(headless=args.headless)
            except Exception as exc:
                log.error(f"No se pudo renovar token: {exc}")
                errores.append(est["codigo"])
                conteo["error"] += 1
                continue

        resultado = descargar_estacion(
            session, token, est, fecha_ini, fecha_fin, args.omitir_existentes,
            args.incluir_observadas,
        )

        # Reintentar una vez si el token expiró a mitad de ciclo
        if resultado == "401":
            log.info("  401 recibido — renovando token y reintentando...")
            try:
                token   = obtener_token(headless=args.headless)
                resultado = descargar_estacion(
                    session, token, est, fecha_ini, fecha_fin, args.omitir_existentes,
                    args.incluir_observadas,
                )
            except Exception:
                resultado = "error"

        conteo[resultado if resultado in conteo else "error"] += 1
        if resultado == "error":
            errores.append(est["codigo"])

        time.sleep(DELAY_ESTACIONES)

    # ── Resumen ────────────────────────────────────────────────────────────────
    dur = (time.time() - _T0) / 60
    log.info(f"\n{'═'*60}")
    log.info(f"RESUMEN  ok={conteo['ok']}  skip={conteo['skip']}  "
             f"vacio={conteo['vacio']}  error={conteo['error']}")
    log.info(f"Duracion: {dur:.1f} min  |  CSV en: {DIR_AUTO.parent}")
    if errores:
        log.warning(f"Errores ({len(errores)}): {errores[:30]}")
    log.info(f"{'═'*60}")


if __name__ == "__main__":
    main()
