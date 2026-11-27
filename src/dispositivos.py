"""Lectura de la batería de los periféricos.

Todo es de sólo lectura: se pregunta el nivel de batería y nada más. No se cambia ningún
ajuste de los dispositivos, no se instalan controladores y no hacen falta permisos de
administrador.

Fuentes:
  * Bluetooth (clásico y LE): la batería que Windows ya conoce (DEVPKEY_Bluetooth_Battery)
    de cualquier aparato que la informe (auriculares, mandos, ratones, teclados...).
  * Estándar HID: cualquier periférico que declare su batería en el descriptor HID
    (Battery Strength / Battery System), sea de la marca que sea.
  * Logitech (HID++ 2.0): ratones, teclados y cascos por receptor Unifying, Bolt o
    Lightspeed, por cable o por Bluetooth.
  * XInput: mandos de Xbox (y compatibles) con adaptador inalámbrico.
  * Protocolos propios (receptores 2.4 GHz que no siguen el estándar):
      - HyperX Cloud III Wireless (03F0:05B7)
      - Ratón SCYROX con receptor 8K (3554:F5F7) o por cable (3554:F5F6)
      - Mando DualSense de PS5 (054C:0CE6 / 0DF2), USB o Bluetooth
"""
from __future__ import annotations

import ctypes
import re
import time
import uuid
from ctypes import wintypes as wt
from dataclasses import dataclass

import hid

import hid_estandar


@dataclass
class Dispositivo:
    clave: str        # identificador estable
    nombre: str
    tipo: str         # raton | teclado | cascos | auriculares | mando | altavoz | otro
    bateria: int      # 0-100
    cargando: bool = False
    en_reposo: bool = False   # no respondió ahora: se muestra su último valor
    ids: tuple = ()           # ((vid, pid), ...) USB del receptor/dispositivo, para medir su polling rate
    hz: int | None = None     # polling rate (Hz), si se conoce
    hz_exacto: bool = False   # True: lo dijo el propio ratón; False: medido


def tipo_por_nombre(nombre: str) -> str:
    n = nombre.lower()
    reglas = [
        ("mando", ("xbox", "dualsense", "dualshock", "controller", "gamepad", "mando", "joy-con")),
        ("auriculares", ("buds", "airpods", "earbuds", "auricular", "freebuds", "pods")),
        ("cascos", ("headset", "headphone", "cloud", "hyperx", "arctis", "cascos", "wh-")),
        ("altavoz", ("jbl", "speaker", "altavoz", "soundcore", "boom")),
        ("raton", ("mouse", "ratón", "raton", "scyrox", "mx master")),
        ("teclado", ("keyboard", "teclado", "keys")),
    ]
    for tipo, claves in reglas:
        if any(c in n for c in claves):
            return tipo
    return "otro"


# --------------------------------------------------------------------------
# Bluetooth (SetupAPI)
# --------------------------------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class _DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wt.ULONG)]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("ClassGuid", _GUID), ("DevInst", wt.DWORD),
                ("Reserved", ctypes.c_void_p)]


def _clave(guid: str, pid: int) -> _DEVPROPKEY:
    u = uuid.UUID(guid)
    g = _GUID(u.fields[0], u.fields[1], u.fields[2])
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return _DEVPROPKEY(g, pid)


_K_BATERIA = _clave("104EA319-6EE2-4701-BD47-8DDBF425BBE5", 2)
_K_CONECTADO = _clave("83DA6326-97A6-4088-9453-A1923F573B29", 15)
_K_NOMBRE = _clave("A45C254E-DF1C-4EFD-8020-67D146A850E0", 14)   # FriendlyName
_K_DESC = _clave("A45C254E-DF1C-4EFD-8020-67D146A850E0", 2)      # DeviceDesc

_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
_setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wt.LPCWSTR, wt.HWND, wt.DWORD]
_setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_SP_DEVINFO_DATA)]
_setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_SP_DEVINFO_DATA),
                                                   wt.LPWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD)]
_setupapi.SetupDiGetDevicePropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_SP_DEVINFO_DATA),
                                                ctypes.POINTER(_DEVPROPKEY), ctypes.POINTER(wt.ULONG),
                                                ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

