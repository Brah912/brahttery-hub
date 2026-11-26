"""Notificaciones modernas de Windows 10/11 (las que aparecen abajo a la derecha y quedan en el panel).

Los "globitos" del icono de la bandeja (Shell_NotifyIcon) Windows 11 a veces los acepta pero no los
muestra. Esto usa el sistema de notificaciones de Windows (ToastNotificationManager):
  * la app se registra con su nombre y su icono (HKCU\\Software\\Classes\\AppUserModelId\\BrahtteryHub),
    así la notificación sale como "Brahttery hub" y se puede configurar en Configuración > Notificaciones;
  * se muestra a través de PowerShell (que trae WinRT), en un proceso oculto: tarda ~1 s pero no
    bloquea a la app. El sonido lo pone la app (sonidos.py): la notificación va en silencio.
"""
from __future__ import annotations

import os
import subprocess
import winreg
from xml.sax.saxutils import escape

import rutas

AUMID = rutas.ID
_CLAVE = rf"Software\Classes\AppUserModelId\{AUMID}"


def registrar(icono: str | None = None) -> None:
    """Nombre e icono con los que Windows muestra las notificaciones de la app."""
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _CLAVE, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, rutas.NOMBRE)
            ruta = icono or rutas.recurso("brahttery_hub.png")
            if os.path.exists(ruta):
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, ruta)
    except OSError:
        pass


def mostrar(titulo: str, texto: str, imagen: str | None = None) -> bool:
    """Lanza la notificación (sin esperar). False si no se pudo ni intentar."""
    registrar()
    logo = (f'<image placement="appLogoOverride" src="{escape(imagen)}"/>'
            if imagen and os.path.exists(imagen) else "")
    xml = (f'<toast><visual><binding template="ToastGeneric"><text>{escape(titulo)}</text>'
           f'<text>{escape(texto)}</text>{logo}</binding></visual><audio silent="true"/></toast>')
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]"
        " | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('{xml.replace(chr(39), chr(39) * 2)}');"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{AUMID}')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-Command", script], creationflags=0x08000000,   # CREATE_NO_WINDOW
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=rutas.entorno_nuevo())
        return True
    except OSError:
        return False
