"""Selector de color propio, con la estética de la app (sustituye al diálogo de Windows).

  ┌──────────────────────────────┐
  │ Elegir color             ✕   │
  │ ┌──────────────────┐  ┌───┐  │   cuadro de saturación / brillo
  │ │                  │  │ ▓ │  │   vista previa: antes / ahora
  │ │        ○         │  └───┘  │
  │ └──────────────────┘  #4CC2FF│
  │ ═══════○═══════════          │   tono
  │ Sugeridos  ● ● ● ● ● ● ● ●   │
  │ Recientes  ● ● ●             │
  │            [Cancelar][Aplicar]│
  └──────────────────────────────┘
"""
from __future__ import annotations

import colorsys
import re
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

# paleta sugerida: tonos actuales, ordenados por color
SUGERIDOS = ["#F87171", "#FB923C", "#FBBF24", "#A3E635", "#34D399", "#2DD4BF", "#22D3EE", "#60A5FA",
             "#818CF8", "#A78BFA", "#E879F9", "#F472B6",
             "#DC2626", "#EA580C", "#CA8A04", "#65A30D", "#059669", "#0D9488", "#0891B2", "#2563EB",
             "#4F46E5", "#7C3AED", "#C026D3", "#DB2777"]


def hex_a_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_a_hex(r: float, g: float, b: float) -> str:
    return "#%02X%02X%02X" % (round(r), round(g), round(b))


def circulo(color: str, lado: int, fondo: str, marcado: bool = False, borde: str | None = None,
            atenuado: float = 0.0, k: int = 3) -> Image.Image:
    """Muestra de color redonda, dibujada a k aumentos para bordes suaves.
    marcado: aro exterior (con un hueco) del color `borde`. atenuado: 0-1, se funde con el fondo."""
    S = lado * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = hex_a_rgb(color)
    f = hex_a_rgb(fondo)
    if atenuado:
        c = tuple(round(x + (y - x) * atenuado) for x, y in zip(c, f))
    claro_fondo = sum(f) > 380
    if marcado:
        anillo = hex_a_rgb(borde or ("#1b1b1f" if claro_fondo else "#ffffff"))
        if atenuado:
            anillo = tuple(round(x + (y - x) * atenuado) for x, y in zip(anillo, f))
        d.ellipse((0, 0, S - 1, S - 1), outline=anillo + (255,), width=round(2 * k))
    m = round(S * (0.2 if marcado else 0.12))
    d.ellipse((m, m, S - 1 - m, S - 1 - m), fill=c + (255,))
    # filo sutil para que el negro se vea en tema oscuro y el blanco en tema claro
    filo = (255, 255, 255, 40) if not claro_fondo else (0, 0, 0, 40)
    d.ellipse((m, m, S - 1 - m, S - 1 - m), outline=filo, width=max(1, k))
    return img.resize((lado * 2, lado * 2), Image.LANCZOS)     # 2x: nítido en pantallas con escala


def circulo_auto(lado: int, fondo: str, marcado: bool, borde: str | None = None, atenuado: float = 0.0,
                 k: int = 3) -> Image.Image:
    """'Auto': círculo mitad claro / mitad oscuro (cambia según el tema de la barra)."""
    S = lado * k
    img = circulo("#FFFFFF", lado, fondo, marcado, borde, atenuado, k).resize((S, S), Image.LANCZOS)
    m = round(S * (0.2 if marcado else 0.12))
    mitad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    oscuro = (30, 30, 34)
    if atenuado:
        oscuro = tuple(round(x + (y - x) * atenuado) for x, y in zip(oscuro, hex_a_rgb(fondo)))
    ImageDraw.Draw(mitad).pieslice((m, m, S - 1 - m, S - 1 - m), 45, 225, fill=oscuro + (255,))
    img.alpha_composite(mitad)
    return img.resize((lado * 2, lado * 2), Image.LANCZOS)


