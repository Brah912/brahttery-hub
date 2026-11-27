"""Consumo en vivo del equipo: procesador, GPU, RAM y discos (solo lectura, con APIs de Windows).

- Procesador: GetSystemTimes (uso), contadores "Processor Information" (frecuencia actual) y el
  nombre del registro. La temperatura del procesador Windows no la da sin un driver especial con
  permisos de administrador (lo que usan HWMonitor y similares): solo se muestra si el sensor
  ACPI de la placa da un valor creíble.
- GPU: contadores "GPU Engine" (los del Administrador de tareas). En placas NVIDIA, además,
  nvml.dll (viene con el driver) da temperatura, memoria de video y nombre.
- RAM: GlobalMemoryStatusEx.
- Discos: contador "PhysicalDisk % Idle Time" (actividad), espacio libre por unidad y el modelo
  de cada disco (IOCTL_STORAGE_QUERY_PROPERTY, sin permisos de escritura).
"""
from __future__ import annotations

import ctypes
import os
import string
import time
import winreg
from ctypes import wintypes as wt

_k32 = ctypes.windll.kernel32

NIVELES = (
    (40, "bajo", "Bajo consumo", "Va tranquilo, le sobra capacidad"),
    (75, "normal", "Consumo normal", "Está trabajando, todo en orden"),
    (101, "alto", "Alto consumo", "Está exigido; puede ir más lento"),
)
NIVELES_TEXTO = [n[1:] for n in NIVELES]
COLORES = {"bajo": "#3DBE74", "normal": "#E5B832", "alto": "#F08A3C"}

# La RAM normalmente está bastante llena en Windows (usa lo libre como caché), así que sus topes son otros.
TOPES = {"cpu": (40, 75), "gpu": (40, 75), "ram": (60, 85), "disco": (40, 75)}
# Temperaturas (°C): hasta acá "fresco", hasta acá "templado", más es "caliente".
TOPES_TEMP = {"cpu": (65, 85), "gpu": (65, 80)}
TEXTO_TEMP = {"bajo": "Fresca", "normal": "Templada", "alto": "Caliente"}


def nivel(porcentaje: float, que: str = "cpu") -> tuple[str, str, str]:
    bajo, alto = TOPES.get(que, (40, 75))
    i = 0 if porcentaje < bajo else 1 if porcentaje < alto else 2
    return NIVELES[i][1:]


def nivel_temp(grados: float, que: str) -> tuple[str, str]:
    bajo, alto = TOPES_TEMP.get(que, (65, 85))
    clave = "bajo" if grados < bajo else "normal" if grados < alto else "alto"
    return clave, TEXTO_TEMP[clave]


class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", wt.DWORD), ("hi", wt.DWORD)]


def _ft(f: _FILETIME) -> int:
    return (f.hi << 32) | f.lo


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _PDH_VALOR(ctypes.Structure):
    _fields_ = [("CStatus", wt.DWORD), ("pad", wt.DWORD), ("doubleValue", ctypes.c_double)]


class _PDH_ITEM(ctypes.Structure):
    _fields_ = [("szName", wt.LPWSTR), ("FmtValue", _PDH_VALOR)]


_PDH_FMT = 0x200 | 0x8000        # double, sin tope en 100
_PDH_MORE_DATA = 0x800007D2


class _NvMem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


def nombre_procesador() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())
    except OSError:
        return "Procesador"


def nucleos() -> tuple[int, int]:
    """(núcleos físicos, hilos)."""
    hilos = os.cpu_count() or 0
    try:
        tam = wt.DWORD(0)
        _k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(tam))     # 0 = RelationProcessorCore
        buf = ctypes.create_string_buffer(tam.value)
        if not _k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(tam)):
            return 0, hilos
        n, pos = 0, 0
        while pos < tam.value:
            n += 1
            pos += int.from_bytes(buf.raw[pos + 4:pos + 8], "little")
        return n, hilos
    except (OSError, AttributeError):
        return 0, hilos


def nombre_gpu() -> str:
    """Primera placa de video real (salta las virtuales/remotas)."""
    class DD(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("DeviceName", wt.WCHAR * 32), ("DeviceString", wt.WCHAR * 128),
                    ("StateFlags", wt.DWORD), ("DeviceID", wt.WCHAR * 128), ("DeviceKey", wt.WCHAR * 128)]
    vistos = []
    i = 0
    while True:
        d = DD()
        d.cb = ctypes.sizeof(DD)
        if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
            break
        i += 1
        s = d.DeviceString.strip()
        if s and s not in vistos:
            vistos.append(s)
    reales = [s for s in vistos if not any(x in s.lower() for x in ("virtual", "remote", "basic display",
                                                                       "mirror", "idd"))]
    return (reales or vistos or ["Placa de video"])[0]


