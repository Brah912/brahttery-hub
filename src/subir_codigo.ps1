# Sube a GitHub el código de la app, en un solo cambio (commit):
#   - los archivos del desarrollo (lista ARCHIVOS, más abajo), dentro de la carpeta "src/" (lo habitual en GitHub),
#   - la página del repositorio: repo\README.md, repo\.gitignore y las capturas de repo\docs.
# NO sube datos personales (config.json, estado.json, historial.json, registros), ni CAMBIOS.md,
# ni las carpetas dist\ y build\.
#
# Usa el mismo token que publicar.ps1:
#   $env:GITHUB_TOKEN = "github_pat_..."
#   powershell -ExecutionPolicy Bypass -File .\subir_codigo.ps1
param([string]$Mensaje = "")
$ErrorActionPreference = "Stop"
$d = $PSScriptRoot
$rutas = [IO.File]::ReadAllText("$d\rutas.py")
$repo = [regex]::Match($rutas, 'REPO_ACTUALIZACIONES\s*=\s*"([^"]*)"').Groups[1].Value.Trim()
$version = [regex]::Match($rutas, 'VERSION\s*=\s*"([0-9.]+)"').Groups[1].Value
if (-not $env:GITHUB_TOKEN) { throw 'Falta el token: $env:GITHUB_TOKEN = "github_pat_..."' }
if (-not $Mensaje) { $Mensaje = "Código fuente de la versión $version" }

$ARCHIVOS = @(
    "Brahttery hub.pyw", "actualizador.py", "apariencia.py", "bandeja.py", "crear_icono.py", "diagnostico.py",
    "dispositivos.py", "estimacion.py", "hid_estandar.py", "manifiesto.py", "modelos.py", "prototipos_icono.py",
    "rutas.py", "selector_color.py", "ventana.py", "sonidos.py", "notificaciones.py",
    "brahttery_hub.ico", "brahttery_hub.png", "brahttery_hub_gris.ico", "brahttery_hub_gris.png",
    "brahttery_hub_oscuro.ico", "brahttery_hub_oscuro.png",
    "compilar.ps1", "publicar.ps1", "subir_readme.ps1", "subir_codigo.ps1", "instalador.iss",
    "requirements.txt", "version_info.txt", "versiones.json"
)
# (ruta en GitHub -> archivo local)
$lista = [ordered]@{}
foreach ($a in $ARCHIVOS) { $lista["src/$a"] = "$d\$a" }
$lista["README.md"] = "$d\repo\README.md"
$lista[".gitignore"] = "$d\repo\.gitignore"
foreach ($f in Get-ChildItem "$d\repo\docs" -File) { $lista["docs/$($f.Name)"] = $f.FullName }
foreach ($l in $lista.Values) { if (-not (Test-Path -LiteralPath $l)) { throw "No existe $l" } }

$cab = @{ Authorization = "Bearer $env:GITHUB_TOKEN"; Accept = "application/vnd.github+json";
          "X-GitHub-Api-Version" = "2022-11-28" }
$api = "https://api.github.com/repos/$repo"
function Enviar($metodo, $url, $datos) {
    Invoke-RestMethod -Method $metodo -Uri $url -Headers $cab -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes(($datos | ConvertTo-Json -Depth 6)))
}

$rama = (Invoke-RestMethod $api -Headers $cab).default_branch
$base = (Invoke-RestMethod "$api/git/ref/heads/$rama" -Headers $cab).object.sha
$arbolBase = (Invoke-RestMethod "$api/git/commits/$base" -Headers $cab).tree.sha
Write-Host "Subiendo $($lista.Count) archivos a github.com/$repo (rama $rama)..."
$arbol = @()
foreach ($ruta in $lista.Keys) {
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($lista[$ruta]))
    $blob = Enviar Post "$api/git/blobs" @{ content = $b64; encoding = "base64" }
    $arbol += @{ path = $ruta; mode = "100644"; type = "blob"; sha = $blob.sha }
    Write-Host "  $ruta"
}
# Versiones anteriores de este script los subían sueltos en la portada: se borran de ahí.
# (y de la carpeta "codigo/", que fue el nombre anterior)
$raiz = Invoke-RestMethod "$api/git/trees/$arbolBase`?recursive=1" -Headers $cab
foreach ($e in $raiz.tree) {
    if ($e.type -eq "blob" -and ($ARCHIVOS -contains $e.path -or $e.path.StartsWith("codigo/"))) {
        $arbol += @{ path = $e.path; mode = "100644"; type = "blob"; sha = $null }
        Write-Host "  (se quita de la portada) $($e.path)"
    }
}
$nuevoArbol = Enviar Post "$api/git/trees" @{ base_tree = $arbolBase; tree = $arbol }
if ($nuevoArbol.sha -eq $arbolBase) { Write-Host "No hay cambios: GitHub ya tiene todo al día."; exit 0 }
$commit = Enviar Post "$api/git/commits" @{ message = $Mensaje; tree = $nuevoArbol.sha; parents = @($base) }
Enviar Patch "$api/git/refs/heads/$rama" @{ sha = $commit.sha } | Out-Null
Write-Host "Listo: https://github.com/$repo  (cambio '$Mensaje')"