def rueda(lado: int, k: int = 3) -> Image.Image:
    """Icono del botón "más colores": rueda cromática."""
    S = lado * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = round(S * 0.12)
    for i in range(72):
        r, g, b = colorsys.hsv_to_rgb(i / 72, 0.75, 1)
        d.pieslice((m, m, S - 1 - m, S - 1 - m), i * 5 - 90, i * 5 - 85 + 1, fill=(round(r * 255), round(g * 255),
                                                                               round(b * 255), 255))
    c = S // 2
    r0 = round(S * 0.16)
    d.ellipse((c - r0, c - r0, c + r0, c + r0), fill=(255, 255, 255, 255))
    return img.resize((lado * 2, lado * 2), Image.LANCZOS)


class Muestra(ctk.CTkLabel):
    """Círculo de color clicable. Es una etiqueta con imagen (un CTkButton redondo reserva
    sitio para sus esquinas y separa demasiado las muestras). Al pasar el ratón se ve un aro."""

    def __init__(self, padre, al_pulsar, lado: int = 34) -> None:
        super().__init__(padre, text="", width=lado, height=lado, cursor="hand2")
        self._al_pulsar = al_pulsar
        self._img = self._img_hover = None
        self.activa = True
        self.bind("<Button-1>", lambda e: self.activa and self._al_pulsar())
        self.bind("<Enter>", lambda e: self.activa and self._img_hover and self.configure(image=self._img_hover))
        self.bind("<Leave>", lambda e: self._img and self.configure(image=self._img))

    def poner(self, img, img_hover=None, activa: bool = True) -> None:
        self._img, self._img_hover, self.activa = img, img_hover or img, activa
        self.configure(image=img, cursor="hand2" if activa else "arrow")


