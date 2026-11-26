"""Genera brahttery-hub.json para una versión (lo llama publicar.ps1).

La app lee este archivo de la última versión publicada en GitHub para saber si hay una
versión nueva, sus notas y el historial. Al ser una descarga normal (no la API de GitHub)
no cuenta para el límite de 60 consultas por hora.

  "setup": desde la 1.4.0 las actualizaciones se instalan con el instalador (en silencio).
  "tamano"/"sha256": el .exe de un solo archivo, para las versiones hasta la 1.3.x.

Además guarda las notas en versiones.json (historial local, de la más nueva a la más vieja).

  py manifiesto.py <version> <exe> <salida.json> [<setup>]   (las notas van en la variable BH_NOTAS)
"""
import datetime
import hashlib
import json
import os
import sys

version, exe, salida = sys.argv[1], sys.argv[2], sys.argv[3]
setup = sys.argv[4] if len(sys.argv) > 4 else None
notas = os.environ.get("BH_NOTAS", "").replace("\r", "").strip()
historial_ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "versiones.json")
try:
    with open(historial_ruta, encoding="utf-8-sig") as f:
        historial = json.load(f)
except (OSError, ValueError):
    historial = []

fecha = datetime.date.today().strftime("%d/%m/%Y")
historial = [{"version": version, "fecha": fecha, "notas": notas}] + \
            [v for v in historial if v.get("version") != version]
with open(historial_ruta, "w", encoding="utf-8") as f:
    json.dump(historial, f, ensure_ascii=False, indent=2)


def huella(ruta: str) -> tuple[int, str]:
    with open(ruta, "rb") as f:
        datos = f.read()
    return len(datos), hashlib.sha256(datos).hexdigest()


tamano, sha = huella(exe)
manifiesto = {"version": version, "fecha": fecha, "notas": notas, "tamano": tamano, "sha256": sha}
if setup:
    t, h = huella(setup)
    manifiesto["setup"] = {"tamano": t, "sha256": h}
manifiesto["historial"] = historial[:10]
with open(salida, "w", encoding="utf-8") as f:
    json.dump(manifiesto, f, ensure_ascii=False, indent=2)
print(f"brahttery-hub.json: version {version}, {len(historial)} versiones en el historial")
