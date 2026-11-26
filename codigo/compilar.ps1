# Compila Brahttery hub con PyInstaller.
#   .\compilar.ps1                 -> dist\Brahttery hub\  (carpeta: el .exe + _internal\)
#   .\compilar.ps1 -UnSoloArchivo  -> dist\un_archivo\Brahttery hub.exe  (todo en un .exe)
#
# La versión normal es en carpeta: arranca más rápido, usa menos RAM (no necesita un proceso
# "lanzador" ni descomprimirse en %TEMP% cada vez) y es la que va en el instalador.
# El .exe de un solo archivo solo se publica para que las versiones viejas (hasta la 1.3.x),
# que se actualizaban cambiando un único .exe, puedan dar el salto a la nueva.
# Requisitos: py -m pip install -r requirements.txt pyinstaller
param([switch]$UnSoloArchivo)
$d = $PSScriptRoot

# La versión sale de rutas.py (VERSION = "x.y.z") y se graba en las propiedades del .exe
$version = [regex]::Match([IO.File]::ReadAllText("$d\rutas.py"), 'VERSION\s*=\s*"([0-9.]+)"').Groups[1].Value
$n = ($version.Split('.') + @('0', '0', '0', '0'))[0..3] -join ', '
$info = (Get-Content "$d\version_info.txt" -Raw) `
    -replace 'filevers=\([^)]*\)', "filevers=($n)" -replace 'prodvers=\([^)]*\)', "prodvers=($n)" `
    -replace "'(FileVersion|ProductVersion)', '[^']*'", "'`$1', '$version'"
[IO.File]::WriteAllText("$d\version_info.txt", $info)    # sin BOM (PyInstaller lo lee como Python)

py "$d\crear_icono.py"
if ($UnSoloArchivo) { $modo = "--onefile"; $salida = "$d\dist\un_archivo"; $trabajo = "$d\build\un_archivo" }
else { $modo = "--onedir"; $salida = "$d\dist"; $trabajo = "$d\build\carpeta" }
py -m PyInstaller --noconfirm $modo --windowed --name "Brahttery hub" `
    --icon "$d\brahttery_hub.ico" --add-data "$d\brahttery_hub.ico;." --add-data "$d\brahttery_hub.png;." `
    --add-data "$d\brahttery_hub_oscuro.ico;." --add-data "$d\brahttery_hub_oscuro.png;." `
    --add-data "$d\brahttery_hub_gris.ico;." --add-data "$d\brahttery_hub_gris.png;." `
    --collect-data customtkinter --version-file "$d\version_info.txt" --exclude-module numpy `
    --workpath $trabajo --specpath "$d\build" --distpath $salida "$d\Brahttery hub.pyw"
