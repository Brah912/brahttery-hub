"""Actualizaciones automáticas desde GitHub Releases.

Cómo funciona:
  1. Se consulta la última versión publicada en
     https://github.com/<REPO_ACTUALIZACIONES>/releases/latest
  2. Si es más nueva que rutas.VERSION se descarga "Brahttery-hub.exe" y se comprueba
     con su huella "Brahttery-hub.exe.sha256" (si no coincide, se descarta).
  3. Se cambia el .exe en su sitio (Windows permite renombrar un programa en marcha),
     se cierra la app y se vuelve a abrir ya actualizada. Los ajustes no se tocan.
"""
from __future__ import annotations

import ctypes
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import rutas

ARCHIVO_EXE = "Brahttery-hub.exe"
ARCHIVO_SHA = ARCHIVO_EXE + ".sha256"
ARCHIVO_SETUP = "Brahttery-hub-Setup.exe"            # instalador con nombre fijo (desde la 1.4.0)
ARCHIVO_SETUP_SHA = ARCHIVO_SETUP + ".sha256"
_AGENTE = f"Brahttery-hub/{rutas.VERSION} (actualizador)"
CARPETA = os.path.join(rutas.DATOS, "actualizacion")
ARCHIVO_MANIFIESTO = "brahttery-hub.json"     # versión, notas e historial (lo genera publicar.ps1)
# Sólo para pruebas (un servidor local que imita a GitHub); normalmente no están definidas.
API = os.environ.get("BRAHTTERY_API", "https://api.github.com").rstrip("/")
WEB = os.environ.get("BRAHTTERY_WEB", "https://github.com").rstrip("/")


class ErrorActualizacion(Exception):
    pass


@dataclass
class Novedad:
    version: str
    notas: str
    url_exe: str            # lo que se descarga: el instalador (desde la 1.4.0) o el .exe suelto
    url_sha: str
    tamano: int
    instalador: bool = False   # True: url_exe es el Setup y se instala ejecutándolo en silencio


def configurado() -> bool:
    return bool(rutas.REPO_ACTUALIZACIONES.strip())


def se_puede_instalar() -> bool:
    """Sólo el .exe se puede reemplazar solo (desde el código fuente no)."""
    return rutas.CONGELADO


def _tupla(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:4]) or (0,)


def es_mas_nueva(version: str, actual: str = rutas.VERSION) -> bool:
    return _tupla(version) > _tupla(actual)