_DIGCF_PRESENT, _DIGCF_ALLCLASSES = 0x2, 0x4
_RE_MAC = re.compile(r"(?:DEV_|&)([0-9A-F]{12})(?:\\|_C0|$)", re.I)


def _prop(hdi, dd, key: _DEVPROPKEY, tam: int = 512):
    buf = ctypes.create_string_buffer(tam)
    tipo = wt.ULONG()
    req = wt.DWORD()
    if not _setupapi.SetupDiGetDevicePropertyW(hdi, ctypes.byref(dd), ctypes.byref(key),
                                               ctypes.byref(tipo), buf, tam, ctypes.byref(req), 0):
        return None
    if tipo.value == 0x12:                      # DEVPROP_TYPE_STRING
        return ctypes.wstring_at(buf)
    if tipo.value in (0x03, 0x11):              # BYTE / BOOLEAN
        return buf.raw[0]
    return None


def leer_bluetooth() -> list[Dispositivo]:
    return _bluetooth()[0]


def leer_bluetooth_desconectados() -> list[Dispositivo]:
    """Emparejados pero desconectados: Windows conserva su último nivel de batería."""
    return _bluetooth()[1]


def _bluetooth() -> tuple[list[Dispositivo], list[Dispositivo]]:
    hdi = _setupapi.SetupDiGetClassDevsW(None, None, None, _DIGCF_PRESENT | _DIGCF_ALLCLASSES)
    if not hdi or hdi == ctypes.c_void_p(-1).value:
        return [], []
    baterias: dict[str, int] = {}               # MAC -> %
    padres: dict[str, tuple[str, bool]] = {}    # MAC -> (nombre, conectado)
    try:
        i = 0
        dd = _SP_DEVINFO_DATA(cbSize=ctypes.sizeof(_SP_DEVINFO_DATA))
        idbuf = ctypes.create_unicode_buffer(512)
        while _setupapi.SetupDiEnumDeviceInfo(hdi, i, ctypes.byref(dd)):
            i += 1
            if not _setupapi.SetupDiGetDeviceInstanceIdW(hdi, ctypes.byref(dd), idbuf, 512, None):
                continue
            iid = idbuf.value.upper()
            if not iid.startswith(("BTHENUM\\", "BTHLE\\")):
                continue
            m = _RE_MAC.search(iid)
            if not m:
                continue
            mac = m.group(1)
            bat = _prop(hdi, dd, _K_BATERIA)
            if bat is not None:
                baterias[mac] = max(baterias.get(mac, 0), bat)
            if iid.startswith(("BTHENUM\\DEV_", "BTHLE\\DEV_")):
                nombre = _prop(hdi, dd, _K_NOMBRE) or _prop(hdi, dd, _K_DESC) or mac
                conectado = bool(_prop(hdi, dd, _K_CONECTADO))
                antes = padres.get(mac)
                padres[mac] = (nombre, conectado or (antes[1] if antes else False))
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdi)

    on, off = [], []
    for mac, bat in baterias.items():
        nombre, conectado = padres.get(mac, (mac, False))
        (on if conectado else off).append(Dispositivo(f"bt:{mac}", nombre, tipo_por_nombre(nombre), int(bat)))
    return on, off


# --------------------------------------------------------------------------
# HID
# --------------------------------------------------------------------------
def _abrir(vid: int, pid: int, usage_page: int, usage: int | None = None):
    for d in hid.enumerate(vid, pid):
        if d["usage_page"] == usage_page and (usage is None or d["usage"] == usage):
            h = hid.device()
            h.open_path(d["path"])
            return h
    return None


def _leer_respuesta(h, prefijo: list[int], intentos: int = 6, ms: int = 250):
    for _ in range(intentos):
        r = h.read(64, ms)
        if r and r[:len(prefijo)] == prefijo:
            return r
    return None


