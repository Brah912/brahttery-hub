"""Batería por el estándar HID (sin protocolos de fabricante).

Muchos periféricos declaran su batería en su descriptor HID con usos estándar:
  * Generic Device Controls (0x06) / Battery Strength (0x20)
  * Battery System (0x85) / AbsoluteStateOfCharge (0x65) o RemainingCapacity (0x66)
  * Battery System (0x85) / Charging (0x44)
Este módulo sólo LEE: pide el informe a Windows (HidD_GetFeature / HidD_GetInputReport),
igual que haría el propio sistema. No envía órdenes, no cambia nada del dispositivo y no
instala controladores.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass

_hid = ctypes.WinDLL("hid")
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_k32.CreateFileW.restype = wt.HANDLE
_k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
_hid.HidD_GetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
_hid.HidD_GetInputReport.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
_hid.HidD_GetProductString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]

_INVALIDO = wt.HANDLE(-1).value
_GENERIC_RW = 0x80000000 | 0x40000000
_SHARE_RW = 0x1 | 0x2
_OPEN_EXISTING = 3
_HIDP_OK = 0x00110000
_INPUT, _FEATURE = 0, 2

# (página, uso) que indican nivel de batería, por orden de preferencia
USOS_NIVEL = ((0x85, 0x65), (0x06, 0x20), (0x85, 0x66))
USO_CARGANDO = (0x85, 0x44)


class _CAPS(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT), ("InputReportByteLength", wt.USHORT),
                ("OutputReportByteLength", wt.USHORT), ("FeatureReportByteLength", wt.USHORT),
                ("Reserved", wt.USHORT * 17), ("NumberLinkCollectionNodes", wt.USHORT),
                ("NumberInputButtonCaps", wt.USHORT), ("NumberInputValueCaps", wt.USHORT),
                ("NumberInputDataIndices", wt.USHORT), ("NumberOutputButtonCaps", wt.USHORT),
                ("NumberOutputValueCaps", wt.USHORT), ("NumberOutputDataIndices", wt.USHORT),
                ("NumberFeatureButtonCaps", wt.USHORT), ("NumberFeatureValueCaps", wt.USHORT),
                ("NumberFeatureDataIndices", wt.USHORT)]


class _VALUE_CAPS(ctypes.Structure):   # HIDP_VALUE_CAPS (72 bytes)
    _fields_ = [("UsagePage", wt.USHORT), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                ("BitField", wt.USHORT), ("LinkCollection", wt.USHORT), ("LinkUsage", wt.USHORT),
                ("LinkUsagePage", wt.USHORT), ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte), ("BitSize", wt.USHORT),
                ("ReportCount", wt.USHORT), ("Reserved2", wt.USHORT * 5), ("UnitsExp", wt.ULONG),
                ("Units", wt.ULONG), ("LogicalMin", wt.LONG), ("LogicalMax", wt.LONG),
                ("PhysicalMin", wt.LONG), ("PhysicalMax", wt.LONG), ("UsageMin", wt.USHORT),
                ("UsageMax", wt.USHORT), ("_resto", wt.USHORT * 6)]


assert ctypes.sizeof(_VALUE_CAPS) == 72

_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_CAPS)]
_hid.HidP_GetCaps.restype = wt.LONG
_hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.POINTER(_VALUE_CAPS), ctypes.POINTER(wt.USHORT),
                                   ctypes.c_void_p]
_hid.HidP_GetValueCaps.restype = wt.LONG
_hid.HidP_GetUsageValue.argtypes = [ctypes.c_int, wt.USHORT, wt.USHORT, wt.USHORT, ctypes.POINTER(wt.ULONG),
                                    ctypes.c_void_p, ctypes.c_void_p, wt.ULONG]
_hid.HidP_GetUsageValue.restype = wt.LONG


@dataclass
class LecturaHID:
    bateria: int
    cargando: bool
    producto: str


def _abrir(ruta: str):
    for acceso in (_GENERIC_RW, 0):     # teclados y ratones de sistema sólo se abren sin acceso
        h = _k32.CreateFileW(ruta, acceso, _SHARE_RW, None, _OPEN_EXISTING, 0, None)
        if h and h != _INVALIDO:
            return h
    return None


def _usos_bateria(pp, caps: _CAPS) -> list[tuple[int, _VALUE_CAPS]]:
    res = []
    for tipo, n in ((_FEATURE, caps.NumberFeatureValueCaps), (_INPUT, caps.NumberInputValueCaps)):
        if not n:
            continue
        arr = (_VALUE_CAPS * n)()
        cnt = wt.USHORT(n)
        if _hid.HidP_GetValueCaps(tipo, arr, ctypes.byref(cnt), pp) != _HIDP_OK:
            continue
        for v in arr[:cnt.value]:
            for pagina, uso in USOS_NIVEL + (USO_CARGANDO,):
                if v.UsagePage == pagina and (v.UsageMin <= uso <= v.UsageMax if v.IsRange else v.UsageMin == uso):
                    res.append((tipo, v))
    return res


def tiene_bateria(ruta: str) -> bool:
    """¿El descriptor de esta colección declara un uso de batería? (sin leer nada del dispositivo)"""
    h = _abrir(ruta)
    if not h:
        return False
    pp = ctypes.c_void_p()
    try:
        if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            return False
        caps = _CAPS()
        if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) != _HIDP_OK:
            return False
        return any(_uso(v) in USOS_NIVEL for _, v in _usos_bateria(pp, caps))
    finally:
        if pp:
            _hid.HidD_FreePreparsedData(pp)
        _k32.CloseHandle(h)


def _uso(v: _VALUE_CAPS) -> tuple[int, int]:
    for p, u in USOS_NIVEL + (USO_CARGANDO,):
        if v.UsagePage == p and (v.UsageMin <= u <= v.UsageMax if v.IsRange else v.UsageMin == u):
            return p, u
    return v.UsagePage, v.UsageMin


def leer(ruta: str) -> LecturaHID | None:
    """Nivel de batería declarado por el descriptor estándar de esa colección HID, o None."""
    h = _abrir(ruta)
    if not h:
        return None
    pp = ctypes.c_void_p()
    try:
        if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            return None
        caps = _CAPS()
        if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) != _HIDP_OK:
            return None
        usos = _usos_bateria(pp, caps)
        if not any(_uso(v) in USOS_NIVEL for _, v in usos):
            return None
        informes: dict[tuple[int, int], ctypes.Array | None] = {}

        def informe(tipo: int, rid: int):
            if (tipo, rid) not in informes:
                largo = caps.FeatureReportByteLength if tipo == _FEATURE else caps.InputReportByteLength
                buf = ctypes.create_string_buffer(max(largo, 2))
                buf[0] = rid
                f = _hid.HidD_GetFeature if tipo == _FEATURE else _hid.HidD_GetInputReport
                informes[(tipo, rid)] = buf if f(h, buf, len(buf)) else None
            return informes[(tipo, rid)]

        nivel, cargando = None, False
        for preferido in USOS_NIVEL + (USO_CARGANDO,):
            for tipo, v in usos:
                if _uso(v) != preferido or (preferido in USOS_NIVEL and nivel is not None):
                    continue
                buf = informe(tipo, v.ReportID)
                if buf is None:
                    continue
                val = wt.ULONG()
                if _hid.HidP_GetUsageValue(tipo, preferido[0], v.LinkCollection, preferido[1], ctypes.byref(val),
                                           pp, buf, len(buf)) != _HIDP_OK:
                    continue
                if preferido == USO_CARGANDO:
                    cargando = bool(val.value)
                    continue
                lo, hi = v.LogicalMin, v.LogicalMax
                if hi <= lo:                       # rango sin declarar: se asume 0-100
                    lo, hi = 0, 100
                bruto = int(val.value)
                if bruto < lo or bruto > hi:       # fuera de rango = "desconocido"
                    continue
                nivel = round(100 * (bruto - lo) / (hi - lo))
        if nivel is None:
            return None
        texto = ctypes.create_unicode_buffer(128)
        producto = texto.value if _hid.HidD_GetProductString(h, texto, ctypes.sizeof(texto)) else ""
        return LecturaHID(max(0, min(100, nivel)), cargando, producto)
    finally:
        if pp:
            _hid.HidD_FreePreparsedData(pp)
        _k32.CloseHandle(h)


# --------------------------------------------------------------------------
# Diagnóstico: volcado de informes (solo lectura) para estudiar periféricos no compatibles
# --------------------------------------------------------------------------
_hid.HidP_GetButtonCaps.argtypes = [ctypes.c_int, ctypes.POINTER(_VALUE_CAPS), ctypes.POINTER(wt.USHORT),
                                    ctypes.c_void_p]
_hid.HidP_GetButtonCaps.restype = wt.LONG


def volcar_informes(ruta: str, max_informes: int = 8) -> dict:
    """Pide a Windows los informes de entrada y de función ("feature") que declara la colección,
    sin enviar nada al dispositivo (HidD_GetInputReport / HidD_GetFeature son lecturas).
    Devuelve {"largos": (entrada, salida, función), "funcion": {id: bytes}, "entrada": {id: bytes}}."""
    h = _abrir(ruta)
    res = {"largos": (0, 0, 0), "funcion": {}, "entrada": {}}
    if not h:
        return res
    pp = ctypes.c_void_p()
    try:
        if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            return res
        caps = _CAPS()
        if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) != _HIDP_OK:
            return res
        res["largos"] = (caps.InputReportByteLength, caps.OutputReportByteLength, caps.FeatureReportByteLength)
        for tipo, clave, largo, nv, nb, leer_informe in (
                (_FEATURE, "funcion", caps.FeatureReportByteLength, caps.NumberFeatureValueCaps,
                 caps.NumberFeatureButtonCaps, _hid.HidD_GetFeature),
                (_INPUT, "entrada", caps.InputReportByteLength, caps.NumberInputValueCaps,
                 caps.NumberInputButtonCaps, _hid.HidD_GetInputReport)):
            if not largo:
                continue
            ids = set()
            for n, f in ((nv, _hid.HidP_GetValueCaps), (nb, _hid.HidP_GetButtonCaps)):
                if n:
                    arr = (_VALUE_CAPS * n)()
                    cnt = wt.USHORT(n)
                    if f(tipo, arr, ctypes.byref(cnt), pp) == _HIDP_OK:
                        ids.update(v.ReportID for v in arr[:cnt.value])
            for rid in sorted(ids or {0})[:max_informes]:
                buf = ctypes.create_string_buffer(largo)
                buf[0] = rid
                if leer_informe(h, buf, largo):
                    res[clave][rid] = buf.raw
        return res
    finally:
        if pp:
            _hid.HidD_FreePreparsedData(pp)
        _k32.CloseHandle(h)
