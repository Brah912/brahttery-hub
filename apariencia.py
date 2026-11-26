"""Apariencia de los iconos: configuración (config.json) y dibujo.

Lo usan tanto la bandeja (bateria_perifericos.pyw) como la ventana de
personalización (configurar.pyw), así la vista previa es idéntica al icono real.

config.json:
{
  "umbral_baja": 20,                 # % por debajo del cual se usa el color de batería baja
  "color_baja": "#ff6363",           # o "auto"
  "punto_carga": true,               # punto verde mientras carga
  "tamano_icono": 92,                # % del hueco que ocupa el dibujo
  "dispositivos": {
    "<clave>": {
      "nombre": "Mi ratón",          # vacío = nombre original
      "icono": "glifo:E962",         # o "imagen:C:/ruta/icono.png"
      "tenir": true,                 # imágenes: pintarlas con el color elegido
      "color": "auto",               # o "#rrggbb"
      "autonomia": 80,               # horas con batería llena (vacío = valor por defecto)
      "oculto": false
    }
  },
  "autonomia_horas": {...}           # (compatibilidad) autonomía por clave o tipo
}
"""
from __future__ import annotations

import json
import os
import winreg

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import modelos
import rutas

RUTA_CONFIG = rutas.RUTA_CONFIG
RUTA_ESTADO = rutas.RUTA_ESTADO

GLIFO_POR_TIPO = {
    "raton": "E962", "teclado": "E765", "cascos": "E7F6", "auriculares": "E7F6",
    "mando": "E7FC", "altavoz": "E7F5", "otro": "E702",
}

GALERIA = [
    ("E962", "Ratón"), ("E765", "Teclado"), ("E92E", "Teclado 2"), ("E7F6", "Cascos"),
    ("E95B", "Cascos con micro"), ("E7FC", "Mando"), ("E7F5", "Altavoz"), ("E93C", "Altavoz 2"),
    ("E720", "Micrófono"), ("E8EA", "Móvil"), ("EE56", "Lápiz"), ("E916", "Reloj"),
    ("E7F4", "Monitor"), ("E714", "Cámara"), ("E702", "Bluetooth"), ("E8D6", "Música"),
    ("EC4F", "Nota"), ("E83F", "Batería"), ("E945", "Rayo"), ("E734", "Estrella"),
    ("E00B", "Corazón"), ("E899", "Cara"), ("E9D9", "Actividad"), ("E772", "Dispositivos"),
]

PREDETERMINADOS = {"umbral_baja": 20, "color_baja": "auto", "punto_carga": True, "tamano_icono": 92,
                   "estilo_iconos": "minimalista", "tema_app": "oscuro", "opacidad_app": 100,
                   "mostrar_icono": "icono", "color_texto": "auto", "auto_actualizar": True,
                   "iconos_visibles": True, "liberar_memoria": True,
                   "avisos_bateria": True, "aviso_critico": True, "sonido_aviso": "app:campanita",
                   "volumen_aviso": 80, "aviso_silencio": False}
# Qué se ve en el icono de la bandeja
MODOS_ICONO = ("icono", "porcentaje", "tiempo")
ACENTO_REALISTA = (76, 194, 255, 255)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def cargar_config() -> dict:
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_config(cfg: dict) -> None:
    tmp = RUTA_CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RUTA_CONFIG)


def global_(cfg: dict, clave: str):
    return cfg.get(clave, PREDETERMINADOS[clave])


def icono_por_defecto(tipo: str) -> str:
    if tipo in modelos.MODELO_POR_TIPO:
        return "modelo:" + modelos.MODELO_POR_TIPO[tipo]
    return "glifo:" + GLIFO_POR_TIPO.get(tipo, "E702")


def ajustes_de(cfg: dict, clave: str, tipo: str) -> dict:
    a = {"nombre": "", "icono": icono_por_defecto(tipo), "tenir": True, "color": "auto", "autonomia": None,
         "oculto": False, "estilo": "general", "acabado": "grafito", "mostrar": "general", "color_texto": None}
    a.update({k: v for k, v in cfg.get("dispositivos", {}).get(clave, {}).items() if v is not None})
    return a


def cargar_estado() -> dict:
    try:
        with open(RUTA_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_estado(estado: dict) -> None:
    tmp = RUTA_ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RUTA_ESTADO)


