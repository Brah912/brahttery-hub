"""Estimación de horas de uso restantes, medidas de verdad.

Cómo se mide
------------
* Cada lectura (una por minuto, la que ya hace la bandeja) suma "tiempo de uso" sólo si el
  dispositivo respondía también en la lectura anterior. Las horas con el periférico apagado,
  dormido o el PC apagado no cuentan: no gastan batería y falsearían el consumo.
* Cada descarga (de una carga a la siguiente) es un "tramo": lista de puntos
  [hora, nivel, uso_acumulado], uno por cada vez que el nivel baja.
* El consumo de un tramo = puntos de batería perdidos / horas de uso entre el primer y el
  último cambio de nivel (contar desde los cambios evita el error de los dispositivos que
  informan de 5 en 5 %).

Análisis diario
---------------
Una vez al día (en el hilo de lectura de la bandeja, en segundo plano) se recalcula el perfil
de cada dispositivo con todas sus descargas de los últimos 30 días: media ponderada por horas
de uso, dando más peso a las recientes. Son unas pocas cuentas sobre un archivo de pocos KB:
no se nota en el PC.

Horas restantes = nivel / consumo, donde el consumo mezcla el perfil aprendido con la
descarga actual. Sin datos suficientes se usa la autonomía nominal (aprox.), modificable por
periférico en la ventana o en config.json -> "autonomia_horas".
"""
from __future__ import annotations

import json
import math
import os
import time

import polling

import rutas

RUTA_HISTORIAL = rutas.RUTA_HISTORIAL

# Autonomía con batería llena, en horas (valores orientativos)
AUTONOMIA_NOMINAL = {
    "hyperx-cloud3": 120,   # HyperX: hasta 120 h
    "scyrox": 80,           # SCYROX V8: ~80 h a 1000 Hz (TechPowerUp; la marca no publica cifra)
    "dualsense": 8,
    "mando": 40,            # mando Xbox con pilas AA
    "auriculares": 6,
    "cascos": 40,
    "raton": 60,
    "teclado": 100,
    "altavoz": 15,
    "otro": 20,
}

# Autonomía oficial de modelos concretos (según la clave del dispositivo). El primero que coincide gana.
MODELOS_CONOCIDOS = (
    ("superlight-2", 95),       # Logitech PRO X SUPERLIGHT 2: hasta 95 h
    ("superlight", 70),         # Logitech PRO X SUPERLIGHT: hasta 70 h
    ("g305", 250),              # Logitech G305: hasta 250 h
    ("scyrox", 80),             # SCYROX V8: ~80 h a 1000 Hz (TechPowerUp; la marca no publica cifra)
)
SUBIDA_CARGA = 10               # una subida de 10 puntos o más sin "cargando" = se cargó
PESO_NOMINAL = 10               # horas de uso que "vale" la autonomía oficial frente a lo medido
MAX_HUECO = 1800                    # s entre lecturas que cuentan como uso: los ratones duermen a los pocos
                                    # segundos quietos y no responden, pero la sesión de uso sigue
DIAS_HISTORIAL = 30                 # descargas que se tienen en cuenta
VIDA_MEDIA_DIAS = 10                # una descarga de hace 10 días pesa la mitad
MIN_CAIDA = 3                       # puntos de batería mínimos para fiarse de un tramo
MIN_USO = 0.5 * 3600                # segundos de uso mínimos de un tramo
ANALIZAR_CADA = 24 * 3600
GUARDAR_CADA = 10 * 60              # el uso acumulado se guarda como mucho cada 10 min