def _modelo_disco(numero: int) -> str:
    """Modelo del disco físico N, con IOCTL_STORAGE_QUERY_PROPERTY (abre sin permisos de lectura/escritura)."""
    _k32.CreateFileW.restype = wt.HANDLE
    h = _k32.CreateFileW(f"\\\\.\\PhysicalDrive{numero}", 0, 3, None, 3, 0, None)
    if not h or h == wt.HANDLE(-1).value:
        return ""
    try:
        consulta = (ctypes.c_ubyte * 12)()               # PropertyId=0 (StorageDeviceProperty), QueryType=0
        salida = ctypes.create_string_buffer(1024)
        dev = wt.DWORD(0)
        if not _k32.DeviceIoControl(wt.HANDLE(h), 0x2D1400, consulta, 12, salida, 1024, ctypes.byref(dev), None):
            return ""
        raw = salida.raw

        def cadena(ofs_pos):
            ofs = int.from_bytes(raw[ofs_pos:ofs_pos + 4], "little")
            if not ofs or ofs >= len(raw):
                return ""
            return raw[ofs:raw.index(b"\0", ofs)].decode("ascii", "replace").strip()

        bus = raw[28] if len(raw) > 28 else 0
        modelo = " ".join(x for x in (cadena(12), cadena(16)) if x)      # fabricante + producto
        tipo = {17: "NVMe", 11: "SATA", 7: "USB", 3: "ATA"}.get(bus, "")
        return f"{modelo} ({tipo})" if tipo and modelo else modelo
    finally:
        _k32.CloseHandle(wt.HANDLE(h))


class _Contador:
    """Un contador PDH con comodín; valores() devuelve {instancia: valor}."""

    def __init__(self, pdh, consulta, ruta: str) -> None:
        self.pdh = pdh
        self.h = wt.HANDLE()
        self.ok = pdh.PdhAddEnglishCounterW(consulta, ruta, None, ctypes.byref(self.h)) == 0

    def valores(self) -> dict[str, float]:
        if not self.ok:
            return {}
        tam, cant = wt.DWORD(0), wt.DWORD(0)
        r = self.pdh.PdhGetFormattedCounterArrayW(self.h, _PDH_FMT, ctypes.byref(tam), ctypes.byref(cant), None)
        if (r & 0xFFFFFFFF) != _PDH_MORE_DATA or tam.value == 0:
            return {}
        buf = ctypes.create_string_buffer(tam.value)
        if self.pdh.PdhGetFormattedCounterArrayW(self.h, _PDH_FMT, ctypes.byref(tam), ctypes.byref(cant), buf):
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(_PDH_ITEM))
        out = {}
        for n in range(cant.value):
            it = items[n]
            if it.FmtValue.CStatus in (0, 1):
                out[it.szName or ""] = out.get(it.szName or "", 0.0) + it.FmtValue.doubleValue
        return out