# --------------------------------------------------------------------------
# Dibujo
# --------------------------------------------------------------------------
def tema_claro() -> bool:
    """Color de la barra de tareas (SystemUsesLightTheme)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


def hex_a_rgba(h: str) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255


_fuentes: dict[int, ImageFont.FreeTypeFont] = {}


def _fuente_iconos(tam: int):
    if tam not in _fuentes:
        win = os.environ.get("WINDIR", r"C:\Windows")
        for n in ("SegoeIcons.ttf", "segmdl2.ttf"):
            try:
                _fuentes[tam] = ImageFont.truetype(os.path.join(win, "Fonts", n), tam)
                break
            except OSError:
                continue
        else:
            _fuentes[tam] = ImageFont.load_default()
    return _fuentes[tam]


_fuentes_texto: dict[int, ImageFont.FreeTypeFont] = {}


def _fuente_texto(px: int):
    """Segoe UI Variable Bold (viene con Windows 11): cifras redondeadas, con un corte pensado
    para tamaños chicos. En Windows 10, Segoe UI Bold."""
    if px not in _fuentes_texto:
        win = os.environ.get("WINDIR", r"C:\Windows")
        try:
            f = ImageFont.truetype(os.path.join(win, "Fonts", "SegUIVar.ttf"), px)
            f.set_variation_by_name("Bold Small")
        except (OSError, ValueError):
            try:
                f = ImageFont.truetype(os.path.join(win, "Fonts", "segoeuib.ttf"), px)
            except OSError:
                f = ImageFont.load_default()
        _fuentes_texto[px] = f
    return _fuentes_texto[px]


def modo_icono(cfg: dict, ajustes: dict) -> str:
    """"icono", "porcentaje" o "tiempo" (lo del periférico, o el de General)."""
    m = ajustes.get("mostrar", "general")
    return m if m in MODOS_ICONO else global_(cfg, "mostrar_icono")


def color_texto(cfg: dict, ajustes: dict) -> str:
    return ajustes.get("color_texto") or global_(cfg, "color_texto")


def tiempo_corto(horas: float) -> str:
    """Formato para un icono de 16 px: 45m, 12h, 3d."""
    if horas < 1:
        return f"{max(1, round(horas * 60))}m"
    if horas < 48:
        return f"{round(horas)}h"
    return f"{round(horas / 24)}d"


def texto_icono(cfg: dict, ajustes: dict, bateria: int, cargando: bool, horas: float | None) -> str | None:
    """Lo que se escribe en el icono según el modo elegido (None = sólo el dibujo).
    Mientras carga no hay tiempo restante que mostrar: se ve el porcentaje."""
    modo = modo_icono(cfg, ajustes)
    if modo == "porcentaje" or (modo == "tiempo" and (cargando or horas is None)):
        return str(max(0, min(100, int(bateria))))
    if modo == "tiempo":
        return tiempo_corto(horas)
    return None


def _imagen_teñida(ruta: str, lado: int, color, tenir: bool) -> Image.Image | None:
    try:
        src = Image.open(ruta).convert("RGBA")
    except Exception:
        return None
    src.thumbnail((lado, lado), Image.LANCZOS)
    if tenir:
        capa = Image.new("RGBA", src.size, color)
        capa.putalpha(src.getchannel("A"))
        src = capa
    return src


def _icono_con_texto(tipo: str, bateria: int, cargando: bool, ajustes: dict, cfg: dict, tam: int, claro: bool,
                     texto: str, tinta: tuple) -> Image.Image:
    """El dibujo entero y grande, y el número encima, abajo a la derecha, con una sombra suave
    y redondeada detrás: el dibujo se sigue viendo (solo un poco atenuado bajo el número) y el
    número se lee bien sobre él. Se dibuja a 4x y se reduce para que todo quede suave."""
    k = 4
    S = tam * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    lado = max(8, round(tam * 0.86))
    dibujo = dibujar_icono(tipo, bateria, False, ajustes, cfg, lado, claro)
    img.alpha_composite(dibujo.resize((lado * k, lado * k), Image.LANCZOS))

    px = round(S * 0.60)
    while px > 8 and _ancho_texto(texto, px) > S * 0.92:
        px -= 1
    f = _fuente_texto(px)
    # el número, pegado abajo a la derecha sin salirse
    x0, y0, x1, y1 = ImageDraw.Draw(img).textbbox((0, 0), texto, font=f)
    pos = (S - x1 - k * 0.3, S - y1 - k * 0.3)
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).text(pos, texto, font=f, fill=255)
    # sombra: el número engordado y difuminado, en el tono contrario (oscura sobre barra oscura)
    # (el engordado se hace a 1x: con un filtro grande sobre la imagen a 4x tardaba ~0,7 s por icono)
    chica = mascara.resize((tam, tam), Image.BILINEAR).filter(ImageFilter.MaxFilter(_impar(tam * 0.16)))
    sombra = chica.resize((S, S), Image.BILINEAR).filter(ImageFilter.GaussianBlur(S * 0.06))
    sombra = sombra.point(lambda v: min(255, v * 235 // 255))
    tono = (246, 246, 248) if claro else (16, 16, 20)
    capa = Image.new("RGBA", (S, S), tono + (0,))
    capa.putalpha(sombra)
    img.alpha_composite(capa)
    numero = Image.new("RGBA", (S, S), tuple(tinta[:3]) + (0,))
    numero.putalpha(mascara)
    img.alpha_composite(numero)
    if cargando and global_(cfg, "punto_carga"):    # el punto de carga pasa arriba a la derecha
        r = S * 0.13
        ImageDraw.Draw(img).ellipse((S - 2 * r, 0, S, 2 * r), fill=(16, 160, 16, 255) if claro else (108, 203, 95, 255))
    return img.resize((tam, tam), Image.LANCZOS)


def _impar(n: float) -> int:
    n = max(3, int(round(n)))
    return n if n % 2 else n + 1


def _ancho_texto(texto: str, px: int) -> int:
    x0, _y0, x1, _y1 = _fuente_texto(px).getbbox(texto)
    return x1 - x0


def dibujar_icono(tipo: str, bateria: int, cargando: bool, ajustes: dict, cfg: dict,
                  tam: int, claro: bool, texto: str | None = None) -> Image.Image:
    """Devuelve el icono como imagen RGBA tam x tam (fondo transparente).
    Con texto (porcentaje o tiempo, ver texto_icono) el dibujo va pequeño arriba a la
    izquierda y el texto grande abajo a la derecha."""
    auto = (0, 0, 0, 255) if claro else (255, 255, 255, 255)
    baja = bateria <= int(global_(cfg, "umbral_baja")) and not cargando
    color_bajo = None
    if baja:
        cb = global_(cfg, "color_baja")
        color_bajo = ((196, 43, 28, 255) if claro else (255, 99, 99, 255)) if cb == "auto" else hex_a_rgba(cb)
        color = color_bajo
    else:
        color = auto if ajustes["color"] == "auto" else hex_a_rgba(ajustes["color"])

    if texto:
        return _icono_con_texto(tipo, bateria, cargando, ajustes, cfg, tam, claro, texto,
                                color_bajo or (auto if color_texto(cfg, ajustes) == "auto"
                                               else hex_a_rgba(color_texto(cfg, ajustes))))

    s = tam * 4                         # se dibuja a 4x y se reduce: bordes suaves
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    lado = round(s * int(global_(cfg, "tamano_icono")) / 100)
    icono = ajustes["icono"]
    pintado = False
    if icono.startswith("modelo:"):
        estilo = ajustes.get("estilo", "general")
        if estilo not in ("realista", "minimalista"):
            estilo = global_(cfg, "estilo_iconos")
        if estilo == "realista":   # el color elegido va en el acento (luces, rueda, logo)
            if baja:
                tinte = color
            elif ajustes["color"] == "auto":
                tinte = ACENTO_REALISTA
            else:
                tinte = hex_a_rgba(ajustes["color"])
        else:
            tinte = color
        pieza = modelos.dibujar(icono[7:], estilo, lado, tinte, ajustes.get("acabado", "grafito"))
        img.alpha_composite(pieza, ((s - lado) // 2, (s - lado) // 2))
        pintado = True
    elif icono.startswith("imagen:"):
        pieza = _imagen_teñida(icono[7:], lado, color, ajustes.get("tenir", True) or baja)
        if pieza is not None:
            img.alpha_composite(pieza, ((s - pieza.width) // 2, (s - pieza.height) // 2))
            pintado = True
    if not pintado:
        codigo = icono[6:] if icono.startswith("glifo:") else GLIFO_POR_TIPO.get(tipo, "E702")
        ImageDraw.Draw(img).text((s / 2, s / 2), chr(int(codigo, 16)), font=_fuente_iconos(lado),
                                 fill=color, anchor="mm")
    if cargando and global_(cfg, "punto_carga"):
        r = s * 0.17
        ImageDraw.Draw(img).ellipse((s - 2 * r, s - 2 * r, s, s),
                                    fill=(16, 160, 16, 255) if claro else (108, 203, 95, 255))
    return img.resize((tam, tam), Image.LANCZOS)
