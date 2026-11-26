"""Prototipos del icono de Brahttery hub.

Genera cada propuesta en prototipos_icono/ y una hoja comparativa
(prototipos_icono/hoja.png) con cada icono en grande, en tamaño de barra de
tareas (32 px) y de bandeja (16 px), sobre fondo oscuro y claro.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

import modelos

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prototipos_icono")
WIN = os.environ.get("WINDIR", r"C:\Windows")


def fuente(tam, negrita=True):
    for n in (("seguibl.ttf", "segoeuib.ttf") if negrita else ("segoeui.ttf",)):
        try:
            return ImageFont.truetype(os.path.join(WIN, "Fonts", n), tam)
        except OSError:
            pass
    return ImageFont.load_default()


def degradado(s, a, b, diagonal=False):
    if diagonal:   # se gira un degradado el doble de grande y se recorta el centro: sin bordes vacíos
        g = Image.linear_gradient("L").resize((s * 2, s * 2)).rotate(45, resample=Image.BICUBIC)
        g = g.crop((s // 2, s // 2, s // 2 + s, s // 2 + s))
    else:
        g = Image.linear_gradient("L").resize((s, s))
    ca = Image.new("RGBA", (s, s), a + (255,))
    cb = Image.new("RGBA", (s, s), b + (255,))
    return Image.composite(cb, ca, g)


def base(s, a, b, forma="squircle", diagonal=False):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    m = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(m)
    if forma == "circulo":
        d.ellipse((0, 0, s - 1, s - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.23, fill=255)
    img.paste(degradado(s, a, b, diagonal), (0, 0), m)
    return img


def bateria(d, u, x0, y0, x1, y1, color, grosor=6, nivel=None, barras=None, radio=9):
    d.rounded_rectangle((x0 * u, y0 * u, x1 * u, y1 * u), radius=radio * u, outline=color, width=round(grosor * u))
    alto = y1 - y0
    d.rounded_rectangle(((x1 + 1) * u, (y0 + alto * 0.3) * u, (x1 + 8) * u, (y1 - alto * 0.3) * u),
                        radius=3 * u, fill=color)
    m = grosor + 3
    if nivel is not None:
        xf = x0 + m + (x1 - x0 - 2 * m) * nivel
        d.rounded_rectangle(((x0 + m) * u, (y0 + m) * u, xf * u, (y1 - m) * u), radius=3 * u, fill=color)
    if barras:
        ancho = (x1 - x0 - 2 * m - (barras - 1) * 4) / barras
        for i in range(barras):
            bx = x0 + m + i * (ancho + 4)
            d.rounded_rectangle((bx * u, (y0 + m) * u, (bx + ancho) * u, (y1 - m) * u), radius=2.5 * u, fill=color)


def rayo(d, u, cx, cy, h, color):
    k = h / 60
    pts = [(cx + 6 * k, cy - 30 * k), (cx - 16 * k, cy + 4 * k), (cx - 1 * k, cy + 4 * k),
           (cx - 6 * k, cy + 30 * k), (cx + 16 * k, cy - 4 * k), (cx + 1 * k, cy - 4 * k)]
    d.polygon([(x * u, y * u) for x, y in pts], fill=color)


BLANCO = (255, 255, 255, 255)


# ---------------------------------------------------------------- propuestas
def p_actual(s):
    img = base(s, (76, 194, 255), (0, 103, 192))
    bateria(ImageDraw.Draw(img), s / 100, 16, 30, 78, 70, BLANCO, barras=3)
    return img


def p_rayo_lima(s):
    img = base(s, (24, 26, 30), (8, 9, 11))
    d = ImageDraw.Draw(img)
    u = s / 100
    lima = (163, 230, 53, 255)
    bateria(d, u, 14, 28, 80, 72, lima, grosor=6)
    rayo(d, u, 47, 50, 36, lima)
    return img


def p_letra_b(s):
    img = base(s, (124, 92, 255), (60, 30, 190), diagonal=True)
    d = ImageDraw.Draw(img)
    u = s / 100
    d.text((42 * u, 52 * u), "B", font=fuente(round(74 * u)), fill=BLANCO, anchor="mm")
    for i in range(3):     # barras de carga a la derecha, como un medidor
        y = 64 - i * 14
        d.rounded_rectangle((74 * u, y * u, 86 * u, (y + 9) * u), radius=2 * u,
                            fill=(255, 255, 255, 255 if i < 2 else 110))
    return img


def p_hub(s):
    img = base(s, (16, 185, 129), (4, 120, 87))
    d = ImageDraw.Draw(img)
    u = s / 100
    nodos = [(50, 18), (20, 72), (80, 72)]
    for x, y in nodos:
        d.line((50 * u, 50 * u, x * u, y * u), fill=(255, 255, 255, 170), width=round(4 * u))
    for x, y in nodos:
        d.ellipse(((x - 9) * u, (y - 9) * u, (x + 9) * u, (y + 9) * u), fill=BLANCO)
    d.rounded_rectangle((33 * u, 39 * u, 67 * u, 61 * u), radius=5 * u, fill=(4, 120, 87, 255),
                        outline=BLANCO, width=round(4.5 * u))
    d.rounded_rectangle((68 * u, 45 * u, 72 * u, 55 * u), radius=1.5 * u, fill=BLANCO)
    d.rounded_rectangle((39 * u, 45 * u, 55 * u, 55 * u), radius=1.5 * u, fill=BLANCO)
    return img


def p_anillo(s):
    img = base(s, (30, 32, 38), (14, 15, 18), forma="circulo")
    d = ImageDraw.Draw(img)
    u = s / 100
    d.arc((12 * u, 12 * u, 88 * u, 88 * u), 0, 360, fill=(255, 255, 255, 40), width=round(9 * u))
    d.arc((12 * u, 12 * u, 88 * u, 88 * u), -90, -90 + 270, fill=(76, 194, 255, 255), width=round(9 * u))
    raton = modelos.dibujar("raton_gaming", "minimalista", round(44 * u), (255, 255, 255, 255))
    img.alpha_composite(raton, (round(28 * u), round(28 * u)))
    return img


def p_vertical_atardecer(s):
    img = base(s, (255, 122, 89), (214, 41, 118), diagonal=True)
    d = ImageDraw.Draw(img)
    u = s / 100
    d.rounded_rectangle((32 * u, 22 * u, 68 * u, 86 * u), radius=9 * u, outline=BLANCO, width=round(6 * u))
    d.rounded_rectangle((42 * u, 13 * u, 58 * u, 21 * u), radius=3 * u, fill=BLANCO)
    d.rounded_rectangle((41 * u, 50 * u, 59 * u, 77 * u), radius=3 * u, fill=BLANCO)
    return img


def p_perifericos(s):
    img = base(s, (241, 243, 247), (205, 210, 220))
    d = ImageDraw.Draw(img)
    u = s / 100
    oscuro = (28, 30, 36, 255)
    for mid, x, y, t in (("cascos_gaming", 8, 10, 46), ("raton_clasico", 52, 14, 40), ("mando_asimetrico", 26, 46, 48)):
        ic = modelos.dibujar(mid, "minimalista", round(t * u), oscuro)
        img.alpha_composite(ic, (round(x * u), round(y * u)))
    d.ellipse((70 * u, 66 * u, 92 * u, 88 * u), fill=(22, 163, 74, 255))
    rayo(d, u, 81, 77, 15, BLANCO)
    return img


def p_neon_bh(s):
    img = base(s, (10, 10, 14), (10, 10, 14))
    d = ImageDraw.Draw(img)
    u = s / 100
    cian = (34, 211, 238, 255)
    bateria(d, u, 12, 26, 82, 74, cian, grosor=5, radio=11)
    d.text((46 * u, 51 * u), "BH", font=fuente(round(30 * u)), fill=cian, anchor="mm")
    return img


def p_cascos_carga(s):
    img = base(s, (251, 191, 36), (234, 88, 12), diagonal=True)
    u = s / 100
    cascos = modelos.dibujar("cascos_estudio", "minimalista", round(62 * u), (255, 255, 255, 255))
    img.alpha_composite(cascos, (round(19 * u), round(8 * u)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((35 * u, 74 * u, 63 * u, 88 * u), radius=3 * u, outline=BLANCO, width=round(3.5 * u))
    d.rounded_rectangle((64 * u, 78 * u, 67 * u, 84 * u), radius=1 * u, fill=BLANCO)
    d.rounded_rectangle((39 * u, 77.5 * u, 53 * u, 84.5 * u), radius=1.5 * u, fill=BLANCO)
    return img


def p_realista(s):
    img = base(s, (55, 60, 72), (22, 24, 30), diagonal=True)
    u = s / 100
    raton = modelos.dibujar("raton_gaming", "realista", round(60 * u), (76, 194, 255, 255), "blanco")
    img.alpha_composite(raton, (round(6 * u), round(18 * u)))
    d = ImageDraw.Draw(img)
    verde = (74, 222, 128, 255)
    bateria(d, u, 58, 58, 86, 76, verde, grosor=3, nivel=0.7, radio=4)
    return img


# ---------------------------------------------------------------- BrH
def _texto_brh(d, u, cx, cy, tam, color, color_r=None, r_peq=0.72):
    """Escribe "BrH" centrado, con la r algo más pequeña para que B y H manden."""
    fb, fr = fuente(round(tam * u)), fuente(round(tam * r_peq * u))
    wb = d.textlength("B", font=fb)
    wr = d.textlength("r", font=fr)
    wh = d.textlength("H", font=fb)
    sep = -0.5 * u
    x = cx * u - (wb + wr + wh + 2 * sep) / 2
    base_y = cy * u + tam * u * 0.36            # línea base común
    d.text((x, base_y), "B", font=fb, fill=color, anchor="ls")
    d.text((x + wb + sep, base_y), "r", font=fr, fill=color_r or color, anchor="ls")
    d.text((x + wb + wr + 2 * sep, base_y), "H", font=fb, fill=color, anchor="ls")


def brh_azul(s):
    img = base(s, (76, 194, 255), (0, 103, 192))
    d = ImageDraw.Draw(img)
    u = s / 100
    _texto_brh(d, u, 50, 44, 46, BLANCO)
    d.rounded_rectangle((22 * u, 72 * u, 78 * u, 80 * u), radius=4 * u, fill=(255, 255, 255, 80))
    d.rounded_rectangle((22 * u, 72 * u, 62 * u, 80 * u), radius=4 * u, fill=BLANCO)
    return img


def brh_lima(s):
    img = base(s, (24, 26, 30), (8, 9, 11))
    d = ImageDraw.Draw(img)
    u = s / 100
    lima = (163, 230, 53, 255)
    bateria(d, u, 9, 26, 83, 74, lima, grosor=5, radio=11)
    _texto_brh(d, u, 46, 49, 36, lima)
    return img


def brh_rayo(s):
    img = base(s, (124, 92, 255), (60, 30, 190), diagonal=True)
    d = ImageDraw.Draw(img)
    u = s / 100
    _texto_brh(d, u, 50, 50, 46, BLANCO, color_r=(253, 224, 71, 255))
    return img


def brh_neon(s):
    img = base(s, (10, 10, 14), (10, 10, 14))
    d = ImageDraw.Draw(img)
    u = s / 100
    cian = (34, 211, 238, 255)
    bateria(d, u, 9, 26, 83, 74, cian, grosor=5, radio=11)
    _texto_brh(d, u, 46, 49, 36, cian)
    return img


def brh_carga(s):
    img = base(s, (30, 32, 38), (12, 13, 16))
    d = ImageDraw.Draw(img)
    u = s / 100
    _texto_brh(d, u, 50, 42, 44, BLANCO, color_r=(76, 194, 255, 255))
    for i in range(4):            # medidor de 4 segmentos, 3 encendidos
        x0 = 20 + i * 15.5
        d.rounded_rectangle((x0 * u, 70 * u, (x0 + 12.5) * u, 80 * u), radius=2.5 * u,
                            fill=(76, 194, 255, 255) if i < 3 else (255, 255, 255, 45))
    return img


def brh_anillo(s):
    img = base(s, (30, 32, 38), (14, 15, 18), forma="circulo")
    d = ImageDraw.Draw(img)
    u = s / 100
    d.arc((7 * u, 7 * u, 93 * u, 93 * u), 0, 360, fill=(255, 255, 255, 40), width=round(7 * u))
    d.arc((7 * u, 7 * u, 93 * u, 93 * u), -90, -90 + 270, fill=(163, 230, 53, 255), width=round(7 * u))
    _texto_brh(d, u, 50, 50, 34, BLANCO)
    return img


ROJO = (220, 20, 40, 255)
ROJO_SUAVE = (246, 200, 205, 255)      # segmento "vacío" del medidor (opaco: no deja huecos)


def _fondo_blanco(s, forma="squircle"):
    img = base(s, (255, 255, 255), (238, 238, 242), forma=forma)
    d = ImageDraw.Draw(img)        # borde fino para que no se pierda sobre fondos claros
    if forma == "circulo":
        d.ellipse((0, 0, s - 1, s - 1), outline=(205, 205, 212, 255), width=max(1, round(s * 0.012)))
    else:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.23, outline=(205, 205, 212, 255),
                            width=max(1, round(s * 0.012)))
    return img


def brh_rojo_medidor(s):
    img = _fondo_blanco(s)
    d = ImageDraw.Draw(img)
    u = s / 100
    _texto_brh(d, u, 50, 42, 44, ROJO)
    for i in range(4):
        x0 = 20 + i * 15.5
        d.rounded_rectangle((x0 * u, 70 * u, (x0 + 12.5) * u, 80 * u), radius=2.5 * u,
                            fill=ROJO if i < 3 else ROJO_SUAVE)
    return img


def brh_rojo_simple(s):
    img = _fondo_blanco(s)
    _texto_brh(ImageDraw.Draw(img), s / 100, 50, 50, 48, ROJO)
    return img


def brh_rojo_bateria(s):
    img = _fondo_blanco(s)
    d = ImageDraw.Draw(img)
    u = s / 100
    bateria(d, u, 9, 26, 83, 74, ROJO, grosor=5, radio=11)
    _texto_brh(d, u, 46, 49, 36, ROJO)
    return img


AZUL = (76, 194, 255, 255)
AZUL_SUAVE = (22, 52, 70, 255)         # segmento "vacío" del medidor sobre negro


def brh_azul_negro(s):
    img = base(s, (24, 24, 28), (4, 4, 6))
    d = ImageDraw.Draw(img)
    u = s / 100
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.23, outline=(52, 52, 60, 255),
                        width=max(1, round(s * 0.012)))
    _texto_brh(d, u, 50, 42, 44, AZUL)
    for i in range(4):
        x0 = 20 + i * 15.5
        d.rounded_rectangle((x0 * u, 70 * u, (x0 + 12.5) * u, 80 * u), radius=2.5 * u,
                            fill=AZUL if i < 3 else AZUL_SUAVE)
    return img


VERDE = (67, 211, 120, 255)
VERDE_SUAVE = (44, 70, 54, 255)        # segmento "vacío" del medidor sobre gris


def brh_verde_gris(s):
    """Tema Gris: fondo gris grafito (como la ventana en ese tema) con BrH y medidor verdes."""
    img = base(s, (64, 66, 73), (41, 43, 48))
    d = ImageDraw.Draw(img)
    u = s / 100
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.23, outline=(88, 91, 100, 255),
                        width=max(1, round(s * 0.012)))
    _texto_brh(d, u, 50, 42, 44, VERDE)
    for i in range(4):
        x0 = 20 + i * 15.5
        d.rounded_rectangle((x0 * u, 70 * u, (x0 + 12.5) * u, 80 * u), radius=2.5 * u,
                            fill=VERDE if i < 3 else VERDE_SUAVE)
    return img


PROPUESTAS_ROJO = [
    ("1", "Medidor", brh_rojo_medidor),
    ("2", "Simple", brh_rojo_simple),
    ("3", "Batería", brh_rojo_bateria),
]

PROPUESTAS_BRH = [
    ("A", "BrH azul", brh_azul),
    ("B", "BrH lima", brh_lima),
    ("C", "BrH violeta", brh_rayo),
    ("D", "BrH neón", brh_neon),
    ("E", "BrH medidor", brh_carga),
    ("F", "BrH anillo", brh_anillo),
]

PROPUESTAS = [
    ("1", "Actual", p_actual),
    ("2", "Rayo lima", p_rayo_lima),
    ("3", "Letra B", p_letra_b),
    ("4", "Hub conectado", p_hub),
    ("5", "Anillo de carga", p_anillo),
    ("6", "Vertical atardecer", p_vertical_atardecer),
    ("7", "Periféricos", p_perifericos),
    ("8", "Neón BH", p_neon_bh),
    ("9", "Cascos en carga", p_cascos_carga),
    ("10", "Realista", p_realista),
]


def generar(f, lado):
    return f(lado * 4).resize((lado, lado), Image.LANCZOS)


def hoja(propuestas=PROPUESTAS, cols=5) -> Image.Image:
    cw, ch = 250, 300
    filas = math.ceil(len(propuestas) / cols)
    img = Image.new("RGB", (cols * cw, filas * ch), (16, 16, 20))
    d = ImageDraw.Draw(img)
    for i, (num, nombre, f) in enumerate(propuestas):
        x, y = (i % cols) * cw, (i // cols) * ch
        grande = generar(f, 150)
        img.paste(grande, (x + 50, y + 22), grande)
        d.text((x + cw / 2, y + 196), f"{num}. {nombre}", font=fuente(17), fill=(240, 240, 244), anchor="mm")
        # tamaños reales sobre barra oscura y clara
        d.rounded_rectangle((x + 30, y + 222, x + 122, y + 278), radius=10, fill=(32, 32, 36))
        d.rounded_rectangle((x + 128, y + 222, x + 220, y + 278), radius=10, fill=(238, 238, 241))
        for bx in (x + 30, x + 128):
            p32, p16 = generar(f, 32), generar(f, 16)
            img.paste(p32, (bx + 14, y + 234), p32)
            img.paste(p16, (bx + 58, y + 242), p16)
    return img


if __name__ == "__main__":
    os.makedirs(CARPETA, exist_ok=True)
    for num, nombre, f in PROPUESTAS:
        generar(f, 256).save(os.path.join(CARPETA, f"{int(num):02d}_{nombre.lower().replace(' ', '_')}.png"))
    hoja().save(os.path.join(CARPETA, "hoja.png"))
    for letra, nombre, f in PROPUESTAS_BRH:
        generar(f, 256).save(os.path.join(CARPETA, f"brh_{letra}_{nombre.split()[1].lower()}.png"))
    hoja(PROPUESTAS_BRH, cols=3).save(os.path.join(CARPETA, "hoja_brh.png"))
    for num, nombre, f in PROPUESTAS_ROJO:
        generar(f, 256).save(os.path.join(CARPETA, f"brh_rojo_{num}_{nombre.lower()}.png"))
    hoja(PROPUESTAS_ROJO, cols=3).save(os.path.join(CARPETA, "hoja_brh_rojo.png"))
    print("prototipos en", CARPETA)
