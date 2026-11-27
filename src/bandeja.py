"""Brahttery hub: batería de periféricos en la bandeja del sistema.

Un icono transparente por periférico conectado (ratón, cascos, mando...).
Al dejar el puntero encima se ve el porcentaje y las horas de uso que quedan.

  * Los iconos nuevos aparecen en los iconos ocultos (flecha ^); arrástralos a la
    barra para fijarlos. Windows recuerda la posición de cada uno.
  * Clic derecho: personalizar, actualizar, iniciar con Windows, salir.
"""
from __future__ import annotations

import ctypes
import dataclasses
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
import winreg
from ctypes import wintypes as wt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import actualizador  # noqa: E402
import apariencia as ap  # noqa: E402
import dispositivos  # noqa: E402
import rutas  # noqa: E402
import notificaciones  # noqa: E402
import polling  # noqa: E402
import sonidos  # noqa: E402
from estimacion import Estimador, formato_horas  # noqa: E402

INTERVALO_LECTURA = 60          # segundos entre lecturas de batería
MANTENER_SEGUNDOS = 1200        # cuánto se mantiene un dispositivo que deja de responder
NOMBRE_APP = rutas.ID
CLAVE_APP = "__app__"           # icono propio de la app cuando no hay periféricos


def log(msg: str) -> None:
    try:
        with open(rutas.RUTA_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateEventW.restype = ctypes.c_void_p
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wt.DWORD]
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x80
WM_DESTROY, WM_TIMER, WM_RBUTTONUP, WM_CONTEXTMENU, WM_APP = 0x0002, 0x0113, 0x0205, 0x007B, 0x8000
WM_LBUTTONUP = 0x0202          # clic izquierdo en un icono: abre la app
WM_DATOS = WM_APP + 1
WM_BANDEJA = WM_APP + 2
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_BOTTOMALIGN = 0x2, 0x100, 0x20
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_GUID = 0x1, 0x2, 0x4, 0x10, 0x20
NIIF_INFO = 0x1
NIIF_USER, NIIF_NOSOUND, NIIF_LARGE_ICON = 0x4, 0x10, 0x20
CRITICO = 5                     # % del segundo aviso (batería crítica)
NIN_BALLOONUSERCLICK = 0x0405
WM_NOVEDAD = WM_APP + 3
WM_AVISO = WM_APP + 4
BUSCAR_ACTUALIZACIONES_CADA = 6 * 3600   # segundos
SM_CXSMICON = 49


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _uuid_de(texto: str) -> uuid.UUID:
    # Windows ata cada GUID a la ruta del programa, así que la ruta forma parte del GUID
    return uuid.uuid5(uuid.UUID("6b1d3c2e-8f4a-4e6b-9a51-3c7d2b9e0f11"), sys.executable.lower() + "|" + texto)


def guid_texto(texto: str) -> str:
    """El GUID tal como lo guarda Windows en el registro: {XXXXXXXX-XXXX-...}."""
    return "{" + str(_uuid_de(texto)).upper() + "}"


# --------------------------------------------------------------------------
# Iconos visibles en la barra (fuera de los ocultos)
# --------------------------------------------------------------------------
# Windows 11 guarda cada icono de la bandeja en HKCU\Control Panel\NotifyIconSettings\<n>
# (IconGuid = nuestro GUID) e IsPromoted = 1 si se ve en la barra en vez de en la flecha ^.
# La app lo activa una sola vez por icono (la primera vez que aparece); si después lo
# escondes desde Configuración, se respeta.
_ICONOS_WIN = r"Control Panel\NotifyIconSettings"
_ICONOS_HECHOS = r"Software\BrahtteryHub\IconosMostrados"


def _ya_mostrado(guid: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ICONOS_HECHOS) as k:
            winreg.QueryValueEx(k, guid)
            return True
    except OSError:
        return False


def promover_iconos(guids: set[str]) -> set[str]:
    """Pone en la barra los iconos indicados. Devuelve los que ya quedaron resueltos."""
    resueltos = {g for g in guids if _ya_mostrado(g)}
    pendientes = guids - resueltos
    if not pendientes:
        return resueltos
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ICONOS_WIN) as base:
            i = 0
            while pendientes:
                try:
                    sub = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(base, sub, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                        guid = str(winreg.QueryValueEx(k, "IconGuid")[0]).upper()
                        if guid in pendientes:
                            winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
                            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _ICONOS_HECHOS, 0,
                                                    winreg.KEY_SET_VALUE) as h:
                                winreg.SetValueEx(h, guid, 0, winreg.REG_DWORD, 1)
                            pendientes.discard(guid)
                            resueltos.add(guid)
                except OSError:
                    continue
    except OSError:
        pass                        # Windows 10: no existe esa clave (allí se fijan a mano)
    return resueltos


