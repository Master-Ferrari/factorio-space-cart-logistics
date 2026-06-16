# Упаковка мода в zip и копирование в папку mods Factorio.
# Запуск: powershell -ExecutionPolicy Bypass -File tools/pack.ps1
# Структура zip:  space-cart-logistics_<version>.zip / space-cart-logistics / {info.json,...}
# scripts/ — только рантайм .lua (едут целиком); build-tooling живёт в tools/ и в мод не входит.
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

# Что входит в мод. scripts/ теперь содержит только рантайм .lua → копируем целиком.
$include = @('info.json', 'data.lua', 'control.lua', 'scripts', 'graphics', 'locale')
foreach ($item in $include) {
  $src = Join-Path $root $item
  if (Test-Path $src) {
    Copy-Item $src -Destination $stageMod -Recurse -Force
  } else {
    Write-Warning "skip missing: $item"
  }
}

$zipPath = Join-Path $modsDir ("$modName" + "_" + "$version.zip")
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($stageRoot, $zipPath)

Remove-Item $stageRoot -Recurse -Force

Write-Output "packed -> $zipPath"
