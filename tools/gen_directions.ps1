# Генерация 12 мок-иконок направлений для поп-апа «Select direction».
# Один вид условия = пара (вход → выход) каретки через тайл: 4 входа × 3 поворота.
# Иконка = путь (прямая/дуга от ребра входа к ребру выхода) + стрелка на ребре
# выхода, смотрящая наружу (направление движения на выходе).
# Имя файла = <вход><выход> в нижнем регистре: ns, sn, ew, we, ne, en, ...
# Запуск: powershell -ExecutionPolicy Bypass -File tools/gen_directions.ps1
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$dir  = Join-Path (Join-Path $root 'graphics') 'directions'
New-Item -ItemType Directory -Path $dir -Force | Out-Null

$W = 64

# 12 видов: вход e → выход x (без разворота: x ≠ противоположная e).
$DIRS = @(
    @{e = 'N'; x = 'S'}, @{e = 'S'; x = 'N'},   # прямая N-S, оба направления
    @{e = 'E'; x = 'W'}, @{e = 'W'; x = 'E'},   # прямая E-W
    @{e = 'N'; x = 'E'}, @{e = 'E'; x = 'N'},   # поворот N-E
    @{e = 'N'; x = 'W'}, @{e = 'W'; x = 'N'},   # поворот N-W
    @{e = 'S'; x = 'E'}, @{e = 'E'; x = 'S'},   # поворот S-E
    @{e = 'S'; x = 'W'}, @{e = 'W'; x = 'S'}    # поворот S-W
)

# (вход,выход) → каноничное соединение (ключ для выбора формы тела).
$CONN = @{
    NS = 'NS'; SN = 'NS'; EW = 'EW'; WE = 'EW'
    NE = 'NE'; EN = 'NE'; NW = 'NW'; WN = 'NW'
    SE = 'SE'; ES = 'SE'; SW = 'SW'; WS = 'SW'
}
# дуга поворота (r=32, центр в углу тайла): bounding-box X,Y + стартовый угол, sweep 90.
# Та же геометрия, что и в gen_placeholders/gen_viewport.
$ARC = @{ NE = @(32, -32, 90); NW = @(-32, -32, 0); SE = @(32, 32, 180); SW = @(-32, 32, 270) }

# Якорь стрелки = точка чуть внутри ребра выхода (origin поворота треугольника)
# + угол по часовой от севера (= наружная нормаль ребра). Локально стрелка смотрит
# на «север», после поворота — наружу. Инсет 14px, чтобы остриё не клипалось бордюром.
$HEAD  = @{ N = @(32, 14); S = @(32, 50); E = @(50, 32); W = @(14, 32) }
$ANGLE = @{ N = 0; E = 90; S = 180; W = 270 }

function Make-Dir($e, $x) {
    $bmp = New-Object System.Drawing.Bitmap $W, $W
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::Transparent)

    # --- тело пути: прямая или дуга соответствующего соединения ---
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 205, 210, 222)), 7
    $pen.StartCap = 'Round'; $pen.EndCap = 'Round'
    $conn = $CONN[$e + $x]
    switch ($conn) {
        'NS' { $g.DrawLine($pen, 32, 4, 32, 60) }
        'EW' { $g.DrawLine($pen, 4, 32, 60, 32) }
        default {
            $a = $ARC[$conn]
            $g.DrawArc($pen, $a[0], $a[1], 64, 64, $a[2], 90)
        }
    }
    $pen.Dispose()

    # --- стрелка на ребре выхода, смотрит наружу ---
    $head = $HEAD[$x]
    $st = $g.Save()
    $g.TranslateTransform([single]$head[0], [single]$head[1])
    $g.RotateTransform([single]$ANGLE[$x])
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 245, 150, 40))
    $pts = @(
        (New-Object System.Drawing.PointF(0, -10)),
        (New-Object System.Drawing.PointF(-11, 12)),
        (New-Object System.Drawing.PointF(11, 12))
    )
    $g.FillPolygon($brush, $pts)
    $brush.Dispose()
    $g.Restore($st)
    $g.Dispose()

    $name = ($e + $x).ToLower() + '.png'
    $bmp.Save((Join-Path $dir $name), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

foreach ($d in $DIRS) { Make-Dir $d.e $d.x }

Write-Output "direction icons written to $dir"