def leer_hyperx_cloud3() -> list[Dispositivo]:
    """Respuesta a 66 89: [66 89 VV VV PP ...] -> VV = mV (big endian), PP = %."""
    h = _abrir(0x03F0, 0x05B7, 0xFF13)
    if not h:
        return []
    try:
        h.write(bytes([0x66, 0x89] + [0] * 60))
        r = _leer_respuesta(h, [0x66, 0x89])
        if not r:
            return []
        voltaje, nivel = (r[2] << 8) | r[3], r[4]
        if voltaje == 0 and nivel == 0:          # cascos apagados
            return []
        h.write(bytes([0x66, 0x8A] + [0] * 60))
        c = _leer_respuesta(h, [0x66, 0x8A])
        cargando = bool(c and c[2] in (1, 2))
        # Con el cable de carga conectado aparece un dispositivo extra 03F0:06B7
        cargando = cargando or bool(hid.enumerate(0x03F0, 0x06B7))
        return [Dispositivo("hyperx-cloud3", "HyperX Cloud III Wireless", "cascos", min(nivel, 100), cargando)]
    finally:
        h.close()


def _trama_scyrox(cmd: int) -> bytes:
    datos = [cmd] + [0] * 14
    return bytes([0x08] + datos + [(0x55 - sum(datos) - 0x08) & 0xFF])


def leer_scyrox() -> list[Dispositivo]:
    """Protocolo Compx: tramas de 17 bytes, report id 0x08. cmd 3 = en línea, cmd 4 = batería."""
    for pid, por_cable in ((0xF5F7, False), (0xF5F6, True)):
        h = _abrir(0x3554, pid, 0xFF02, 0x02)
        if not h:
            continue
        try:
            if not por_cable:
                en_linea = False
                for _ in range(2):               # reintento: al despertar puede no contestar
                    h.write(_trama_scyrox(3))
                    r = _leer_respuesta(h, [0x08, 0x03])
                    if r and r[6] == 1:
                        en_linea = True
                        break
                if not en_linea:                 # ratón apagado / fuera de alcance
                    continue
            h.write(_trama_scyrox(4))
            r = _leer_respuesta(h, [0x08, 0x04])
            if not r:
                continue
            return [Dispositivo("scyrox", "Ratón SCYROX", "raton", min(r[6], 100), por_cable or r[7] == 1,
                                ids=((0x3554, 0xF5F7), (0x3554, 0xF5F6)))]
        finally:
            h.close()
    return []


def leer_dualsense() -> list[Dispositivo]:
    res = []
    for d in hid.enumerate(0x054C):
        if d["product_id"] not in (0x0CE6, 0x0DF2) or d["usage_page"] != 0x01 or d["usage"] != 0x05:
            continue
        h = hid.device()
        h.open_path(d["path"])
        try:
            byte = None
            for intento in range(2):
                for _ in range(15):
                    r = h.read(100, 100)
                    if not r:
                        continue
                    if r[0] == 0x31 and len(r) > 54:      # Bluetooth, modo completo
                        byte = r[54]
                    elif r[0] == 0x01 and len(r) > 53:    # USB
                        byte = r[53]
                    if byte is not None:
                        break
                if byte is not None or intento:
                    break
                # Por Bluetooth arranca en modo simple: pedir el report 0x05 lo pasa a modo completo
                try:
                    h.get_feature_report(0x05, 41)
                except OSError:
                    pass
            if byte is None:
                continue
            estado = byte >> 4                   # 0 descargando, 1 cargando, 2 lleno
            nivel = 100 if estado == 2 else min((byte & 0x0F) * 10 + 5, 100)
            res.append(Dispositivo(f"dualsense:{d['serial_number'] or len(res)}", "DualSense",
                                   "mando", nivel, estado in (1, 2)))
        finally:
            h.close()
    return res


# --------------------------------------------------------------------------
# Estándar HID (cualquier marca)
# --------------------------------------------------------------------------
# Dispositivos que ya tienen un lector propio (no se leen dos veces)
_PROPIOS = {(0x03F0, 0x05B7), (0x3554, 0xF5F7), (0x3554, 0xF5F6), (0x054C, 0x0CE6), (0x054C, 0x0DF2)}
_sin_bateria: set[bytes] = set()     # colecciones cuyo descriptor no declara batería (no cambia)