def guid_de(texto: str) -> GUID:
    """GUID estable para cada dispositivo: así Windows recuerda si lo fijaste en la barra."""
    u = _uuid_de(texto)
    g = GUID(u.fields[0], u.fields[1], u.fields[2])
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HICON), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                ("hbmMask", wt.HBITMAP), ("hbmColor", wt.HBITMAP)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
user32.RegisterWindowMessageW.restype = wt.UINT
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID]
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.CreateIconIndirect.restype = wt.HICON
user32.DestroyIcon.argtypes = [wt.HICON]
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateBitmap.restype = wt.HBITMAP
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]


tema_claro = ap.tema_claro


inicio_activado = rutas.inicio_activado


_ultima_apertura = 0.0


def abrir_ventana() -> None:
    """Muestra la ventana: si ya está en marcha (oculta) aparece al instante; si no, se abre."""
    global _ultima_apertura
    user32.AllowSetForegroundWindow(-1)       # deja que la ventana se ponga delante (ASFW_ANY)
    if rutas.avisar_ventana(rutas.EVENTO_MOSTRAR):
        return
    if time.monotonic() - _ultima_apertura < 4:     # ya se está abriendo (p. ej. doble clic)
        return
    _ultima_apertura = time.monotonic()
    subprocess.Popen(rutas.comando("--configurar"), env=rutas.entorno_nuevo())


def alternar_inicio() -> None:
    rutas.poner_inicio(not rutas.inicio_activado())


# --------------------------------------------------------------------------
# Iconos
# --------------------------------------------------------------------------
def crear_icono(d: dispositivos.Dispositivo, ajustes: dict, cfg: dict, tam: int, claro: bool,
                texto: str | None = None) -> wt.HICON:
    return hicon_de(ap.dibujar_icono(d.tipo, d.bateria, d.cargando, ajustes, cfg, tam, claro, texto), tam)


def icono_app(tam: int, cfg: dict) -> wt.HICON:
    """Icono BrH de la app (se usa cuando no hay ningún periférico que mostrar)."""
    from PIL import Image
    nombre = {"oscuro": "brahttery_hub_oscuro", "gris": "brahttery_hub_gris"}.get(cfg.get("tema_app"),
                                                                                  "brahttery_hub")
    img = Image.open(rutas.recurso(nombre + ".png")).convert("RGBA").resize((tam, tam), Image.LANCZOS)
    return hicon_de(img, tam)


def hicon_de(img, tam: int) -> wt.HICON:
    bgra = img.tobytes("raw", "BGRA")
    bmi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=tam, biHeight=-tam,
                           biPlanes=1, biBitCount=32, biCompression=0)
    bits = ctypes.c_void_p()
    color_bmp = gdi32.CreateDIBSection(None, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, bgra, len(bgra))
    mascara = gdi32.CreateBitmap(tam, tam, 1, 1, None)
    info = ICONINFO(True, 0, 0, mascara, color_bmp)
    hicon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(color_bmp)
    gdi32.DeleteObject(mascara)
    return hicon


def texto_tooltip(d: dispositivos.Dispositivo, ajustes: dict, est: Estimador) -> str:
    if d.cargando:
        linea = f"{d.bateria} % · cargando"
    else:
        horas, medido = est.horas(d.clave, d.tipo, d.bateria, ajustes.get("autonomia"), d.hz)
        linea = f"{d.bateria} % · quedan ~{formato_horas(horas)}"
        linea += "" if medido else " (aprox.)"
    if d.hz:
        linea += f"\n{d.hz} Hz"
    if d.en_reposo:
        linea += "\nEn reposo (último valor leído)"
    return f"{ajustes.get('nombre') or d.nombre}\n{linea}"[:127]


