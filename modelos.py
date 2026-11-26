"""Diseños de periféricos dibujados por código, en dos estilos.

  * minimalista: trazo de un solo color (como los iconos de Windows).
  * realista: volumen con degradado, sombra, brillo y un detalle de color (acento).

Cada modelo se describe con primitivas en una caja de 100 x 100:
  ("rr", x0, y0, x1, y1, radio)        rectángulo redondeado
  ("el", x0, y0, x1, y1)               elipse
  ("pl", [(x, y), ...])                polígono
  ("ln", [(x, y), ...], grosor)        línea
  ("ar", x0, y0, x1, y1, ini, fin, g)  arco
Grupos: cuerpo (se unen en una silueta), piezas (paneles/teclas), detalles (líneas),
huecos (zonas oscuras) y acento (partes de color).
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _teclas(x0, y0, x1, y1, filas, cols, hueco=1.6, espacio=True):
    res = []
    alto = (y1 - y0 - hueco * (filas - 1)) / filas
    ancho = (x1 - x0 - hueco * (cols - 1)) / cols
    for f in range(filas):
        yy = y0 + f * (alto + hueco)
        if espacio and f == filas - 1:
            # fila inferior: teclas laterales + barra espaciadora
            n = max(2, cols // 4)
            for c in range(n):
                xx = x0 + c * (ancho + hueco)
                res.append(("rr", xx, yy, xx + ancho, yy + alto, 1))
            xs = x0 + n * (ancho + hueco)
            xe = x1 - n * (ancho + hueco)
            res.append(("rr", xs, yy, xe - hueco, yy + alto, 1))
            for c in range(n):
                xx = x1 - (c + 1) * ancho - c * hueco
                res.append(("rr", xx, yy, xx + ancho, yy + alto, 1))
            continue
        for c in range(cols):
            xx = x0 + c * (ancho + hueco)
            res.append(("rr", xx, yy, xx + ancho, yy + alto, 1))
    return res


def _rejilla(x0, y0, x1, y1, filas, cols, r):
    res = []
    for f in range(filas):
        for c in range(cols):
            cx = x0 + (x1 - x0) * (c + 0.5) / cols + (r * 0.9 if f % 2 else 0)
            cy = y0 + (y1 - y0) * (f + 0.5) / filas
            if cx + r <= x1 + r:
                res.append(("el", cx - r, cy - r, cx + r, cy + r))
    return res


def _espejo(prims):
    out = []
    for p in prims:
        k = p[0]
        if k in ("rr", "el"):
            out.append((k, 100 - p[3], p[2], 100 - p[1], p[4], *p[5:]))
        elif k == "pl":
            out.append(("pl", [(100 - x, y) for x, y in p[1]]))
        elif k == "ln":
            out.append(("ln", [(100 - x, y) for x, y in p[1]], p[2]))
    return out


_buds_izq = [("el", 10, 22, 40, 50), ("rr", 20, 40, 31, 86, 5.5)]

MODELOS: dict[str, dict] = {
    # ------------------------------------------------------------------ ratones
    "raton_clasico": {
        "nombre": "Clásico", "tipo": "raton",
        "cuerpo": [("el", 26, 4, 74, 56), ("rr", 26, 28, 74, 96, 24)],
        "detalles": [("ln", [(50, 5), (50, 38)], 2.2), ("ar", 26, 22, 74, 54, 20, 160, 2.2)],
        "acento": [("rr", 46.5, 13, 53.5, 29, 3.5)],
    },
    "raton_gaming": {
        "nombre": "Gaming", "tipo": "raton",
        "cuerpo": [("el", 24, 6, 76, 60), ("rr", 25, 30, 75, 95, 21), ("el", 17, 42, 34, 82)],
        "piezas": [("rr", 19, 46, 25, 54, 2), ("rr", 19, 56, 25, 64, 2)],
        "detalles": [("ln", [(50, 7), (50, 40)], 2.2), ("ln", [(28, 40), (72, 40)], 2.0)],
        "acento": [("rr", 46.5, 14, 53.5, 30, 3.5), ("rr", 36, 84, 64, 88.5, 2.2)],
    },
    "raton_ligero": {
        "nombre": "Ultraligero", "tipo": "raton",
        "cuerpo": [("el", 29, 4, 71, 50), ("rr", 29, 24, 71, 96, 21)],
        "detalles": [("ln", [(50, 5), (50, 36)], 2.2)],
        "huecos": _rejilla(34, 44, 66, 90, 5, 4, 2.6),
        "acento": [("rr", 46.5, 12, 53.5, 27, 3.5)],
    },
    "raton_vertical": {
        "nombre": "Vertical", "tipo": "raton",
        "cuerpo": [("pl", [(18, 88), (22, 46), (36, 18), (56, 10), (74, 18), (84, 44), (84, 88)]),
                   ("rr", 18, 70, 84, 92, 8)],
        "piezas": [("pl", [(38, 22), (56, 14), (72, 21), (66, 34), (44, 36)])],
        "detalles": [("ln", [(55, 15), (55, 35)], 2.0), ("ln", [(22, 60), (82, 60)], 1.6)],
        "acento": [("el", 28, 48, 38, 58)],
    },
    # ----------------------------------------------------------------- teclados
    "teclado_completo": {
        "nombre": "Completo", "tipo": "teclado",
        "cuerpo": [("rr", 3, 30, 97, 72, 6)],
        "piezas": _teclas(7, 35, 74, 68, 4, 11) + _teclas(77, 35, 93, 68, 4, 3, espacio=False),
        "acento": [("rr", 80, 31.5, 92, 33.5, 1)],
    },
    "teclado_75": {
        "nombre": "Compacto 75 %", "tipo": "teclado",
        "cuerpo": [("rr", 9, 26, 91, 76, 7)],
        "piezas": _teclas(13, 39, 87, 72, 4, 10) + _teclas(13, 31, 76, 36, 1, 9, espacio=False),
        "acento": [("el", 79, 29, 87, 37)],
    },
    "teclado_60": {
        "nombre": "Mini 60 %", "tipo": "teclado",
        "cuerpo": [("rr", 13, 32, 87, 70, 6)],
        "piezas": _teclas(17, 36, 83, 66, 4, 9),
        "acento": [("rr", 20, 67, 80, 68.6, 0.8)],
    },
    # ------------------------------------------------------------------ cascos
    "cascos_gaming": {
        "nombre": "Gaming con micro", "tipo": "cascos",
        "cuerpo": [("ar", 15, 8, 85, 82, 180, 360, 9), ("rr", 12, 44, 34, 86, 10), ("rr", 66, 44, 88, 86, 10),
                   ("ln", [(22, 80), (28, 92), (44, 94)], 4)],
        "piezas": [("rr", 30, 50, 36, 80, 3), ("rr", 64, 50, 70, 80, 3)],
        "acento": [("el", 17, 57, 29, 71), ("el", 71, 57, 83, 71), ("el", 42, 90, 50, 98)],
    },
    "cascos_estudio": {
        "nombre": "Estudio", "tipo": "cascos",
        "cuerpo": [("ar", 18, 6, 82, 76, 180, 360, 6), ("el", 11, 40, 37, 90), ("el", 63, 40, 89, 90),
                   ("rr", 19, 34, 25, 46, 2), ("rr", 75, 34, 81, 46, 2)],
        "piezas": [("el", 17, 48, 31, 82), ("el", 69, 48, 83, 82)],
        "acento": [("rr", 46, 4.5, 54, 8.5, 2)],
    },
    "cascos_ligeros": {
        "nombre": "Ligeros", "tipo": "cascos",
        "cuerpo": [("ar", 20, 12, 80, 80, 180, 360, 4.5), ("el", 13, 50, 37, 80), ("el", 63, 50, 87, 80)],
        "detalles": [("el", 19, 56, 31, 74), ("el", 69, 56, 81, 74)],
        "acento": [("el", 22.5, 61.5, 27.5, 68.5), ("el", 72.5, 61.5, 77.5, 68.5)],
    },
    # ------------------------------------------------------------- auriculares
    "buds_tallo": {
        "nombre": "Con tallo", "tipo": "auriculares",
        "cuerpo": _buds_izq + _espejo(_buds_izq),
        "piezas": [("el", 15, 27, 31, 43), ("el", 69, 27, 85, 43)],
        "acento": [("rr", 23, 70, 28, 80, 2.5), ("rr", 72, 70, 77, 80, 2.5)],
    },
    "buds_redondos": {
        "nombre": "Redondos", "tipo": "auriculares",
        "cuerpo": [("el", 8, 22, 48, 62), ("el", 52, 38, 92, 78)],
        "piezas": [("el", 15, 29, 41, 55), ("el", 59, 45, 85, 71)],
        "acento": [("el", 24, 38, 32, 46), ("el", 68, 54, 76, 62)],
    },
    "buds_estuche": {
        "nombre": "Estuche", "tipo": "auriculares",
        "cuerpo": [("rr", 14, 26, 86, 82, 26)],
        "detalles": [("ln", [(16, 46), (84, 46)], 2.0)],
        "acento": [("el", 47, 60, 53, 66)],
    },
    # ------------------------------------------------------------------- mandos
    "mando_asimetrico": {
        "nombre": "Asimétrico", "tipo": "mando",
        "cuerpo": [("el", 4, 30, 40, 92), ("el", 60, 30, 96, 92), ("rr", 16, 26, 84, 66, 18)],
        "piezas": [("el", 20, 34, 34, 48), ("el", 56, 52, 70, 66)],
        "detalles": [("ln", [(37, 53), (37, 65)], 3.2), ("ln", [(31, 59), (43, 59)], 3.2)],
        "acento": [("el", 71, 31, 77, 37), ("el", 77, 37, 83, 43), ("el", 65, 37, 71, 43), ("el", 71, 43, 77, 49),
                   ("el", 46, 28, 54, 36)],
    },
    "mando_simetrico": {
        "nombre": "Simétrico", "tipo": "mando",
        "cuerpo": [("el", 4, 30, 38, 94), ("el", 62, 30, 96, 94), ("rr", 14, 24, 86, 66, 16)],
        "piezas": [("rr", 37, 28, 63, 46, 4), ("el", 30, 52, 44, 66), ("el", 56, 52, 70, 66)],
        "detalles": [("ln", [(22, 34), (22, 46)], 3.2), ("ln", [(16, 40), (28, 40)], 3.2)],
        "acento": [("rr", 40, 25.5, 60, 27.5, 1), ("el", 74, 31, 80, 37), ("el", 80, 37, 86, 43),
                   ("el", 68, 37, 74, 43), ("el", 74, 43, 80, 49)],
    },
    "mando_retro": {
        "nombre": "Retro", "tipo": "mando",
        "cuerpo": [("rr", 6, 32, 94, 70, 17)],
        "detalles": [("ln", [(24, 42), (24, 60)], 4), ("ln", [(15, 51), (33, 51)], 4),
                     ("ln", [(42, 56), (48, 56)], 2.5), ("ln", [(52, 56), (58, 56)], 2.5)],
        "acento": [("el", 66, 50, 76, 60), ("el", 78, 42, 88, 52)],
    },
    # ---------------------------------------------------------------- altavoces
    "altavoz_portatil": {
        "nombre": "Portátil", "tipo": "altavoz",
        "cuerpo": [("rr", 10, 24, 90, 78, 27)],
        "huecos": _rejilla(22, 32, 78, 70, 5, 9, 1.6),
        "acento": [("rr", 40, 47, 60, 55, 4)],
    },
    "altavoz_torre": {
        "nombre": "Torre", "tipo": "altavoz",
        "cuerpo": [("rr", 26, 6, 74, 94, 9)],
        "piezas": [("el", 32, 44, 68, 80), ("el", 41, 16, 59, 34)],
        "acento": [("el", 45, 57, 55, 67), ("el", 47.5, 22.5, 52.5, 27.5)],
    },
    "altavoz_redondo": {
        "nombre": "Redondo", "tipo": "altavoz",
        "cuerpo": [("el", 12, 12, 88, 88)],
        "detalles": [("el", 24, 24, 76, 76), ("el", 35, 35, 65, 65)],
        "acento": [("el", 44, 44, 56, 56)],
    },
}

MODELO_POR_TIPO = {
    "raton": "raton_gaming", "teclado": "teclado_75", "cascos": "cascos_gaming",
    "auriculares": "buds_tallo", "mando": "mando_asimetrico", "altavoz": "altavoz_portatil",
}

ACABADOS = {
    #            cuerpo arriba     cuerpo abajo     piezas arriba     piezas abajo     detalles
    "grafito": ((86, 89, 98), (30, 31, 36), (104, 107, 117), (46, 47, 54), (14, 14, 17)),
    "blanco": ((253, 253, 254), (196, 198, 205), (236, 237, 241), (184, 186, 194), (122, 124, 133)),
}


# --------------------------------------------------------------------------
# Dibujo
# --------------------------------------------------------------------------
def _dibujar(prims, S, relleno=True, trazo=0):
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    u = S / 100
    for p in prims:
        k = p[0]
        if k == "rr":
            caja = [p[1] * u, p[2] * u, p[3] * u, p[4] * u]
            if relleno:
                d.rounded_rectangle(caja, radius=p[5] * u, fill=255)
            else:
                d.rounded_rectangle(caja, radius=p[5] * u, outline=255, width=max(1, round(trazo)))
        elif k == "el":
            caja = [p[1] * u, p[2] * u, p[3] * u, p[4] * u]
            if relleno:
                d.ellipse(caja, fill=255)
            else:
                d.ellipse(caja, outline=255, width=max(1, round(trazo)))
        elif k == "pl":
            pts = [(x * u, y * u) for x, y in p[1]]
            if relleno:
                d.polygon(pts, fill=255)
            else:
                d.polygon(pts, outline=255, width=max(1, round(trazo)))
        elif k == "ln":
            g = (trazo or p[2] * u)
            pts = [(x * u, y * u) for x, y in p[1]]
            d.line(pts, fill=255, width=max(1, round(g)), joint="curve")
            r = g / 2
            for x, y in (pts[0], pts[-1]):
                d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        elif k == "ar":
            d.arc([p[1] * u, p[2] * u, p[3] * u, p[4] * u], p[5], p[6], fill=255, width=max(1, round(p[7] * u)))
    return m


def _erosion(m: Image.Image, px: float) -> Image.Image:
    """Encoge la silueta unos `px` píxeles (desenfoque + umbral: rápido a cualquier tamaño)."""
    if px <= 0.5:
        return m
    return m.filter(ImageFilter.GaussianBlur(px / 2.4)).point(lambda v: 255 if v >= 250 else 0)


def _degradado(S, arriba, abajo) -> Image.Image:
    col = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / max(1, S - 1)
        col.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(arriba, abajo)))
    return col.resize((S, S))


def _aclarar(c, f):
    return tuple(min(255, round(v + (255 - v) * f)) for v in c[:3])


def dibujar(modelo_id: str, estilo: str, S: int, color: tuple, acabado: str = "grafito") -> Image.Image:
    """Devuelve una imagen RGBA S x S. `color`: trazo (minimalista) o acento (realista)."""
    m = MODELOS.get(modelo_id) or MODELOS["raton_gaming"]
    cuerpo = _dibujar(m["cuerpo"], S)
    u = S / 100

    if estilo == "minimalista":
        g = 6.0 * u                                  # grosor del trazo
        alfa = ImageChops.subtract(cuerpo, _erosion(cuerpo, g))
        if m.get("piezas"):
            alfa = ImageChops.lighter(alfa, _dibujar(m["piezas"], S, relleno=False, trazo=g * 0.55))
        if m.get("detalles"):
            det = [p for p in m["detalles"] if p[0] == "ln"]
            otros = [p for p in m["detalles"] if p[0] != "ln"]
            alfa = ImageChops.lighter(alfa, _dibujar(det, S, trazo=g * 0.6))
            if otros:
                alfa = ImageChops.lighter(alfa, _dibujar(otros, S, relleno=False, trazo=g * 0.55))
        if m.get("huecos"):
            alfa = ImageChops.lighter(alfa, _dibujar(m["huecos"], S))
        if m.get("acento"):
            alfa = ImageChops.lighter(alfa, _dibujar(m["acento"], S))
        img = Image.new("RGBA", (S, S), tuple(color[:3]) + (255,))
        img.putalpha(alfa)
        return img

    # ---------------------------------------------------------------- realista
    c_arr, c_abj, p_arr, p_abj, c_det = ACABADOS.get(acabado, ACABADOS["grafito"])
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    sombra = Image.new("RGBA", (S, S), (0, 0, 0, 255))
    sombra.putalpha(cuerpo.filter(ImageFilter.GaussianBlur(3 * u)).point(lambda v: int(v * 0.45)))
    img.alpha_composite(sombra, (0, round(2.5 * u)))

    base = _degradado(S, c_arr, c_abj).convert("RGBA")
    base.putalpha(cuerpo)
    img.alpha_composite(base)

    borde = ImageChops.subtract(cuerpo, _erosion(cuerpo, 2.2 * u))       # contorno con volumen
    oscuro = Image.new("RGBA", (S, S), (0, 0, 0, 255))
    oscuro.putalpha(borde.point(lambda v: int(v * 0.35)))
    img.alpha_composite(oscuro)

    if m.get("piezas"):
        piezas = _dibujar(m["piezas"], S)
        pz = _degradado(S, p_arr, p_abj).convert("RGBA")
        pz.putalpha(piezas)
        img.alpha_composite(pz)
        filo = Image.new("RGBA", (S, S), (0, 0, 0, 255))
        filo.putalpha(ImageChops.subtract(piezas, _erosion(piezas, 1.2 * u)).point(lambda v: int(v * 0.45)))
        img.alpha_composite(filo)

    for grupo, col, alfa_k in (("detalles", c_det, 0.85), ("huecos", c_det, 1.0)):
        if m.get(grupo):
            prims = m[grupo]
            lineas = [p for p in prims if p[0] == "ln"]
            resto = [p for p in prims if p[0] != "ln"]
            a = _dibujar(lineas, S, trazo=None) if lineas else Image.new("L", (S, S), 0)
            if resto:
                a = ImageChops.lighter(a, _dibujar(resto, S, relleno=(grupo == "huecos"), trazo=1.8 * u))
            capa = Image.new("RGBA", (S, S), col + (255,))
            capa.putalpha(ImageChops.multiply(a, cuerpo).point(lambda v: int(v * alfa_k)))
            img.alpha_composite(capa)

    if m.get("acento"):
        ac = _dibujar(m["acento"], S)
        capa = _degradado(S, _aclarar(color, 0.35), tuple(color[:3])).convert("RGBA")
        capa.putalpha(ac)
        img.alpha_composite(capa)

    # brillo superior suave
    brillo = Image.new("RGBA", (S, S), (255, 255, 255, 255))
    grad = Image.linear_gradient("L").resize((S, S)).point(lambda v: int(max(0, 150 - v) * 0.45))
    brillo.putalpha(ImageChops.multiply(_erosion(cuerpo, 2.5 * u), grad))
    img.alpha_composite(brillo)
    return img