def _tipo_por_colecciones(colecciones: set[tuple[int, int]], nombre: str) -> str:
    tipo = tipo_por_nombre(nombre)
    if tipo != "otro":
        return tipo
    if (0x01, 0x02) in colecciones:
        return "raton"
    if (0x01, 0x06) in colecciones:
        return "teclado"
    if (0x01, 0x04) in colecciones or (0x01, 0x05) in colecciones:
        return "mando"
    if any(p == 0x0B for p, _ in colecciones):     # telefonía: cascos con micro
        return "cascos"
    return "otro"


def leer_hid_estandar() -> list[Dispositivo]:
    por_disp: dict[tuple, list[dict]] = {}
    for d in hid.enumerate():
        if (d["vendor_id"], d["product_id"]) in _PROPIOS or d["vendor_id"] == 0x046D:
            continue
        por_disp.setdefault((d["vendor_id"], d["product_id"], d["serial_number"]), []).append(d)
    res = []
    for (vid, pid, serie), cols in por_disp.items():
        for d in cols:
            if d["path"] in _sin_bateria:
                continue
            ruta = d["path"].decode(errors="replace")
            if not hid_estandar.tiene_bateria(ruta):
                _sin_bateria.add(d["path"])
                continue
            lec = hid_estandar.leer(ruta)
            if not lec:
                continue
            nombre = (d["product_string"] or lec.producto or f"Dispositivo {vid:04X}:{pid:04X}").strip()
            tipo = _tipo_por_colecciones({(c["usage_page"], c["usage"]) for c in cols}, nombre)
            res.append(Dispositivo(f"hid:{vid:04x}{pid:04x}:{serie or ''}", nombre, tipo, lec.bateria,
                                   lec.cargando, ids=((vid, pid),)))
            break
    return res


# --------------------------------------------------------------------------
# Logitech HID++ 2.0
# --------------------------------------------------------------------------
_LOGI_RECEPTORES = {0xC52B, 0xC52F, 0xC532, 0xC534, 0xC539, 0xC53A, 0xC53D, 0xC53F, 0xC541, 0xC545,
                    0xC547, 0xC548, 0xC54D}
_LOGI_SW = 0x0B          # identificador de software (cualquiera 1-15)
_LOGI_TIPOS = {0: "teclado", 2: "teclado", 3: "raton", 4: "raton", 5: "raton", 8: "cascos", 11: "mando",
               12: "mando"}
# curva de descarga típica de una celda Li-ion (mV, %), para los que sólo informan voltaje
_CURVA_LIION = ((4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50), (3778, 40),
                (3751, 30), (3717, 20), (3671, 10), (3500, 0))


def _logi_pedir(h, idx: int, indice: int, funcion: int, params: bytes = b"", espera: float = 0.4):
    msg = bytes([0x11, idx, indice, (funcion << 4) | _LOGI_SW]) + params
    h.write(msg + bytes(20 - len(msg)))
    fin = time.monotonic() + espera
    while time.monotonic() < fin:
        r = h.read(20, 60)
        if not r or r[0] not in (0x10, 0x11) or r[1] != idx:
            continue
        if r[2] in (0x8F, 0xFF) and r[3] == indice:            # error (HID++ 1.0 / 2.0)
            return None
        if r[2] == indice and r[3] == (funcion << 4) | _LOGI_SW:
            return bytes(r[4:])
    return None


def _logi_indice(h, idx: int, feature: int) -> int:
    r = _logi_pedir(h, idx, 0x00, 0, bytes([feature >> 8, feature & 0xFF]))
    return r[0] if r else 0


def _logi_mv_a_pct(mv: int) -> int:
    for (v1, p1), (v2, p2) in zip(_CURVA_LIION, _CURVA_LIION[1:]):
        if mv >= v2:
            return round(p2 + (p1 - p2) * min(1, (mv - v2) / (v1 - v2)))
    return 0


