"""Genera los iconos de Brahttery hub.

  brahttery_hub.ico / .png          BrH rojo sobre blanco (icono del .exe; tema Claro)
  brahttery_hub_gris.ico / .png     BrH verde sobre gris (tema Gris)
  brahttery_hub_oscuro.ico / .png   BrH azul sobre negro (tema Oscuro)
"""
from PIL import Image

from prototipos_icono import brh_azul_negro, brh_rojo_medidor, brh_verde_gris

TAMANOS = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def guardar(funcion, nombre: str) -> None:
    def dibujar(lado: int) -> Image.Image:
        return funcion(lado * 4).resize((lado, lado), Image.LANCZOS)

    grande = dibujar(256)
    grande.save(nombre + ".ico", sizes=[(t, t) for t in TAMANOS],
                append_images=[dibujar(t) for t in TAMANOS if t != 256])
    grande.save(nombre + ".png")


if __name__ == "__main__":
    guardar(brh_rojo_medidor, "brahttery_hub")
    guardar(brh_azul_negro, "brahttery_hub_oscuro")
    guardar(brh_verde_gris, "brahttery_hub_gris")
    print("iconos creados")