# --------------------------------------------------------------------------
# Aplicación de bandeja
# --------------------------------------------------------------------------
class Bandeja:
    def __init__(self) -> None:
        self.cfg = ap.cargar_config()
        self.cfg_mtime = self._mtime_config()
        self.est = Estimador(self.cfg.get("autonomia_horas"))
        self.conocidos: dict[str, dict] = ap.cargar_estado().get("conocidos", {})
        self.datos: list[dispositivos.Dispositivo] = []
        self.vistos: dict[str, tuple[dispositivos.Dispositivo, float]] = {}
        # Al arrancar, lo que se leyó hace poco (o cuyo receptor sigue enchufado) se muestra ya con
        # su último valor: así un ratón en reposo no desaparece al reiniciar la app.
        for clave, c in self.conocidos.items():
            visto = c.get("visto") or 0
            if time.time() - visto < MANTENER_SEGUNDOS or (visto and dispositivos.receptor_presente(clave)):
                d = dispositivos.Dispositivo(clave, c.get("nombre", clave), c.get("tipo", "otro"),
                                             int(c.get("bateria", 0)), bool(c.get("cargando")))
                self.vistos[clave] = (d, visto)
        self.iconos: dict[str, tuple[int, wt.HICON, tuple]] = {}   # clave -> (uID, hicon, firma)
        self.ids: dict[str, int] = {}
        self.ultima_lectura = 0.0
        self.tema = tema_claro()
        self.evento_leer = threading.Event()
        self.msg_taskbar_creada = user32.RegisterWindowMessageW("TaskbarCreated")

        self._wndproc = WNDPROC(self._proc)
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self._wndproc,
                         hInstance=hinst, lpszClassName=NOMBRE_APP)
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(WS_EX_TOOLWINDOW, NOMBRE_APP, f"{NOMBRE_APP} {rutas.VERSION}", WS_POPUP,
                                           0, 0, 0, 0, None, None, hinst, None)
        user32.SetTimer(self.hwnd, 1, 1000, None)      # vigilar config.json y el tema claro/oscuro
        self.hz_avisado: dict[str, int] = {}
        self.novedad = None                             # versión nueva publicada (si la hay)
        self.avisado: dict[str, str] = {}               # clave -> "baja"/"critico" ya avisado
        self.avisos: list = []                          # avisos pendientes de mostrar (hilo principal)
        self.ev_probar = kernel32.CreateEventW(None, False, False, rutas.EVENTO_PROBAR_AVISO)
        self.por_mostrar: dict[str, float] = {}         # GUID -> cuándo se añadió (para sacarlo de ^)
        threading.Thread(target=self._hilo_lectura, daemon=True).start()
        threading.Thread(target=self._hilo_actualizaciones, daemon=True).start()

    # ---- actualizaciones: una consulta a GitHub cada pocas horas, nada más
    def _hilo_actualizaciones(self) -> None:
        if not actualizador.configurado():
            return
        time.sleep(90)
        avisada = None
        while True:
            try:
                nov = actualizador.buscar()
                self.novedad = nov
                if nov and nov.version != avisada:
                    avisada = nov.version
                    user32.PostMessageW(self.hwnd, WM_NOVEDAD, 0, 0)
            except Exception as e:      # noqa: BLE001  (sin conexión: se reintenta más tarde)
                log(f"Actualizaciones: {e}")
            time.sleep(BUSCAR_ACTUALIZACIONES_CADA)

    # ---- aviso de batería baja: notificación de Windows + sonido elegido
    def _revisar_avisos(self, leidos: list) -> None:
        """Se llama en cada lectura con los periféricos que respondieron de verdad. Un aviso al
        bajar del umbral y otro al llegar a CRITICO; se vuelven a armar al cargar o al subir."""
        if not ap.global_(self.cfg, "avisos_bateria"):
            return
        umbral = int(ap.global_(self.cfg, "umbral_baja"))
        for d in leidos:
            if self._ajustes(d)["oculto"]:
                continue
            ya = self.avisado.get(d.clave)
            if d.cargando or d.bateria > umbral + 3:
                self.avisado.pop(d.clave, None)
            elif d.bateria <= CRITICO and ap.global_(self.cfg, "aviso_critico") and ya != "critico":
                self.avisado[d.clave] = "critico"
                self.avisos.append((d, "critico"))
            elif d.bateria <= umbral and ya is None:
                self.avisado[d.clave] = "baja"
                self.avisos.append((d, "baja"))
        if self.avisos:
            user32.PostMessageW(self.hwnd, WM_AVISO, 0, 0)

    def _revisar_hz(self, d) -> None:
        """Avisa (una vez por cambio) cuando un ratón pasa a 2000 Hz o más."""
        if not d.hz:
            return
        previo = self.hz_avisado.get(d.clave, (self.conocidos.get(d.clave) or {}).get("hz_avisado"))
        if d.hz == previo:
            return
        self.hz_avisado[d.clave] = d.hz
        self.conocidos.setdefault(d.clave, {})["hz_avisado"] = d.hz
        if d.hz >= polling.ALTO and ap.global_(self.cfg, "avisos_bateria"):
            self.avisos.append((d, "hz"))
            user32.PostMessageW(self.hwnd, WM_AVISO, 0, 0)

    def _mostrar_avisos(self) -> None:
        while self.avisos:
            d, nivel = self.avisos.pop(0)
            self._notificar_bateria(d, nivel)

    def _notificar_bateria(self, d, nivel: str) -> None:
        if not self.iconos:
            return
        a = self._ajustes(d)
        nombre = a.get("nombre") or d.nombre
        if nivel == "hz":
            horas, _ = self.est.horas(d.clave, d.tipo, d.bateria, a.get("autonomia"), d.hz)
            titulo = f"{nombre}: polling rate en {d.hz} Hz"
            texto = (f"A {d.hz} Hz {polling.texto_efecto(d.hz)}. Con {d.bateria} % quedan unas "
                     f"{formato_horas(horas)} de uso. Si no lo necesitás, bajalo a 1000 Hz desde el "
                     f"programa del ratón.")
        elif nivel == "prueba":
            titulo = f"{nombre}: batería baja (prueba)"
            texto = "Así se verá el aviso cuando un periférico se esté quedando sin batería."
        else:
            horas, _ = self.est.horas(d.clave, d.tipo, d.bateria, a.get("autonomia"), d.hz)
            titulo = f"{nombre}: batería {'crítica' if nivel == 'critico' else 'baja'}"
            texto = (f"Queda {d.bateria} % (unas {formato_horas(horas)} de uso). "
                     f"{'Cárgalo ya.' if nivel == 'critico' else 'Ponlo a cargar cuando puedas.'}")
        # Notificación moderna de Windows (la del globito de la bandeja, Windows 11 a veces no la muestra)
        imagen = os.path.join(rutas.DATOS, "aviso_icono.png")
        try:
            ap.dibujar_icono(d.tipo, d.bateria, False, a, self.cfg, 96, False).save(imagen)
        except OSError:
            imagen = None
        ok = notificaciones.mostrar(titulo, texto, imagen)
        if not ok:                      # plan B: el globito de la bandeja
            clave = d.clave if d.clave in self.iconos else next(iter(self.iconos))
            nid = self._nid(clave)
            nid.uFlags = NIF_INFO | NIF_GUID
            nid.dwInfoFlags = NIIF_INFO | NIIF_NOSOUND
            nid.szInfoTitle, nid.szInfo = titulo[:63], texto[:255]
            ok = shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        try:
            if nivel != "hz" and not ap.global_(self.cfg, "aviso_silencio"):
                sonidos.reproducir(ap.global_(self.cfg, "sonido_aviso"), ap.global_(self.cfg, "volumen_aviso"))
        except Exception:
            log(traceback.format_exc())
        log(f"Aviso de batería {nivel}: {nombre} {d.bateria}% (notificación {'enviada' if ok else 'rechazada'})")

    def _probar_aviso(self) -> None:
        """Botón "Probar aviso" de la ventana: muestra el aviso con el primer periférico."""
        if self.datos:
            self._notificar_bateria(self.datos[0], "prueba")
        else:
            try:
                if not ap.global_(self.cfg, "aviso_silencio"):
                    sonidos.reproducir(ap.global_(self.cfg, "sonido_aviso"), ap.global_(self.cfg, "volumen_aviso"))
            except Exception:
                pass

    def _avisar_novedad(self) -> None:
        if not self.novedad or not self.iconos:
            return
        nid = self._nid(next(iter(self.iconos)))
        nid.uFlags = NIF_INFO | NIF_GUID
        nid.dwInfoFlags = NIIF_INFO
        nid.szInfoTitle = f"{rutas.NOMBRE} {self.novedad.version} disponible"
        nid.szInfo = "Haz clic aquí para ver las novedades e instalarla."
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # ---- lectura en segundo plano
    def _hilo_lectura(self) -> None:
        while True:
            try:
                self._leer_una_vez()
            except Exception:
                log(traceback.format_exc())
            self.evento_leer.wait(INTERVALO_LECTURA)
            self.evento_leer.clear()

    def _leer_una_vez(self) -> None:
        errores: list[str] = []
        datos = dispositivos.leer_todo(errores)
        for e in errores:
            log(e)
        ahora = time.time()
        for d in datos:
            if d.tipo == "raton" and d.hz is None:
                d.hz = polling.para(d.ids) if d.ids else None     # lo mide la ventana
                if d.hz is None:                     # último valor conocido (sin mover el ratón no se mide)
                    d.hz = (self.conocidos.get(d.clave) or {}).get("hz")
            self.vistos[d.clave] = (d, ahora)
            self.est.registrar(d.clave, d.bateria, d.cargando, ahora, d.hz)
            self._revisar_hz(d)
        if self.est.toca_analizar(ahora):       # una vez al día: perfil de consumo de cada uno
            try:
                self.est.analizar(ahora)
                log("Análisis de consumo: " + (", ".join(
                    f"{c} {p['por_hora']:.2f} %/h ({p['horas']:.1f} h)" for c, p in self.est.perfiles.items())
                    or "aún sin datos suficientes"))
            except Exception:
                log(traceback.format_exc())
        claves = {d.clave for d in datos}
        try:
            self._revisar_avisos([d for d in datos if d.clave in claves])
        except Exception:
            log(traceback.format_exc())
        for clave, (d, t) in list(self.vistos.items()):
            if clave in claves:
                continue
            if ahora - t < MANTENER_SEGUNDOS or dispositivos.receptor_presente(clave):
                datos.append(dataclasses.replace(d, en_reposo=True))
            else:
                del self.vistos[clave]
        orden = list(dispositivos.ORDEN_TIPOS)
        datos.sort(key=lambda d: (orden.index(d.tipo), d.nombre))
        resumen = ", ".join(f"{d.nombre} {d.bateria}%" for d in datos) or "ninguno"
        if resumen != getattr(self, "_resumen", None):
            log("Leídos: " + resumen)
            self._resumen = resumen
        self.datos = datos
        self.ultima_lectura = ahora
        for d in datos:     # lista de periféricos conocidos, para la ventana de personalización
            if d.clave not in claves:   # en reposo: se conserva cuándo respondió de verdad
                continue
            self.conocidos[d.clave] = {"nombre": d.nombre, "tipo": d.tipo, "bateria": d.bateria,
                                       "cargando": d.cargando, "visto": ahora}
            if d.hz:
                self.conocidos[d.clave].update(hz=d.hz, hz_exacto=d.hz_exacto)
        try:    # Bluetooth emparejados y apagados: Windows guarda su última batería
            for d in dispositivos.leer_bluetooth_desconectados():
                previo = self.conocidos.get(d.clave)
                if not previo or not previo.get("visto"):
                    self.conocidos[d.clave] = {"nombre": d.nombre, "tipo": d.tipo, "bateria": d.bateria,
                                               "cargando": False, "visto": None}
        except Exception:
            log(traceback.format_exc())
        try:
            ap.guardar_estado({"conocidos": self.conocidos, "conectados": [d.clave for d in datos],
                               "hora": ahora})
        except OSError:
            log(traceback.format_exc())
        user32.PostMessageW(self.hwnd, WM_DATOS, 0, 0)

    # ---- iconos de bandeja
    def _nid(self, clave: str) -> NOTIFYICONDATAW:
        if clave not in self.ids:
            self.ids[clave] = len(self.ids) + 1
        nid = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self.hwnd, uID=self.ids[clave])
        nid.guidItem = guid_de(clave)
        return nid

    def sincronizar(self, forzar: bool = False) -> None:
        tam = user32.GetSystemMetrics(SM_CXSMICON)
        visibles = [d for d in self.datos if not self._ajustes(d)["oculto"]]
        actuales = {d.clave for d in visibles}
        if not visibles:    # sin periféricos: icono de la app, para que se vea que está abierta
            actuales.add(CLAVE_APP)
            self._poner_icono_app(tam, forzar)
        for clave in list(self.iconos):
            if clave not in actuales:
                self._quitar(clave)
        for d in visibles:
            ajustes = self._ajustes(d)
            tip = texto_tooltip(d, ajustes, self.est)
            horas, _ = self.est.horas(d.clave, d.tipo, d.bateria, ajustes.get("autonomia"), d.hz)
            texto = ap.texto_icono(self.cfg, ajustes, d.bateria, d.cargando, horas)
            firma = (d.tipo, d.bateria, d.cargando, self.tema, tam, tip, texto, self.cfg_mtime)
            previo = self.iconos.get(d.clave)
            if previo and previo[2] == firma and not forzar:
                continue
            hicon = crear_icono(d, ajustes, self.cfg, tam, self.tema, texto)
            nid = self._nid(d.clave)
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_GUID
            nid.uCallbackMessage = WM_BANDEJA
            nid.hIcon = hicon
            nid.szTip = tip
            if previo and not forzar:
                ok = shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
            else:
                ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
                if not ok:  # GUID ya registrado (p. ej. tras un cierre brusco): se reemplaza
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                    ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
            if not ok:
                log(f"No se pudo mostrar el icono de {d.nombre} (error {ctypes.get_last_error()})")
            if previo:
                user32.DestroyIcon(previo[1])
            else:
                self._anotar_para_mostrar(d.clave)
            self.iconos[d.clave] = (self.ids[d.clave], hicon, firma)

    def _poner_icono_app(self, tam: int, forzar: bool) -> None:
        firma = (tam, self.cfg.get("tema_app"), self.ultima_lectura > 0)
        previo = self.iconos.get(CLAVE_APP)
        if previo and previo[2] == firma and not forzar:
            return
        hicon = icono_app(tam, self.cfg)
        nid = self._nid(CLAVE_APP)
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_GUID
        nid.uCallbackMessage = WM_BANDEJA
        nid.hIcon = hicon
        nid.szTip = (rutas.NOMBRE + "\n" + ("Sin periféricos compatibles detectados" if self.ultima_lectura
                                            else "Buscando periféricos…"))
        ok = False
        if previo and not forzar:
            ok = shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        if not ok:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        if not ok:
            log(f"No se pudo mostrar el icono de la app (error {ctypes.get_last_error()})")
        if previo:
            user32.DestroyIcon(previo[1])
        else:
            self._anotar_para_mostrar(CLAVE_APP)
        self.iconos[CLAVE_APP] = (self.ids[CLAVE_APP], hicon, firma)

    def _anotar_para_mostrar(self, clave: str) -> None:
        if ap.global_(self.cfg, "iconos_visibles"):
            guid = guid_texto(clave)
            if not _ya_mostrado(guid):
                self.por_mostrar.setdefault(guid, time.time())

    def _mostrar_pendientes(self) -> None:
        """Windows crea la entrada del icono un momento después de añadirlo: se reintenta cada
        segundo (máx. 1 min) hasta encontrarla y ponerla en la barra."""
        hechos = promover_iconos(set(self.por_mostrar))
        ahora = time.time()
        for guid in list(self.por_mostrar):
            if guid in hechos or ahora - self.por_mostrar[guid] > 60:
                del self.por_mostrar[guid]

    def _ajustes(self, d: dispositivos.Dispositivo) -> dict:
        return ap.ajustes_de(self.cfg, d.clave, d.tipo)

    def _mtime_config(self) -> float:
        try:
            return os.path.getmtime(ap.RUTA_CONFIG)
        except OSError:
            return 0.0

    def _quitar(self, clave: str) -> None:
        nid = self._nid(clave)
        nid.uFlags = NIF_GUID
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        _, hicon, _ = self.iconos.pop(clave)
        user32.DestroyIcon(hicon)

    # ---- menú
    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, rutas.NOMBRE)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        for d in self.datos:
            a = self._ajustes(d)
            texto = texto_tooltip(d, a, self.est).replace("\n", ": ") + ("  (oculto)" if a["oculto"] else "")
            user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, texto)
        if self.ultima_lectura:
            user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0,
                               "Leído a las " + time.strftime("%H:%M:%S", time.localtime(self.ultima_lectura)))
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        if self.novedad:
            user32.AppendMenuW(menu, MF_STRING, 4, f"Actualizar a la versión {self.novedad.version}…")
        user32.AppendMenuW(menu, MF_STRING, 4, "Personalizar…")
        user32.AppendMenuW(menu, MF_STRING, 1, "Actualizar ahora")
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if inicio_activado() else 0), 2, "Iniciar con Windows")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, 3, "Salir")
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_BOTTOMALIGN,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if cmd == 4:
            abrir_ventana()
        elif cmd == 1:
            self.evento_leer.set()
        elif cmd == 2:
            try:
                alternar_inicio()
            except OSError:
                log(traceback.format_exc())
        elif cmd == 3:
            user32.DestroyWindow(self.hwnd)

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_DATOS:
                self.sincronizar()
                return 0
            if msg == WM_BANDEJA:
                if (lparam & 0xFFFF) in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._menu()
                elif (lparam & 0xFFFF) in (WM_LBUTTONUP, NIN_BALLOONUSERCLICK):
                    abrir_ventana()
                return 0
            if msg == WM_NOVEDAD:
                self._avisar_novedad()
                return 0
            if msg == WM_AVISO:
                self._mostrar_avisos()
                return 0
            if msg == WM_TIMER:
                if self.ev_probar and kernel32.WaitForSingleObject(self.ev_probar, 0) == 0:
                    self._probar_aviso()
                if self.por_mostrar:
                    self._mostrar_pendientes()
                tema = tema_claro()
                mtime = self._mtime_config()
                if mtime != self.cfg_mtime:          # cambios desde la ventana de personalización
                    self.cfg = ap.cargar_config()
                    self.cfg_mtime = mtime
                    self.est.nominal.update(self.cfg.get("autonomia_horas", {}))
                    self.tema = tema
                    self.sincronizar()
                elif tema != self.tema:
                    self.tema = tema
                    self.sincronizar()
                return 0
            if msg == self.msg_taskbar_creada:      # Explorer se reinició: volver a añadir los iconos
                self.sincronizar(forzar=True)
                return 0
            if msg == WM_DESTROY:
                rutas.avisar_ventana(rutas.EVENTO_SALIR)    # la ventana oculta también termina
                for clave in list(self.iconos):
                    self._quitar(clave)
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            log(traceback.format_exc())
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def bucle(self) -> None:
        m = wt.MSG()
        while user32.GetMessageW(ctypes.byref(m), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(m))
            user32.DispatchMessageW(ctypes.byref(m))