def _logi_bateria(h, idx: int) -> tuple[int, bool, bool] | None:
    """(nivel %, cargando, viene_del_voltaje)."""
    f = _logi_indice(h, idx, 0x1004)                       # Unified Battery
    if f:
        r = _logi_pedir(h, idx, f, 1)
        if r:
            nivel = r[0]
            if not nivel:                                   # sólo informa por niveles
                nivel = {1: 5, 2: 20, 4: 60, 8: 100}.get(r[1] & 0x0F, 0)
            return nivel, r[2] in (1, 2, 3), False
    f = _logi_indice(h, idx, 0x1000)                       # Battery Level Status
    if f:
        r = _logi_pedir(h, idx, f, 0)
        if r:
            return r[0], r[2] in (1, 2, 3), False
    f = _logi_indice(h, idx, 0x1001)                       # Battery Voltage
    if f:
        r = _logi_pedir(h, idx, f, 0)
        if r:
            return _logi_mv_a_pct((r[0] << 8) | r[1]), bool(r[2] & 0x80), True
    return None


_LOGI_HZ_EXT = (125, 250, 500, 1000, 2000, 4000, 8000)     # índices de 0x8061 (8 ms … 125 µs)


def _logi_hz(h, idx: int) -> int | None:
    """Polling rate que tiene configurado el ratón (solo se consulta; nunca se cambia)."""
    f = _logi_indice(h, idx, 0x8061)                       # Extended Adjustable Report Rate (2K/4K/8K)
    if f:
        r = _logi_pedir(h, idx, f, 2)                      # getReportRate -> índice
        if r and r[0] < len(_LOGI_HZ_EXT):
            return _LOGI_HZ_EXT[r[0]]
    f = _logi_indice(h, idx, 0x8060)                       # Adjustable Report Rate
    if f:
        r = _logi_pedir(h, idx, f, 1)                      # getReportRate -> milisegundos
        if r and 1 <= r[0] <= 8:
            return round(1000 / r[0])
    return None


def _logi_nombre_tipo(h, idx: int) -> tuple[str, str]:
    f = _logi_indice(h, idx, 0x0005)                       # Device Name & Type
    if not f:
        return "Logitech", "otro"
    r = _logi_pedir(h, idx, f, 0)
    largo = r[0] if r else 0
    nombre = b""
    while len(nombre) < largo:
        r = _logi_pedir(h, idx, f, 1, bytes([len(nombre)]))
        if not r:
            break
        nombre += r[:largo - len(nombre)]
    r = _logi_pedir(h, idx, f, 2)
    texto = nombre.decode("utf-8", "replace").strip("\x00 ") or "Logitech"
    tipo = _LOGI_TIPOS.get(r[0], "otro") if r else "otro"
    if not texto.lower().startswith("logi"):
        texto = "Logitech " + texto
    return texto, tipo if tipo != "otro" else tipo_por_nombre(texto)


_suave: dict[str, float] = {}


def _suavizar_voltaje(clave: str, crudo: int, cargando: bool) -> int:
    """El porcentaje calculado del voltaje sube y baja unos puntos según el esfuerzo del momento
    (41, 38, 41, 37...). Se suaviza y, mientras no carga, no se deja subir: si no, el cálculo
    del consumo veía "cargas" falsas y caídas rápidas (hasta 3 veces más consumo del real).
    Una subida grande (15 puntos o más) sí cuenta: se cargó estando apagado o desconectado."""
    previo = _suave.get(clave)
    if previo is None or cargando or crudo >= previo + 15:
        _suave[clave] = float(crudo)
    else:
        _suave[clave] = min(previo, previo * 0.75 + crudo * 0.25)
    return round(_suave[clave])


def leer_logitech() -> list[Dispositivo]:
    res: dict[str, Dispositivo] = {}
    for d in hid.enumerate(0x046D):
        if (d["usage_page"], d["usage"]) not in ((0xFF00, 0x0002), (0xFF43, 0x0202)):
            continue
        indices = range(1, 7) if d["product_id"] in _LOGI_RECEPTORES else (0xFF,)
        h = hid.device()
        try:
            h.open_path(d["path"])
        except OSError:
            continue
        try:
            for idx in indices:
                # ping (versión del protocolo): si no contesta, no hay nada conectado en ese hueco
                if not _logi_pedir(h, idx, 0x00, 1, bytes([0, 0, 0x5A]), espera=0.25):
                    continue
                bat = _logi_bateria(h, idx)
                if not bat:
                    continue
                nombre, tipo = _logi_nombre_tipo(h, idx)
                clave = "logi:" + re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-")
                nivel = _suavizar_voltaje(clave, bat[0], bat[1]) if bat[2] else bat[0]
                hz = _logi_hz(h, idx) if tipo == "raton" else None
                res[clave] = Dispositivo(clave, nombre, tipo, max(0, min(100, nivel)), bat[1],
                                         ids=((0x046D, d["product_id"]),), hz=hz, hz_exacto=hz is not None)
        finally:
            h.close()
    return list(res.values())


