"""Brahttery hub: ventana para personalizar los periféricos.

  * Temas de la interfaz: Claro, Gris y Oscuro (General -> Interfaz).
  * Estilo de los iconos: Realista o Minimalista, para todos o por periférico.
  * Diseños por modelo: varios ratones, teclados, cascos, auriculares, mandos y altavoces.
  * Arriba, los periféricos encendidos; abajo, los apagados (difuminados, también editables).
  * Los cambios se guardan al momento en config.json y la bandeja los aplica sola.
"""
from __future__ import annotations

import ctypes
import os
import queue
import re
import sys
import threading
import time
from ctypes import wintypes as wt
import tkinter
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import actualizador  # noqa: E402
import apariencia as ap  # noqa: E402
import modelos  # noqa: E402
from selector_color import Muestra, SelectorColor, circulo, circulo_auto, rueda  # noqa: E402
import rutas  # noqa: E402
from estimacion import AUTONOMIA_NOMINAL, MODELOS_CONOCIDOS, Estimador, formato_horas  # noqa: E402

TITULO = rutas.NOMBRE
_WIN = os.environ.get("WINDIR", r"C:\Windows")

# ------------------------------------------------------------------ temas
TEMAS = {
    "oscuro": dict(
        MODO="dark", CLARO=False, FONDO="#0c0c0e", LINEA="#2a2a31", BORDE="#26262c", BORDE_HOVER="#4a4a55",
        BORDE_OFF="#1a1a1f", HOVER_OFF="#34343b", SUPERFICIE="#16161a", SUPERFICIE_HOVER="#1f1f25",
        PILL_OFF="#121215", PISTA="#1c1c21", PISTA_OFF="#2c2c32", TEXTO="#f2f2f4", SECUNDARIO="#9a9aa3",
        APAGADO="#55555c", ACENTO="#4CC2FF", ACENTO_HOVER="#8fd8ff", MARCA="#FFFFFF", ICONO_NAV="#C8C8D0",
        PELIGRO_HOVER="#2a1517", PELIGRO_BORDE="#4a2226", PELIGRO_TEXTO="#ff8a8f"),
    "gris": dict(
        MODO="dark", CLARO=False, FONDO="#2b2d31", LINEA="#3d3f45", BORDE="#45474e", BORDE_HOVER="#6a6c75",
        BORDE_OFF="#383a40", HOVER_OFF="#4c4e55", SUPERFICIE="#35373c", SUPERFICIE_HOVER="#3f4147",
        PILL_OFF="#313338", PISTA="#3a3c42", PISTA_OFF="#45474d", TEXTO="#f2f3f5", SECUNDARIO="#b5bac1",
        APAGADO="#7c7f87", ACENTO="#4CC2FF", ACENTO_HOVER="#8fd8ff", MARCA="#FFFFFF", ICONO_NAV="#d0d3d8",
        PELIGRO_HOVER="#3d2a2c", PELIGRO_BORDE="#6b3a3e", PELIGRO_TEXTO="#ff9aa0"),
    "claro": dict(
        MODO="light", CLARO=True, FONDO="#f7f7f9", LINEA="#e2e2e8", BORDE="#dcdce3", BORDE_HOVER="#a9a9b5",
        BORDE_OFF="#e6e6eb", HOVER_OFF="#c9c9d1", SUPERFICIE="#ececf0", SUPERFICIE_HOVER="#e2e2e8",
        PILL_OFF="#f0f0f3", PISTA="#e4e4ea", PISTA_OFF="#dcdce2", TEXTO="#1b1b1f", SECUNDARIO="#5d5d68",
        APAGADO="#a9a9b2", ACENTO="#0067C0", ACENTO_HOVER="#1a7fd4", MARCA="#1b1b1f", ICONO_NAV="#45454f",
        PELIGRO_HOVER="#fbe9ea", PELIGRO_BORDE="#f0b8bc", PELIGRO_TEXTO="#c42b1c"),
}
NOMBRES_TEMA = {"claro": "Claro", "gris": "Gris", "oscuro": "Oscuro"}
P: dict = {}


# --------------------------------------------- botones laterales del ratón (sin gancho global)
_user32 = ctypes.WinDLL("user32")
_user32.GetAncestor.restype = wt.HWND
_user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
_user32.WindowFromPoint.restype = wt.HWND
_user32.WindowFromPoint.argtypes = [wt.POINT]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def texto_sobre_acento() -> str:
    """Texto legible sobre un botón del color de acento (claro: acento oscuro, texto blanco)."""
    return "#ffffff" if P["CLARO"] else "#0c0c0e"


ICONO_POR_TEMA = {"oscuro": "brahttery_hub_oscuro", "gris": "brahttery_hub_gris", "claro": "brahttery_hub"}
LUZ_POR_TEMA = {"oscuro": (76, 194, 255), "gris": (67, 211, 120), "claro": (220, 20, 40)}   # color de las letras


def icono_tema() -> str:
    """Oscuro: BrH azul sobre negro. Gris: BrH verde sobre gris. Claro: BrH rojo sobre blanco."""
    return ICONO_POR_TEMA.get(P.get("NOMBRE"), "brahttery_hub")


def aplicar_tema(nombre: str) -> None:
    P.clear()
    P.update(TEMAS.get(nombre, TEMAS["oscuro"]))
    P["NOMBRE"] = nombre if nombre in TEMAS else "oscuro"
    ctk.set_appearance_mode(P["MODO"])


NOMBRES_TIPO = {"raton": "Ratón", "teclado": "Teclado", "cascos": "Cascos", "auriculares": "Auriculares",
                "mando": "Mando", "altavoz": "Altavoz", "otro": "Periférico"}
COLORES = ["#FFFFFF", "#000000", "#4CC2FF", "#0078D4", "#6CCB5F", "#FFB900", "#FF8C00",
           "#E74856", "#E3008C", "#8764B8", "#00B7C3", "#A0A0A0"]
COLORES_BAJA = ["#E74856", "#FF8C00", "#FFB900", "#E3008C"]
ESTILOS = {"general": "Como en General", "realista": "Realista", "minimalista": "Minimalista"}
ACABADOS = {"grafito": "Grafito", "blanco": "Blanco"}
MODOS = {"icono": "Solo icono", "porcentaje": "Porcentaje", "tiempo": "Tiempo restante"}
MODOS_DISP = {"general": "Como en General", **MODOS}
TEXTO_COLOR_INFO = "Color de porcentaje/hora restante"
MINUTOS_OCULTA = 10       # la ventana oculta se cierra (y libera ~80 MB) tras estos minutos

# Ficha técnica de cada tipo de periférico: (clave, etiqueta, ejemplo, unidad si se escribe solo el número).
# La completa cada uno a mano; el orden de RESUMEN_FICHA decide qué se ve abreviado en la tarjeta.
_MODELO = ("modelo", "Modelo", "SCYROX V8", "")
_CONEXION = ("conexion", "Conexión", "2,4 GHz · Bluetooth · USB-C", "")
_BATERIA = ("bateria", "Batería", "300 mAh", "mAh")
_PESO = ("peso", "Peso", "36 g", "g")
CAMPOS_FICHA = {
    "raton": [_MODELO, ("sensor", "Sensor", "PixArt PAW3950", ""), ("dpi", "DPI máximo", "30000", "DPI"),
              ("sondeo", "Frecuencia de sondeo", "8000 Hz", "Hz"), _PESO, ("switches", "Switches", "Omron ópticos", ""),
              _CONEXION, _BATERIA],
    "teclado": [_MODELO, ("formato", "Formato", "75 %", ""), ("switches", "Switches", "Gateron Yellow", ""),
                ("sondeo", "Frecuencia de sondeo", "1000 Hz", "Hz"), _CONEXION, _BATERIA, _PESO],
    "cascos": [_MODELO, ("drivers", "Drivers", "53 mm", "mm"), ("respuesta", "Respuesta de frecuencia", "10–21 000 Hz", ""),
               ("microfono", "Micrófono", "Desmontable, cancelación de ruido", ""), _CONEXION, _BATERIA, _PESO],
    "auriculares": [_MODELO, ("drivers", "Drivers", "12,4 mm", "mm"), ("anc", "Cancelación de ruido", "Sí, hasta 49 dB", ""),
                    ("estuche", "Batería del estuche", "Hasta 36 h en total", ""),
                    ("agua", "Resistencia al agua", "IP54", ""), _CONEXION, _BATERIA],
    "mando": [_MODELO, _CONEXION, _BATERIA, ("extras", "Extras", "Gatillos hápticos, giroscopio", ""), _PESO],
    "altavoz": [_MODELO, ("potencia", "Potencia", "20 W", "W"), ("agua", "Resistencia al agua", "IP67", ""),
                _CONEXION, _BATERIA, _PESO],
    "otro": [_MODELO, _CONEXION, _BATERIA, _PESO],
}
RESUMEN_FICHA = {"raton": ("sensor", "dpi", "sondeo", "peso"), "teclado": ("formato", "switches", "sondeo"),
                 "cascos": ("drivers", "conexion", "peso"), "auriculares": ("anc", "drivers", "agua"),
                 "mando": ("conexion", "extras"), "altavoz": ("potencia", "agua", "conexion"),
                 "otro": ("conexion", "bateria")}


def _con_unidad(valor: str, unidad: str) -> str:
    """'30000' -> '30 000 DPI'; si ya trae texto, se deja como lo escribió el usuario."""
    v = valor.strip()
    if unidad and re.fullmatch(r"\d+([.,]\d+)?", v):
        n = v.replace(",", ".")
        if "." not in n and len(n) > 4:
            v = f"{int(n):,}".replace(",", " ")
        return f"{v} {unidad}"
    return v


def resumen_ficha(tipo: str, ficha: dict, largo: int = 40) -> str:
    """Línea corta para la tarjeta: 'PAW3950 · 30 000 DPI · 8000 Hz · 36 g'."""
    campos = {c[0]: c for c in CAMPOS_FICHA.get(tipo, CAMPOS_FICHA["otro"])}
    partes = []
    for clave in RESUMEN_FICHA.get(tipo, ()) + ("modelo",):
        v = (ficha or {}).get(clave, "").strip()
        if v and clave in campos:
            partes.append(_con_unidad(v, campos[clave][3]))
        if len(partes) == 4:
            break
    texto = " · ".join(partes)
    return texto if len(texto) <= largo else texto[:largo - 1].rstrip(" ·") + "…"


def fuente(tam: int, peso: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI Semibold" if peso == "bold" else "Segoe UI", size=tam)


def _pil_fuente(tam: int, negrita: bool = False):
    try:
        return ImageFont.truetype(os.path.join(_WIN, "Fonts", "seguisb.ttf" if negrita else "segoeui.ttf"), tam)
    except OSError:
        return ImageFont.load_default()


def _rgb(h: str) -> tuple:
    return ap.hex_a_rgba(h)[:3]


def color_bateria(nivel: int, umbral: int) -> str:
    if nivel <= umbral:
        return "#E74856"
    if nivel <= 40:
        return "#FFB900"
    return P["ACENTO"]


def hace(t: float | None) -> str:
    if not t:
        return "sin datos"
    s = time.time() - t
    if s < 60:
        return "hace un momento"
    if s < 3600:
        return f"hace {int(s // 60)} min"
    if s < 86400:
        return f"hace {int(s // 3600)} h"
    return f"hace {int(s // 86400)} d"


def autonomia_defecto(clave: str, tipo: str, cfg: dict) -> float:
    extra = cfg.get("autonomia_horas", {})
    for k in (clave, clave.split(":")[0], tipo):
        if k in extra:
            return extra[k]
        if k in AUTONOMIA_NOMINAL:
            return AUTONOMIA_NOMINAL[k]
        if k == clave:                                  # modelos con autonomía oficial conocida
            for fragmento, horas in MODELOS_CONOCIDOS:
                if fragmento in clave.lower():
                    return horas
    return AUTONOMIA_NOMINAL["otro"]


inicio_activado = rutas.inicio_activado
poner_inicio = rutas.poner_inicio


# ------------------------------------------------------- miniaturas de opciones
def miniatura_tema(nombre: str, k: int = 2) -> Image.Image:
    t = TEMAS[nombre]
    w, h = 150 * k, 92 * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=10 * k, fill=_rgb(t["FONDO"]) + (255,),
                        outline=_rgb(t["BORDE"]) + (255,), width=k)
    d.line((0, 16 * k, w, 16 * k), fill=_rgb(t["LINEA"]), width=k)
    d.line((38 * k, 16 * k, 38 * k, h - 2 * k), fill=_rgb(t["LINEA"]), width=k)
    for i in range(3):
        d.rounded_rectangle((7 * k, (24 + i * 10) * k, 31 * k, (28 + i * 10) * k), radius=2 * k,
                            fill=_rgb(t["SUPERFICIE"] if i else t["SECUNDARIO"]))
    for i in range(3):
        x0 = (46 + i * 34) * k
        d.rounded_rectangle((x0, 24 * k, x0 + 28 * k, 52 * k), radius=5 * k, outline=_rgb(t["BORDE_HOVER"]),
                            width=k)
        d.rounded_rectangle((x0 + 5 * k, 44 * k, x0 + 22 * k, 46 * k), radius=k, fill=_rgb(t["ACENTO"]))
        d.rounded_rectangle((x0, 58 * k, x0 + 28 * k, 84 * k), radius=5 * k, outline=_rgb(t["BORDE_OFF"]),
                            width=k)
    return img


def miniatura_estilo(estilo: str, claro: bool, k: int = 2) -> Image.Image:
    w, h = 150 * k, 92 * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fondo = (238, 238, 241) if claro else (28, 28, 32)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=10 * k, fill=fondo + (255,))
    trazo = (27, 27, 31, 255) if claro else (255, 255, 255, 255)
    for i, mid in enumerate(("raton_gaming", "cascos_gaming", "mando_asimetrico")):
        color = ap.ACENTO_REALISTA if estilo == "realista" else trazo
        ic = modelos.dibujar(mid, estilo, 42 * k * 4, color).resize((42 * k, 42 * k), Image.LANCZOS)
        img.alpha_composite(ic, ((8 + i * 46) * k, 25 * k))
    return img


def miniatura_modo(modo: str, claro: bool, cfg: dict, k: int = 2) -> Image.Image:
    """Una barra de tareas en miniatura con tres iconos en ese modo (icono / % / tiempo)."""
    w, h = 150 * k, 92 * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=10 * k, fill=((238, 238, 241) if claro else (28, 28, 32)) + (255,))
    c = dict(cfg, mostrar_icono=modo)
    for i, (tipo, nivel, horas) in enumerate((("raton", 55, 33), ("cascos", 80, 96), ("mando", 12, 0.6))):
        a = ap.ajustes_de(cfg, "", tipo)
        texto = ap.texto_icono(c, dict(a, mostrar=modo), nivel, False, horas)
        ic = ap.dibujar_icono(tipo, nivel, False, a, c, 40 * k, claro, texto)
        img.alpha_composite(ic, ((9 + i * 46) * k, 26 * k))
    return img


LOGO_LIENZO = 54          # px: sitio para el logo (30 px) + cuando crece + su luz


