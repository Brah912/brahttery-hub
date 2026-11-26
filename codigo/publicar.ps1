# Publica una actualización de Brahttery hub en GitHub Releases.
# Quien tenga la app instalada la verá en "Acerca de" (y con un aviso en la bandeja)
# y podrá instalarla con un clic, sin reinstalar nada.
#
# Pasos:
#   1. Sube VERSION en rutas.py (por ejemplo de "1.1.0" a "1.2.0").
#   2. Ejecuta:   .\publicar.ps1 -Notas "Qué cambió en esta versión"
#      (-SinCompilar sube lo que ya está en dist\publicar, sin volver a compilar)
#
# Para subirla sola, define antes un token de GitHub con permiso "Contents: Read and write"
# sobre el repositorio:   $env:GITHUB_TOKEN = "github_pat_..."
# Sin token, el script deja los archivos listos en dist\publicar y te dice cómo subirlos a mano.
param([string]$Notas = "", [switch]$SinCompilar)
$ErrorActionPreference = "Stop"
$d = $PSScriptRoot
$rutas = Get-Content "$d\rutas.py" -Raw
$version = [regex]::Match($rutas, 'VERSION\s*=\s*"([0-9.]+)"').Groups[1].Value
$repo = [regex]::Match($rutas, 'REPO_ACTUALIZACIONES\s*=\s*"([^"]*)"').Groups[1].Value.Trim()
if (-not $repo) { throw 'Falta REPO_ACTUALIZACIONES en rutas.py (formato "usuario/repositorio").' }

$sal = "$d\dist\publicar"
function Compilar([switch]$UnArchivo) {
    $ErrorActionPreference = "Continue"     # PyInstaller escribe su progreso por stderr
    & "$d\compilar.ps1" -UnSoloArchivo:$UnArchivo 2>&1 | Out-File "$d\build\compilar.log" -Encoding utf8
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) { throw "La compilación falló; mira build\compilar.log" }
}
function Huella([string]$archivo) {
    $h = (Get-FileHash $archivo -Algorithm SHA256).Hash.ToLower()
    Set-Content "$archivo.sha256" "$h  $(Split-Path $archivo -Leaf)" -Encoding ascii -NoNewline
    return $h
}
if (-not $SinCompilar) {
    if (Test-Path $sal) { Remove-Item "$sal\*" -Force }
    New-Item -ItemType Directory -Force $sal | Out-Null

    # 1. La app en carpeta (la que va en el instalador)
    Write-Host "Compilando la versión $version..."
    Compilar
    $exeVer = (Get-Item "$d\dist\Brahttery hub\Brahttery hub.exe").VersionInfo.ProductVersion
    if ($exeVer -ne $version) { throw "El .exe compilado es la versión $exeVer, no la $version" }

    # 2. El instalador. Es también lo que descargan las actualizaciones automáticas (desde la 1.4.0).
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Falta Inno Setup. Instálalo con:  winget install JRSoftware.InnoSetup" }
    Write-Host "Creando el instalador..."
    & $iscc /Q "/DVersion=$version" "$d\instalador.iss"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el instalador" }
    Move-Item "$d\dist\Brahttery-hub-Setup-$version.exe" "$sal\" -Force
    # copia con nombre fijo: https://github.com/<repo>/releases/latest/download/Brahttery-hub-Setup.exe
    Copy-Item "$sal\Brahttery-hub-Setup-$version.exe" "$sal\Brahttery-hub-Setup.exe" -Force
    Huella "$sal\Brahttery-hub-Setup.exe" | Out-Null

    # 3. El .exe de un solo archivo: solo para que las versiones hasta la 1.3.x puedan actualizarse
    #    (ellas reemplazan un único .exe). Desde la 1.4.0 se actualiza con el instalador.
    Write-Host "Compilando el .exe de un solo archivo (para versiones antiguas)..."
    Compilar -UnArchivo
    Copy-Item "$d\dist\un_archivo\Brahttery hub.exe" "$sal\Brahttery-hub.exe" -Force
    Huella "$sal\Brahttery-hub.exe" | Out-Null
}
if (-not (Test-Path "$sal\Brahttery-hub-Setup.exe.sha256")) { throw "No hay nada preparado en $sal" }

