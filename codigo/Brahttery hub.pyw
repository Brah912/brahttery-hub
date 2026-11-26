"""Brahttery hub: punto de entrada único (también del .exe).

  Brahttery hub.pyw               -> icono(s) de batería en la bandeja del sistema
  Brahttery hub.pyw --configurar  -> ventana de personalización
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if "--configurar" in sys.argv[1:]:
        import ventana
        ventana.main()
    else:
        import bandeja
        bandeja.main()
