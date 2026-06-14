# Упаковка мода в zip и копирование в папку mods Factorio.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts/pack.ps1
# Структура zip:  space-cart-logistics_<version>.zip / space-cart-logistics / {info.json,...}
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$info = Get-Content (Join-Path $root 'info.json') -Raw | ConvertFrom-Json
$modName = $info.name
$version = $info.version

$modsDir = Join-Path $env:APPDATA 'Factorio\mods'
if (-not (Test-Path $modsDir)) {
  throw "Factorio mods folder not found: $modsDir"
}

# Стейджинг во временной папке с правильным внутренним именем.
$stageRoot = Join-Path $env:TEMP ("scl_pack_" + [guid]::NewGuid().ToString('N'))
$stageMod  = Join-Path $stageRoot $modName
New-Item -ItemType Directory -Path $stageMod -Force | Out-Null

# Что входит в мод.
$include = @('info.json', 'data.lua', 'control.lua', 'graphics', 'locale')
foreach ($item in $include) {
  $src = Join-Path $root $item
  if (Test-Path $src) {
    Copy-Item $src -Destination $stageMod -Recurse -Force
  } else {
    Write-Warning "skip missing: $item"
  }
}

# Рантайм-модули из scripts/*.lua (build-скрипты .ps1 в мод не входят).
$stageScripts = Join-Path $stageMod 'scripts'
New-Item -ItemType Directory -Path $stageScripts -Force | Out-Null
Get-ChildItem (Join-Path $root 'scripts') -Filter '*.lua' | ForEach-Object {
  Copy-Item $_.FullName -Destination $stageScripts -Force
}

$zipPath = Join-Path $modsDir ("$modName" + "_" + "$version.zip")
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($stageRoot, $zipPath)

Remove-Item $stageRoot -Recurse -Force

Write-Output "packed -> $zipPath"