class SelectorColor(ctk.CTkToplevel):
    def __init__(self, master, inicial: str, al_aceptar, P: dict, fuente, recientes: list[str],
                 titulo: str = "Elegir color", icono=None) -> None:
        super().__init__(master, fg_color=P["FONDO"])
        self.P, self.fuente, self.al_aceptar = P, fuente, al_aceptar
        self.recientes = [c for c in recientes if re.fullmatch(r"#[0-9A-Fa-f]{6}", c)][:8]
        self.inicial = inicial if re.fullmatch(r"#[0-9A-Fa-f]{6}", inicial or "") else "#4CC2FF"
        r, g, b = (x / 255 for x in hex_a_rgb(self.inicial))
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self.escala = ctk.ScalingTracker.get_window_scaling(master)
        self.title(titulo)
        self.resizable(False, False)
        self.transient(master)
        if icono:
            self.after(250, lambda: icono(self))

        cont = ctk.CTkFrame(self, fg_color="transparent")
        cont.pack(padx=22, pady=20)
        ctk.CTkLabel(cont, text=titulo, font=fuente(17, "bold"), text_color=P["TEXTO"]).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        # cuadro saturación/brillo + barra de tono
        self.W, self.H, self.HB = self._px(250), self._px(170), self._px(16)
        self.lienzo = tk.Canvas(cont, width=self.W, height=self.H, highlightthickness=0, bd=0,
                                bg=P["FONDO"], cursor="crosshair")
        self.lienzo.grid(row=1, column=0, sticky="nw")
        self.barra = tk.Canvas(cont, width=self.W, height=self.HB + self._px(8), highlightthickness=0, bd=0,
                               bg=P["FONDO"], cursor="hand2")
        self.barra.grid(row=2, column=0, sticky="w", pady=(12, 0))
        for w, f in ((self.lienzo, self._clic_cuadro), (self.barra, self._clic_tono)):
            w.bind("<Button-1>", f)
            w.bind("<B1-Motion>", f)
        self._foto_tono = ImageTk.PhotoImage(self._img_tono(), master=self)
        self.barra.create_image(0, self._px(4), image=self._foto_tono, anchor="nw")
        self._marca_tono = self.barra.create_oval(0, 0, 0, 0, outline="#ffffff", width=max(2, self._px(2)))
        self._foto_cuadro = None
        self._img_cuadro_id = self.lienzo.create_image(0, 0, anchor="nw")
        self._marca = self.lienzo.create_oval(0, 0, 0, 0, outline="#ffffff", width=max(2, self._px(2)))

        # derecha: antes / ahora + código
        der = ctk.CTkFrame(cont, fg_color="transparent")
        der.grid(row=1, column=1, rowspan=2, sticky="n", padx=(18, 0))
        self.previa = ctk.CTkLabel(der, text="")
        self.previa.pack()
        ctk.CTkLabel(der, text="Antes   ·   Ahora", font=fuente(11), text_color=P["SECUNDARIO"]).pack(pady=(4, 12))
        ctk.CTkLabel(der, text="Código", font=fuente(12), text_color=P["SECUNDARIO"]).pack(anchor="w")
        self.v_hex = ctk.StringVar()
        self.e_hex = ctk.CTkEntry(der, textvariable=self.v_hex, width=110, height=34, corner_radius=10,
                                  font=fuente(14, "bold"), justify="center", fg_color=P["SUPERFICIE"],
                                  border_color=P["BORDE"], text_color=P["TEXTO"])
        self.e_hex.pack(pady=(4, 0))
        self.e_hex.bind("<Return>", self._hex_escrito)
        self.e_hex.bind("<FocusOut>", self._hex_escrito)

        # sugeridos y recientes
        fila = 3
        for titulo_fila, colores in (("Sugeridos", SUGERIDOS), ("Recientes", self.recientes)):
            if not colores:
                continue
            ctk.CTkLabel(cont, text=titulo_fila, font=fuente(12), text_color=P["SECUNDARIO"]).grid(
                row=fila, column=0, columnspan=2, sticky="w", pady=(16, 4))
            rej = ctk.CTkFrame(cont, fg_color="transparent")
            rej.grid(row=fila + 1, column=0, columnspan=2, sticky="w")
            for i, c in enumerate(colores):
                m = Muestra(rej, lambda c=c: self._poner_hex(c), lado=30)
                m.poner(ctk.CTkImage(circulo(c, 28, P["FONDO"]), size=(28, 28)),
                        ctk.CTkImage(circulo(c, 28, P["FONDO"], True, P["SECUNDARIO"]), size=(28, 28)))
                m.grid(row=i // 12, column=i % 12, padx=1, pady=1)
            fila += 2

        botones = ctk.CTkFrame(cont, fg_color="transparent")
        botones.grid(row=fila, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ctk.CTkButton(botones, text="Cancelar", width=110, height=36, corner_radius=10, font=fuente(13),
                      fg_color=P["SUPERFICIE"], hover_color=P["SUPERFICIE_HOVER"], text_color=P["TEXTO"],
                      border_width=1, border_color=P["BORDE"], command=self.destroy).pack(side="left", padx=(0, 8))
        ctk.CTkButton(botones, text="Aplicar", width=110, height=36, corner_radius=10, font=fuente(13, "bold"),
                      fg_color=P["ACENTO"], hover_color=P["ACENTO_HOVER"],
                      text_color="#ffffff" if P.get("CLARO") else "#0c0c0e", command=self._aceptar).pack(side="left")
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._aceptar() if self.focus_get() is not self.e_hex._entry else None)

        self._pintar(todo=True)
        self._centrar(master)
        self.after(50, self._modal)

    # ------------------------------------------------------------ utilidades
    def _px(self, n: float) -> int:
        return round(n * self.escala)

    def _centrar(self, master) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = master.winfo_rootx() + (master.winfo_width() - w) // 2
        y = master.winfo_rooty() + (master.winfo_height() - h) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _modal(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def color(self) -> str:
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        return rgb_a_hex(r * 255, g * 255, b * 255)

    # -------------------------------------------------------------- dibujo
    def _img_tono(self) -> Image.Image:
        W, H = self.W, self.HB
        k = 3
        img = Image.new("RGB", (W, 1))
        img.putdata([tuple(round(x * 255) for x in colorsys.hsv_to_rgb(i / W, 1, 1)) for i in range(W)])
        img = img.resize((W * k, H * k))
        mascara = Image.new("L", (W * k, H * k), 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, W * k - 1, H * k - 1), radius=H * k // 2, fill=255)
        fondo = Image.new("RGB", (W * k, H * k), self.P["FONDO"])
        fondo.paste(img, (0, 0), mascara)
        return fondo.resize((W, H), Image.LANCZOS)

    def _img_cuadro(self) -> Image.Image:
        W, H = self.W, self.H
        r, g, b = (round(x * 255) for x in colorsys.hsv_to_rgb(self.h, 1, 1))
        base = Image.new("RGB", (W, H), (r, g, b))
        blanco = Image.new("RGB", (W, H), (255, 255, 255))
        horizontal = Image.linear_gradient("L").rotate(-90).resize((W, H))    # 255 a la izquierda -> 0
        base = Image.composite(blanco, base, horizontal)
        negro = Image.new("RGB", (W, H), (0, 0, 0))
        vertical = Image.linear_gradient("L").resize((W, H))                  # 0 arriba -> 255 abajo
        base = Image.composite(negro, base, vertical)
        k = 3                                                                  # esquinas redondeadas suaves
        mascara = Image.new("L", (W * k, H * k), 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, W * k - 1, H * k - 1), radius=self._px(12) * k, fill=255)
        fondo = Image.new("RGB", (W, H), self.P["FONDO"])
        fondo.paste(base, (0, 0), mascara.resize((W, H), Image.LANCZOS))
        return fondo

    def _img_previa(self) -> Image.Image:
        lado, k = 92, 3
        S = lado * k
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = 18 * k
        d.rounded_rectangle((0, 0, S - 1, S - 1), radius=r, fill=hex_a_rgb(self.color()) + (255,))
        mitad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(mitad).rounded_rectangle((0, 0, S - 1, S - 1), radius=r, fill=hex_a_rgb(self.inicial) + (255,))
        img.paste(mitad.crop((0, 0, S // 2, S)), (0, 0), mitad.crop((0, 0, S // 2, S)))
        ImageDraw.Draw(img).rounded_rectangle((0, 0, S - 1, S - 1), radius=r, outline=hex_a_rgb(self.P["BORDE"]) + (255,),
                                              width=k)
        return img.resize((lado * 2, lado * 2), Image.LANCZOS)

    def _pintar(self, todo: bool = False, cuadro: bool = False) -> None:
        if todo or cuadro:
            self._foto_cuadro = ImageTk.PhotoImage(self._img_cuadro(), master=self)
            self.lienzo.itemconfigure(self._img_cuadro_id, image=self._foto_cuadro)
        x, y = self.s * (self.W - 1), (1 - self.v) * (self.H - 1)
        r = self._px(8)
        self.lienzo.coords(self._marca, x - r, y - r, x + r, y + r)
        self.lienzo.itemconfigure(self._marca, outline="#ffffff" if self.v < 0.6 or self.s > 0.5 else "#1b1b1f")
        hx = self.h * (self.W - 1)
        rt = self.HB // 2 + self._px(3)
        cy = self._px(4) + self.HB // 2
        self.barra.coords(self._marca_tono, hx - rt, cy - rt, hx + rt, cy + rt)
        self.previa.configure(image=ctk.CTkImage(self._img_previa(), size=(92, 92)))
        if self.focus_get() is not getattr(self.e_hex, "_entry", None):
            self.v_hex.set(self.color())

    # ------------------------------------------------------------ eventos
    def _clic_cuadro(self, e) -> None:
        self.s = min(1, max(0, e.x / (self.W - 1)))
        self.v = min(1, max(0, 1 - e.y / (self.H - 1)))
        self._pintar()

    def _clic_tono(self, e) -> None:
        self.h = min(0.999, max(0, e.x / (self.W - 1)))
        self._pintar(cuadro=True)

    def _poner_hex(self, c: str) -> None:
        r, g, b = (x / 255 for x in hex_a_rgb(c))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s > 0:                       # en grises el tono no importa: se conserva el que había
            self.h = h
        self.s, self.v = s, v
        self.focus_set()
        self._pintar(cuadro=True)

    def _hex_escrito(self, _e=None) -> None:
        t = self.v_hex.get().strip()
        if not t.startswith("#"):
            t = "#" + t
        if re.fullmatch(r"#[0-9A-Fa-f]{3}", t):
            t = "#" + "".join(ch * 2 for ch in t[1:])
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", t):
            self._poner_hex(t.upper())
        else:
            self.v_hex.set(self.color())

    def _aceptar(self) -> None:
        self._hex_escrito()
        c = self.color()
        self.destroy()
        self.al_aceptar(c)
