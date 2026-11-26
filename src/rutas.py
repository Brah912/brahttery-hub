"""Identidad de la app y dónde guarda sus datos.

Los datos (config.json, estado.json, historial.json y el registro) van en
%APPDATA%\\Brahttery hub, así funcionan igual desde el .exe que desde el código.
La primera vez se copian los que hubiera junto al código (versiones anteriores).
"""
from __future__ import annotations

import os
import shutil
import sys
import winreg

NOMBRE = "Brahttery hub"
ID = "BrahtteryHub"                       # clave de registro, mutex y clase de ventana
VERSION = "1.4.4"                         # súbela antes de publicar una actualización
# Repositorio de GitHub donde se publican las versiones ("usuario/repositorio").
# Vacío = la app no busca actualizaciones.
REPO_ACTUALIZACIONES = "Brah912/brahttery-hub"
_IDS_ANTIGUOS = ("BateriaPerifericos", "BrahteryHub")   # nombres de versiones anteriores

CONGELADO = getattr(sys, "frozen", False)  # True cuando se ejecuta desde el .exe
CARPETA_CODIGO = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), NOMBRE)
os.makedirs(DATOS, exist_ok=True)

RUTA_CONFIG = os.path.join(DATOS, "config.json")
RUTA_ESTADO = os.path.join(DATOS, "estado.json")
RUTA_HISTORIAL = os.path.join(DATOS, "historial.json")
RUTA_LOG = os.path.join(DATOS, "brahttery_hub.log")


def _migrar() -> None:
    origenes = [os.path.join(os.path.dirname(DATOS), "Brahtery hub"),      # nombre anterior (con una t)
                os.path.dirname(sys.executable) if CONGELADO else CARPETA_CODIGO]
    for origen in origenes:
        for nombre in ("config.json", "estado.json", "historial.json"):
            viejo, nuevo = os.path.join(origen, nombre), os.path.join(DATOS, nombre)
            if os.path.exists(viejo) and not os.path.exists(nuevo):
                try:
                    shutil.copy2(viejo, nuevo)
                except OSError:
                    pass


_migrar()


# --------------------------------------------------------------------------
# Cómo lanzarse a sí misma
# --------------------------------------------------------------------------
def _pythonw() -> str:
    return os.path.join(os.path.dirname(sys.executable), "pythonw.exe")


def _lanzador() -> str:
    return os.path.join(CARPETA_CODIGO, "Brahttery hub.pyw")


# --------------------------------------------------------------------------
# Comunicación bandeja <-> ventana (la ventana sigue viva, oculta, al cerrarla)
# --------------------------------------------------------------------------
MUTEX_VENTANA = "Local\\" + ID + "Ventana"
EVENTO_MOSTRAR = "Local\\" + ID + "Mostrar"     # "enséñate" (clic en un icono de la bandeja)
EVENTO_SALIR = "Local\\" + ID + "Salir"         # "termina del todo" (Salir en la bandeja)
EVENTO_PROBAR_AVISO = "Local\\" + ID + "ProbarAviso"   # botón "Probar aviso" de la ventana


def avisar_ventana(evento: str) -> bool:
    """Activa el evento si la ventana está en marcha. False si no hay ninguna ventana."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenEventW.restype = ctypes.c_void_p
    k32.SetEvent.argtypes = k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.OpenEventW(0x0002, False, evento)          # EVENT_MODIFY_STATE
    if not h:
        return False
    k32.SetEvent(h)
    k32.CloseHandle(h)
    return True


def entorno_nuevo() -> dict:
    """Entorno para lanzar otra copia de la app (ventana, o la versión nueva tras actualizar).

    El .exe de un solo archivo (PyInstaller) se descomprime en una carpeta temporal y deja su
    ruta en variables de entorno; un proceso hijo que las herede intenta usar esa carpeta.
    Si el padre se cierra (o es la versión vieja, recién reemplazada), la carpeta desaparece y
    el hijo falla con "Failed to import encodings module". Con esto cada copia es independiente."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def comando(*args: str) -> list[str]:
    """Comando para abrir la app (bandeja) o, con "--configurar", la ventana."""
    if CONGELADO:
        return [sys.executable, *args]
    return [_pythonw(), _lanzador(), *args]


