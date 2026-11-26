"""Informe de diagnóstico para cuando un periférico no aparece o no se lee bien.

Genera un archivo de texto con lo que la app ve en el PC (sin datos personales):
  * versión de la app y de Windows, y cómo está configurada la bandeja;
  * lo que leen ahora los lectores de batería (y sus errores);
  * todos los dispositivos HID: fabricante, producto, VID:PID, colecciones y, para las
    colecciones de fabricante (página 0xFF00 o más), los informes que el propio dispositivo
    devuelve al pedírselos. Eso permite descubrir dónde guarda la batería un periférico nuevo.
    Todo es de SOLO LECTURA: no se envía ninguna orden al dispositivo;
  * los dispositivos Bluetooth con batería (la dirección MAC va recortada);
  * las últimas líneas del registro.
"""
from __future__ import annotations

import ctypes
import os
import platform
import time
import traceback
from ctypes import wintypes as wt

import hid

import apariencia as ap
import dispositivos
import hid_estandar
import rutas

ARCHIVO = os.path.join(rutas.DATOS, "diagnostico.txt")


class _PROCESO(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", wt.WCHAR * 260)]


def procesos_app() -> list[tuple[int, str]]:
    """(PID, ruta) de cada 'Brahttery hub.exe' en marcha: sirve para ver si quedó una copia vieja."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k32.OpenProcess.restype = wt.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESO)]
    k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    foto = k32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    res = []
    e = _PROCESO(dwSize=ctypes.sizeof(_PROCESO))
    ok = k32.Process32FirstW(foto, ctypes.byref(e))
    while ok:
        if e.szExeFile.lower() == "brahttery hub.exe":
            ruta = "?"
            h = k32.OpenProcess(0x1000, False, e.th32ProcessID)     # PROCESS_QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(1024)
                n = wt.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                    ruta = buf.value
                k32.CloseHandle(h)
            res.append((e.th32ProcessID, ruta))
        ok = k32.Process32NextW(foto, ctypes.byref(e))
    k32.CloseHandle(foto)
    return res


def _hex(b: bytes, maximo: int = 64) -> str:
    texto = b[:maximo].hex(" ")
    return texto + (" …" if len(b) > maximo else "")


def generar() -> str:
    """Escribe el informe en %APPDATA%\\Brahttery hub\\diagnostico.txt y devuelve su ruta."""
    L: list[str] = []
    w = L.append
    w(f"Brahttery hub {rutas.VERSION} — informe de diagnóstico")
    w(f"Fecha: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    w(f"Windows: {platform.platform()}  ({platform.machine()})")
    w(f"Programa: {'instalado (.exe)' if rutas.CONGELADO else 'código fuente'}")
    cfg = ap.cargar_config()
    w("Bandeja: " + ", ".join(f"{k}={ap.global_(cfg, k)}" for k in
                              ("mostrar_icono", "color_texto", "punto_carga", "estilo_iconos", "umbral_baja")))
    propios = {c: d.get("mostrar") for c, d in cfg.get("dispositivos", {}).items() if d.get("mostrar")}
    if propios:
        w("Modo propio por periférico: " + ", ".join(f"{c}={m}" for c, m in propios.items()))

    w("")
    w("=== Copias de la app en marcha ===")
    try:
        for pid, ruta in procesos_app():
            w(f"  PID {pid}: {ruta}")
        u32 = ctypes.WinDLL("user32")
        u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
        u32.FindWindowW.restype = wt.HWND
        h = u32.FindWindowW(rutas.ID, None)
        if h:
            buf = ctypes.create_unicode_buffer(128)
            u32.GetWindowTextW(h, buf, 128)
            partes = buf.value.split()
            w(f"  Bandeja en marcha: versión {partes[1] if len(partes) > 1 else 'anterior a la 1.4.1'}")
        else:
            w("  Bandeja en marcha: ninguna")
        for viejo in rutas._IDS_ANTIGUOS:
            if u32.FindWindowW(viejo, None):
                w(f"  ATENCIÓN: también hay una bandeja de una versión muy antigua ({viejo})")
    except Exception as e:
        w(f"  ERROR {e!r}")

    w("")
    w("=== Guardado de ajustes y bandeja ===")
    ahora = time.time()
    for nombre, ruta in (("config.json (ajustes)", rutas.RUTA_CONFIG), ("estado.json (lo escribe la bandeja)", rutas.RUTA_ESTADO)):
        try:
            hace = ahora - os.path.getmtime(ruta)
            w(f"  {nombre}: {os.path.getsize(ruta)} bytes, guardado hace {hace:.0f} s")
        except OSError as e:
            w(f"  {nombre}: no se puede leer ({e.strerror})")
    try:
        prueba = os.path.join(rutas.DATOS, "prueba_escritura.tmp")
        with open(prueba, "w", encoding="utf-8") as f:
            f.write("ok")
        os.replace(prueba, prueba + "2")
        os.remove(prueba + "2")
        w("  Escribir en la carpeta de datos: OK")
    except OSError as e:
        w(f"  Escribir en la carpeta de datos: FALLA ({e!r}) <- la bandeja no se enteraría de los cambios")
    fuentes = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    w("  Fuentes para los números: " + ", ".join(
        f"{f} {'sí' if os.path.exists(os.path.join(fuentes, f)) else 'NO'}"
        for f in ("SegUIVar.ttf", "segoeuib.ttf", "segoeui.ttf", "SegoeIcons.ttf", "segmdl2.ttf")))
    try:
        import apariencia as _ap
        d = _ap.ajustes_de(cfg, "prueba", "raton")
        texto = _ap.texto_icono(cfg, d, 55, False, 12.0)
        img = _ap.dibujar_icono("raton", 55, False, d, cfg, 16, False, texto)
        w(f"  Dibujo de prueba de un icono (modo {_ap.modo_icono(cfg, d)}, texto {texto!r}): OK {img.size}")
    except Exception:
        w("  Dibujo de prueba de un icono: FALLA")
        w("    " + traceback.format_exc().strip().replace("\n", "\n    "))

    w("")
    w("=== Lo que lee la app ahora ===")
    errores: list[str] = []
    t = time.perf_counter()
    try:
        leidos = dispositivos.leer_todo(errores)
    except Exception:
        leidos = []
        errores.append(traceback.format_exc())
    w(f"(lectura completa en {1000 * (time.perf_counter() - t):.0f} ms)")
    for d in leidos:
        w(f"  {d.clave:28} {d.nombre:32} tipo={d.tipo:11} batería={d.bateria:3}%  cargando={d.cargando}")
    if not leidos:
        w("  (ningún periférico con batería legible)")
    for e in errores:
        w("  ERROR " + e.strip())

    w("")
    w("=== Cálculo del tiempo restante ===")
    try:
        from estimacion import Estimador, formato_horas
        est = Estimador(cfg.get("autonomia_horas"))
        for d in leidos:
            nominal = est.autonomia_nominal(d.clave, d.tipo)
            horas, medido = est.horas(d.clave, d.tipo, d.bateria, None)
            info = est.disp.get(d.clave, {})
            tramos = info.get("tramos", [])
            ult = tramos[-1] if tramos else []
            perfil = est.perfiles.get(d.clave)
            w(f"  {d.nombre}: {d.bateria}% -> {formato_horas(horas)} ({'medido' if medido else 'estimado'})"
              f" | autonomía oficial/típica {nominal} h")
            w(f"     uso registrado {info.get('uso', 0) / 3600:.1f} h | descargas guardadas {len(tramos)}"
              f" | descarga actual: {len(ult)} puntos"
              + (f", de {ult[0][1]} % a {ult[-1][1]} % en {(ult[-1][2] - ult[0][2]) / 3600:.1f} h de uso" if len(ult) > 1 else ""))
            if perfil:
                w(f"     perfil: {perfil['por_hora']:.2f} %/h en {perfil['horas']:.1f} h de uso ({perfil['descargas']} descargas)")
    except Exception as e:
        w(f"  ERROR {e!r}")

    w("")
    w("=== Dispositivos HID ===")
    por_disp: dict[tuple, list[dict]] = {}
    for d in hid.enumerate():
        por_disp.setdefault((d["vendor_id"], d["product_id"]), []).append(d)
    for (vid, pid), cols in sorted(por_disp.items()):
        d0 = cols[0]
        w(f"- {vid:04X}:{pid:04X}  {d0['manufacturer_string'] or '?'} / {d0['product_string'] or '?'}")
        for c in sorted(cols, key=lambda c: (c["interface_number"], c["usage_page"], c["usage"])):
            ruta = c["path"].decode(errors="replace")
            linea = f"    colección {c['usage_page']:04X}:{c['usage']:04X}  interfaz {c['interface_number']}"
            try:
                if hid_estandar.tiene_bateria(ruta):
                    linea += "  [declara batería estándar]"
            except Exception:
                pass
            w(linea)
            if c["usage_page"] >= 0xFF00:
                try:
                    v = hid_estandar.volcar_informes(ruta)
                    w(f"      largos (entrada, salida, función): {v['largos']}")
                    for tipo in ("funcion", "entrada"):
                        for rid, datos in v[tipo].items():
                            w(f"      {tipo} id {rid}: {_hex(datos)}")
                except Exception as e:
                    w(f"      (no se pudo leer: {e!r})")

    w("")
    w("=== Bluetooth con batería ===")
    try:
        on, off = dispositivos._bluetooth()
        for d, estado in [(x, "conectado") for x in on] + [(x, "desconectado") for x in off]:
            mac = d.clave.split(":", 1)[-1]
            w(f"  {d.nombre:32} {estado:12} batería={d.bateria}%  (…{mac[-4:]})")
        if not on and not off:
            w("  (ninguno)")
    except Exception as e:
        w(f"  ERROR {e!r}")

    w("")
    w("=== Últimas líneas del registro ===")
    try:
        with open(rutas.RUTA_LOG, encoding="utf-8", errors="replace") as f:
            for linea in f.read().splitlines()[-60:]:
                w("  " + linea)
    except OSError:
        w("  (sin registro)")

    with open(ARCHIVO, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return ARCHIVO
