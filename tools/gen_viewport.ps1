# Генерация слоёв вьюпорта GUI: база + 6 цветных путей, 256x256, прозрачный фон.
# Окно собирает картинку тайла стопкой слоёв (база + активные пути по eff_mask).
# Запуск: powershell -ExecutionPolicy Bypass -File tools/gen_viewport.ps1
#
# Геометрия = tools/gen_placeholders.ps1 ×4 (64→256): тайл [0..256], центр 128,
# середины рёбер N(128,0) S(128,256) E(256,128) W(0,128). Повороты — дуга r=128
# вокруг угла тайла. Цвета путей — из readme (палитра 6 соединений).
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$vp   = Join-Path (Join-Path $root 'graphics') 'viewport'
New-Item -ItemType Directory -Path $vp -Force | Out-Null

$W    = 256
$penW = 32

# --- База: тёмная плита тайла + рамка + слабый центральный узел ---
$bmp = New-Object System.Drawing.Bitmap $W, $W
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = 'AntiAlias'
$g.Clear([System.Drawing.Color]::Transparent)
$fill = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(120, 70, 75, 90))
$g.FillRectangle($fill, 8, 8, 240, 240)
$border = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(180, 120, 125, 140)), 4
$g.DrawRectangle($border, 8, 8, 240, 240)
$node = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(150, 200, 205, 215))
$g.FillEllipse($node, 114, 114, 28, 28)
$g.Dispose()
$bmp.Save((Join-Path $vp 'base.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

# --- Один путь своим цветом на прозрачном фоне ---
# kind: 'ns'/'ew' — прямая; 'arc' — дуга с боксом ($bx,$by,256,256) и стартовым углом.
function Make-Layer($name, $r, $gc, $b, $kind, $bx, $by, $start) {
    $bmp = New-Object System.Drawing.Bitmap $W, $W
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::Transparent)
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, $r, $gc, $b)), $penW
    $pen.StartCap = 'Round'; $pen.EndCap = 'Round'
    switch ($kind) {
        'ns'  { $g.DrawLine($pen, 128, 0, 128, 256) }                  # N-S
        'ew'  { $g.DrawLine($pen, 0, 128, 256, 128) }                  # E-W
        'arc' { $g.DrawArc($pen, $bx, $by, 256, 256, $start, 90) }     # поворот r=128
    }
    $pen.Dispose(); $g.Dispose()
    $bmp.Save((Join-Path $vp $name), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

# Цвета: N-S=red, E-W=cyan, N-E=purple, N-W=yellow, S-E=green, S-W=orange (readme).
# Дуги (центр в углу тайла): N-E центр(256,0) бокс(128,-128) старт90; N-W центр(0,0)
# бокс(-128,-128) старт0; S-E центр(256,256) бокс(128,128) старт180; S-W центр(0,256)
# бокс(-128,128) старт270 — всё ×4 от gen_placeholders.
Make-Layer 'ns.png' 230 60 60  'ns'  0    0    0
Make-Layer 'ew.png' 60 200 220 'ew'  0    0    0
Make-Layer 'ne.png' 175 95 225 'arc' 128  -128 90
Make-Layer 'nw.png' 235 205 70 'arc' -128 -128 0
Make-Layer 'se.png' 70 200 95  'arc' 128  128  180
Make-Layer 'sw.png' 240 150 50 'arc' -128 128  270

Write-Output "viewport layers written to $vp"