class Medidor:
    """Se crea una vez y se llama a leer() cada segundo."""

    def __init__(self) -> None:
        self._cpu_ant = self._tiempos()
        self.cpu_nombre = nombre_procesador()
        self.cpu_nucleos, self.cpu_hilos = nucleos()
        self.gpu_nombre = nombre_gpu()
        self._pdh = None
        self._consulta = wt.HANDLE()
        self._c = {}
        try:
            pdh = ctypes.windll.pdh
            if pdh.PdhOpenQueryW(None, None, ctypes.byref(self._consulta)) == 0:
                self._pdh = pdh
                for clave, ruta in (("gpu", r"\GPU Engine(*)\Utilization Percentage"),
                                    ("disco", r"\PhysicalDisk(*)\% Idle Time"),
                                    ("rendim", r"\Processor Information(*)\% Processor Performance"),
                                    ("frec", r"\Processor Information(*)\Processor Frequency"),
                                    ("zona", r"\Thermal Zone Information(*)\High Precision Temperature")):
                    self._c[clave] = _Contador(pdh, self._consulta, ruta)
                pdh.PdhCollectQueryData(self._consulta)
        except (OSError, AttributeError):
            self._pdh = None
        # NVIDIA: nvml.dll viene con el driver
        self._nv = None
        self._nv_disp = ctypes.c_void_p()
        try:
            nv = ctypes.CDLL(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvml.dll"))
            if nv.nvmlInit_v2() == 0 and nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self._nv_disp)) == 0:
                self._nv = nv
                nombre = ctypes.create_string_buffer(96)
                if nv.nvmlDeviceGetName(self._nv_disp, nombre, 96) == 0 and nombre.value:
                    self.gpu_nombre = nombre.value.decode("ascii", "replace")
        except (OSError, AttributeError):
            self._nv = None
        self._modelos: dict[int, str] = {}
        self._espacio_t = 0.0
        self._espacio: dict[str, tuple[float, float]] = {}

    @staticmethod
    def _tiempos() -> tuple[int, int, int]:
        i, k, u = _FILETIME(), _FILETIME(), _FILETIME()
        _k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        return _ft(i), _ft(k), _ft(u)

    def _cpu(self) -> float:
        i, k, u = self._tiempos()
        i0, k0, u0 = self._cpu_ant
        self._cpu_ant = (i, k, u)
        total = (k - k0) + (u - u0)          # el tiempo de kernel ya incluye el inactivo
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (total - (i - i0)) / total))

    @staticmethod
    def _ram() -> tuple[float, float, float]:
        m = _MEM()
        m.dwLength = ctypes.sizeof(_MEM)
        _k32.GlobalMemoryStatusEx(ctypes.byref(m))
        return float(m.dwMemoryLoad), (m.ullTotalPhys - m.ullAvailPhys) / 2**30, m.ullTotalPhys / 2**30

    def _gpu(self) -> float | None:
        c = self._c.get("gpu")
        if not c or not c.ok:
            return None
        por_tipo: dict[str, float] = {}
        for nombre, v in c.valores().items():
            tipo = nombre.rsplit("engtype_", 1)[-1] if "engtype_" in nombre else "otro"
            por_tipo[tipo] = por_tipo.get(tipo, 0.0) + v
        return min(100.0, max(por_tipo.values(), default=0.0))

    def _nvidia(self) -> dict:
        if self._nv is None:
            return {}
        out = {}
        t = ctypes.c_uint()
        if self._nv.nvmlDeviceGetTemperature(self._nv_disp, 0, ctypes.byref(t)) == 0:
            out["gpu_temp"] = float(t.value)
        m = _NvMem()
        if self._nv.nvmlDeviceGetMemoryInfo(self._nv_disp, ctypes.byref(m)) == 0 and m.total:
            out["vram_usada"], out["vram_total"] = m.used / 2**30, m.total / 2**30
        return out

    def _cpu_temp(self) -> float | None:
        """Sensor ACPI de la placa: solo si da algo creíble (muchas placas devuelven un número fijo falso)."""
        vals = [v / 10 - 273.15 for v in self._c.get("zona", _Vacio()).valores().values()] if "zona" in self._c else []
        vals = [v for v in vals if 30 <= v <= 110]
        return max(vals) if vals else None

    def _discos(self) -> list[dict]:
        c = self._c.get("disco")
        actividad = c.valores() if c else {}
        if time.monotonic() - self._espacio_t > 30 or not self._espacio:      # el espacio cambia poco
            self._espacio_t = time.monotonic()
            self._espacio = {}
            for letra in string.ascii_uppercase:
                raiz = f"{letra}:\\"
                if _k32.GetDriveTypeW(raiz) != 3:          # solo discos fijos
                    continue
                libre, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
                if _k32.GetDiskFreeSpaceExW(raiz, None, ctypes.byref(total), ctypes.byref(libre)):
                    self._espacio[letra] = (total.value / 1e9, libre.value / 1e9)
        discos = []
        for inst, ocioso in sorted(actividad.items()):
            if inst == "_Total":
                continue
            partes = inst.split()
            try:
                numero = int(partes[0])
            except (ValueError, IndexError):
                continue
            letras = [p[0] for p in partes[1:] if p.endswith(":")]
            if numero not in self._modelos:
                self._modelos[numero] = _modelo_disco(numero) or f"Disco {numero}"
            total = sum(self._espacio.get(l, (0, 0))[0] for l in letras)
            libre = sum(self._espacio.get(l, (0, 0))[1] for l in letras)
            discos.append({"numero": numero, "modelo": self._modelos[numero], "letras": letras,
                           "actividad": max(0.0, min(100.0, 100.0 - ocioso)), "total": total, "libre": libre})
        return discos

    def leer(self) -> dict:
        if self._pdh is not None:
            self._pdh.PdhCollectQueryData(self._consulta)
        ram, usada, total = self._ram()
        frec = None
        f, p = self._c.get("frec"), self._c.get("rendim")
        if f and p and f.ok and p.ok:
            base = f.valores().get("_Total")
            pct = p.valores().get("_Total")
            if base and pct:
                frec = base * pct / 100 / 1000          # GHz reales (con turbo)
        datos = {"cpu": self._cpu(), "cpu_ghz": frec, "cpu_temp": self._cpu_temp(), "gpu": self._gpu(),
                 "ram": ram, "ram_usada": usada, "ram_total": total, "discos": self._discos()}
        datos.update(self._nvidia())
        return datos

    def cerrar(self) -> None:
        if self._pdh is not None:
            self._pdh.PdhCloseQuery(self._consulta)
            self._pdh = None
        if self._nv is not None:
            self._nv.nvmlShutdown()
            self._nv = None


class _Vacio:
    def valores(self) -> dict:
        return {}