# --------------------------------------------------------------------------
# Inicio con Windows
# --------------------------------------------------------------------------
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _valor(nombre: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
            return winreg.QueryValueEx(k, nombre)[0]
    except OSError:
        return None


# Lo que el usuario marca en Configuración > Aplicaciones > Inicio o en el Administrador de
# tareas: 02 = activada, 03 = desactivada (primer byte). Si no hay valor, cuenta como activada.
_APROBADO = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
_PROPIA = r"Software\BrahtteryHub"          # datos propios de la app en el registro


def _desactivada_en_windows() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APROBADO) as k:
            dato = winreg.QueryValueEx(k, ID)[0]
        return bool(dato) and dato[0] % 2 == 1
    except OSError:
        return False


def _aprobar_en_windows(activar: bool) -> None:
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _APROBADO, 0, winreg.KEY_SET_VALUE) as k:
            if activar:
                winreg.SetValueEx(k, ID, 0, winreg.REG_BINARY, bytes([2]) + bytes(11))
            else:
                winreg.DeleteValue(k, ID)
    except OSError:
        pass


def inicio_activado() -> bool:
    """Arranca con Windows: el valor existe y no está desactivado en el Administrador de tareas."""
    return _valor(ID) is not None and not _desactivada_en_windows()


def _escribir_run() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, ID, 0, winreg.REG_SZ, " ".join(f'"{p}"' for p in comando("--inicio")))


def poner_inicio(activar: bool) -> None:
    if activar:
        _escribir_run()
        _aprobar_en_windows(True)       # si estaba desactivada en Windows, vuelve a activarse
    else:
        if _valor(ID) is not None:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, ID)
        _aprobar_en_windows(False)


def actualizar_inicio() -> None:
    """Si estaba activado (con este nombre o con el antiguo), apunta al programa actual.
    No toca lo que el usuario haya desactivado desde Windows."""
    antiguo = False
    for viejo in _IDS_ANTIGUOS:
        if _valor(viejo) is not None:
            antiguo = True
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, viejo)
    if antiguo or _valor(ID) is not None:
        _escribir_run()


def inicio_primera_vez() -> bool:
    """La primera vez que se abre la app en este usuario, se apunta sola al arranque de Windows.
    Se anota que ya se hizo: si después lo desactivas, no se vuelve a activar.
    (El instalador también lo anota, según la casilla que se haya marcado.)"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PROPIA) as k:
            if winreg.QueryValueEx(k, "InicioConfigurado")[0]:
                return False
    except OSError:
        pass
    if _valor(ID) is None:
        poner_inicio(True)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _PROPIA, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "InicioConfigurado", 0, winreg.REG_DWORD, 1)
    return True


# Entrada de "Aplicaciones instaladas" que crea el instalador (instalador.iss, AppId)
_DESINSTALAR = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{B19F4761-885D-4C03-BF3A-DE1ECEA7DD9C}_is1"


def actualizar_version_instalada() -> None:
    """Tras una actualización automática, Windows debe mostrar la versión nueva en Aplicaciones."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _DESINSTALAR, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
            ubicacion = winreg.QueryValueEx(k, "InstallLocation")[0]
            if CONGELADO and os.path.normcase(os.path.dirname(sys.executable)).rstrip("\\") == \
                    os.path.normcase(ubicacion).rstrip("\\"):
                for nombre, valor in (("DisplayVersion", VERSION), ("DisplayName", NOMBRE)):
                    winreg.SetValueEx(k, nombre, 0, winreg.REG_SZ, valor)
    except OSError:
        pass                                    # no instalada con el instalador


def recurso(nombre: str) -> str:
    """Ruta de un archivo incluido en el .exe (o junto al código)."""
    base = getattr(sys, "_MEIPASS", CARPETA_CODIGO)
    return os.path.join(base, nombre)