def fotogramas_logo(logo: Image.Image, pasos: int = 7) -> list[Image.Image]:
    """Fotogramas del logo de la barra superior: de normal (30 px, sin luz) a destacado
    (35 px con una luz difuminada del color de sus letras). Se dibujan al doble para pantallas
    con escala."""
    k = 2
    L = LOGO_LIENZO * k
    color = LUZ_POR_TEMA.get(P.get("NOMBRE"), LUZ_POR_TEMA["claro"])
    res = []
    for i in range(pasos):
        t = i / (pasos - 1)
        t = t * t * (3 - 2 * t)                         # suave al empezar y al terminar
        lado = round((30 + 5 * t) * k)
        pieza = logo.resize((lado, lado), Image.LANCZOS)
        img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        pos = ((L - lado) // 2, (L - lado) // 2)
        if t > 0:
            sombra = Image.new("L", (L, L), 0)
            sombra.paste(pieza.getchannel("A"), pos)
            sombra = sombra.filter(ImageFilter.GaussianBlur(4 * k))
            luz = Image.new("RGBA", (L, L), color + (0,))
            luz.putalpha(sombra.point(lambda a, t=t: min(255, int(a * 1.6 * t))))
            img.alpha_composite(luz)
        img.alpha_composite(pieza, pos)
        res.append(img)
    return res


def _bloques(w, limite: int = 60) -> list:
    """Divide un árbol de controles en bloques que se pueden destruir por separado: cada bloque es
    un control con todo lo que tiene dentro. Solo se parten los contenedores grandes, y nunca las
    piezas internas de customtkinter (su lienzo de dibujo): sin su lienzo, un botón falla."""
    # Se recorre el árbol una sola vez (cada winfo_children es una llamada a Tk: contar el
    # subárbol en cada nivel costaba miles de llamadas).
    hijos_de, orden, pila = {}, [], [w]
    while pila:
        x = pila.pop()
        orden.append(x)
        hijos_de[x] = x.winfo_children()
        pila.extend(hijos_de[x])
    tam = {}
    for x in reversed(orden):
        tam[x] = 1 + sum(tam[h] for h in hijos_de[x])

    def partir(x) -> list:
        hijos = [h for h in hijos_de[x] if isinstance(h, ctk.CTkBaseClass) or type(h) is tkinter.Canvas]
        if tam[x] <= limite or not hijos:
            return [x]
        res = []
        for h in hijos:
            res.extend(partir(h))
        return res + [x]                            # el contenedor, al final
    return partir(w)


def _ruta_foto_tema(nombre: str) -> str:
    """Foto de General en un tema, para el fundido instantáneo (lleva la versión: si la ventana
    cambia en una actualización, se descarta sola)."""
    return os.path.join(rutas.DATOS, f"tema_{nombre}_{rutas.VERSION}.png")


def capturar_ventana(root):
    """Foto del contenido de la ventana (PIL) aunque otra ventana la tape: PrintWindow con
    PW_RENDERFULLCONTENT, unos 10 ms. None si no se puede."""
    try:
        from PIL import Image
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        u.GetParent.restype = wt.HWND
        u.GetParent.argtypes = [wt.HWND]
        u.PrintWindow.argtypes = [wt.HWND, ctypes.c_void_p, wt.UINT]
        u.GetDC.restype = ctypes.c_void_p
        u.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
        g.CreateCompatibleDC.restype = g.CreateCompatibleBitmap.restype = g.SelectObject.restype = ctypes.c_void_p
        g.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        g.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        g.GetBitmapBits.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
        g.DeleteObject.argtypes = g.DeleteDC.argtypes = [ctypes.c_void_p]
        root.update_idletasks()
        hwnd = u.GetParent(root.winfo_id())
        r = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        W, H = r.right - r.left, r.bottom - r.top
        sdc = u.GetDC(None)
        mdc = g.CreateCompatibleDC(sdc)
        bmp = g.CreateCompatibleBitmap(sdc, W, H)
        g.SelectObject(mdc, bmp)
        ok = u.PrintWindow(hwnd, mdc, 2)
        buf = ctypes.create_string_buffer(W * H * 4)
        g.GetBitmapBits(bmp, W * H * 4, buf)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(None, sdc)
        if not ok:
            return None
        img = Image.frombuffer("RGBA", (W, H), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")
        x0, y0 = root.winfo_rootx() - r.left, root.winfo_rooty() - r.top
        return img.crop((x0, y0, x0 + root.winfo_width(), y0 + root.winfo_height()))
    except Exception:
        return None


def rueda_rapida(cont) -> None:
    """customtkinter desplaza 1 píxel por unidad (unos 20 px por cada paso de la rueda):
    se sentía lento. Con 3 son unos 60 px por paso."""
    try:
        cont._parent_canvas.configure(yscrollincrement=3)
    except Exception:
        pass


def _mezcla(c1: str, c2: str, t: float) -> str:
    """Color entre c1 y c2 (t = 0 -> c1, 1 -> c2), para atenuar opciones desactivadas."""
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ====================================================================== App
class App(ctk.CTk):
    def __init__(self) -> None:
        self.cfg = ap.cargar_config()
        self.cfg.setdefault("dispositivos", {})
        aplicar_tema(ap.global_(self.cfg, "tema_app"))
        super().__init__(fg_color=P["FONDO"])
        self.title(TITULO)
        self.geometry("1120x780")
        self.minsize(860, 600)
        self._poner_icono()
        self.after(300, self._poner_icono)     # customtkinter pone el suyo al arrancar
        self._aplicar_opacidad(ap.global_(self.cfg, "opacidad_app"))

        self.est = Estimador(self.cfg.get("autonomia_horas"))
        self.estado = ap.cargar_estado()
        self._firma_estado = None
        self._guardado = None
        self.vista = ""
        self.sel: str | None = None
        self._columnas = 0
        # historial de navegación (como un navegador): (vista, argumento)
        self._atras: list[tuple] = []
        self._adelante: list[tuple] = []
        self._actual: tuple | None = None
        self._navegando = False
        self._paginas: dict[str, ctk.CTkFrame] = {}     # páginas ya construidas (se muestran/ocultan)
        self._sucias: set[str] = set()                   # páginas que hay que reconstruir
        self._cargando_editor = False
        self._oculta = False                             # cerrada = oculta en segundo plano
        self._grupos_swatch = []
        # actualizaciones: estado compartido entre el hilo de descarga y la interfaz
        self._act = {"estado": "inicial", "novedad": None, "bajado": 0, "total": 0, "error": "", "ruta": "",
                     "historial": None, "auto": False, "comprobado": 0.0}
        self._cola_act: queue.Queue = queue.Queue()
        self._construir()
        self.ver_perifericos()
        self._atajos_navegacion()
        self._crear_eventos()
        self.after(3000, self._vigilar_estado)
        self.after(700, self._precargar)
        self.after(1500, lambda: self.buscar_actualizacion(auto=True))   # al abrir: se actualiza sola

    def _precargar(self) -> None:
        """Construye (ocultas) las páginas que faltan, una por turno, para que la primera visita sea
        instantánea. Si el usuario ya entró en una, esa se salta."""
        for clave, construir in (("general", self._construir_general), ("editor", self._construir_editor),
                                 ("actualizaciones", self._construir_actualizaciones),
                                 ("acerca", self._construir_acerca)):
            if clave not in self._paginas:
                construir()
                self.after(150, self._precargar)
                return

    # ------------------------------------------------------------ navegación
    def _atajos_navegacion(self) -> None:
        """Botones laterales del ratón (Atrás / Adelante), Alt+← y Alt+→."""
        self.bind_all("<Alt-Left>", self.atras, add="+")
        self.bind_all("<Alt-Right>", self.adelante, add="+")
        # Tk 8.6 en Windows no entrega los botones laterales del ratón. Antes se leían con un gancho
        # global de Windows (WH_MOUSE_LL): cada movimiento del ratón de TODO el PC pasaba por esta
        # app, y mientras estaba ocupada (al abrirse, por ejemplo) el puntero iba a tirones en todo
        # Windows. Ahora se mira el estado de esos dos botones cada 25 ms, y solo mientras la
        # ventana está a la vista y el puntero encima: no afecta a nada más del sistema.
        self._xbotones = {0x05: False, 0x06: False}      # VK_XBUTTON1 (Atrás), VK_XBUTTON2 (Adelante)
        self._hwnd_raiz = 0
        self.after(25, self._revisar_boton)

    def _sobre_mi(self) -> bool:
        punto = wt.POINT()
        if not _user32.GetCursorPos(ctypes.byref(punto)):
            return False
        debajo = _user32.WindowFromPoint(punto)
        return bool(debajo) and bool(self._hwnd_raiz) and _user32.GetAncestor(debajo, 2) == self._hwnd_raiz

    def _revisar_boton(self) -> None:
        try:
            if not self._hwnd_raiz:
                self._hwnd_raiz = _user32.GetAncestor(self.winfo_id(), 2)    # GA_ROOT
            if self._oculta:
                self.after(400, self._revisar_boton)
                return
            encima = self._sobre_mi()
            for vk, antes in self._xbotones.items():
                pulsado = bool(_user32.GetAsyncKeyState(vk) & 0x8000)
                self._xbotones[vk] = pulsado
                if antes and not pulsado and encima:     # al soltarlo, como un clic normal
                    (self.atras if vk == 0x05 else self.adelante)()
            self.after(25 if encima else 120, self._revisar_boton)
        except Exception:
            try:
                self.after(250, self._revisar_boton)
            except Exception:
                pass

    def _registrar(self, destino: tuple) -> None:
        if not self._navegando and destino != self._actual:
            if self._actual is not None:
                self._atras.append(self._actual)
                del self._atras[:-50]
            self._adelante.clear()
        self._actual = destino
        self._pintar_nav()

    def _abrir(self, destino: tuple) -> None:
        vista, arg = destino
        self._navegando = True
        try:
            if vista == "editor":
                if arg in self.estado.get("conocidos", {}) or arg in self.cfg["dispositivos"]:
                    self.ver_editor(arg)
                else:
                    self.ver_perifericos()
            else:
                {"perifericos": self.ver_perifericos, "general": self.ver_general,
                 "actualizaciones": self.ver_actualizaciones,
                 "acerca": self.ver_acerca}.get(vista, self.ver_perifericos)()
        finally:
            self._navegando = False

    def atras(self, _e=None):
        if self._atras:
            self._adelante.append(self._actual)
            self._abrir(self._atras.pop())
        return "break"

    def adelante(self, _e=None):
        if self._adelante:
            self._atras.append(self._actual)
            self._abrir(self._adelante.pop())
        return "break"

    def _pintar_nav(self) -> None:
        for boton, hay in ((getattr(self, "b_atras", None), self._atras),
                           (getattr(self, "b_adelante", None), self._adelante)):
            try:
                boton.configure(state="normal" if hay else "disabled",
                                text_color=P["TEXTO"] if hay else P["APAGADO"])
            except Exception:
                pass

    # ------------------------------------------------------------ estructura
    def _construir(self) -> None:
        self._grupos_swatch = []
        self.configure(fg_color=P["FONDO"])
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._barra_superior()
        ctk.CTkFrame(self, height=1, fg_color=P["LINEA"], corner_radius=0).grid(row=1, column=0, columnspan=3,
                                                                                 sticky="ew")
        self._lateral()
        ctk.CTkFrame(self, width=1, fg_color=P["LINEA"], corner_radius=0).grid(row=2, column=1, sticky="ns")
        self.principal = ctk.CTkFrame(self, fg_color=P["FONDO"], corner_radius=0)
        self.principal.grid(row=2, column=2, sticky="nsew")

    def cambiar_tema(self, nombre: str) -> None:
        """Transición suave entre temas.

        Se pone encima una foto de la ventana tal como se ve. Si ya se tiene una foto de cómo queda
        General en el tema elegido (se guarda la primera vez que se usa), el fundido entre las dos
        empieza al instante y la ventana se rehace después, debajo de una imagen que ya es igual al
        resultado. Si no, se rehace debajo de la foto de antes y después se funde."""
        if self.__dict__.get("_cambiando_tema"):
            return
        self._cambiando_tema = True
        self.cfg["tema_app"] = nombre
        self._programar_guardado()
        final = max(40, min(100, int(ap.global_(self.cfg, "opacidad_app")))) / 100
        antes = capturar_ventana(self)
        cubierta = self._cubrir_con_foto(antes, final)
        destino = self._foto_tema(nombre)
        if cubierta is not None and antes is not None and destino is not None and destino.size == antes.size:
            self._fundir_fotos(cubierta, antes, destino,
                               lambda: self.after(10, self._rehacer_con_tema, nombre, final, cubierta, True))
        else:
            self.after(15, self._rehacer_con_tema, nombre, final, cubierta, False)

    def _cubrir_con_foto(self, foto, alfa: float):
        """Ventana sin bordes justo encima de esta, con una foto. None si no se puede."""
        if foto is None:
            return None
        try:
            from PIL import ImageTk
            x, y = self.winfo_rootx(), self.winfo_rooty()
            cubierta = tkinter.Toplevel(self)
            cubierta.overrideredirect(True)
            cubierta.geometry(f"{foto.width}x{foto.height}+{x}+{y}")
            cubierta.attributes("-alpha", alfa)
            cubierta.attributes("-topmost", True)
            cubierta._foto = ImageTk.PhotoImage(foto, master=cubierta)
            cubierta._etiqueta = tkinter.Label(cubierta, image=cubierta._foto, bd=0, highlightthickness=0)
            cubierta._etiqueta.pack()
            cubierta.update()
            return cubierta
        except Exception:
            return None

    def _fundir_fotos(self, cubierta, a, b, al_terminar, pasos: int = 8) -> None:
        """Fundido de la foto a a la foto b dentro de la cubierta (unos 0,2 s)."""
        from PIL import Image, ImageTk
        # a la mitad de tamaño para que cada paso sea rápido; el último paso, a tamaño completo
        a2, b2 = a.resize((a.width // 2, a.height // 2)), b.resize((b.width // 2, b.height // 2))

        def paso(i=1):
            try:
                t = i / pasos
                t = t * t * (3 - 2 * t)
                img = b if i == pasos else Image.blend(a2, b2, t).resize(a.size, Image.BILINEAR)
                cubierta._foto = ImageTk.PhotoImage(img, master=cubierta)
                cubierta._etiqueta.configure(image=cubierta._foto)
                cubierta.update_idletasks()
            except Exception:
                al_terminar()
                return
            if i < pasos:
                self.after(12, paso, i + 1)
            else:
                al_terminar()
        paso()

    def _guardar_foto_tema(self) -> None:
        """Foto de General en el tema actual: hace instantáneo el próximo cambio a este tema."""
        if self.vista != "general" or self._oculta or self.__dict__.get("_cambiando_tema"):
            return
        foto = capturar_ventana(self)
        if foto is not None:
            nombre = P["NOMBRE"]
            self.__dict__.setdefault("_fotos_tema", {})[nombre] = foto
            # también en disco: así el cambio es instantáneo aunque se cierre y se vuelva a abrir la app
            threading.Thread(target=lambda: foto.save(_ruta_foto_tema(nombre)), daemon=True).start()

    def _foto_tema(self, nombre: str):
        fotos = self.__dict__.setdefault("_fotos_tema", {})
        if nombre not in fotos:
            try:
                from PIL import Image
                with Image.open(_ruta_foto_tema(nombre)) as f:
                    fotos[nombre] = f.convert("RGB")
            except OSError:
                return None
        return fotos[nombre]

    def _rehacer_con_tema(self, nombre: str, final: float, cubierta=None, ya_fundida: bool = False) -> None:
        try:
            self._rehacer_con_tema_(nombre, final, cubierta, ya_fundida)
        except Exception:
            # pase lo que pase, la ventana no se queda tapada ni bloqueada
            if cubierta is not None:
                try:
                    cubierta.destroy()
                except Exception:
                    pass
            self._cambiando_tema = False
            raise

    def _rehacer_con_tema_(self, nombre: str, final: float, cubierta=None, ya_fundida: bool = False) -> None:
        # Lo viejo se esconde al instante y se destruye después, de a poco (destruir ~1000
        # controles de golpe congelaba la ventana ~0,7 s). Antes de aplicar el tema se les quita
        # de los avisos de customtkinter: si no, los repintaría con los colores nuevos para nada.
        viejos = [w for w in self.winfo_children() if not isinstance(w, tkinter.Toplevel)]   # no la foto
        todos, pila = [], list(viejos)
        while pila:
            w = pila.pop()
            todos.append(w)
            pila.extend(w.winfo_children())
        for w in viejos:
            w.grid_forget()
        ids = {id(w) for w in todos}
        fuera = lambda cb: id(getattr(cb, "__self__", None)) not in ids      # noqa: E731
        ctk.AppearanceModeTracker.callback_list = [cb for cb in ctk.AppearanceModeTracker.callback_list if fuera(cb)]
        for ventana, lista in ctk.ScalingTracker.window_widgets_dict.items():
            lista[:] = [cb for cb in lista if fuera(cb)]
        bloques = [u for w in viejos for u in _bloques(w)]
        aplicar_tema(nombre)
        self._paginas.clear()
        self._sucias.clear()
        self._grupos_swatch = []
        self._construir()
        self._poner_icono()
        self.ver_general()
        self._pintar_actualizacion()
        self.update_idletasks()
        self.update()

        def terminar():
            self._cambiando_tema = False
            self._destruir_de_a_poco(bloques)          # ya terminó el fundido: ahora sí, lo viejo
            self.after(400, self._guardar_foto_tema)
            self.after(2500, self._precargar)           # las otras páginas, de a una y sin prisa

        if cubierta is None:
            terminar()
            return

        def fundir(i=1):
            # Si ya se fundió con la foto del tema nuevo, debajo hay lo mismo: basta un fundido corto.
            pasos = 4 if ya_fundida else 9
            t = i / pasos
            try:
                cubierta.attributes("-alpha", final * (1 - t * t * (3 - 2 * t)))   # suave al empezar y al acabar
            except Exception:
                terminar()
                return
            if i < pasos:
                self.after(20, fundir, i + 1)
            else:
                cubierta.destroy()
                terminar()
        fundir()

    def _destruir_de_a_poco(self, widgets: list, lote: int = 25) -> None:
        """Destruye controles ya ocultos en tandas pequeñas, sin congelar la ventana."""
        def tanda(i=0):
            for w in widgets[i:i + lote]:
                try:
                    if w.winfo_exists():
                        w.destroy()
                except Exception:
                    pass
            if i + lote < len(widgets):
                self.after(30, tanda, i + lote)
        self.after(250, tanda)

    def _aplicar_opacidad(self, porcentaje) -> None:
        try:
            self.attributes("-alpha", max(40, min(100, int(porcentaje))) / 100)
        except Exception:
            pass

    def _poner_icono(self) -> None:
        """Icono de la ventana y de la barra de tareas según el tema.

        iconbitmap solo cambia el icono pequeño (barra de título); la barra de tareas
        usa el grande, que sin iconphoto se queda con la pluma de Tk.
        """
        nombre = icono_tema()
        try:
            self.iconbitmap(default=rutas.recurso(nombre + ".ico"))
        except Exception:
            pass
        try:
            from PIL import ImageTk
            grande = Image.open(rutas.recurso(nombre + ".png")).convert("RGBA")
            self._fotos_icono = [ImageTk.PhotoImage(grande.resize((t, t), Image.LANCZOS), master=self)
                                 for t in (256, 64, 48, 32, 16)]
            self.wm_iconphoto(True, *self._fotos_icono)
        except Exception:
            pass

    def _barra_superior(self) -> None:
        barra = ctk.CTkFrame(self, fg_color=P["FONDO"], corner_radius=0, height=64)
        barra.grid(row=0, column=0, columnspan=3, sticky="ew")
        barra.grid_propagate(False)
        barra.grid_columnconfigure(2, weight=1)
        try:
            logo = Image.open(rutas.recurso(icono_tema() + ".png")).convert("RGBA")
        except OSError:
            logo = ap.dibujar_icono("otro", 100, False, {"icono": "glifo:E83F", "color": P["ACENTO"], "tenir": True},
                                    {"tamano_icono": 92}, 56, False)
        # Logo: al pasar el ratón crece un poco y se enciende una luz del color de sus letras
        # (azul en el tema oscuro, roja en claro y gris). Animación de pocos fotogramas precalculados.
        self._fotos_logo = [ctk.CTkImage(f, size=(LOGO_LIENZO, LOGO_LIENZO)) for f in fotogramas_logo(logo)]
        l_logo = ctk.CTkLabel(barra, text="", image=self._fotos_logo[0])
        l_logo.grid(row=0, column=0, padx=(22 - (LOGO_LIENZO - 30) // 2, max(0, 10 - (LOGO_LIENZO - 30) // 2)),
                    pady=(64 - LOGO_LIENZO) // 2)
        estado = {"paso": 0, "meta": 0, "tarea": None}

        def animar():
            estado["tarea"] = None
            if estado["paso"] == estado["meta"]:
                return
            estado["paso"] += 1 if estado["meta"] > estado["paso"] else -1
            try:
                l_logo.configure(image=self._fotos_logo[estado["paso"]])
            except Exception:
                return
            estado["tarea"] = self.after(16, animar)

        def hacia(meta):
            estado["meta"] = meta
            if estado["tarea"] is None:
                animar()

        l_logo.bind("<Enter>", lambda e: hacia(len(self._fotos_logo) - 1))
        l_logo.bind("<Leave>", lambda e: hacia(0))
        ctk.CTkLabel(barra, text=rutas.NOMBRE, font=fuente(17, "bold"),
                     text_color=P["TEXTO"]).grid(row=0, column=1, sticky="w")
        nav = ctk.CTkFrame(barra, fg_color="transparent")
        nav.grid(row=0, column=2, sticky="w", padx=(24, 0))
        estilo = dict(width=34, height=32, corner_radius=10, font=fuente(18), fg_color="transparent",
                      hover_color=P["SUPERFICIE_HOVER"], text_color_disabled=P["APAGADO"])
        self.b_atras = ctk.CTkButton(nav, text="‹", command=self.atras, **estilo)
        self.b_atras.pack(side="left")
        self.b_adelante = ctk.CTkButton(nav, text="›", command=self.adelante, **estilo)
        self.b_adelante.pack(side="left", padx=(2, 0))
        self.l_actualizado = ctk.CTkLabel(barra, text="", font=fuente(12), text_color=P["SECUNDARIO"])
        self.l_actualizado.grid(row=0, column=4, padx=22)
        self._texto_actualizado()
        self._pintar_nav()

    def _lateral(self) -> None:
        lat = ctk.CTkFrame(self, fg_color=P["FONDO"], corner_radius=0, width=220)
        lat.grid(row=2, column=0, sticky="ns")
        lat.grid_propagate(False)
        lat.grid_rowconfigure(10, weight=1)
        self.nav: dict[str, ctk.CTkButton] = {}
        for fila, (clave, texto, glifo, cmd) in enumerate([
            ("perifericos", "Periféricos", "E772", self.ver_perifericos),
            ("general", "General", "E713", self.ver_general),
            ("actualizaciones", "Actualizaciones", "E895", self.ver_actualizaciones),
            ("acerca", "Acerca de", "E946", self.ver_acerca),
        ]):
            self.nav[clave] = self._boton_nav(lat, texto, glifo, cmd)
            self.nav[clave].grid(row=fila * 2, column=0, padx=12, pady=(16 if fila == 0 else 4, 0), sticky="ew")
        # "!" sobre el botón cuando hay una versión nueva (con el color de acento del tema)
        self.aviso_act = ctk.CTkLabel(self.nav["actualizaciones"], text="!", width=22, height=22, corner_radius=11,
                                      fg_color=P["ACENTO"], text_color=texto_sobre_acento(),
                                      font=fuente(13, "bold"))
        self.aviso_act.bind("<Button-1>", lambda e: self.ver_actualizaciones())
        # barra de descarga debajo de "Actualizaciones" (sólo mientras se actualiza)
        self.f_descarga_lat = ctk.CTkFrame(lat, fg_color="transparent")
        self.pb_lat = ctk.CTkProgressBar(self.f_descarga_lat, height=5, corner_radius=3, width=150,
                                         progress_color=P["ACENTO"], fg_color=P["PISTA"])
        self.pb_lat.set(0)
        self.pb_lat.pack(side="left", padx=(14, 8))
        self.l_lat = ctk.CTkLabel(self.f_descarga_lat, text="", font=fuente(11), text_color=P["SECUNDARIO"])
        self.l_lat.pack(side="left")
        # Minimizar: la ventana se oculta y la app sigue en segundo plano (igual que la X)
        self._boton_nav(lat, "Minimizar", "E921", self.ocultar).grid(row=11, column=0, padx=12, pady=(0, 4),
                                                                     sticky="ew")
        # Cerrar: termina la app del todo (iconos de la bandeja incluidos)
        cerrar = self._boton_nav(lat, "Cerrar", "E711", self.salir_del_todo)
        cerrar.configure(hover_color=P["PELIGRO_HOVER"])
        cerrar.grid(row=12, column=0, padx=12, pady=(0, 16), sticky="ew")

    def _boton_nav(self, padre, texto: str, glifo: str, cmd) -> ctk.CTkButton:
        img = ap.dibujar_icono("otro", 100, False, {"icono": "glifo:" + glifo, "color": P["ICONO_NAV"],
                                                    "tenir": True}, {"tamano_icono": 80}, 40, False)
        return ctk.CTkButton(padre, text="  " + texto, image=ctk.CTkImage(img, size=(18, 18)), anchor="w",
                             width=196, height=42, corner_radius=10, font=fuente(14),
                             fg_color="transparent", hover_color=P["SUPERFICIE_HOVER"], text_color=P["SECUNDARIO"],
                             command=cmd)

    def _marcar_nav(self, clave: str) -> None:
        for k, b in self.nav.items():
            b.configure(fg_color=P["SUPERFICIE"] if k == clave else "transparent",
                        text_color=P["TEXTO"] if k == clave else P["SECUNDARIO"])

    # ------------------------------------------------------------- páginas
    # Cada página se construye una vez, oculta, y después solo se muestra u oculta: crear y
    # destruir widgets de customtkinter es lo que hacía que cambiar de pestaña fuera lento.
    def _hay_pagina(self, clave: str) -> bool:
        return clave in self._paginas and clave not in self._sucias

    def _nueva_pagina(self, clave: str) -> ctk.CTkFrame:
        vieja = self._paginas.pop(clave, None)
        if vieja is not None:
            self.after(400, vieja.destroy)            # se destruye cuando la nueva ya está delante
        self._sucias.discard(clave)
        pagina = ctk.CTkFrame(self.principal, fg_color=P["FONDO"], corner_radius=0)
        self._paginas[clave] = pagina
        return pagina

    def _mostrar(self, clave: str) -> None:
        # Las páginas se apilan una encima de otra y solo se trae al frente la elegida: así no se
        # recoloca nada al cambiar de pestaña (ocultar y volver a mostrar obliga a redibujar todo).
        pagina = self._paginas[clave]
        if not pagina.winfo_manager():
            pagina.place(x=0, y=0, relwidth=1, relheight=1)
        pagina.lift()

    def _ensuciar(self, *claves: str) -> None:
        self._sucias.update(claves)

    def _scroll(self, padre) -> ctk.CTkScrollableFrame:
        cont = ctk.CTkScrollableFrame(padre, fg_color=P["FONDO"], corner_radius=0,
                                      scrollbar_button_color=P["PISTA"], scrollbar_button_hover_color=P["PISTA_OFF"])
        cont.pack(fill="both", expand=True)
        rueda_rapida(cont)
        return cont

    # ------------------------------------------------------------- datos
    def dispositivos(self) -> tuple[list[str], list[str]]:
        conocidos = self.estado.setdefault("conocidos", {})
        for clave in self.cfg["dispositivos"]:
            conocidos.setdefault(clave, {"nombre": clave, "tipo": "otro", "bateria": 0, "cargando": False})
        conectados = set(self.estado.get("conectados", []))
        orden = list(NOMBRES_TIPO)

        def k(c):
            d = conocidos[c]
            return (orden.index(d.get("tipo")) if d.get("tipo") in orden else 99, d.get("nombre", c))

        todos = sorted(conocidos, key=k)
        return [c for c in todos if c in conectados], [c for c in todos if c not in conectados]

    def dev(self, clave: str) -> dict:
        return self.estado.get("conocidos", {}).get(clave) or {"nombre": clave, "tipo": "otro", "bateria": 0,
                                                              "cargando": False}

    def ajustes(self, clave: str) -> dict:
        return ap.ajustes_de(self.cfg, clave, self.dev(clave).get("tipo", "otro"))

    def encendido(self, clave: str) -> bool:
        return clave in set(self.estado.get("conectados", []))

    def estilo_de(self, a: dict) -> str:
        e = a.get("estilo", "general")
        return e if e in ("realista", "minimalista") else ap.global_(self.cfg, "estilo_iconos")

    def icono(self, clave: str, tam: int, apagado: bool = False) -> ctk.CTkImage:
        d = self.dev(clave)
        img = ap.dibujar_icono(d.get("tipo", "otro"), int(d.get("bateria", 0)),
                               bool(d.get("cargando")) and not apagado, self.ajustes(clave), self.cfg, tam * 2,
                               P["CLARO"])
        if apagado:     # difuminado: gris, transparente y un poco desenfocado
            alfa = img.getchannel("A").point(lambda v: int(v * 0.38))
            img = Image.merge("RGBA", (*[img.convert("L")] * 3, alfa)).filter(ImageFilter.GaussianBlur(tam * 0.035))
        return ctk.CTkImage(img, size=(tam, tam))

    def _texto_actualizado(self) -> None:
        hora = self.estado.get("hora")
        self.l_actualizado.configure(text=f"Última lectura {hace(hora)}" if hora else "Bandeja sin iniciar")

    def _vigilar_estado(self) -> None:
        self.estado = ap.cargar_estado()
        self.est.recargar_si_cambio()
        try:
            self._texto_actualizado()
        except Exception:
            pass
        firma = (tuple(self.estado.get("conectados", [])),
                 tuple((k, v.get("bateria"), v.get("cargando")) for k, v in self.estado.get("conocidos", {}).items()))
        if firma != self._firma_estado:
            primera = self._firma_estado is None
            self._firma_estado = firma
            if not primera:
                self._ensuciar("perifericos")
                if self.vista == "perifericos" and not self._oculta:    # oculta: se rehace al mostrarla
                    self.ver_perifericos()
        self.after(5000, self._vigilar_estado)

    # ============================================ segundo plano (ocultar / mostrar)
    def _crear_eventos(self) -> None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateEventW.restype = ctypes.c_void_p
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
        k32.ResetEvent.argtypes = [ctypes.c_void_p]
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wt.DWORD]
        self._k32 = k32
        self._ev_mostrar = k32.CreateEventW(None, False, False, rutas.EVENTO_MOSTRAR)
        self._ev_salir = k32.CreateEventW(None, False, False, rutas.EVENTO_SALIR)
        k32.ResetEvent(self._ev_salir)       # por si quedó activado de una versión anterior
        self.protocol("WM_DELETE_WINDOW", self.ocultar)
        self.after(150, self._revisar_eventos)

    def _revisar_eventos(self) -> None:
        if self._ev_salir and self._k32.WaitForSingleObject(self._ev_salir, 0) == 0:
            self.destroy()
            return
        if self._ev_mostrar and self._k32.WaitForSingleObject(self._ev_mostrar, 0) == 0:
            self.mostrar()
        self.after(150, self._revisar_eventos)

    def salir_del_todo(self) -> None:
        """Finaliza la app: cierra la bandeja (y sus iconos) y esta ventana. Para volver a
        tenerla hay que abrirla otra vez (o se abre sola al encender el PC)."""
        try:
            actualizador.cerrar_bandeja(espera=3)
        except Exception:
            pass
        self.destroy()

    def ocultar(self) -> None:
        """Cerrar la ventana no termina la app: queda oculta y vuelve al instante con un clic
        en cualquier icono de la bandeja."""
        self._oculta = True
        self.withdraw()
        # Para no ocupar RAM todo el día: si sigue oculta un rato, la ventana se cierra de verdad
        # (la bandeja sigue). El próximo clic en un icono la vuelve a abrir en un par de segundos.
        if self.__dict__.get("_cierre_oculta"):
            self.after_cancel(self._cierre_oculta)
        self._cierre_oculta = None
        if ap.global_(self.cfg, "liberar_memoria"):
            self._cierre_oculta = self.after(int(MINUTOS_OCULTA * 60 * 1000), self._cerrar_si_sigue_oculta)

    def _cerrar_si_sigue_oculta(self) -> None:
        self._cierre_oculta = None
        if self._oculta and self._act["estado"] not in ("descargando", "instalando"):
            if self._guardado:                  # que no se pierda un cambio pendiente de guardar
                self.after_cancel(self._guardado)
                self._guardar()
            self.destroy()

    def mostrar(self) -> None:
        if self.__dict__.get("_cierre_oculta"):
            self.after_cancel(self._cierre_oculta)
            self._cierre_oculta = None
        if self._oculta:
            self._oculta = False
            self.deiconify()
            if self.vista == "perifericos" and "perifericos" in self._sucias:
                self.ver_perifericos()
        if self.state() == "iconic":
            self.deiconify()
        self.lift()
        self._al_abrir_actualizaciones()
        self.attributes("-topmost", True)            # traerla delante de todo y soltarla
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # ====================================================== vista: periféricos
    def ver_perifericos(self) -> None:
        self._registrar(("perifericos", None))
        self.vista = "perifericos"
        self._marcar_nav("perifericos")
        if self._hay_pagina("perifericos"):
            self._mostrar("perifericos")
            return
        cont = self._scroll(self._nueva_pagina("perifericos"))
        self.cont = cont
        encendidos, apagados = self.dispositivos()
        self._secciones = []
        for titulo, claves, on in (("Encendidos", encendidos, True), ("Apagados", apagados, False)):
            cab = ctk.CTkFrame(cont, fg_color="transparent")
            cab.pack(fill="x", padx=28, pady=(26 if on else 34, 12))
            ctk.CTkLabel(cab, text=titulo, font=fuente(18, "bold"),
                         text_color=P["TEXTO"] if on else P["SECUNDARIO"]).pack(side="left")
            ctk.CTkLabel(cab, text=f" {len(claves)} ", font=fuente(12), fg_color=P["SUPERFICIE"], corner_radius=8,
                         text_color=P["SECUNDARIO"]).pack(side="left", padx=10)
            rejilla = ctk.CTkFrame(cont, fg_color="transparent")
            rejilla.pack(fill="x", padx=20)
            if not claves:
                ctk.CTkLabel(rejilla, text="Ningún periférico encendido ahora mismo." if on else
                             "No hay periféricos apagados.", font=fuente(13), text_color=P["APAGADO"]
                             ).grid(row=0, column=0, padx=8, sticky="w")
            tarjetas = [self._tarjeta(rejilla, c, on) for c in claves]
            self._secciones.append((rejilla, tarjetas))
        self._columnas = 0
        cont.bind("<Configure>", lambda e: self._recolocar())
        self._recolocar(max(1, (self.principal.winfo_width() - 40) // 272))
        self._mostrar("perifericos")

    def _recolocar(self, cols: int | None = None) -> None:
        if self.vista != "perifericos":
            return
        if cols is None:
            cols = max(1, (self.cont.winfo_width() - 40) // 272)
        if cols == self._columnas:
            return
        self._columnas = cols
        for rejilla, tarjetas in self._secciones:
            for i, t in enumerate(tarjetas):
                t.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="nw")

    def _tarjeta(self, padre, clave: str, on: bool) -> ctk.CTkFrame:
        d = self.dev(clave)
        a = self.ajustes(clave)
        umbral = int(ap.global_(self.cfg, "umbral_baja"))
        nivel = int(d.get("bateria", 0))
        cargando = bool(d.get("cargando")) and on
        c_texto = P["TEXTO"] if on else P["APAGADO"]
        c_sec = P["SECUNDARIO"] if on else P["APAGADO"]

        t = ctk.CTkFrame(padre, width=256, height=262, corner_radius=18, fg_color="transparent",
                         border_width=1, border_color=P["BORDE"] if on else P["BORDE_OFF"])
        t.grid_propagate(False)
        t.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(t, text="", image=self.icono(clave, 50, apagado=not on)).grid(
            row=0, column=0, padx=(18, 0), pady=(18, 0), sticky="w")
        estado = "Cargando" if cargando else ("Encendido" if on else "Apagado")
        ctk.CTkLabel(t, text=f"  {estado}  ", font=fuente(11), corner_radius=8, height=22,
                     fg_color=P["SUPERFICIE"] if on else P["PILL_OFF"], text_color=c_sec
                     ).grid(row=0, column=1, padx=16, pady=(20, 0), sticky="ne")
        etiquetas = (["Oculto"] if a["oculto"] else []) + (["Modificado"] if a.get("notas") else [])
        for i, texto in enumerate(etiquetas):       # debajo del estado: oculto / con notas de modificaciones
            ctk.CTkLabel(t, text=f"  {texto}  ", font=fuente(11), corner_radius=8, height=22,
                         fg_color=P["PILL_OFF"], text_color=P["APAGADO"] if texto == "Oculto" else c_sec
                         ).grid(row=0, column=1, padx=16, pady=(48 + 28 * i, 0), sticky="ne")

        nombre = a["nombre"] or d.get("nombre", clave)
        ctk.CTkLabel(t, text=nombre, font=fuente(14, "bold"), text_color=c_texto, anchor="w",
                     wraplength=220).grid(row=1, column=0, columnspan=2, padx=20, pady=(12, 0), sticky="w")
        tipo_txt = NOMBRES_TIPO.get(d.get("tipo"), "Periférico")
        resumen = resumen_ficha(d.get("tipo", "otro"), a.get("ficha") or {}, largo=62)
        ctk.CTkLabel(t, text=tipo_txt + (f"  ·  {resumen}" if resumen else ""), font=fuente(12), text_color=c_sec,
                     anchor="w", justify="left", wraplength=216).grid(row=2, column=0, columnspan=2, padx=20,
                                                                      sticky="w")

        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.grid(row=3, column=0, columnspan=2, padx=20, pady=(8, 0), sticky="ew")
        ctk.CTkLabel(fila, text=f"{nivel}", font=fuente(30, "bold"), text_color=c_texto).pack(side="left")
        ctk.CTkLabel(fila, text=" %", font=fuente(15), text_color=c_sec).pack(side="left", pady=(10, 0))

        barra = ctk.CTkProgressBar(t, height=5, corner_radius=3, fg_color=P["PISTA"],
                                   progress_color=color_bateria(nivel, umbral) if on else P["PISTA_OFF"])
        barra.set(max(0.0, min(1.0, nivel / 100)))
        barra.grid(row=4, column=0, columnspan=2, padx=20, pady=(6, 0), sticky="ew")

        if not on:
            pie = (f"Último valor · {hace(d.get('visto'))}" if d.get("visto")
                   else "Último valor guardado por Windows")
        elif cargando:
            pie = "Cargando"
        else:
            horas, medido = self.est.horas(clave, d.get("tipo", "otro"), nivel, a.get("autonomia"))
            pie = f"Quedan ~{formato_horas(horas)}" + ("" if medido else " (aprox.)")
        ctk.CTkLabel(t, text=pie, font=fuente(12), text_color=c_sec, anchor="w").grid(
            row=5, column=0, columnspan=2, padx=20, pady=(6, 0), sticky="w")

        def entrar(_e=None):
            t.configure(border_color=P["BORDE_HOVER"] if on else P["HOVER_OFF"])

        def salir(_e=None):
            t.configure(border_color=P["BORDE"] if on else P["BORDE_OFF"])

        def enlazar(w):
            w.bind("<Enter>", entrar, add="+")
            w.bind("<Leave>", salir, add="+")
            w.bind("<Button-1>", lambda e: self.ver_editor(clave), add="+")
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
            for h in w.winfo_children():
                enlazar(h)

        enlazar(t)
        return t

    # ======================================================== vista: editor
    def ver_editor(self, clave: str) -> None:
        self._registrar(("editor", clave))
        self.vista = "editor"
        self._marcar_nav("perifericos")
        if not self._hay_pagina("editor"):
            self._construir_editor()
        self._cargar_editor(clave)
        self._mostrar("editor")

    def _construir_editor(self) -> None:
        """Crea los controles del editor (vacíos). _cargar_editor los rellena para cada periférico."""
        pagina = self._nueva_pagina("editor")
        self._glifo_marcado = None
        self._marcos_modelo: dict[str, dict] = {}
        self._modelos_tipo = None
        d = {"nombre": "", "tipo": "raton"}
        a = ap.ajustes_de({}, "", "raton")
        clave = ""

        cab = ctk.CTkFrame(pagina, fg_color="transparent")
        cab.pack(fill="x", padx=24, pady=(18, 0))
        ctk.CTkButton(cab, text="‹  Periféricos", width=120, height=34, corner_radius=10, font=fuente(13),
                      fg_color="transparent", hover_color=P["SUPERFICIE_HOVER"], text_color=P["SECUNDARIO"],
                      command=self.ver_perifericos).pack(side="left")
        self.e_estado = ctk.CTkLabel(cab, text="", font=fuente(11), corner_radius=8,
                                     height=22, fg_color=P["SUPERFICIE"], text_color=P["SECUNDARIO"])
        self.e_estado.pack(side="right")

        cont = ctk.CTkScrollableFrame(pagina, fg_color=P["FONDO"], corner_radius=0,
                                      scrollbar_button_color=P["PISTA"], scrollbar_button_hover_color=P["PISTA_OFF"])
        cont.pack(fill="both", expand=True, padx=4, pady=(6, 0))
        rueda_rapida(cont)
        self.e_cont = cont

        top = ctk.CTkFrame(cont, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(6, 4))
        self.e_icono_grande = ctk.CTkLabel(top, text="")
        self.e_icono_grande.pack(side="left")
        tt = ctk.CTkFrame(top, fg_color="transparent")
        tt.pack(side="left", padx=16)
        self.e_titulo = ctk.CTkLabel(tt, text="", font=fuente(22, "bold"), text_color=P["TEXTO"], anchor="w")
        self.e_titulo.pack(anchor="w")
        self.e_subtitulo = ctk.CTkLabel(tt, text="", font=fuente(12), text_color=P["SECUNDARIO"], anchor="w")
        self.e_subtitulo.pack(anchor="w")

        # Vista previa
        sec = self._seccion(cont, "Vista previa", "Así se verá en la barra de tareas")
        self.e_previa = ctk.CTkLabel(sec, text="")
        self.e_previa.pack(anchor="w")

        # Diseño
        sec = self._seccion(cont, "Diseño", "Elige el modelo que más se parezca a tu periférico")
        tipos = [t for t in NOMBRES_TIPO if t != "otro"]
        tipo_ini = d.get("tipo") if d.get("tipo") in tipos else "raton"
        if a["icono"].startswith("modelo:"):
            tipo_ini = modelos.MODELOS.get(a["icono"][7:], {}).get("tipo", tipo_ini)
        self.v_tipo_modelo = ctk.StringVar(value=NOMBRES_TIPO[tipo_ini])
        self._estilo_pintado = None
        ctk.CTkSegmentedButton(sec, values=[NOMBRES_TIPO[t] for t in tipos], variable=self.v_tipo_modelo,
                               font=fuente(12), height=32, corner_radius=10,
                               selected_color=P["ACENTO"], selected_hover_color=P["ACENTO_HOVER"],
                               unselected_color=P["SUPERFICIE"], unselected_hover_color=P["SUPERFICIE_HOVER"],
                               fg_color=P["SUPERFICIE"], text_color=P["TEXTO"],
                               command=lambda v: self._pintar_modelos()).pack(anchor="w")
        self.f_modelos = ctk.CTkFrame(sec, fg_color="transparent")
        self.f_modelos.pack(anchor="w", pady=(12, 0))
        self.botones_modelo: dict[str, ctk.CTkButton] = {}

        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w", pady=(16, 0))
        ctk.CTkLabel(fila, text="Estilo", font=fuente(13), text_color=P["TEXTO"], width=70, anchor="w"
                     ).pack(side="left")
        self.v_estilo = ctk.StringVar(value=ESTILOS.get(a.get("estilo", "general"), ESTILOS["general"]))
        self._segmentado(fila, list(ESTILOS.values()), self.v_estilo,
                         lambda v: self._set("estilo", {n: k for k, n in ESTILOS.items()}[v])).pack(side="left")
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(fila, text="Acabado", font=fuente(13), text_color=P["TEXTO"], width=70, anchor="w"
                     ).pack(side="left")
        self.v_acabado = ctk.StringVar(value=ACABADOS.get(a.get("acabado", "grafito"), "Grafito"))
        self._segmentado(fila, list(ACABADOS.values()), self.v_acabado,
                         lambda v: self._set("acabado", {n: k for k, n in ACABADOS.items()}[v])).pack(side="left")
        self.l_acabado = ctk.CTkLabel(fila, text="  solo en estilo realista", font=fuente(12),
                                      text_color=P["SECUNDARIO"])
        self.l_acabado.pack(side="left", padx=8)
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(fila, text="Mostrar", font=fuente(13), text_color=P["TEXTO"], width=70, anchor="w"
                     ).pack(side="left")
        self.v_mostrar = ctk.StringVar(value=MODOS_DISP["general"])
        self._segmentado(fila, list(MODOS_DISP.values()), self.v_mostrar,
                         lambda v: self._set("mostrar", {n: k for k, n in MODOS_DISP.items()}[v])).pack(side="left")

        # Color
        sec = self._seccion(cont, "Color", "Minimalista: color del trazo. Realista: color de las luces y detalles. "
                                           "Auto = según el tema de la barra")
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")
        self._swatches(f, ["auto"] + COLORES, lambda c: self._set("color", c),
                       lambda: self.ajustes(self.sel)["color"])
        etiqueta = ctk.CTkLabel(sec, text=TEXTO_COLOR_INFO, font=fuente(13), text_color=P["TEXTO"])
        etiqueta.pack(anchor="w", pady=(16, 6))
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")
        self._swatches(f, ["auto"] + COLORES, lambda c: self._set("color_texto", c),
                       lambda: ap.color_texto(self.cfg, self.ajustes(self.sel)) if self.sel else "auto",
                       activo=lambda: bool(self.sel) and ap.modo_icono(self.cfg, self.ajustes(self.sel)) != "icono",
                       etiqueta=etiqueta)

        # Nombre
        sec = self._seccion(cont, "Nombre", "Vacío = nombre original")
        self.e_ayuda_nombre = sec.ayuda
        self.v_nombre = ctk.StringVar(value=a["nombre"])
        ctk.CTkEntry(sec, textvariable=self.v_nombre, width=380, height=38, corner_radius=10, font=fuente(13),
                     fg_color=P["SUPERFICIE"], border_color=P["BORDE"], text_color=P["TEXTO"]).pack(anchor="w")
        self.v_nombre.trace_add("write", lambda *x: self._cargando_editor
                                or self._set("nombre", self.v_nombre.get().strip()))

        # Especificaciones y notas
        sec = self._seccion(cont, "Especificaciones",
                            "Completa lo que sepas de tu periférico: lo principal se resume en su tarjeta. "
                            "Se guarda solo en tu PC")
        self.f_fichas = ctk.CTkFrame(sec, fg_color="transparent")
        self.f_fichas.pack(fill="x")
        self._fichas: dict[str, dict] = {}          # tipo -> {"marco", "vars"} (se crean una vez por tipo)
        self._ficha_tipo = None
        ctk.CTkLabel(sec, text="Notas y modificaciones", font=fuente(13), text_color=P["TEXTO"]).pack(
            anchor="w", pady=(16, 2))
        ctk.CTkLabel(sec, text="Por ejemplo: pies de PTFE, batería reemplazada, switches cambiados, firmware…",
                     font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w", pady=(0, 6))
        self.t_notas = ctk.CTkTextbox(sec, height=96, corner_radius=10, font=fuente(13), fg_color=P["SUPERFICIE"],
                                      border_width=1, border_color=P["BORDE"], text_color=P["TEXTO"], wrap="word")
        self.t_notas.pack(fill="x")
        self.t_notas.bind("<KeyRelease>", lambda e: self._cargando_editor or self._set_nota())

        # Símbolos e imagen
        sec = self._seccion(cont, "Símbolos e imagen propia", "En lugar de un diseño, usa un símbolo o una imagen")
        rej = ctk.CTkFrame(sec, fg_color="transparent")
        rej.pack(anchor="w")
        self.botones_icono = {}
        for i, (codigo, _nombre) in enumerate(ap.GALERIA):
            img = ap.dibujar_icono("otro", 100, False, {"icono": "glifo:" + codigo, "color": P["TEXTO"],
                                                        "tenir": True}, {"tamano_icono": 90}, 48, False)
            b = ctk.CTkButton(rej, text="", image=ctk.CTkImage(img, size=(22, 22)), width=46, height=46,
                              corner_radius=12, fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"],
                              border_width=2, border_color=P["SUPERFICIE"],
                              command=lambda c=codigo: self._set("icono", "glifo:" + c))
            b.grid(row=i // 12, column=i % 12, padx=3, pady=3)
            self.botones_icono[codigo] = b
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w", pady=(10, 0))
        ctk.CTkButton(fila, text="Imagen propia…", width=140, height=34, corner_radius=10, font=fuente(13),
                      fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"], border_width=1,
                      border_color=P["BORDE"], text_color=P["TEXTO"], command=self._elegir_imagen).pack(side="left")
        self.v_tenir = ctk.BooleanVar(value=bool(a.get("tenir", True)))
        self.s_tenir = ctk.CTkSwitch(fila, text="Pintar la imagen con el color", variable=self.v_tenir,
                                     font=fuente(13), text_color=P["SECUNDARIO"], progress_color=P["ACENTO"],
                                     command=lambda: self._set("tenir", bool(self.v_tenir.get())))
        self.s_tenir.pack(side="left", padx=16)
        self.l_imagen = ctk.CTkLabel(sec, text="", font=fuente(12), text_color=P["SECUNDARIO"])
        self.l_imagen.pack(anchor="w")

        # Uso
        sec = self._seccion(cont, "Uso", "")
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w")
        ctk.CTkLabel(fila, text="Autonomía con la batería llena", font=fuente(13), text_color=P["TEXTO"]
                     ).pack(side="left")
        self.v_auto = ctk.StringVar(value="" if a["autonomia"] is None else f"{a['autonomia']:g}")
        ctk.CTkEntry(fila, textvariable=self.v_auto, width=80, height=34, corner_radius=10, font=fuente(13),
                     fg_color=P["SUPERFICIE"], border_color=P["BORDE"], text_color=P["TEXTO"]
                     ).pack(side="left", padx=10)
        ctk.CTkLabel(fila, text="horas", font=fuente(13), text_color=P["SECUNDARIO"]).pack(side="left")
        self.v_auto.trace_add("write", lambda *x: self._cargando_editor or self._cambio_autonomia())
        self.e_ayuda_auto = ctk.CTkLabel(sec, text="", font=fuente(12), text_color=P["SECUNDARIO"])
        self.e_ayuda_auto.pack(anchor="w", pady=(6, 0))
        self.e_medicion = ctk.CTkLabel(sec, text="", font=fuente(12), text_color=P["TEXTO"], anchor="w",
                                       justify="left", wraplength=700)
        self.e_medicion.pack(anchor="w", pady=(6, 10))
        self.v_oculto = ctk.BooleanVar(value=bool(a["oculto"]))
        ctk.CTkSwitch(sec, text="Ocultar en la bandeja", variable=self.v_oculto, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"],
                      command=lambda: self._set("oculto", bool(self.v_oculto.get()))).pack(anchor="w")

        ctk.CTkButton(cont, text="Restablecer este periférico", width=220, height=36, corner_radius=10,
                      font=fuente(13), fg_color="transparent", hover_color=P["PELIGRO_HOVER"], border_width=1,
                      border_color=P["PELIGRO_BORDE"], text_color=P["PELIGRO_TEXTO"], command=self._restablecer
                      ).pack(anchor="w", padx=24, pady=(18, 28))

    def _cargar_editor(self, clave: str) -> None:
        """Rellena el editor (ya construido) con los datos de un periférico."""
        self.sel = clave
        d = self.dev(clave)
        on = self.encendido(clave)
        a = self.ajustes(clave)
        tipos = [t for t in NOMBRES_TIPO if t != "otro"]
        tipo_ini = d.get("tipo") if d.get("tipo") in tipos else "raton"
        if a["icono"].startswith("modelo:"):
            tipo_ini = modelos.MODELOS.get(a["icono"][7:], {}).get("tipo", tipo_ini)
        self._cargando_editor = True
        try:
            self.e_estado.configure(text=f"  {'Encendido' if on else 'Apagado'}  ")
            self.e_subtitulo.configure(
                text=f"{NOMBRES_TIPO.get(d.get('tipo'), 'Periférico')} · {d.get('nombre', clave)}"
                     + ("" if on else " · apagado, puedes editarlo igualmente"))
            self.e_ayuda_nombre.configure(text=f"Vacío = nombre original ({d.get('nombre', clave)})")
            self.v_nombre.set(a["nombre"])
            self.v_tipo_modelo.set(NOMBRES_TIPO[tipo_ini])
            self.v_estilo.set(ESTILOS.get(a.get("estilo", "general"), ESTILOS["general"]))
            self.v_acabado.set(ACABADOS.get(a.get("acabado", "grafito"), "Grafito"))
            self.v_mostrar.set(MODOS_DISP.get(a.get("mostrar", "general"), MODOS_DISP["general"]))
            self.v_tenir.set(bool(a.get("tenir", True)))
            self.v_auto.set("" if a["autonomia"] is None else f"{a['autonomia']:g}")
            defecto = autonomia_defecto(clave, d.get("tipo", "otro"), self.cfg)
            self.e_ayuda_auto.configure(text=f"Vacío = {defecto:g} h (valor por defecto). Se usa hasta que el "
                                             f"programa mide tu consumo real.")
            self.e_medicion.configure(text=self.est.resumen(clave))
            self.v_oculto.set(bool(a["oculto"]))
            self._cargar_ficha(d.get("tipo", "otro"), a.get("ficha") or {})
            self.t_notas.delete("1.0", "end")
            if a.get("notas"):
                self.t_notas.insert("1.0", a["notas"])
        finally:
            self._cargando_editor = False
        self._refrescar_editor()
        try:
            self.e_cont._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def _segmentado(self, padre, valores, var, cmd) -> ctk.CTkSegmentedButton:
        return ctk.CTkSegmentedButton(padre, values=valores, variable=var, font=fuente(12), height=32,
                                      corner_radius=10, selected_color=P["ACENTO"],
                                      selected_hover_color=P["ACENTO_HOVER"], unselected_color=P["SUPERFICIE"],
                                      unselected_hover_color=P["SUPERFICIE_HOVER"], fg_color=P["SUPERFICIE"],
                                      text_color=P["TEXTO"], command=cmd)

    def _pintar_modelos(self) -> None:
        """Rejilla de modelos del tipo elegido, dibujados en el estilo actual de este periférico."""
        # Los botones de cada tipo se crean una sola vez; después solo se cambia su imagen
        # (cuando cambia el estilo, el acabado o el color) y cuál está marcado.
        if not self.sel:
            return
        tipo = {n: k for k, n in NOMBRES_TIPO.items()}[self.v_tipo_modelo.get()]
        a = self.ajustes(self.sel)
        cache = self._marcos_modelo
        if tipo not in cache:
            marco = ctk.CTkFrame(self.f_modelos, fg_color="transparent")
            botones = {}
            for i, (mid, m) in enumerate((k, v) for k, v in modelos.MODELOS.items() if v["tipo"] == tipo):
                b = ctk.CTkButton(marco, text=m["nombre"], compound="top", width=118, height=104,
                                  corner_radius=14, font=fuente(12), fg_color=P["SUPERFICIE"],
                                  hover_color=P["SUPERFICIE_HOVER"], text_color=P["TEXTO"], border_width=2,
                                  border_color=P["SUPERFICIE"],
                                  command=lambda x=mid: self._set("icono", "modelo:" + x))
                b.grid(row=0, column=i, padx=4)
                botones[mid] = b
            cache[tipo] = {"marco": marco, "botones": botones, "firma": None, "marcado": None}
        for t, c in cache.items():
            if t != tipo:
                c["marco"].pack_forget()
        actual = cache[tipo]
        actual["marco"].pack(anchor="w")
        firma = self._firma_modelos(a)
        if actual["firma"] != firma:
            for mid, b in actual["botones"].items():
                img = ap.dibujar_icono(tipo, 100, False, dict(a, icono="modelo:" + mid), self.cfg, 112, P["CLARO"])
                b.configure(image=ctk.CTkImage(img, size=(56, 56)))
            actual["firma"] = firma
        self.botones_modelo = actual["botones"]
        self._modelos_tipo = actual
        self._marcar_modelo()
        self._estilo_pintado = firma

    def _firma_modelos(self, a: dict) -> tuple:
        return (self.v_tipo_modelo.get(), self.estilo_de(a), a.get("acabado"), a.get("color"), P["NOMBRE"])

    def _marcar_modelo(self) -> None:
        icono = self.ajustes(self.sel)["icono"]
        elegido = icono[7:] if icono.startswith("modelo:") else None
        estado = getattr(self, "_modelos_tipo", None)
        if not estado or estado["marcado"] == elegido:
            return
        if estado["marcado"] in self.botones_modelo:
            self.botones_modelo[estado["marcado"]].configure(border_color=P["SUPERFICIE"])
        if elegido in self.botones_modelo:
            self.botones_modelo[elegido].configure(border_color=P["ACENTO"])
        estado["marcado"] = elegido

    def _seccion(self, padre, titulo: str, ayuda: str) -> ctk.CTkFrame:
        caja = ctk.CTkFrame(padre, fg_color="transparent", corner_radius=16, border_width=1, border_color=P["BORDE"])
        caja.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(caja, text=titulo, font=fuente(15, "bold"), text_color=P["TEXTO"]).pack(anchor="w", padx=20,
                                                                                            pady=(14, 0))
        if ayuda:
            ctk.CTkLabel(caja, text=ayuda, font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w", padx=20)
        interior = ctk.CTkFrame(caja, fg_color="transparent")
        interior.pack(fill="x", padx=20, pady=(10, 16))
        interior.ayuda = caja.winfo_children()[1] if ayuda else None
        return interior

    def _swatches(self, padre, colores, al_elegir, actual, activo=None, etiqueta=None) -> None:
        """Fila de colores. activo(): si devuelve False, la fila se ve difuminada y no responde
        (p. ej. el color del texto cuando el icono no muestra texto)."""
        botones = {}

        def elegir(c):
            al_elegir(c)
            self._pintar_swatches()

        for c in colores:
            if c == "auto":
                b = ctk.CTkButton(padre, text="Auto", width=78, height=34, corner_radius=17, font=fuente(12),
                                  compound="left", fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"],
                                  text_color=P["TEXTO"], text_color_disabled=P["APAGADO"],
                                  command=lambda: elegir("auto"))
                b.pack(side="left", padx=(0, 8))
            else:
                b = Muestra(padre, lambda c=c: elegir(c))
                b.pack(side="left", padx=1)
            botones[c] = b

        # color propio elegido con el selector (aparece sólo si hay uno)
        propio = Muestra(padre, lambda: None)

        def personalizado():
            sel = actual()
            ini = sel if isinstance(sel, str) and sel.startswith("#") else P["ACENTO"]

            def aceptar(c):
                recientes = [c] + [x for x in self.cfg.get("colores_recientes", []) if x != c]
                self.cfg["colores_recientes"] = recientes[:8]
                elegir(c)
            SelectorColor(self, ini, aceptar, P, fuente, self.cfg.get("colores_recientes", []),
                          icono=lambda w: self._poner_icono_en(w))

        otro = Muestra(padre, personalizado)
        otro.pack(side="left", padx=(8, 0))
        self._grupos_swatch.append({"botones": botones, "otro": otro, "propio": propio, "actual": actual,
                                    "activo": activo, "etiqueta": etiqueta})
        self._pintar_swatches()

    def _img_muestra(self, color: str, marcado: bool, atenuado: bool, lado: int = 30,
                     hover: bool = False) -> ctk.CTkImage:
        """hover: aro tenue (al pasar el ratón); marcado: aro del color del texto (elegido)."""
        clave = (color, marcado, atenuado, lado, hover, P["NOMBRE"])
        cache = self.__dict__.setdefault("_cache_muestras", {})
        if clave not in cache:
            f = 0.7 if atenuado else 0.0
            aro = P["APAGADO"] if hover else P["TEXTO"]
            img = circulo_auto(lado, P["FONDO"], marcado, aro, f) if color == "auto" else \
                circulo(color, lado, P["FONDO"], marcado, aro, f)
            cache[clave] = ctk.CTkImage(img, size=(lado, lado))
        return cache[clave]

    def _img_rueda(self, on: bool) -> ctk.CTkImage:
        cache = self.__dict__.setdefault("_cache_rueda", {})
        if on not in cache:
            img = rueda(30)
            if not on:                                   # difuminada: más transparente
                img.putalpha(img.getchannel("A").point(lambda a: a * 35 // 100))
            cache[on] = ctk.CTkImage(img, size=(30, 30))
        return cache[on]

    def _poner_icono_en(self, ventana) -> None:
        try:
            ventana.iconbitmap(rutas.recurso(icono_tema() + ".ico"))
        except Exception:
            pass

    def _pintar_swatches(self) -> None:
        for g in list(self._grupos_swatch):
            try:
                sel = g["actual"]()
                on = g["activo"] is None or bool(g["activo"]())
                estado = "normal" if on else "disabled"
                for c, b in g["botones"].items():
                    if c == "auto":
                        b.configure(state=estado, image=self._img_muestra("auto", c == sel, not on, 22),
                                    border_width=2 if c == sel else 0, border_color=P["TEXTO"] if on else P["APAGADO"])
                    else:
                        b.poner(self._img_muestra(c, c == sel, not on),
                                self._img_muestra(c, True, not on, hover=c != sel), activa=on)
                propio = g["propio"]
                if isinstance(sel, str) and sel.startswith("#") and sel not in g["botones"]:
                    propio.poner(self._img_muestra(sel, True, not on), activa=on)
                    if not propio.winfo_manager():
                        propio.pack(side="left", padx=(8, 0), before=g["otro"])
                elif propio.winfo_manager():
                    propio.pack_forget()
                g["otro"].poner(self._img_rueda(on), activa=on)
                if g["etiqueta"] is not None:
                    g["etiqueta"].configure(text_color=P["TEXTO"] if on else P["APAGADO"])
            except Exception:       # el grupo pertenece a una vista ya cerrada
                self._grupos_swatch.remove(g)

    def _refrescar_editor(self) -> None:
        if self.vista != "editor" or not self.sel:
            return
        clave = self.sel
        a = self.ajustes(clave)
        d = self.dev(clave)
        on = self.encendido(clave)
        self.e_titulo.configure(text=a["nombre"] or d.get("nombre", clave))
        self.e_icono_grande.configure(image=self.icono(clave, 64, apagado=not on))
        previo = getattr(self, "_glifo_marcado", None)       # solo se repintan los dos botones que cambian
        actual = a["icono"][6:] if a["icono"].startswith("glifo:") else None
        if previo != actual:
            if previo in self.botones_icono:
                self.botones_icono[previo].configure(border_color=P["SUPERFICIE"])
            if actual in self.botones_icono:
                self.botones_icono[actual].configure(border_color=P["ACENTO"])
            self._glifo_marcado = actual
        if self._estilo_pintado != self._firma_modelos(a):
            self._pintar_modelos()
        else:
            self._marcar_modelo()
        es_img = a["icono"].startswith("imagen:")
        self.l_imagen.configure(text=("Imagen: " + os.path.basename(a["icono"][7:])) if es_img else "")
        self.s_tenir.configure(state="normal" if es_img else "disabled")
        self.l_acabado.configure(text="" if self.estilo_de(a) == "realista" else "  solo en estilo realista")
        self._pintar_swatches()
        self.e_previa.configure(image=self._imagen_previa(clave, a))

    def _imagen_previa(self, clave: str, a: dict) -> ctk.CTkImage:
        d = self.dev(clave)
        tipo = d.get("tipo", "otro")
        nivel = int(d.get("bateria", 80)) or 80
        umbral = int(ap.global_(self.cfg, "umbral_baja"))
        casos = [("Normal", nivel, False), ("Batería baja", min(umbral, 10), False), ("Cargando", nivel, True)]
        k = 2                                   # se dibuja al doble para pantallas nítidas
        ancho, alto = 600 * k, 64 * k
        img = Image.new("RGBA", (ancho, alto * 2 + 10 * k), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        f = _pil_fuente(11 * k)
        for fila, (claro, fondo, tinta) in enumerate([(False, (32, 32, 36), (150, 150, 160)),
                                                      (True, (238, 238, 240), (90, 90, 100))]):
            y0 = fila * (alto + 10 * k)
            dr.rounded_rectangle((0, y0, ancho - 1, y0 + alto), radius=12 * k, fill=fondo + (255,))
            dr.text((16 * k, y0 + alto / 2), "Barra oscura" if not claro else "Barra clara", font=f,
                    fill=tinta + (255,), anchor="lm")
            x = 130 * k
            for etiqueta, niv, carga in casos:
                horas, _ = self.est.horas(clave, tipo, niv, a.get("autonomia"))
                texto = ap.texto_icono(self.cfg, a, niv, carga, horas)
                for t in (32, 16):
                    ic = ap.dibujar_icono(tipo, niv, carga, a, self.cfg, t * k, claro, texto)
                    img.alpha_composite(ic, (int(x), int(y0 + (alto - t * k) / 2 - 6 * k)))
                    x += (t + 10) * k
                dr.text((x - 34 * k, y0 + alto - 9 * k), etiqueta, font=_pil_fuente(10 * k), fill=tinta + (255,),
                        anchor="mm")
                x += 44 * k
        return ctk.CTkImage(img, size=(ancho // k, img.height // k))

    def _set(self, campo: str, valor) -> None:
        if not self.sel:
            return
        self.cfg["dispositivos"].setdefault(self.sel, {})[campo] = valor
        self._programar_guardado()
        self._ensuciar("perifericos")
        self._refrescar_editor()

    # ---- ficha técnica (los campos dependen del tipo: se crean una vez por tipo y se reutilizan)
    def _cargar_ficha(self, tipo: str, ficha: dict) -> None:
        tipo = tipo if tipo in CAMPOS_FICHA else "otro"
        if tipo not in self._fichas:
            marco = ctk.CTkFrame(self.f_fichas, fg_color="transparent")
            marco.grid_columnconfigure((0, 1), weight=1, uniform="ficha")
            variables = {}
            for i, (clave, etiqueta, ejemplo, _u) in enumerate(CAMPOS_FICHA[tipo]):
                celda = ctk.CTkFrame(marco, fg_color="transparent")
                celda.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 16) if i % 2 == 0 else 0, pady=4)
                ctk.CTkLabel(celda, text=etiqueta, font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w")
                v = ctk.StringVar()
                ctk.CTkEntry(celda, textvariable=v, height=34, corner_radius=10, font=fuente(13),
                             fg_color=P["SUPERFICIE"], border_color=P["BORDE"], text_color=P["TEXTO"]
                             ).pack(fill="x")
                ctk.CTkLabel(celda, text=f"Ej.: {ejemplo}", font=fuente(11), text_color=P["APAGADO"]).pack(anchor="w")
                v.trace_add("write", lambda *x, c=clave, var=v: self._cargando_editor
                            or self._set_ficha(c, var.get()))
                variables[clave] = v
            self._fichas[tipo] = {"marco": marco, "vars": variables}
        if self._ficha_tipo != tipo:
            for t, f in self._fichas.items():
                if t != tipo:
                    f["marco"].pack_forget()
            self._fichas[tipo]["marco"].pack(fill="x")
            self._ficha_tipo = tipo
        for clave, v in self._fichas[tipo]["vars"].items():
            v.set(ficha.get(clave, ""))

    def _set_ficha(self, campo: str, valor: str) -> None:
        """Se guarda al escribir, sin redibujar el editor (sería lento tecla a tecla)."""
        if not self.sel:
            return
        disp = self.cfg["dispositivos"].setdefault(self.sel, {})
        ficha = dict(disp.get("ficha") or {})
        if valor.strip():
            ficha[campo] = valor.strip()
        else:
            ficha.pop(campo, None)
        if ficha:
            disp["ficha"] = ficha
        else:
            disp.pop("ficha", None)
        self._programar_guardado()
        self._ensuciar("perifericos")

    def _set_nota(self) -> None:
        if not self.sel:
            return
        disp = self.cfg["dispositivos"].setdefault(self.sel, {})
        texto = self.t_notas.get("1.0", "end").strip()
        if texto:
            disp["notas"] = texto
        else:
            disp.pop("notas", None)
        self._programar_guardado()
        self._ensuciar("perifericos")

    def _cambio_autonomia(self) -> None:
        texto = self.v_auto.get().strip().replace(",", ".")
        try:
            valor = float(texto) if texto and float(texto) > 0 else None
        except ValueError:
            valor = None
        self._set("autonomia", valor)

    def _elegir_imagen(self) -> None:
        ruta = filedialog.askopenfilename(parent=self, title="Elige una imagen para el icono",
                                          filetypes=[("Imágenes", "*.png *.ico *.jpg *.jpeg *.bmp *.gif *.webp"),
                                                     ("Todos los archivos", "*.*")])
        if ruta:
            self._set("icono", "imagen:" + ruta)

    def _restablecer(self) -> None:
        if self.sel:
            self.cfg["dispositivos"].pop(self.sel, None)
            self._programar_guardado()
            self._ensuciar("perifericos")
            self._cargar_editor(self.sel)

    # ========================================================== vista: general
    def _tiles(self, padre, opciones: list[tuple[str, str, Image.Image]], actual: str, al_elegir) -> dict:
        botones = {}
        for valor, texto, img in opciones:
            b = ctk.CTkButton(padre, text=texto, image=ctk.CTkImage(img, size=(img.width // 2, img.height // 2)),
                              compound="top", width=170, height=132, corner_radius=14, font=fuente(13),
                              fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"], text_color=P["TEXTO"],
                              border_width=2, border_color=P["ACENTO"] if valor == actual else P["SUPERFICIE"],
                              command=lambda v=valor: al_elegir(v))
            b.pack(side="left", padx=(0, 10))
            botones[valor] = b
        return botones

    def ver_general(self) -> None:
        self._registrar(("general", None))
        self.vista = "general"
        self._marcar_nav("general")
        if not self._hay_pagina("general"):
            self._construir_general()
        self._mostrar("general")
        if self._foto_tema(P["NOMBRE"]) is None:
            self.after(600, self._guardar_foto_tema)     # para que el cambio a este tema sea instantáneo

    def _construir_general(self) -> None:
        cont = self._scroll(self._nueva_pagina("general"))
        ctk.CTkLabel(cont, text="General", font=fuente(22, "bold"), text_color=P["TEXTO"]).pack(anchor="w", padx=28,
                                                                                              pady=(24, 6))

        sec = self._seccion(cont, "Interfaz", "Tema de esta ventana")
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")
        self._tiles(f, [(n, NOMBRES_TEMA[n], miniatura_tema(n)) for n in ("claro", "gris", "oscuro")],
                    P["NOMBRE"], lambda v: self.cambiar_tema(v) if v != P["NOMBRE"] else None)

        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(fill="x", pady=(18, 0))
        ctk.CTkLabel(fila, text="Opacidad de la ventana", font=fuente(13), text_color=P["TEXTO"]).pack(side="left")
        l_opac = ctk.CTkLabel(fila, text="", font=fuente(15, "bold"), text_color=P["TEXTO"], width=60)
        l_opac.pack(side="right")
        vo = ctk.IntVar(value=int(ap.global_(self.cfg, "opacidad_app")))

        def opacidad(val):
            valor = int(float(val))
            self.cfg["opacidad_app"] = valor
            l_opac.configure(text=f"{valor} %")
            self._aplicar_opacidad(valor)
            self._programar_guardado()

        ctk.CTkSlider(fila, from_=40, to=100, number_of_steps=60, variable=vo, command=opacidad,
                      progress_color=P["ACENTO"], button_color=P["ACENTO"], button_hover_color=P["ACENTO_HOVER"],
                      fg_color=P["PISTA"]).pack(side="left", fill="x", expand=True, padx=12)
        l_opac.configure(text=f"{vo.get()} %")
        ctk.CTkLabel(sec, text="Más baja = la ventana se vuelve translúcida y se ve menos brillante.",
                     font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w", pady=(4, 0))

        sec = self._seccion(cont, "Estilo de los iconos",
                            "Se aplica a todos los periféricos (cada uno puede tener el suyo en su página)")
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")
        estilo = ap.global_(self.cfg, "estilo_iconos")

        def elegir_estilo(v):
            self._set_global("estilo_iconos", v)
            for valor, b in tiles_estilo.items():
                b.configure(border_color=P["ACENTO"] if valor == v else P["SUPERFICIE"])

        tiles_estilo = self._tiles(f, [(e, ESTILOS[e], miniatura_estilo(e, P["CLARO"]))
                                       for e in ("realista", "minimalista")], estilo, elegir_estilo)

        sec = self._seccion(cont, "Qué muestra el icono",
                            "En la barra de tareas, junto al dibujo (cada periférico puede tener el suyo)")
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")

        def elegir_modo(v):
            self._set_global("mostrar_icono", v)
            for valor, b in tiles_modo.items():
                b.configure(border_color=P["ACENTO"] if valor == v else P["SUPERFICIE"])
            self._pintar_swatches()

        tiles_modo = self._tiles(f, [(m, MODOS[m], miniatura_modo(m, P["CLARO"], self.cfg)) for m in MODOS],
                                 ap.global_(self.cfg, "mostrar_icono"), elegir_modo)
        etiqueta = ctk.CTkLabel(sec, text=TEXTO_COLOR_INFO, font=fuente(13), text_color=P["TEXTO"])
        etiqueta.pack(anchor="w", pady=(16, 6))
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")
        def elegir_color_texto(c):
            self._set_global("color_texto", c)
            for m, b in tiles_modo.items():          # las miniaturas muestran el color nuevo
                img = miniatura_modo(m, P["CLARO"], self.cfg)
                b.configure(image=ctk.CTkImage(img, size=(img.width // 2, img.height // 2)))

        self._swatches(f, ["auto"] + COLORES, elegir_color_texto, lambda: ap.global_(self.cfg, "color_texto"),
                       activo=lambda: ap.global_(self.cfg, "mostrar_icono") != "icono", etiqueta=etiqueta)
        ctk.CTkLabel(sec, text="Tiempo restante: 45m, 12h o 3d. Mientras carga se muestra el porcentaje. "
                               "Con batería baja el texto usa el color de aviso.",
                     font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w", pady=(8, 0))

        sec = self._seccion(cont, "Batería baja", "Por debajo de este porcentaje el icono cambia de color")
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(fill="x")
        l_umbral = ctk.CTkLabel(fila, text="", font=fuente(15, "bold"), text_color=P["TEXTO"], width=60)
        l_umbral.pack(side="right")
        v = ctk.IntVar(value=int(ap.global_(self.cfg, "umbral_baja")))

        def umbral(val):
            self.cfg["umbral_baja"] = int(float(val))
            l_umbral.configure(text=f"{self.cfg['umbral_baja']} %")
            self._programar_guardado()

        ctk.CTkSlider(fila, from_=5, to=50, number_of_steps=45, variable=v, command=umbral,
                      progress_color=P["ACENTO"], button_color=P["ACENTO"], button_hover_color=P["ACENTO_HOVER"],
                      fg_color=P["PISTA"]).pack(side="left", fill="x", expand=True, padx=(0, 12))
        l_umbral.configure(text=f"{v.get()} %")
        ctk.CTkLabel(sec, text="Color", font=fuente(13), text_color=P["SECUNDARIO"]).pack(anchor="w", pady=(14, 6))
        f = ctk.CTkFrame(sec, fg_color="transparent")
        f.pack(anchor="w")
        self._swatches(f, ["auto"] + COLORES_BAJA, lambda c: self._set_global("color_baja", c),
                       lambda: ap.global_(self.cfg, "color_baja"))
        self._seccion_avisos(cont)

        sec = self._seccion(cont, "Iconos", "")
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(fill="x")
        ctk.CTkLabel(fila, text="Tamaño del dibujo", font=fuente(13), text_color=P["TEXTO"]).pack(side="left")
        l_tam = ctk.CTkLabel(fila, text="", font=fuente(15, "bold"), text_color=P["TEXTO"], width=60)
        l_tam.pack(side="right")
        vt = ctk.IntVar(value=int(ap.global_(self.cfg, "tamano_icono")))

        def tam(val):
            self.cfg["tamano_icono"] = int(float(val))
            l_tam.configure(text=f"{self.cfg['tamano_icono']} %")
            self._programar_guardado()

        ctk.CTkSlider(fila, from_=60, to=100, number_of_steps=40, variable=vt, command=tam,
                      progress_color=P["ACENTO"], button_color=P["ACENTO"], button_hover_color=P["ACENTO_HOVER"],
                      fg_color=P["PISTA"]).pack(side="left", fill="x", expand=True, padx=12)
        l_tam.configure(text=f"{vt.get()} %")
        vp = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "punto_carga")))
        ctk.CTkSwitch(sec, text="Punto verde mientras carga", variable=vp, font=fuente(13), text_color=P["TEXTO"],
                      progress_color=P["ACENTO"], command=lambda: self._set_global("punto_carga", bool(vp.get()))
                      ).pack(anchor="w", pady=(14, 0))
        vv = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "iconos_visibles")))
        ctk.CTkSwitch(sec, text="Mostrar los iconos nuevos en la barra de tareas", variable=vv, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"],
                      command=lambda: self._set_global("iconos_visibles", bool(vv.get()))).pack(anchor="w",
                                                                                                pady=(10, 0))
        vm = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "liberar_memoria")))
        ctk.CTkSwitch(sec, text=f"Liberar memoria: cerrar la ventana si queda oculta {MINUTOS_OCULTA} minutos",
                      variable=vm, font=fuente(13), text_color=P["TEXTO"], progress_color=P["ACENTO"],
                      command=lambda: self._set_global("liberar_memoria", bool(vm.get()))).pack(anchor="w",
                                                                                               pady=(10, 0))

        sec = self._seccion(cont, "Sistema", "")
        vi = ctk.BooleanVar(value=inicio_activado())
        ctk.CTkSwitch(sec, text="Abrir Brahttery hub al iniciar Windows", variable=vi, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"], command=lambda: poner_inicio(bool(vi.get()))
                      ).pack(anchor="w")
        ctk.CTkLabel(sec, text="Viene activado: al encender el PC la app arranca en segundo plano, sólo con sus "
                               "iconos en la bandeja. También lo puedes cambiar en Configuración > Aplicaciones > "
                               "Inicio.", font=fuente(12), text_color=P["SECUNDARIO"], wraplength=700,
                     justify="left").pack(anchor="w", pady=(6, 0))

    def _seccion_avisos(self, cont) -> None:
        """Aviso de batería baja: notificación de Windows + sonido (de la app, de Windows o propio)."""
        import sonidos
        sec = self._seccion(cont, "Aviso de batería baja",
                            "Una notificación de Windows con sonido, para que lo pongas a cargar a tiempo")
        va = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "avisos_bateria")))
        vc = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "aviso_critico")))
        ctk.CTkSwitch(sec, text="Avisarme al bajar del porcentaje de «Batería baja»", variable=va, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"],
                      command=lambda: self._set_global("avisos_bateria", bool(va.get()))).pack(anchor="w")
        ctk.CTkSwitch(sec, text="Otro aviso al llegar al 5 %", variable=vc, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"],
                      command=lambda: self._set_global("aviso_critico", bool(vc.get()))).pack(anchor="w", pady=(8, 0))

        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w", fill="x", pady=(16, 0))
        ctk.CTkLabel(fila, text="Sonido", font=fuente(13), text_color=P["TEXTO"], width=70, anchor="w").pack(side="left")
        opciones: dict[str, str] = {}
        v_son = ctk.StringVar()
        menu = ctk.CTkOptionMenu(fila, variable=v_son, values=["…"], width=250, height=34, corner_radius=10,
                                 font=fuente(13), dropdown_font=fuente(13), fg_color=P["SUPERFICIE"],
                                 button_color=P["SUPERFICIE_HOVER"], button_hover_color=P["BORDE_HOVER"],
                                 text_color=P["TEXTO"], dropdown_fg_color=P["SUPERFICIE"],
                                 dropdown_hover_color=P["SUPERFICIE_HOVER"], dropdown_text_color=P["TEXTO"])
        menu.pack(side="left")
        estilo = dict(height=34, corner_radius=10, font=fuente(13), fg_color=P["SUPERFICIE"],
                      hover_color=P["SUPERFICIE_HOVER"], border_width=1, border_color=P["BORDE"], text_color=P["TEXTO"])
        b_probar = ctk.CTkButton(fila, text="▶  Escuchar", width=110, **estilo)
        b_probar.pack(side="left", padx=(8, 0))
        b_agregar = ctk.CTkButton(fila, text="Agregar sonido…", width=140, **estilo)
        b_agregar.pack(side="left", padx=(8, 0))
        b_quitar = ctk.CTkButton(fila, text="Quitar", width=80, **estilo)

        fila_v = ctk.CTkFrame(sec, fg_color="transparent")
        fila_v.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(fila_v, text="Volumen", font=fuente(13), text_color=P["TEXTO"], width=70,
                     anchor="w").pack(side="left")
        l_vol = ctk.CTkLabel(fila_v, text="", font=fuente(15, "bold"), text_color=P["TEXTO"], width=60)
        l_vol.pack(side="right")
        vv = ctk.IntVar(value=int(ap.global_(self.cfg, "volumen_aviso")))

        def volumen(val):
            self.cfg["volumen_aviso"] = int(float(val))
            l_vol.configure(text=f"{self.cfg['volumen_aviso']} %")
            self._programar_guardado()

        deslizador = ctk.CTkSlider(fila_v, from_=0, to=100, number_of_steps=20, variable=vv, command=volumen,
                                   progress_color=P["ACENTO"], button_color=P["ACENTO"],
                                   button_hover_color=P["ACENTO_HOVER"], fg_color=P["PISTA"])
        deslizador.pack(side="left", fill="x", expand=True, padx=12)
        l_vol.configure(text=f"{vv.get()} %")

        def probar_volumen():
            if not ap.global_(self.cfg, "aviso_silencio"):
                sonidos.reproducir(opciones.get(v_son.get(), "ninguno"), ap.global_(self.cfg, "volumen_aviso"))

        # al soltar el deslizador se escucha cómo queda
        deslizador.bind("<ButtonRelease-1>", lambda e: probar_volumen(), add="+")
        fila_m = ctk.CTkFrame(sec, fg_color="transparent")
        fila_m.pack(anchor="w", pady=(10, 0))
        vs = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "aviso_silencio")))

        def silenciar():
            self._set_global("aviso_silencio", bool(vs.get()))
            estado = "disabled" if vs.get() else "normal"
            deslizador.configure(state=estado, button_color=P["APAGADO"] if vs.get() else P["ACENTO"],
                                 progress_color=P["APAGADO"] if vs.get() else P["ACENTO"])
            l_vol.configure(text="Mudo" if vs.get() else f"{int(ap.global_(self.cfg, 'volumen_aviso'))} %")
            b_vol.configure(state=estado)

        ctk.CTkSwitch(fila_m, text="Silenciar (solo la notificación, sin sonido)", variable=vs, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"], command=silenciar).pack(side="left")
        b_vol = ctk.CTkButton(fila_m, text="▶  Probar volumen", width=150, **estilo, command=probar_volumen)
        b_vol.pack(side="left", padx=(16, 0))
        silenciar() if vs.get() else None

        fila_p = ctk.CTkFrame(sec, fg_color="transparent")
        fila_p.pack(anchor="w", pady=(16, 0))
        ctk.CTkButton(fila_p, text="Probar aviso completo", width=200, height=36, corner_radius=10,
                      font=fuente(13, "bold"), fg_color=P["ACENTO"], hover_color=P["ACENTO_HOVER"],
                      text_color=texto_sobre_acento(),
                      command=lambda: rutas.avisar_ventana(rutas.EVENTO_PROBAR_AVISO)).pack(side="left")
        l_info = ctk.CTkLabel(fila_p, text="Muestra la notificación de Windows con el sonido elegido",
                              font=fuente(12), text_color=P["SECUNDARIO"])
        l_info.pack(side="left", padx=12)

        def refrescar(elegir: str | None = None):
            opciones.clear()
            for ident, nombre in sonidos.lista():
                opciones[nombre] = ident
            menu.configure(values=list(opciones))
            actual = elegir or ap.global_(self.cfg, "sonido_aviso")
            nombre = next((n for n, i in opciones.items() if i == actual), None)
            if nombre is None:                      # el sonido elegido ya no existe
                actual = sonidos.PREDETERMINADO
                nombre = next(n for n, i in opciones.items() if i == actual)
            v_son.set(nombre)
            if actual.startswith("propio:"):
                b_quitar.pack(side="left", padx=(8, 0))
            else:
                b_quitar.pack_forget()

        def elegir(nombre):
            ident = opciones.get(nombre, sonidos.PREDETERMINADO)
            self._set_global("sonido_aviso", ident)
            refrescar(ident)
            sonidos.reproducir(ident, ap.global_(self.cfg, "volumen_aviso"))

        def agregar():
            ruta = filedialog.askopenfilename(parent=self, title="Elige un sonido para el aviso",
                                              filetypes=[("Sonidos", "*.wav *.mp3 *.wma"), ("Todos", "*.*")])
            if not ruta:
                return
            try:
                ident = sonidos.agregar(ruta)
            except (OSError, ValueError) as e:
                l_info.configure(text=f"No se pudo agregar: {e}", text_color=P["PELIGRO_TEXTO"])
                return
            l_info.configure(text="Sonido agregado", text_color=P["SECUNDARIO"])
            elegir(next(n for n, i in sonidos.lista() if i == ident))

        def quitar():
            sonidos.quitar(ap.global_(self.cfg, "sonido_aviso"))
            self._set_global("sonido_aviso", sonidos.PREDETERMINADO)
            refrescar()

        menu.configure(command=elegir)
        b_probar.configure(command=lambda: sonidos.reproducir(opciones.get(v_son.get(), "ninguno"),
                                                              ap.global_(self.cfg, "volumen_aviso")))
        b_agregar.configure(command=agregar)
        b_quitar.configure(command=quitar)
        refrescar()

    def _set_global(self, clave: str, valor) -> None:
        self.cfg[clave] = valor
        self._programar_guardado()
        self._ensuciar("perifericos")

    # ========================================================= vista: acerca
    def ver_acerca(self) -> None:
        self._registrar(("acerca", None))
        self.vista = "acerca"
        self._marcar_nav("acerca")
        if not self._hay_pagina("acerca"):
            self._construir_acerca()
        self._mostrar("acerca")

    def _construir_acerca(self) -> None:
        cont = self._nueva_pagina("acerca")
        ctk.CTkLabel(cont, text="Acerca de", font=fuente(22, "bold"), text_color=P["TEXTO"]).pack(
            anchor="w", padx=28, pady=(24, 6))
        sec = self._seccion(cont, rutas.NOMBRE, "")
        for linea in (f"Versión {rutas.VERSION}",
                      "",
                      "Muestra la batería de tus periféricos en la bandeja del sistema.",
                      "Detecta cualquier dispositivo que informe su batería a Windows: Bluetooth,",
                      "periféricos USB que siguen el estándar HID, Logitech (receptores Unifying,",
                      "Bolt y Lightspeed), mandos de Xbox y DualSense, HyperX Cloud III y SCYROX.",
                      "Sólo lee el nivel de batería: no cambia ajustes ni instala controladores.",
                      "",
                      "Al pasar el puntero por un icono verás el porcentaje y las horas de uso."):
            ctk.CTkLabel(sec, text=linea, font=fuente(13), text_color=P["SECUNDARIO"], anchor="w").pack(anchor="w")
        ctk.CTkButton(sec, text="Abrir carpeta de datos", width=220, height=36, corner_radius=10,
                      font=fuente(13), fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"], border_width=1,
                      border_color=P["BORDE"], text_color=P["TEXTO"], command=lambda: os.startfile(rutas.DATOS)
                      ).pack(anchor="w", pady=(16, 0))

        sec = self._seccion(cont, "¿Un periférico no aparece o no se lee bien?",
                            "Crea un informe y mándaselo a quien te pasó la app")
        fila = ctk.CTkFrame(sec, fg_color="transparent")
        fila.pack(anchor="w")
        b_diag = ctk.CTkButton(fila, text="Crear informe de diagnóstico", width=240, height=36, corner_radius=10,
                               font=fuente(13), fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"],
                               border_width=1, border_color=P["BORDE"], text_color=P["TEXTO"],
                               text_color_disabled=P["APAGADO"])
        b_diag.pack(side="left")
        l_diag = ctk.CTkLabel(fila, text="", font=fuente(12), text_color=P["SECUNDARIO"])
        l_diag.pack(side="left", padx=12)
        ctk.CTkLabel(sec, text="Incluye la versión de Windows, los dispositivos que ve la app y lo que informan, "
                               "y el registro de errores. No incluye datos personales y no le envía nada a ningún "
                               "dispositivo: solo lee.", font=fuente(12), text_color=P["SECUNDARIO"],
                     wraplength=700, justify="left").pack(anchor="w", pady=(8, 0))

        def crear_informe():
            b_diag.configure(state="disabled", text="Creando… (puede tardar 2 min)")
            cola: queue.Queue = queue.Queue()

            def trabajo():
                try:
                    import diagnostico
                    cola.put(("ok", diagnostico.generar()))
                except Exception as e:      # noqa: BLE001
                    cola.put(("error", str(e)))
            threading.Thread(target=trabajo, daemon=True).start()

            def esperar():
                try:
                    tipo, dato = cola.get_nowait()
                except queue.Empty:
                    self.after(150, esperar)
                    return
                b_diag.configure(state="normal", text="Crear informe de diagnóstico")
                if tipo == "ok":
                    l_diag.configure(text="Listo: se abrió la carpeta con «diagnostico.txt»", text_color=P["SECUNDARIO"])
                    import subprocess
                    subprocess.Popen(["explorer", "/select,", dato])
                else:
                    l_diag.configure(text=f"No se pudo crear: {dato}", text_color=P["PELIGRO_TEXTO"])
            self.after(150, esperar)

        b_diag.configure(command=crear_informe)

    # ===================================================== vista: actualizaciones
    def ver_actualizaciones(self) -> None:
        self._registrar(("actualizaciones", None))
        self.vista = "actualizaciones"
        self._marcar_nav("actualizaciones")
        if not self._hay_pagina("actualizaciones"):
            self._construir_actualizaciones()
        self._mostrar("actualizaciones")
        if self._act["historial"] is None and self._act["estado"] not in ("buscando", "descargando", "instalando"):
            self.buscar_actualizacion()          # para tener las notas aunque ya se buscara

    def _construir_actualizaciones(self) -> None:
        cont = self._scroll(self._nueva_pagina("actualizaciones"))
        ctk.CTkLabel(cont, text="Actualizaciones", font=fuente(22, "bold"), text_color=P["TEXTO"]).pack(
            anchor="w", padx=28, pady=(24, 6))

        sec = self._seccion(cont, f"Versión instalada: {rutas.VERSION}", "")
        self.l_act = ctk.CTkLabel(sec, text="", font=fuente(15, "bold"), text_color=P["TEXTO"], anchor="w",
                                  justify="left")
        self.l_act.pack(anchor="w")
        self.l_act_det = ctk.CTkLabel(sec, text="", font=fuente(12), text_color=P["SECUNDARIO"], anchor="w",
                                      justify="left", wraplength=700)
        self.l_act_det.pack(anchor="w", pady=(2, 0))
        self.pb_act = ctk.CTkProgressBar(sec, height=8, corner_radius=4, progress_color=P["ACENTO"],
                                         fg_color=P["PISTA"])
        self.pb_act.set(0)
        self.b_act = ctk.CTkButton(sec, text="", width=230, height=38, corner_radius=10, font=fuente(13, "bold"),
                                   fg_color=P["ACENTO"], hover_color=P["ACENTO_HOVER"],
                                   text_color=texto_sobre_acento(), text_color_disabled=P["SECUNDARIO"],
                                   command=self._accion_actualizacion)
        self.b_act.pack(anchor="w", pady=(14, 0))
        va = ctk.BooleanVar(value=bool(ap.global_(self.cfg, "auto_actualizar")))
        ctk.CTkSwitch(sec, text="Actualizar automáticamente al abrir la app", variable=va, font=fuente(13),
                      text_color=P["TEXTO"], progress_color=P["ACENTO"],
                      command=lambda: self._set_global("auto_actualizar", bool(va.get()))).pack(anchor="w", pady=(16, 0))
        ctk.CTkLabel(sec, text="Al abrir la ventana se busca una versión nueva y, si la hay, se descarga, se verifica "
                               "y se instala sola; la app se cierra y vuelve a abrirse ya actualizada. "
                               "Tus ajustes no se tocan.",
                     font=fuente(12), text_color=P["SECUNDARIO"], wraplength=700, justify="left"
                     ).pack(anchor="w", pady=(4, 0))

        sec = self._seccion(cont, "Notas de las versiones", "Qué trae cada versión publicada")
        self.f_notas = ctk.CTkFrame(sec, fg_color="transparent")
        self.f_notas.pack(fill="x")
        self._notas_pintadas = None
        self._pintar_actualizacion()

    def _pintar_notas(self) -> None:
        hist = self._act["historial"]
        firma = (tuple((v.version, v.notas) for v in hist) if hist is not None else None, self._act["estado"])
        if getattr(self, "_notas_pintadas", None) == firma:
            return
        self._notas_pintadas = firma
        for w in self.f_notas.winfo_children():
            w.destroy()
        if hist is None:
            texto = ("No se pudieron cargar las notas: " + self._act["error"]) if self._act["estado"] == "error" \
                else "Cargando las notas…"
            ctk.CTkLabel(self.f_notas, text=texto, font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w")
            return
        if not hist:
            ctk.CTkLabel(self.f_notas, text="Todavía no hay versiones publicadas.", font=fuente(12),
                         text_color=P["SECUNDARIO"]).pack(anchor="w")
            return
        for v in hist:
            nueva = actualizador.es_mas_nueva(v.version)
            caja = ctk.CTkFrame(self.f_notas, fg_color=P["SUPERFICIE"], corner_radius=12, border_width=1,
                                border_color=P["ACENTO"] if nueva else P["SUPERFICIE"])
            caja.pack(fill="x", pady=(0, 8))
            cab = ctk.CTkFrame(caja, fg_color="transparent")
            cab.pack(fill="x", padx=16, pady=(12, 2))
            ctk.CTkLabel(cab, text=f"Versión {v.version}", font=fuente(14, "bold"), text_color=P["TEXTO"]
                         ).pack(side="left")
            etiqueta = "Nueva" if nueva else ("Instalada" if v.version == rutas.VERSION else "")
            if etiqueta:
                ctk.CTkLabel(cab, text=f"  {etiqueta}  ", font=fuente(11, "bold"), corner_radius=8, height=20,
                             fg_color=P["ACENTO"] if nueva else P["PISTA"],
                             text_color=texto_sobre_acento() if nueva else P["TEXTO"]).pack(side="left", padx=10)
            ctk.CTkLabel(cab, text=v.fecha, font=fuente(12), text_color=P["SECUNDARIO"]).pack(side="right")
            ctk.CTkLabel(caja, text=v.notas or "Sin notas.", font=fuente(13), text_color=P["SECUNDARIO"],
                         anchor="w", justify="left", wraplength=680).pack(anchor="w", padx=16, pady=(2, 14))

    # ======================================================== actualizaciones
    def _al_abrir_actualizaciones(self) -> None:
        """Al volver a mostrar la ventana: si hay una versión nueva, se instala (si está en
        automático); si hace más de una hora que no se mira, se vuelve a mirar."""
        estado = self._act["estado"]
        if estado == "disponible" and ap.global_(self.cfg, "auto_actualizar") and actualizador.se_puede_instalar():
            self._descargar_actualizacion()
        elif estado not in ("buscando", "descargando", "instalando") and \
                time.time() - self._act["comprobado"] > 3600:
            self.buscar_actualizacion(auto=True)

    def buscar_actualizacion(self, auto: bool = False) -> None:
        if self._act["estado"] in ("buscando", "descargando", "instalando"):
            return
        if not actualizador.configurado():
            self._act["estado"] = "sin_repo"
            self._pintar_actualizacion()
            return
        self._act.update(estado="buscando", error="", auto=auto)
        self._pintar_actualizacion()

        def trabajo():
            try:
                self._cola_act.put(("encontrada", actualizador.consultar()))
            except Exception as e:      # noqa: BLE001  (sin red, GitHub caído...)
                self._cola_act.put(("error", str(e) or "No se pudo comprobar."))
        threading.Thread(target=trabajo, daemon=True).start()
        self.after(150, self._atender_actualizacion)

    def _descargar_actualizacion(self) -> None:
        nov = self._act["novedad"]
        self._act.update(estado="descargando", bajado=0, total=nov.tamano, error="")
        self._pintar_actualizacion()

        def trabajo():
            try:
                ruta = actualizador.descargar(nov, lambda b, t: self._cola_act.put(("progreso", (b, t))))
                self._cola_act.put(("descargada", ruta))
            except Exception as e:      # noqa: BLE001
                self._cola_act.put(("error", str(e) or "La descarga falló."))
        threading.Thread(target=trabajo, daemon=True).start()
        self.after(150, self._atender_actualizacion)

    def _atender_actualizacion(self) -> None:
        try:
            while True:
                tipo, dato = self._cola_act.get_nowait()
                if tipo == "encontrada":
                    nov, hist = dato
                    self._act.update(estado="disponible" if nov else "al_dia", novedad=nov, historial=hist,
                                     comprobado=time.time())
                    if nov and self._act["auto"] and ap.global_(self.cfg, "auto_actualizar") \
                            and actualizador.se_puede_instalar():
                        self._descargar_actualizacion()     # automática: sin pulsar nada
                        return
                elif tipo == "progreso":
                    self._act["bajado"], self._act["total"] = dato
                elif tipo == "descargada":
                    self._act.update(estado="instalando", ruta=dato)
                    self.after(1200, self._instalar_actualizacion)
                elif tipo == "error":
                    self._act.update(estado="error", error=dato, comprobado=time.time())
        except queue.Empty:
            pass
        self._pintar_actualizacion()
        if self._act["estado"] in ("buscando", "descargando"):
            self.after(150, self._atender_actualizacion)

    def _instalar_actualizacion(self) -> None:
        try:
            actualizador.instalar(self._act["ruta"])
        except Exception as e:      # noqa: BLE001
            self._act.update(estado="error", error=str(e))
            self._pintar_actualizacion()
            return
        self.destroy()              # la versión nueva se abre sola

    def _accion_actualizacion(self) -> None:
        estado = self._act["estado"]
        if estado == "disponible":
            if actualizador.se_puede_instalar():
                self._descargar_actualizacion()
            else:
                import webbrowser
                webbrowser.open(f"https://github.com/{rutas.REPO_ACTUALIZACIONES}/releases/latest")
        elif estado == "error" and self._act["novedad"] is not None:
            self._descargar_actualizacion()
        else:
            self.buscar_actualizacion()

    def _pintar_actualizacion(self) -> None:
        a = self._act
        nov = a["novedad"]
        estado = a["estado"]
        pct = a["bajado"] / a["total"] if estado == "descargando" and a["total"] else (1 if estado == "instalando" else 0)

        # ---- barra lateral: "!" si hay versión nueva y barra de descarga mientras se actualiza
        aviso = getattr(self, "aviso_act", None)
        if aviso is not None and aviso.winfo_exists():
            if nov and estado in ("disponible", "error"):
                aviso.place(relx=1.0, x=-12, rely=0.5, anchor="e")
            else:
                aviso.place_forget()
            if estado in ("descargando", "instalando"):
                self.pb_lat.set(pct)
                self.l_lat.configure(text="Instalando…" if estado == "instalando" else f"{int(pct * 100)} %")
                if not self.f_descarga_lat.winfo_manager():
                    self.f_descarga_lat.grid(row=5, column=0, sticky="w", pady=(2, 2))
            elif self.f_descarga_lat.winfo_manager():
                self.f_descarga_lat.grid_remove()

        # ---- página Actualizaciones
        if not getattr(self, "l_act", None) or not self.l_act.winfo_exists():
            return
        textos = {
            "inicial": ("Buscando actualizaciones…", "", None),
            "sin_repo": ("Actualizaciones no configuradas",
                         "Esta copia no tiene configurado de dónde descargar actualizaciones.", None),
            "buscando": ("Buscando actualizaciones…", "", None),
            "al_dia": ("Tienes la última versión", "Brahttery hub está al día.", "Buscar actualizaciones"),
            "disponible": (f"Versión {nov.version if nov else ''} disponible",
                           "Pulsa el botón para instalarla: la app se cerrará y se abrirá actualizada.",
                           "Actualizar ahora" if actualizador.se_puede_instalar() else "Abrir página de descarga"),
            "descargando": ("Descargando la actualización…", "", None),
            "instalando": ("Instalando…", "Brahttery hub se cerrará y se abrirá actualizado.", None),
            "error": ("No se pudo actualizar", a["error"], "Reintentar"),
        }
        titulo, detalle, boton = textos.get(estado, ("", "", None))
        if estado == "descargando" and a["total"]:
            detalle = f"{a['bajado'] / 1e6:.1f} de {a['total'] / 1e6:.1f} MB ({int(pct * 100)} %)"
        self.l_act.configure(text=titulo, text_color=P["PELIGRO_TEXTO"] if estado == "error" else P["TEXTO"])
        self.l_act_det.configure(text=detalle)
        if estado in ("descargando", "instalando"):
            self.pb_act.set(pct)
            if not self.pb_act.winfo_manager():
                self.pb_act.pack(anchor="w", fill="x", pady=(12, 0), before=self.b_act)
        elif self.pb_act.winfo_manager():
            self.pb_act.pack_forget()
        espera = {"inicial": "Buscando…", "buscando": "Buscando…", "descargando": "Descargando…",
                  "instalando": "Instalando…", "sin_repo": "Buscar actualizaciones"}
        self.b_act.configure(text=boton or espera.get(estado, "…"), state="normal" if boton else "disabled",
                             fg_color=P["ACENTO"] if boton else P["SUPERFICIE"])
        if estado not in ("descargando", "instalando"):
            self._pintar_notas()

    # ============================================================== guardar
    def _programar_guardado(self) -> None:
        if self._guardado:
            self.after_cancel(self._guardado)
        self._guardado = self.after(300, self._guardar)

    def _guardar(self) -> None:
        self._guardado = None
        for clave, disp in list(self.cfg["dispositivos"].items()):
            for k in [k for k, v in disp.items() if v in ("", None)]:
                del disp[k]
            if not disp:
                del self.cfg["dispositivos"][clave]
        try:
            ap.guardar_config(self.cfg)
        except Exception as e:      # noqa: BLE001  sin esto, la bandeja nunca se entera del cambio
            try:
                with open(rutas.RUTA_LOG, "a", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + f"Ventana: no se pudo guardar config.json: {e!r}\n")
            except OSError:
                pass


def main() -> None:
    try:    # identidad propia en la barra de tareas (no agrupar con Python)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(rutas.ID)
    except Exception:
        pass
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, rutas.MUTEX_VENTANA)
    if ctypes.get_last_error() == 183:       # ya en marcha (quizá oculta): que se muestre
        if rutas.avisar_ventana(rutas.EVENTO_MOSTRAR):
            return
        # La que está abierta es de una versión anterior a la 1.2.0 (no entiende el aviso):
        # se cierra y se abre esta, que es la actual.
        u32 = ctypes.WinDLL("user32")
        u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
        u32.FindWindowW.restype = wt.HWND
        u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        fin = time.monotonic() + 6
        while time.monotonic() < fin and (h := u32.FindWindowW(None, TITULO)):
            u32.PostMessageW(h, 0x0010, 0, 0)          # WM_CLOSE
            time.sleep(0.3)
    App().mainloop()


if __name__ == "__main__":
    main()
