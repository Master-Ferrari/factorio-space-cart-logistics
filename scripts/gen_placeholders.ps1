# Генерация плейсхолдер-графики для мода space-cart-logistics.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts/gen_placeholders.ps1
#
# Контракт «бит → ячейка» (см. readme):
#   Биты: 0=N-S, 1=E-W, 2=N-E, 3=N-W, 4=S-E, 5=S-W.  mask = OR активных (0..63).
#   Ячейка = mask row-major, 8 в ряд: col = mask & 7, row = mask >> 3.
#   Ячейка 0 (mask 0) — полностью прозрачная (невидимый тайл).
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$gfx  = Join-Path $root 'graphics'
if (-not (Test-Path $gfx)) { New-Item -ItemType Directory -Path $gfx | Out-Null }

# --- Рисуем одну ячейку рельса 64x64 для заданной маски в заданный Graphics со смещением (ox,oy) ---
function Draw-RailCell([System.Drawing.Graphics]$g, [int]$mask, [int]$ox, [int]$oy) {
    if ($mask -eq 0) { return }   # прозрачная ячейка

    $bg   = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(60, 80, 80, 95))
    $pen  = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(235, 185, 185, 195)), 8
    $pen.StartCap = 'Round'; $pen.EndCap = 'Round'
    $node = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(245, 215, 215, 225))

    # лёгкий фон тайла, чтобы видеть его границы
    $g.FillRectangle($bg, ($ox + 2), ($oy + 2), 60, 60)

    # прямые
    if ($mask -band 1)  { $g.DrawLine($pen, ($ox + 32), ($oy + 0),  ($ox + 32), ($oy + 64)) }  # N-S
    if ($mask -band 2)  { $g.DrawLine($pen, ($ox + 0),  ($oy + 32), ($ox + 64), ($oy + 32)) }  # E-W
    # повороты (дуга r=32, центр в углу тайла)
    if ($mask -band 4)  { $g.DrawArc($pen, ($ox + 32), ($oy - 32), 64, 64, 90,  90) }          # N-E центр(64,0)
    if ($mask -band 8)  { $g.DrawArc($pen, ($ox - 32), ($oy - 32), 64, 64, 0,   90) }          # N-W центр(0,0)
    if ($mask -band 16) { $g.DrawArc($pen, ($ox + 32), ($oy + 32), 64, 64, 180, 90) }          # S-E центр(64,64)
    if ($mask -band 32) { $g.DrawArc($pen, ($ox - 32), ($oy + 32), 64, 64, 270, 90) }          # S-W центр(0,64)

    # центральный узел
    $g.FillEllipse($node, ($ox + 26), ($oy + 26), 12, 12)
}

# --- Лист рельса 512x512: 64 ячейки (8x8) по контракту бит→ячейка ---
$railSheet = New-Object System.Drawing.Bitmap 512, 512
$gr = [System.Drawing.Graphics]::FromImage($railSheet)
$gr.SmoothingMode = 'AntiAlias'
$gr.Clear([System.Drawing.Color]::Transparent)
for ($mask = 0; $mask -lt 64; $mask++) {
    $col = $mask -band 7
    $row = $mask -shr 3
    Draw-RailCell $gr $mask ($col * 64) ($row * 64)
}
$gr.Dispose()
$railSheet.Save((Join-Path $gfx 'rail.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$railSheet.Dispose()

# --- Иконка рельса 64x64 (крест, mask 63) ---
$railIcon = New-Object System.Drawing.Bitmap 64, 64
$gri = [System.Drawing.Graphics]::FromImage($railIcon)
$gri.SmoothingMode = 'AntiAlias'
$gri.Clear([System.Drawing.Color]::Transparent)
Draw-RailCell $gri 63 0 0
$gri.Dispose()
$railIcon.Save((Join-Path $gfx 'rail-icon.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$railIcon.Dispose()

# --- Каретка: лист 32 кадра (2048x64), стрелка по часовой от севера ---
function Draw-Cart([System.Drawing.Graphics]$g, [single]$angleDeg) {
    $state = $g.Save()
    $g.TranslateTransform(32, 32)
    $g.RotateTransform($angleDeg)
    $body  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 70, 110, 160))
    $arrow = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 240, 150, 40))
    $edge  = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 20, 30, 45)), 2
    $g.FillRectangle($body, -14, -8, 28, 22)
    $g.DrawRectangle($edge, -14, -8, 28, 22)
    $pts = @(
        (New-Object System.Drawing.PointF(0,   -24)),
        (New-Object System.Drawing.PointF(-12,  -6)),
        (New-Object System.Drawing.PointF(12,   -6))
    )
    $g.FillPolygon($arrow, $pts)
    $g.DrawPolygon($edge, $pts)
    $g.Restore($state)
}

$frames = 32
$sheet = New-Object System.Drawing.Bitmap ($frames * 64), 64
$gs = [System.Drawing.Graphics]::FromImage($sheet)
$gs.SmoothingMode = 'AntiAlias'
$gs.Clear([System.Drawing.Color]::Transparent)
for ($i = 0; $i -lt $frames; $i++) {
    $frame = New-Object System.Drawing.Bitmap 64, 64
    $gf = [System.Drawing.Graphics]::FromImage($frame)
    $gf.SmoothingMode = 'AntiAlias'
    $gf.Clear([System.Drawing.Color]::Transparent)
    Draw-Cart $gf ([single]($i * (360.0 / $frames)))
    $gf.Dispose()
    $gs.DrawImage($frame, ($i * 64), 0)
    $frame.Dispose()
}
$gs.Dispose()
$sheet.Save((Join-Path $gfx 'cart.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$sheet.Dispose()

# --- Иконка каретки 64x64 (кадр "север") ---
$icon = New-Object System.Drawing.Bitmap 64, 64
$gi = [System.Drawing.Graphics]::FromImage($icon)
$gi.SmoothingMode = 'AntiAlias'
$gi.Clear([System.Drawing.Color]::Transparent)
Draw-Cart $gi ([single]0)
$gi.Dispose()
$icon.Save((Join-Path $gfx 'cart-icon.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$icon.Dispose()

Write-Output "placeholders written to $gfx"
