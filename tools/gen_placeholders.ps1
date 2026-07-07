# Генерация плейсхолдер-графики для мода space-cart-logistics.
# Запуск: powershell -ExecutionPolicy Bypass -File tools/gen_placeholders.ps1
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

# --- Мок-иконка технологии 256x256 (рельс-крест + стрелка каретки на плашке) ---
$tech = New-Object System.Drawing.Bitmap 256, 256
$gt = [System.Drawing.Graphics]::FromImage($tech)
$gt.SmoothingMode = 'AntiAlias'
$gt.Clear([System.Drawing.Color]::Transparent)
# плашка-фон
$tbg = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 40, 52, 66))
$tbd = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 90, 120, 150)), 6
$gt.FillEllipse($tbg, 16, 16, 224, 224)
$gt.DrawEllipse($tbd, 16, 16, 224, 224)
# рельс-крест (толстые линии по центру)
$trail = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(235, 200, 200, 210)), 22
$trail.StartCap = 'Round'; $trail.EndCap = 'Round'
$gt.DrawLine($trail, 128, 40, 128, 216)
$gt.DrawLine($trail, 40, 128, 216, 128)
# стрелка каретки (по часовой от севера), поверх
$ts = $gt.Save()
$gt.TranslateTransform(128, 128)
$tarrow = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 240, 150, 40))
$tedge  = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 20, 30, 45)), 4
$tbody  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 70, 110, 160))
$gt.FillRectangle($tbody, -28, -16, 56, 44)
$gt.DrawRectangle($tedge, -28, -16, 56, 44)
$tpts = @(
    (New-Object System.Drawing.PointF(0,   -48)),
    (New-Object System.Drawing.PointF(-24, -12)),
    (New-Object System.Drawing.PointF(24,  -12))
)
$gt.FillPolygon($tarrow, $tpts)
$gt.DrawPolygon($tedge, $tpts)
$gt.Restore($ts)
$gt.Dispose()
$tech.Save((Join-Path $gfx 'tech-icon.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$tech.Dispose()

# --- Док (M7): база dock.png (4 ячейки 64x64 в ряд: N,E,S,W), иконка,
# --- арм-оверлей dock-arm.png (69 кадров 192x192: 4 стороны x выдвижение 0..16 + disabled).
# Контракт кадров руки — scripts/docks.lua: variation = side_idx*17 + arm + 1, 69 = disabled.

# Площадка дока с вырезом-направлением (angleDeg: N=0, E=90, S=180, W=270), в (ox,oy)
function Draw-DockBase([System.Drawing.Graphics]$g, [single]$angleDeg, [int]$ox, [int]$oy) {
    $state = $g.Save()
    $g.TranslateTransform(($ox + 32), ($oy + 32))
    $g.RotateTransform($angleDeg)
    $pad   = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 96, 78, 56))
    $plate = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 140, 116, 84))
    $edge  = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 30, 24, 18)), 3
    $slot  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 240, 150, 40))
    $g.FillRectangle($pad, -28, -28, 56, 56)
    $g.DrawRectangle($edge, -28, -28, 56, 56)
    $g.FillRectangle($plate, -20, -20, 40, 40)
    # вырез-стрелка к целевому тайлу (вверх в локальной рамке)
    $pts = @(
        (New-Object System.Drawing.PointF(0,   -30)),
        (New-Object System.Drawing.PointF(-10, -14)),
        (New-Object System.Drawing.PointF(10,  -14))
    )
    $g.FillPolygon($slot, $pts)
    $g.Restore($state)
}

$dockAngles = @(0, 90, 180, 270)   # N, E, S, W — порядок ячеек листа
$dockSheet = New-Object System.Drawing.Bitmap 256, 64
$gd = [System.Drawing.Graphics]::FromImage($dockSheet)
$gd.SmoothingMode = 'AntiAlias'
$gd.Clear([System.Drawing.Color]::Transparent)
for ($i = 0; $i -lt 4; $i++) { Draw-DockBase $gd $dockAngles[$i] ($i * 64) 0 }
$gd.Dispose()
$dockSheet.Save((Join-Path $gfx 'dock.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$dockSheet.Dispose()

$dockIcon = New-Object System.Drawing.Bitmap 64, 64
$gdi = [System.Drawing.Graphics]::FromImage($dockIcon)
$gdi.SmoothingMode = 'AntiAlias'
$gdi.Clear([System.Drawing.Color]::Transparent)
Draw-DockBase $gdi 0 0 0
$gdi.Dispose()
$dockIcon.Save((Join-Path $gfx 'dock-icon.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$dockIcon.Dispose()

# Кадр руки: канва 192x192 (scale 0.5 -> 3x3 тайла, центр = центр дока). Рука тянется
# от центра дока к центру целевого тайла (64 src px), длина = arm/16 доли пути.
function Draw-DockArm([System.Drawing.Graphics]$g, [single]$angleDeg, [int]$arm, [int]$ox, [int]$oy) {
    $state = $g.Save()
    $g.TranslateTransform(($ox + 96), ($oy + 96))
    $g.RotateTransform($angleDeg)
    $armPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 215, 215, 225)), 8
    $armPen.StartCap = 'Round'; $armPen.EndCap = 'Round'
    $hub  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 60, 60, 70))
    $claw = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 240, 150, 40))
    $len = [int](64 * $arm / 16)
    if ($len -gt 0) { $g.DrawLine($armPen, 0, 0, 0, -$len) }
    $g.FillEllipse($hub, -7, -7, 14, 14)
    $g.FillEllipse($claw, -6, (-$len - 6), 12, 12)
    $g.Restore($state)
}

$armCols = 17          # line_length в data.lua
$armFrames = 4 * 17 + 1  # 68 кадров руки + disabled
$armRows = [math]::Ceiling($armFrames / $armCols)
$armSheet = New-Object System.Drawing.Bitmap ($armCols * 192), ($armRows * 192)
$ga = [System.Drawing.Graphics]::FromImage($armSheet)
$ga.SmoothingMode = 'AntiAlias'
$ga.Clear([System.Drawing.Color]::Transparent)
for ($f = 0; $f -lt $armFrames; $f++) {
    $ox = ($f % $armCols) * 192
    $oy = [math]::Floor($f / $armCols) * 192
    if ($f -lt 68) {
        Draw-DockArm $ga $dockAngles[[math]::Floor($f / 17)] ($f % 17) $ox $oy
    } else {
        # disabled: красный крест над доком
        $x = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(230, 200, 50, 40)), 8
        $x.StartCap = 'Round'; $x.EndCap = 'Round'
        $ga.DrawLine($x, ($ox + 78), ($oy + 78), ($ox + 114), ($oy + 114))
        $ga.DrawLine($x, ($ox + 114), ($oy + 78), ($ox + 78), ($oy + 114))
    }
}
$ga.Dispose()
$armSheet.Save((Join-Path $gfx 'dock-arm.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$armSheet.Dispose()

Write-Output "placeholders written to $gfx"
