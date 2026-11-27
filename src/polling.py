"""Polling rate (tasa de sondeo) de los ratones: cuántas veces por segundo avisan a la PC.

Dos formas, las dos solo de lectura:
- Logitech: se le pregunta al ratón (HID++ 0x8060 / 0x8061, en dispositivos.py). Es exacta.
- Cualquier marca: se mide. Mientras la ventana de la app está abierta y en primer plano (Windows 11
  frena a ~125 Hz el Raw Input de los programas en segundo plano, así que la bandeja no puede), se
  suscribe unos segundos a Raw Input de Windows (lo mismo que usan los juegos y las páginas de "polling rate checker") y
  cuenta cuántos avisos por segundo manda cada ratón mientras se mueve. El resultado se redondea
  al valor estándar más cercano (125, 250, 500, 1000, 2000, 4000, 8000 Hz).

También tiene cuánto consume cada tasa respecto de 1000 Hz, con las cifras oficiales de las marcas.
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import re
import time
from ctypes import wintypes as wt

ESTANDAR = (125, 250, 500, 1000, 2000, 4000, 8000)

# Consumo relativo a 1000 Hz (1 / duración relativa). Fuentes:
# Razer Viper V3 Pro (oficial): 95 h a 1000, 62 h a 2000, 40 h a 4000, 17 h a 8000.
# Logitech Pro X Superlight 2 (95 h oficial; ~60/40/20 h medido por TechPowerUp).
# Por debajo de 1000 Hz no hay cifras oficiales: se estima un ahorro pequeño.
CONSUMO = {125: 0.85, 250: 0.88, 500: 0.92, 1000: 1.0, 2000: 1.55, 4000: 2.4, 8000: 5.2}
ALTO = 2000          # desde acá se avisa al usuario

_u32 = ctypes.windll.user32
WM_INPUT = 0x00FF
_RIDEV_INPUTSINK = 0x00000100
_RIDEV_REMOVE = 0x00000001
_RID_HEADER = 0x10000005
_RID_INPUT = 0x10000003
_RIDI_DEVICENAME = 0x20000007


class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT), ("dwFlags", wt.DWORD),
                ("hwndTarget", wt.HWND)]


class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD), ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]


_u32.GetRawInputData.argtypes = [wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT), wt.UINT]
_u32.GetRawInputData.restype = wt.UINT
_u32.GetRawInputDeviceInfoW.argtypes = [wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT)]
_u32.GetRawInputDeviceInfoW.restype = wt.UINT
_u32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(_RAWINPUTDEVICE), wt.UINT, wt.UINT]

_VIDPID = re.compile(r"VID[_&](?:[0-9A-F]{4})?([0-9A-F]{4})[_&]PID[_&]([0-9A-F]{4})", re.I)


def redondear(hz: float) -> int:
    """Al valor estándar más cercano (en escala logarítmica: 1500 está entre 1000 y 2000)."""
    return min(ESTANDAR, key=lambda e: abs(math.log(max(hz, 1) / e)))


def factor(hz: int | None) -> float:
    """Cuánto consume a esa tasa respecto de 1000 Hz (1.0 si no se sabe)."""
    if not hz:
        return 1.0
    return CONSUMO.get(hz) or CONSUMO[redondear(hz)]


def texto_efecto(hz: int) -> str:
    """Explicación simple del efecto en la batería, para avisos y la ventana."""
    f = factor(hz)
    if f >= 1.3:
        return f"la batería dura unas {f:.1f} veces menos que a 1000 Hz".replace(".", ",")
    if f < 0.97:
        return "gasta un poco menos de batería que a 1000 Hz"
    return "es lo habitual: consumo normal de batería"


def _ruta() -> str:
    import rutas
    return os.path.join(rutas.DATOS, "polling.json")


_cache = {"mtime": None, "datos": {}}


def medidos() -> dict[tuple[int, int], tuple[int, float]]:
    """Lo que midió la ventana (la bandeja lo lee de acá). Se relee solo si el archivo cambió."""
    try:
        mtime = os.path.getmtime(_ruta())
        if mtime != _cache["mtime"]:
            with open(_ruta(), encoding="utf-8") as f:
                crudo = json.load(f)
            _cache["datos"] = {tuple(int(x, 16) for x in k.split(":")): (int(v[0]), float(v[1]))
                               for k, v in crudo.items()}
            _cache["mtime"] = mtime
    except (OSError, ValueError, TypeError, IndexError):
        pass
    return _cache["datos"]


def para(ids) -> int | None:
    """Hz medidos para un dispositivo (por sus (vid, pid)); el más reciente."""
    datos = medidos()
    mejores = [datos[i] for i in ids if i in datos]
    return max(mejores, key=lambda r: r[1])[0] if mejores else None


class Medidor:
    """Vive en la ventana. Mientras está en primer plano, cada MEDIR_CADA s escucha MEDIR_DURANTE s."""

    MEDIR_CADA = 60
    MEDIR_DURANTE = 10

    def __init__(self, hwnd) -> None:
        self.hwnd = hwnd
        self.activo = False
        self._fin = 0.0
        self._proxima = time.monotonic() + 3
        self._tiempos: dict[int, list[tuple[float, int]]] = {}   # hDevice -> (llegada, desplazamiento)
        self._buf = (ctypes.c_ubyte * 128)()
        self._nombres: dict[int, tuple[int, int] | None] = {}
        self.resultados: dict[tuple[int, int], tuple[int, float]] = {}   # (vid, pid) -> (Hz, cuándo)

    # ---- suscripción
    def _registrar(self, quitar: bool) -> bool:
        rid = _RAWINPUTDEVICE(0x01, 0x02, _RIDEV_REMOVE if quitar else _RIDEV_INPUTSINK,
                              None if quitar else self.hwnd)
        return bool(_u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)))

    def tic(self, en_frente: bool = True) -> None:
        """Llamar una vez por segundo. en_frente: la ventana de la app está en primer plano."""
        ahora = time.monotonic()
        if self.activo and not en_frente:              # pasó a segundo plano: lo medido no sirve
            self._registrar(True)
            self.activo = False
            self._tiempos.clear()
            self._proxima = ahora + 5
        elif not en_frente:
            return
        elif self.activo and ahora >= self._fin:
            self._registrar(True)
            self.activo = False
            self._calcular()
        elif not self.activo and ahora >= self._proxima:
            self._proxima = ahora + self.MEDIR_CADA
            self._tiempos.clear()
            if self._registrar(False):
                self.activo = True
                self._fin = ahora + self.MEDIR_DURANTE

    # ---- WM_INPUT
    def mensaje(self, lparam) -> None:
        if not self.activo:
            return
        tam = wt.UINT(len(self._buf))
        if _u32.GetRawInputData(lparam, _RID_INPUT, self._buf, ctypes.byref(tam),
                                ctypes.sizeof(_RAWINPUTHEADER)) in (0, 0xFFFFFFFF):
            return
        h = _RAWINPUTHEADER.from_buffer(self._buf)
        if h.dwType != 0:                                  # 0 = ratón
            return
        o = ctypes.sizeof(_RAWINPUTHEADER) + 12            # RAWMOUSE.lLastX / lLastY
        dx = int.from_bytes(self._buf[o:o + 4], "little", signed=True)
        dy = int.from_bytes(self._buf[o + 4:o + 8], "little", signed=True)
        lista = self._tiempos.setdefault(h.hDevice or 0, [])
        if len(lista) < 200_000:
            lista.append((time.perf_counter(), abs(dx) + abs(dy)))

    def _vidpid(self, hdev: int) -> tuple[int, int] | None:
        if hdev in self._nombres:
            return self._nombres[hdev]
        tam = wt.UINT(0)
        _u32.GetRawInputDeviceInfoW(hdev, _RIDI_DEVICENAME, None, ctypes.byref(tam))
        res = None
        if tam.value:
            buf = ctypes.create_unicode_buffer(tam.value + 1)
            if _u32.GetRawInputDeviceInfoW(hdev, _RIDI_DEVICENAME, buf, ctypes.byref(tam)) != 0xFFFFFFFF:
                m = _VIDPID.search(buf.value)
                if m:
                    res = (int(m.group(1), 16), int(m.group(2), 16))
        self._nombres[hdev] = res
        return res

    def _calcular(self) -> None:
        """Parte el movimiento en ventanas de ~0,1 s y se queda con las "saturadas": las que traen
        2 o más puntos de desplazamiento por aviso, o sea, el ratón se movía más rápido de lo que
        sondea y por eso mandó un aviso en CADA sondeo. La mediana de esas ventanas es la tasa.
        (Si se mueve despacio manda menos avisos que su tasa real: esas ventanas no cuentan.)"""
        ahora = time.time()
        for hdev, ts in self._tiempos.items():
            if len(ts) < 100:
                continue
            tasas = []
            ini = 0
            for i in range(1, len(ts)):
                if ts[i][0] - ts[i - 1][0] > 0.04:          # se cortó el movimiento
                    ini = i
                    continue
                dur = ts[i][0] - ts[ini][0]
                if dur >= 0.1:
                    n = i - ini
                    mov = sum(m for _, m in ts[ini + 1:i + 1]) / n
                    if mov >= 2:
                        tasas.append(n / dur)
                    ini = i
            if len(tasas) < 5:
                continue
            tasas.sort()
            vp = self._vidpid(hdev)
            if vp:
                self.resultados[vp] = (redondear(tasas[len(tasas) // 2]), ahora)
        self._tiempos.clear()
        if self.resultados:
            self._guardar()

    def _guardar(self) -> None:
        datos = {f"{v:04X}:{p:04X}": [hz, t] for (v, p), (hz, t) in medidos().items()}
        datos.update({f"{v:04X}:{p:04X}": [hz, t] for (v, p), (hz, t) in self.resultados.items()})
        tmp = _ruta() + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f)
            os.replace(tmp, _ruta())
        except OSError:
            pass

    def cerrar(self) -> None:
        if self.activo:
            self._registrar(True)
            self.activo = False


# ---- ventana oculta propia (en el hilo de tk: su bucle despacha también estos mensajes)
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.DefWindowProcW.restype = ctypes.c_ssize_t
_u32.CreateWindowExW.restype = wt.HWND
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_u32.GetForegroundWindow.restype = wt.HWND


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", _WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


def en_primer_plano() -> bool:
    """¿La ventana activa de Windows es de este proceso?"""
    pid = wt.DWORD(0)
    _u32.GetWindowThreadProcessId(_u32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid()


def medidor_propio() -> Medidor | None:
    """Crea una ventana oculta que recibe WM_INPUT y un Medidor sobre ella."""
    estado = {}

    def proc(h, m, w, l):
        if m == WM_INPUT and "med" in estado:
            try:
                estado["med"].mensaje(l)
            except Exception:       # noqa: BLE001
                pass
        return _u32.DefWindowProcW(h, m, w, l)

    try:
        wp = _WNDPROC(proc)
        wc = _WNDCLASSEXW(cbSize=ctypes.sizeof(_WNDCLASSEXW), lpfnWndProc=wp, lpszClassName="BrahtteryHubHz")
        _u32.RegisterClassExW(ctypes.byref(wc))
        hwnd = _u32.CreateWindowExW(0x80, "BrahtteryHubHz", "BrahtteryHubHz", 0x80000000, 0, 0, 0, 0,
                                    None, None, None, None)
        if not hwnd:
            return None
        med = Medidor(hwnd)
        med._wndproc = wp            # que no se libere
        estado["med"] = med
        return med
    except (OSError, AttributeError):
        return None
