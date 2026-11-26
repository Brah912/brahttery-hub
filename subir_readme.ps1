# Sube la página del repositorio en GitHub: README.md y las imágenes de repo\docs.
# Usa el mismo token que publicar.ps1:
#   $env:GITHUB_TOKEN = "github_pat_..."
#   powershell -ExecutionPolicy Bypass -File .\subir_readme.ps1
$ErrorActionPreference = "Stop"
$d = $PSScriptRoot
$repo = [regex]::Match((Get-Content "$d\rutas.py" -Raw -Encoding UTF8), 'REPO_ACTUALIZACIONES\s*=\s*"([^"]*)"').Groups[1].Value.Trim()
if (-not $env:GITHUB_TOKEN) { throw 'Falta el token: $env:GITHUB_TOKEN = "github_pat_..."' }
$cab = @{ Authorization = "Bearer $env:GITHUB_TOKEN"; Accept = "application/vnd.github+json";
          "X-GitHub-Api-Version" = "2022-11-28" }

$archivos = @(Get-Item "$d\repo\README.md") + @(Get-ChildItem "$d\repo\docs" -File)
foreach ($f in $archivos) {
    $ruta = $f.FullName.Substring("$d\repo\".Length).Replace('\', '/')
    $url = "https://api.github.com/repos/$repo/contents/$ruta"
    $sha = $null
    try { $sha = (Invoke-RestMethod $url -Headers $cab).sha } catch { }      # no existe todavía
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($f.FullName))
    if ($sha) {
        # sin cambios: no se vuelve a subir
        $actual = (Invoke-RestMethod $url -Headers $cab).content -replace '\s', ''
        if ($actual -eq $b64) { Write-Host "  sin cambios: $ruta"; continue }
    }
    $datos = @{ message = "Actualizar $ruta"; content = $b64 }
    if ($sha) { $datos.sha = $sha }
    Invoke-RestMethod -Method Put -Uri $url -Headers $cab -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes(($datos | ConvertTo-Json))) | Out-Null
    Write-Host "  subido: $ruta"
}
Write-Host "Listo: https://github.com/$repo"