class Estimador:
    def __init__(self, extra_nominal: dict | None = None) -> None:
        self.nominal = dict(AUTONOMIA_NOMINAL)
        self.nominal.update(extra_nominal or {})
        self._mtime = 0.0
        self._guardado = 0.0
        self.datos: dict = {}
        self._cargar()

    # ------------------------------------------------------------------ disco
    def _cargar(self) -> None:
        try:
            self._mtime = os.path.getmtime(RUTA_HISTORIAL)
            with open(RUTA_HISTORIAL, encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            datos = {}
        if datos.get("version") != 2:           # formato antiguo: {clave: [[t, nivel], ...]}
            disp = {}
            for clave, puntos in (datos.items() if isinstance(datos, dict) else []):
                if isinstance(puntos, list) and puntos:
                    t0 = puntos[0][0]
                    disp[clave] = {"tramos": [[[t, n, t - t0] for t, n in puntos]],
                                   "ultimo": puntos[-1][0], "uso": puntos[-1][0] - t0}
            datos = {"version": 2, "disp": disp, "perfiles": {}, "analizado": 0}
        self.datos = datos
        self.disp: dict[str, dict] = datos.setdefault("disp", {})
        self.perfiles: dict[str, dict] = datos.setdefault("perfiles", {})
        if datos.get("perfiles_v") != 2:      # 2.0.0: los perfiles viejos contaban doble la descarga en curso
            datos["perfiles_v"] = 2
            datos["analizado"] = 0

    def recargar_si_cambio(self) -> None:
        """Para la ventana: lee lo nuevo que haya escrito la bandeja."""
        try:
            if os.path.getmtime(RUTA_HISTORIAL) != self._mtime:
                self._cargar()
        except OSError:
            pass

    def _guardar(self) -> None:
        tmp = RUTA_HISTORIAL + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, separators=(",", ":"))
            os.replace(tmp, RUTA_HISTORIAL)
            self._mtime = os.path.getmtime(RUTA_HISTORIAL)
            self._guardado = time.time()
        except OSError:
            pass

    # ------------------------------------------------------------- registrar
    def registrar(self, clave: str, nivel: int, cargando: bool, ahora: float | None = None,
                  hz: int | None = None) -> None:
        """Una lectura real del dispositivo (no se llama para los que están en reposo).
        hz: polling rate del ratón en ese momento (se guarda en cada punto para que el consumo
        medido se pueda pasar a "consumo a 1000 Hz" y luego ajustarse a la tasa actual)."""
        ahora = time.time() if ahora is None else ahora
        punto = [ahora, nivel, 0] + ([hz] if hz else [])
        d = self.disp.setdefault(clave, {"tramos": [], "ultimo": 0, "uso": 0})
        tramos = d["tramos"]
        hueco = ahora - (d.get("ultimo") or 0)
        if 0 < hueco <= MAX_HUECO and not cargando and not d.get("cargando"):
            d["uso"] = d.get("uso", 0) + hueco          # siguió encendido: es tiempo de uso
        d["ultimo"] = ahora
        cambio = False
        if cargando:
            if not d.get("cargando"):
                d["cargando"] = True
                cambio = True
        else:
            actual = tramos[-1] if tramos and not d.get("cargando") else None
            d["cargando"] = False
            ultimo = actual[-1][1] if actual else None
            if actual is None or nivel >= ultimo + SUBIDA_CARGA:   # se cargó (aunque no lo dijera): tramo nuevo
                if not (tramos and len(tramos[-1]) <= 1):
                    tramos.append([])
                else:
                    tramos[-1] = []
                punto[2] = d["uso"]
                tramos[-1].append(punto)
                cambio = True
            elif nivel < ultimo:                        # bajó: nuevo punto
                punto[2] = d["uso"]
                actual.append(punto)
                del actual[:-1000]
                cambio = True
            # subidas pequeñas: vaivén del sensor (sobre todo si mide voltaje), se ignoran
        limite = ahora - DIAS_HISTORIAL * 86400
        while tramos and tramos[0] and tramos[0][-1][0] < limite:
            tramos.pop(0)
            cambio = True
        if cambio or ahora - self._guardado > GUARDAR_CADA:
            self._guardar()

    # --------------------------------------------------------------- consumo
    @staticmethod
    def _consumo_tramo(tramo: list) -> tuple[float, float] | None:
        """(% por hora de uso, horas de uso) de un tramo, o None si es demasiado corto."""
        if len(tramo) < 2:
            return None
        caida = tramo[0][1] - tramo[-1][1]
        uso = tramo[-1][2] - tramo[0][2]
        if caida < MIN_CAIDA or uso < MIN_USO:
            return None
        # Recta de mínimos cuadrados con TODOS los puntos (no solo el primero y el último):
        # una lectura baja suelta al final ya no dispara el consumo.
        xs = [(p[2] - tramo[0][2]) / 3600 for p in tramo]
        ys = [p[1] for p in tramo]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        pendiente = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
        por_hora = -pendiente if pendiente < 0 else caida / (uso / 3600)
        # Se guarda como consumo a 1000 Hz: si el tramo se midió a 8000 Hz, gastaba ~5 veces más.
        factores = [polling.factor(p[3]) for p in tramo if len(p) > 3]
        if factores:
            por_hora /= sum(factores) / len(factores)
        return por_hora, uso / 3600

    def analizar(self, ahora: float | None = None) -> None:
        """Recalcula el perfil de consumo de cada dispositivo con sus descargas recientes."""
        ahora = time.time() if ahora is None else ahora
        for clave, d in self.disp.items():
            suma = peso_total = horas = 0.0
            n = 0
            tramos = d.get("tramos", [])
            for i, tramo in enumerate(tramos):
                if i == len(tramos) - 1 and not d.get("cargando"):
                    continue        # la descarga en curso la suma consumo() aparte (si no, contaba doble)
                c = self._consumo_tramo(tramo)
                if not c:
                    continue
                por_hora, uso = c
                edad = (ahora - tramo[-1][0]) / 86400
                peso = uso * math.pow(0.5, edad / VIDA_MEDIA_DIAS)
                suma += por_hora * peso
                peso_total += peso
                horas += uso
                n += 1
            if peso_total > 0:
                self.perfiles[clave] = {"por_hora": round(suma / peso_total, 4), "horas": round(horas, 2),
                                        "descargas": n, "fecha": ahora}
            else:
                self.perfiles.pop(clave, None)
        self.datos["analizado"] = ahora
        self._guardar()

    def toca_analizar(self, ahora: float | None = None) -> bool:
        ahora = time.time() if ahora is None else ahora
        return ahora - self.datos.get("analizado", 0) >= ANALIZAR_CADA

    def consumo(self, clave: str) -> tuple[float, float] | None:
        """(% por hora de uso, horas de uso que lo respaldan): perfil + descarga en curso."""
        perfil = self.perfiles.get(clave)
        d = self.disp.get(clave)
        actual = None
        if d and d.get("tramos") and not d.get("cargando"):
            actual = self._consumo_tramo(d["tramos"][-1])
        if perfil and actual:
            # la descarga actual pesa según sus horas; el perfil, con un máximo de 20 h
            wp, wa = min(perfil["horas"], 20), actual[1]
            return (perfil["por_hora"] * wp + actual[0] * wa) / (wp + wa), perfil["horas"] + actual[1]
        if perfil:
            return perfil["por_hora"], perfil["horas"]
        return actual

    def horas(self, clave: str, tipo: str, nivel: int, total: float | None = None,
              hz: int | None = None) -> tuple[float, bool]:
        """Devuelve (horas de uso restantes, medido_de_verdad). `total` fija la autonomía nominal.
        hz: polling rate actual. El consumo medido y la autonomía oficial son a 1000 Hz (así
        publican las marcas): se ajustan a la tasa actual (8000 Hz ≈ 5 veces más consumo)."""
        f = polling.factor(hz)
        total = (total or self.autonomia_nominal(clave, tipo)) / f
        c = self.consumo(clave)
        if c:
            c = (c[0] * f, c[1])
        if c and c[0] > 0:
            # Con pocas horas medidas, la medida se mezcla con la autonomía oficial/típica (cuenta
            # como PESO_NOMINAL horas de uso): así una racha rara al principio no da cifras absurdas.
            por_hora = (c[0] * c[1] + (100 / total) * PESO_NOMINAL) / (c[1] + PESO_NOMINAL)
            return nivel / por_hora, True
        return total * nivel / 100, False

    def autonomia_nominal(self, clave: str, tipo: str) -> float:
        """Horas con la batería llena: la que puso el usuario, la oficial del modelo o la típica del tipo."""
        if clave in self.nominal:
            return self.nominal[clave]
        for fragmento, horas in MODELOS_CONOCIDOS:
            if fragmento in clave.lower():
                return horas
        return self.nominal.get(clave.split(":")[0]) or self.nominal.get(tipo) or self.nominal["otro"]

    def resumen(self, clave: str) -> str:
        """Texto para la ventana: en qué se basa el cálculo de este dispositivo."""
        c = self.consumo(clave)
        if not c:
            d = self.disp.get(clave)
            uso = 0.0
            if d and d.get("tramos") and d["tramos"][-1]:
                uso = (d.get("uso", 0) - d["tramos"][-1][0][2]) / 3600
            return ("Midiendo el consumo… " + (f"llevas {uso:.1f} h de uso en esta descarga. " if uso >= 0.1 else "")
                    + "Hace falta que baje al menos 3 % con media hora de uso.")
        por_hora, horas = c
        p = self.perfiles.get(clave)
        base = f"Consumo medido: {por_hora:.1f} % por hora de uso (autonomía real ≈ {100 / por_hora:.0f} h), " \
               f"con {horas:.0f} h de uso registradas"
        if p:
            base += f" en {p['descargas']} descarga{'s' if p['descargas'] != 1 else ''}"
            base += ". Último análisis: " + time.strftime("%d/%m %H:%M", time.localtime(p["fecha"]))
        return base + "."


def formato_horas(horas: float) -> str:
    if horas < 1:
        return f"{max(1, round(horas * 60))} min"
    if horas < 48:
        return f"{round(horas)} h"
    dias, resto = divmod(round(horas), 24)
    return f"{round(horas)} h ({dias} d {resto} h)" if resto else f"{round(horas)} h ({dias} d)"
