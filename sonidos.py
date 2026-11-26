"""Sonidos para el aviso de batería baja.

Tres orígenes:
  * "app:<nombre>"     sonidos propios de la app, sintetizados la primera vez (WAV en la carpeta de datos);
  * "win:<archivo>"    una selección de los sonidos que trae Windows (C:\\Windows\\Media);
  * "propio:<archivo>" sonidos que agrega el usuario (se copian a la carpeta de datos);
y además "ninguno". Se reproducen con MCI (winmm), que acepta WAV, MP3 y WMA, con volumen.
"""
from __future__ import annotations

import ctypes
import math
import os
import shutil
import struct
import wave

import rutas

CARPETA = os.path.join(rutas.DATOS, "sonidos")
PROPIOS = os.path.join(CARPETA, "propios")
EXTENSIONES = (".wav", ".mp3", ".wma")
PREDETERMINADO = "app:campanita"

# (nombre visible, notas: [(frecuencia Hz, inicio s, duración s)])
_APP = {
    "campanita": ("Campanita", [(1318.5, 0.0, 0.9), (1046.5, 0.16, 1.1)]),
    "burbuja": ("Burbuja", [(880.0, 0.0, 0.25), (1174.7, 0.09, 0.35)]),
    "aviso_suave": ("Aviso suave", [(659.3, 0.0, 0.5), (659.3, 0.28, 0.5), (523.3, 0.56, 0.8)]),
    "descenso": ("Descenso", [(987.8, 0.0, 0.45), (784.0, 0.17, 0.45), (587.3, 0.34, 0.9)]),
    "pulso": ("Pulso", [(740.0, 0.0, 0.14), (740.0, 0.2, 0.14), (740.0, 0.4, 0.14)]),
}
_WINDOWS = [
    ("Windows Battery Low.wav", "Batería baja (Windows)"),
    ("Windows Battery Critical.wav", "Batería crítica (Windows)"),
    ("Windows Notify System Generic.wav", "Notificación (Windows)"),
    ("Windows Notify Messaging.wav", "Mensaje (Windows)"),
    ("Windows Ding.wav", "Ding (Windows)"),
    ("Alarm02.wav", "Alarma suave (Windows)"),
    ("Ring05.wav", "Timbre (Windows)"),
]


def _media() -> str:
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media")


def _sintetizar(ruta: str, notas: list[tuple[float, float, float]], tasa: int = 44100) -> None:
    """Notas tipo campana: seno + armónicos suaves, ataque corto y caída exponencial."""
    largo = max(i + d for _, i, d in notas) + 0.05
    n = int(largo * tasa)
    muestras = [0.0] * n
    for f, inicio, dur in notas:
        a0, a1 = int(inicio * tasa), min(n, int((inicio + dur) * tasa))
        for k in range(a0, a1):
            t = (k - a0) / tasa
            env = min(1.0, t / 0.006) * math.exp(-t * 5.5 / dur)
            v = math.sin(2 * math.pi * f * t) + 0.35 * math.sin(4 * math.pi * f * t) * math.exp(-t * 9)
            muestras[k] += 0.33 * env * v
    pico = max(1e-6, max(abs(m) for m in muestras))
    datos = b"".join(struct.pack("<h", int(32767 * 0.85 * m / pico)) for m in muestras)
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tasa)
        w.writeframes(datos)


def _asegurar_app() -> None:
    os.makedirs(CARPETA, exist_ok=True)
    for clave, (_nombre, notas) in _APP.items():
        ruta = os.path.join(CARPETA, f"app_{clave}.wav")
        if not os.path.exists(ruta):
            try:
                _sintetizar(ruta, notas)
            except OSError:
                pass


def lista() -> list[tuple[str, str]]:
    """[(id, nombre visible)] en el orden en que se muestran."""
    res = [("ninguno", "Sin sonido")]
    res += [(f"app:{c}", n) for c, (n, _x) in _APP.items()]
    res += [(f"win:{a}", n) for a, n in _WINDOWS if os.path.exists(os.path.join(_media(), a))]
    if os.path.isdir(PROPIOS):
        for a in sorted(os.listdir(PROPIOS), key=str.lower):
            if a.lower().endswith(EXTENSIONES):
                res.append((f"propio:{a}", f"{os.path.splitext(a)[0]} (tuyo)"))
    return res


def ruta(ident: str) -> str | None:
    tipo, _, nombre = ident.partition(":")
    if tipo == "app" and nombre in _APP:
        _asegurar_app()
        r = os.path.join(CARPETA, f"app_{nombre}.wav")
    elif tipo == "win":
        r = os.path.join(_media(), nombre)
    elif tipo == "propio":
        r = os.path.join(PROPIOS, nombre)
    else:
        return None
    return r if os.path.exists(r) else None


def agregar(origen: str) -> str:
    """Copia un archivo de sonido del usuario a la carpeta de la app. Devuelve su id."""
    if not origen.lower().endswith(EXTENSIONES):
        raise ValueError("Formato no admitido: usa WAV, MP3 o WMA.")
    if os.path.getsize(origen) > 10 * 1024 * 1024:
        raise ValueError("El archivo es demasiado grande (máximo 10 MB).")
    os.makedirs(PROPIOS, exist_ok=True)
    nombre = os.path.basename(origen)
    shutil.copy2(origen, os.path.join(PROPIOS, nombre))
    return f"propio:{nombre}"


def quitar(ident: str) -> None:
    if ident.startswith("propio:"):
        try:
            os.remove(os.path.join(PROPIOS, ident[7:]))
        except OSError:
            pass


_winmm = ctypes.WinDLL("winmm")
_winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]


def _mci(orden: str) -> int:
    return _winmm.mciSendStringW(orden, None, 0, None)


def reproducir(ident: str, volumen: int = 80) -> bool:
    """Reproduce el sonido sin esperar a que termine. False si no hay sonido o no se pudo."""
    r = ruta(ident)
    if not r:
        return False
    _mci("close brahttery_aviso")
    if _mci(f'open "{r}" type mpegvideo alias brahttery_aviso') != 0:
        return False
    _mci(f"setaudio brahttery_aviso volume to {max(0, min(100, int(volumen))) * 10}")
    return _mci("play brahttery_aviso from 0") == 0