def _pedir(url: str, timeout: float = 10):
    req = urllib.request.Request(url, headers={"User-Agent": _AGENTE, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


@dataclass
class Version:
    version: str
    fecha: str          # "26/11/2026"
    notas: str          # texto ya limpio de Markdown


def limpiar_notas(md: str) -> str:
    """Las notas de GitHub vienen en Markdown: se dejan como texto legible."""
    lineas = []
    for linea in (md or "").replace("\r", "").split("\n"):
        s = linea.strip()
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"^[-*+]\s+", "•  ", s)
        s = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), s)
        s = re.sub(r"`([^`]*)`", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        lineas.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()


def _error_http(e: urllib.error.HTTPError) -> ErrorActualizacion:
    if e.code in (403, 429):        # límite de consultas de GitHub (60 por hora y conexión)
        return ErrorActualizacion("GitHub limitó las consultas por un rato. Se volverá a intentar más tarde.")
    return ErrorActualizacion(f"GitHub respondió {e.code}.")


def _leer_manifiesto() -> dict | None:
    """El archivo brahttery-hub.json de la última versión publicada, o None si esa versión no
    lo trae (publicada antes de que existiera). Es una descarga normal de GitHub, no la API:
    no cuenta para el límite de 60 consultas por hora."""
    url = f"{WEB}/{rutas.REPO_ACTUALIZACIONES.strip()}/releases/latest/download/{ARCHIVO_MANIFIESTO}"
    try:
        with _pedir(url) as r:
            return json.loads(r.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise _error_http(e) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorActualizacion("Sin conexión con GitHub.") from e
    except ValueError as e:
        raise ErrorActualizacion("La información de la versión publicada no es válida.") from e


def consultar(cuantas: int = 8) -> tuple[Novedad | None, list[Version]]:
    """La novedad (si hay una versión más nueva) y el historial de versiones publicadas, de la
    más nueva a la más vieja, para mostrar sus notas."""
    if not configurado():
        raise ErrorActualizacion("No hay un repositorio de actualizaciones configurado.")
    m = _leer_manifiesto()
    if m is None:
        return _consultar_api(cuantas)
    repo = rutas.REPO_ACTUALIZACIONES.strip()
    version = str(m.get("version", "")).lstrip("vV")
    historial = [Version(str(v.get("version", "")).lstrip("vV"), str(v.get("fecha", "")),
                         limpiar_notas(str(v.get("notas", ""))))
                 for v in m.get("historial", []) if v.get("version")][:cuantas]
    novedad = None
    if version and es_mas_nueva(version):
        base = f"{WEB}/{repo}/releases/download/v{version}/"
        notas = limpiar_notas(str(m.get("notas", "")))
        if m.get("setup"):          # desde la 1.4.0: se actualiza con el instalador
            novedad = Novedad(version, notas, base + ARCHIVO_SETUP, base + ARCHIVO_SETUP_SHA,
                              int(m["setup"].get("tamano") or 0), instalador=True)
        else:
            novedad = Novedad(version, notas, base + ARCHIVO_EXE, base + ARCHIVO_SHA, int(m.get("tamano") or 0))
    return novedad, historial


def _consultar_api(cuantas: int) -> tuple[Novedad | None, list[Version]]:
    """Plan B (versiones publicadas sin brahttery-hub.json): la API de GitHub."""
    url = f"{API}/repos/{rutas.REPO_ACTUALIZACIONES.strip()}/releases?per_page={cuantas}"
    try:
        with _pedir(url) as r:
            publicadas = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, []
        raise _error_http(e) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorActualizacion("Sin conexión con GitHub.") from e
    publicadas = [p for p in publicadas if not p.get("draft") and not p.get("prerelease")
                  and (p.get("tag_name") or "").lstrip("vV")]
    publicadas.sort(key=lambda p: _tupla(p["tag_name"].lstrip("vV")), reverse=True)
    historial = []
    for p in publicadas:
        fecha = (p.get("published_at") or "")[:10]
        if len(fecha) == 10:
            fecha = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
        historial.append(Version(p["tag_name"].lstrip("vV"), fecha, limpiar_notas(p.get("body") or "")))
    novedad = None
    if publicadas and es_mas_nueva(publicadas[0]["tag_name"].lstrip("vV")):
        novedad = _novedad_de(publicadas[0])
    return novedad, historial


def _novedad_de(datos: dict) -> Novedad:
    version = (datos.get("tag_name") or "").lstrip("vV")
    activos = {a.get("name"): a for a in datos.get("assets", [])}
    notas = limpiar_notas(datos.get("body") or "")
    setup, setup_sha = activos.get(ARCHIVO_SETUP), activos.get(ARCHIVO_SETUP_SHA)
    if setup and setup_sha:
        return Novedad(version, notas, setup["browser_download_url"], setup_sha["browser_download_url"],
                       int(setup.get("size") or 0), instalador=True)
    exe, sha = activos.get(ARCHIVO_EXE), activos.get(ARCHIVO_SHA)
    if not exe or not sha:
        raise ErrorActualizacion(f"La versión {version} no incluye {ARCHIVO_EXE} y su .sha256.")
    return Novedad(version, notas, exe["browser_download_url"], sha["browser_download_url"],
                   int(exe.get("size") or 0))


def buscar() -> Novedad | None:
    """Novedad si hay una versión más nueva publicada; None si ya está al día (para la bandeja)."""
    return consultar(1)[0]


def descargar(nov: Novedad, progreso=None, cancelar: threading.Event | None = None) -> str:
    """Descarga y verifica el nuevo .exe. Devuelve su ruta. progreso(bajado, total)."""
    os.makedirs(CARPETA, exist_ok=True)
    try:
        with _pedir(nov.url_sha) as r:
            esperado = r.read().decode("ascii", "replace").split()[0].lower()
    except (urllib.error.URLError, TimeoutError, OSError, IndexError) as e:
        raise ErrorActualizacion("No se pudo descargar la huella de verificación.") from e
    if not re.fullmatch(r"[0-9a-f]{64}", esperado):
        raise ErrorActualizacion("La huella de verificación no es válida.")
    destino = os.path.join(CARPETA, f"Brahttery-hub-Setup-{nov.version}.exe" if nov.instalador
                           else f"Brahttery hub {nov.version}.exe")
    parcial = destino + ".part"
    h = hashlib.sha256()
    try:
        with _pedir(nov.url_exe, timeout=30) as r, open(parcial, "wb") as f:
            total = int(r.headers.get("Content-Length") or nov.tamano or 0)
            bajado = 0
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise ErrorActualizacion("Descarga cancelada.")
                trozo = r.read(256 * 1024)
                if not trozo:
                    break
                f.write(trozo)
                h.update(trozo)
                bajado += len(trozo)
                if progreso:
                    progreso(bajado, total)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _borrar(parcial)
        raise ErrorActualizacion("La descarga se cortó. Inténtalo de nuevo.") from e
    except ErrorActualizacion:
        _borrar(parcial)
        raise
    if h.hexdigest() != esperado:
        _borrar(parcial)
        raise ErrorActualizacion("El archivo descargado no coincide con su huella; se descartó.")
    os.replace(parcial, destino)
    return destino


def instalar(nuevo: str) -> None:
    """Instala la versión descargada; la app se cierra y se abre actualizada.

    Instalador (desde la 1.4.0): se cierra la bandeja (así quita sus iconos) y se ejecuta el
    Setup en silencio; este cierra lo que quede, reemplaza la carpeta del programa y lo vuelve a
    abrir. .exe suelto (versiones anteriores): se cambia el .exe en su sitio."""
    if not se_puede_instalar():
        raise ErrorActualizacion("Sólo el .exe se puede actualizar solo.")
    if os.path.basename(nuevo).startswith("Brahttery-hub-Setup"):
        cerrar_bandeja()
        subprocess.Popen([nuevo, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL"],
                         close_fds=True, env=rutas.entorno_nuevo())
        return
    exe = sys.executable
    viejo = exe[:-4] + f".old-{int(time.time())}.exe"
    os.replace(exe, viejo)                       # renombrar un .exe en marcha está permitido
    try:
        os.replace(nuevo, exe)
    except OSError:
        os.replace(viejo, exe)                   # deshacer: la app sigue como estaba
        raise ErrorActualizacion("No se pudo reemplazar el programa (¿carpeta protegida?).")
    cerrar_bandeja()
    subprocess.Popen([exe, "--actualizado"], close_fds=True, env=rutas.entorno_nuevo())


def cerrar_bandeja(espera: float = 6) -> None:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(rutas.ID, None)
    if not hwnd:
        return
    user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE: quita sus iconos y sale
    fin = time.monotonic() + espera
    while user32.FindWindowW(rutas.ID, None) and time.monotonic() < fin:
        time.sleep(0.1)


def limpiar() -> None:
    """Borra los .exe viejos que dejó una actualización anterior, las descargas usadas y las
    carpetas temporales que quedaron de copias de la app cerradas de golpe."""
    if rutas.CONGELADO:
        for f in glob.glob(sys.executable[:-4] + ".old-*.exe"):
            _borrar(f)
        limpiar_temporales()
    for f in glob.glob(os.path.join(CARPETA, "*")):
        _borrar(f)
    # fotos de los temas (fundido instantáneo) de versiones anteriores
    for f in glob.glob(os.path.join(rutas.DATOS, "tema_*_*.png")):
        if not f.endswith(f"_{rutas.VERSION}.png"):
            _borrar(f)


def limpiar_temporales(carpeta: str | None = None, min_edad: float = 120) -> tuple[int, int, int]:
    """El .exe se descomprime en %TEMP%\\_MEIxxxxx al arrancar y la borra al cerrarse bien.
    Si el proceso se corta (apagado del PC, cierre forzado), la carpeta queda (~37 MB cada una).

    Solo se tocan las carpetas de ESTA app (tienen brahttery_hub.ico) que no estén en uso.
    Para saberlo se intenta abrir para escritura sus DLL/PYD: Windows no lo permite si una copia
    de la app en marcha las tiene cargadas. (Renombrar la carpeta NO sirve: Windows deja renombrar
    aunque haya DLL cargadas.) Devuelve (borradas, en uso, bytes liberados)."""
    base = carpeta or tempfile.gettempdir()
    propia = os.path.normcase(getattr(sys, "_MEIPASS", "") or "")
    borradas = en_uso = liberado = 0
    for d in glob.glob(os.path.join(base, "_MEI*")):
        if os.path.normcase(d) == propia or not os.path.isfile(os.path.join(d, "brahttery_hub.ico")):
            continue
        try:
            if time.time() - os.path.getmtime(d) < min_edad:     # otra copia recién arrancando
                continue
            if _en_uso(d):
                en_uso += 1
                continue
            tamano = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)
            aparte = d + "-borrar"
            os.rename(d, aparte)          # falla si alguna copia de la app la está usando
        except OSError:
            en_uso += 1
            continue
        shutil.rmtree(aparte, ignore_errors=True)
        borradas += 1
        liberado += tamano
    return borradas, en_uso, liberado


def _en_uso(carpeta: str) -> bool:
    """¿Algún programa en marcha tiene cargada una DLL/PYD de esta carpeta?"""
    for raiz, _dirs, archivos in os.walk(carpeta):
        for f in archivos:
            if f.lower().endswith((".dll", ".pyd")):
                try:
                    with open(os.path.join(raiz, f), "r+b"):
                        pass
                except PermissionError:
                    return True
                except OSError:
                    continue
    return False


def _borrar(ruta: str) -> None:
    try:
        os.remove(ruta)
    except OSError:
        pass