# --------------------------------------------------------------------------
# XInput (mandos de Xbox y compatibles)
# --------------------------------------------------------------------------
class _XINPUT_BATERIA(ctypes.Structure):
    _fields_ = [("tipo", ctypes.c_ubyte), ("nivel", ctypes.c_ubyte)]


_xinput = None
for _dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        _xinput = ctypes.WinDLL(_dll)
        break
    except OSError:
        pass


def leer_xinput() -> list[Dispositivo]:
    if not _xinput:
        return []
    res = []
    estado = (ctypes.c_ubyte * 16)()
    for usuario in range(4):
        if _xinput.XInputGetState(usuario, estado) != 0:        # no hay mando en ese puesto
            continue
        for tipo_disp, tipo, nombre in ((0, "mando", "Mando Xbox"), (1, "cascos", "Cascos Xbox")):
            b = _XINPUT_BATERIA()
            if _xinput.XInputGetBatteryInformation(usuario, tipo_disp, ctypes.byref(b)) != 0:
                continue
            if b.tipo in (0x00, 0x01, 0xFF):         # desconectado, por cable o desconocido
                continue
            nivel = {0: 5, 1: 35, 2: 70, 3: 100}.get(b.nivel, 0)
            sufijo = f" {usuario + 1}" if usuario else ""
            res.append(Dispositivo(f"xinput:{tipo_disp}:{usuario}", nombre + sufijo, tipo, nivel))
    return res


# Receptores USB propios: si siguen enchufados, el periférico sólo está en reposo (ahorro de
# energía) y se sigue mostrando con su último valor en vez de darlo por apagado.
_RECEPTORES = {"scyrox": ((0x3554, 0xF5F7), (0x3554, 0xF5F6)), "hyperx-cloud3": ((0x03F0, 0x05B7),)}


def receptor_presente(clave: str) -> bool:
    return any(hid.enumerate(v, p) for v, p in _RECEPTORES.get(clave, ()))


ORDEN_TIPOS = ("raton", "teclado", "cascos", "auriculares", "mando", "altavoz", "otro")
LECTORES = [leer_hyperx_cloud3, leer_scyrox, leer_dualsense, leer_logitech, leer_hid_estandar, leer_xinput,
            leer_bluetooth]


def _nombre_norm(n: str) -> str:
    return re.sub(r"[^a-z0-9]", "", n.lower())


def leer_todo(errores: list[str] | None = None) -> list[Dispositivo]:
    res: list[Dispositivo] = []
    for lector in LECTORES:
        try:
            res.extend(lector())
        except Exception as e:  # un lector que falla no tumba a los demás
            if errores is not None:
                errores.append(f"{lector.__name__}: {e!r}")
    # Un mismo aparato puede verse por dos vías (p. ej. Bluetooth y HID): se queda con una.
    bt = [d for d in res if d.clave.startswith("bt:")]
    nombres_bt = {_nombre_norm(d.nombre) for d in bt}
    xbox_bt = any("xbox" in d.nombre.lower() for d in bt)
    res = [d for d in res
           if not (d.clave.startswith(("hid:", "logi:")) and _nombre_norm(d.nombre) in nombres_bt)
           and not (d.clave.startswith("xinput:0:") and xbox_bt)]
    res.sort(key=lambda d: (ORDEN_TIPOS.index(d.tipo), d.nombre))
    return res


if __name__ == "__main__":
    errs: list[str] = []
    for d in leer_todo(errs):
        print(f"{d.nombre:35} {d.tipo:12} {d.bateria:3}% {'(cargando)' if d.cargando else ''}")
    for e in errs:
        print("ERROR", e)