def version_bandeja_en_marcha() -> str | None:
    """Versión de la bandeja que ya está en marcha (la lleva en el título de su ventana oculta,
    desde la 1.4.1). Las anteriores solo ponían "BrahtteryHub": cuentan como "0". None si no hay."""
    hwnd = user32.FindWindowW(NOMBRE_APP, None)
    if not hwnd:
        return None
    buf = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(hwnd, buf, 128)
    partes = buf.value.split()
    return partes[1] if len(partes) > 1 else "0"


def main() -> None:
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # Per-monitor v2
    except Exception:
        pass
    manual = "--inicio" not in sys.argv[1:]     # doble clic (no el arranque con Windows)
    if "--actualizado" in sys.argv[1:]:         # recién actualizada: dejar que la versión vieja termine
        time.sleep(2.5)
    threading.Thread(target=actualizador.limpiar, daemon=True).start()
    # Las primeras versiones registraban la bandeja con otro nombre (y otro bloqueo): podían quedar
    # en marcha a la vez que esta, con iconos que no se actualizan. Se cierran.
    for viejo in rutas._IDS_ANTIGUOS:
        h = user32.FindWindowW(viejo, None)
        if h:
            log(f"Cerrando una bandeja de una versión muy antigua ({viejo})")
            user32.PostMessageW(h, 0x0010, 0, 0)            # WM_CLOSE
    kernel32.CreateMutexW(None, False, "Local\\" + NOMBRE_APP)
    if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS: ya hay una abierta
        otra = version_bandeja_en_marcha()
        if otra is not None and actualizador.es_mas_nueva(rutas.VERSION, otra):
            # Es de una versión anterior (p. ej. una copia vieja que arrancó con Windows): no
            # conoce las opciones nuevas, así que se cierra y esta ocupa su lugar.
            log(f"Cerrando la bandeja de una versión anterior ({otra}) para usar la {rutas.VERSION}")
            actualizador.cerrar_bandeja()
        else:
            if manual:                          # abrir de nuevo el .exe muestra la ventana
                abrir_ventana()
            return
    if manual:
        abrir_ventana()
    try:
        if rutas.inicio_primera_vez():          # primera vez: se apunta sola al arranque de Windows
            log("Añadida a las aplicaciones de arranque de Windows")
        rutas.actualizar_inicio()
        rutas.actualizar_version_instalada()
    except OSError:
        log(traceback.format_exc())
    try:
        Bandeja().bucle()
    except Exception:
        log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