# brahttery-hub.json: versión, notas e historial. La app lo descarga para buscar novedades
# sin usar la API de GitHub (que limita a 60 consultas por hora y conexión).
$env:BH_NOTAS = $Notas
py "$d\manifiesto.py" $version "$sal\Brahttery-hub.exe" "$sal\brahttery-hub.json" "$sal\Brahttery-hub-Setup.exe"
if ($LASTEXITCODE -ne 0) { throw "No se pudo generar brahttery-hub.json" }

# Texto de la página de la versión en GitHub: las notas + cómo instalar + huellas
$shaSetup = (Get-Content "$sal\Brahttery-hub-Setup.exe.sha256" -Raw).Split(' ')[0]
$cuerpoMd = "## Novedades`n`n$Notas`n`n## Descargar e instalar`n`n" +
    "1. Descarga **Brahttery-hub-Setup.exe** (más abajo, en *Assets*).`n" +
    "2. Ábrelo. Si Windows muestra *Windows protegió su PC*, pulsa **Más información → Ejecutar de todas formas** " +
    "(la app no tiene firma digital de pago; ver [por qué](https://github.com/$repo#por-qué-windows-avisa-al-instalarla)).`n" +
    "3. **Siguiente → Instalar → Finalizar.** No pide permisos de administrador y conserva tus ajustes.`n`n" +
    "¿Ya la tienes instalada? No hace falta descargar nada: se actualiza sola al abrirla.`n`n" +
    "Guía completa y cómo funciona: [README](https://github.com/$repo#readme)`n`n" +
    "<sub>SHA-256 de Brahttery-hub-Setup.exe: ``$shaSetup``</sub>"

if (-not $env:GITHUB_TOKEN) {
    Write-Host ""
    Write-Host "Listo para subir (sin GITHUB_TOKEN no se sube solo):"
    Write-Host "  1. Abre https://github.com/$repo/releases/new"
    Write-Host "  2. Etiqueta: v$version   Título: Brahttery hub $version"
    Write-Host "  3. Arrastra los archivos de $sal"
    Write-Host "  4. Pulsa 'Publish release'"
    exit 0
}

$cab = @{ Authorization = "Bearer $env:GITHUB_TOKEN"; Accept = "application/vnd.github+json";
          "X-GitHub-Api-Version" = "2022-11-28" }
# GitHub no deja crear versiones en un repositorio vacío: la primera vez se sube un README
$vacio = $false
try { Invoke-RestMethod "https://api.github.com/repos/$repo/commits?per_page=1" -Headers $cab | Out-Null }
catch { $vacio = $_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 409 }
if ($vacio) {
    Write-Host "El repositorio está vacío: creando README.md..."
    $readme = "# Brahttery hub`n`nMuestra la batería de tus periféricos en la bandeja de Windows.`n`n" +
              "Descarga la última versión en [Releases](https://github.com/$repo/releases/latest) " +
              "(descarga el archivo Brahttery-hub-Setup-....exe). La app se actualiza sola.`n"
    $cont = @{ message = "README"; content = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($readme)) } |
        ConvertTo-Json
    Invoke-RestMethod -Method Put -Uri "https://api.github.com/repos/$repo/contents/README.md" -Headers $cab `
        -Body ([Text.Encoding]::UTF8.GetBytes($cont)) -ContentType "application/json; charset=utf-8" | Out-Null
}

$cuerpo = @{ tag_name = "v$version"; name = "Brahttery hub $version"; body = $cuerpoMd } | ConvertTo-Json
Write-Host "Creando la versión v$version en github.com/$repo..."
$rel = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$repo/releases" -Headers $cab `
    -Body ([Text.Encoding]::UTF8.GetBytes($cuerpo)) -ContentType "application/json; charset=utf-8"
$subida = $rel.upload_url -replace '\{.*\}', ''
foreach ($f in Get-ChildItem $sal -File) {
    Write-Host "  subiendo $($f.Name)..."
    Invoke-RestMethod -Method Post -Uri "$subida`?name=$([uri]::EscapeDataString($f.Name))" -Headers $cab `
        -InFile $f.FullName -ContentType "application/octet-stream" | Out-Null
}
Write-Host "Publicada: $($rel.html_url)"
