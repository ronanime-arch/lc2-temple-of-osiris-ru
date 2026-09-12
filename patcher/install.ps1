# Установка русской озвучки Lara Croft and the Temple of Osiris.
# Нужен только Windows PowerShell — ни Python, ни ffmpeg, ни распаковщиков.
#
#   .\install.ps1                      # найти игру рядом и поставить
#   .\install.ps1 -Game "D:\...\Game"  # указать папку игры вручную
#   .\install.ps1 -Restore             # вернуть английскую озвучку
#   .\install.ps1 -Force               # ставить, даже если файл не той сборки

[CmdletBinding()]
param(
    [string]$Game,
    [string]$Patch,
    [switch]$Restore,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ARC  = 'bigfile_ENGLISH.000.tiger'
$SRC_SHA = '959B8EDE228471F10CBEE111BBE5DC007F5823866E2201C5DD9136615ACA5FD5'
$DST_SHA = 'B6235BC76AFC16B9361BD96E27475F7BBAD7CF114DFAA2C6D999E7A0FA11B07C'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Halt { if (-not $env:LC2_NOPAUSE) { Write-Host 'Нажмите Enter, чтобы закрыть окно.'; [void](Read-Host) } }
function Fail($m) { Write-Host ''; Write-Host "ОШИБКА: $m" -ForegroundColor Red; Write-Host ''; Halt; exit 1 }
function Ok($m)   { Write-Host $m -ForegroundColor Green }
function Info($m) { Write-Host $m }

# --- где игра -----------------------------------------------------------
if (-not $Game) {
    $try = @($here, (Split-Path -Parent $here), (Join-Path $here 'Game'),
             (Join-Path (Split-Path -Parent $here) 'Game'))
    foreach ($d in $try) {
        if ($d -and (Test-Path (Join-Path $d $ARC))) { $Game = $d; break }
    }
}
if (-not $Game) {
    Info 'Папка игры не найдена рядом с установщиком.'
    Info "Укажите папку, в которой лежат LC2.exe и $ARC"
    $Game = (Read-Host 'Папка игры').Trim('"').Trim()
}
$arc = Join-Path $Game $ARC
$bak = "$arc.bak"
if (-not (Test-Path $arc)) { Fail "в папке `"$Game`" нет файла $ARC" }
Info "Игра: $Game"

# --- откат --------------------------------------------------------------
if ($Restore) {
    if (-not (Test-Path $bak)) { Fail "резервной копии $ARC.bak нет — откатывать нечего" }
    Copy-Item $bak $arc -Force
    Ok 'Английская озвучка возвращена из резервной копии.'
    Halt; exit 0
}

# --- патч ---------------------------------------------------------------
if (-not $Patch) { $Patch = Join-Path $here 'lc2_ru.lc2p' }
if (-not (Test-Path $Patch)) { Fail "файл патча не найден: $Patch" }

# --- резервная копия ----------------------------------------------------
if (Test-Path $bak) {
    Info "Резервная копия уже есть, ставим поверх неё: $ARC.bak"
    Copy-Item $bak $arc -Force
} else {
    Info 'Делаю резервную копию (около минуты)...'
    Copy-Item $arc $bak
    Ok "Резерв: $ARC.bak — не удаляйте его."
}

Info 'Читаю файл игры...'
$d = [System.IO.File]::ReadAllBytes($arc)
$sha = (Get-FileHash -Path $arc -Algorithm SHA256).Hash
if ($sha -eq $DST_SHA) {
    Ok 'Русская озвучка уже стоит. Ничего делать не нужно.'
    Halt; exit 0
}
if ($sha -ne $SRC_SHA) {
    Write-Host ''
    Write-Host 'ВНИМАНИЕ: этот bigfile_ENGLISH.000.tiger отличается от того,' -ForegroundColor Yellow
    Write-Host 'на котором патч собирался. Скорее всего, у вас другая сборка игры.' -ForegroundColor Yellow
    Write-Host "  ожидалось: $SRC_SHA" -ForegroundColor DarkGray
    Write-Host "  у вас:     $sha" -ForegroundColor DarkGray
    Write-Host 'Патч привязан к записям архива, а не к смещениям в файле,' -ForegroundColor Yellow
    Write-Host 'поэтому он может встать и так. Каждая запись проверяется отдельно.' -ForegroundColor Yellow
    if (-not $Force) {
        $a = Read-Host 'Попробовать? Резерв уже сделан, откат — install.ps1 -Restore (д/н)'
        if ($a -notmatch '^(д|y)') { Info 'Отменено.'; exit 0 }
    }
}

# --- таблица TAFS: хеш записи -> смещение и размер -----------------------
if ($d.Length -lt 0x40 -or [System.Text.Encoding]::ASCII.GetString($d, 0, 4) -ne 'TAFS') {
    Fail 'это не архив TAFS — файл повреждён или не тот'
}
$cnt = [BitConverter]::ToUInt32($d, 0x0c)
$ents = @{}
for ($i = 0; $i -lt $cnt; $i++) {
    $p = 0x34 + $i * 24
    $ents[[BitConverter]::ToUInt32($d, $p)] = @([BitConverter]::ToUInt32($d, $p + 20),
                                                [BitConverter]::ToUInt32($d, $p + 8))
}
Info "Записей в архиве: $cnt"

# --- применение ---------------------------------------------------------
$p = [System.IO.File]::ReadAllBytes($Patch)
if ([System.Text.Encoding]::ASCII.GetString($p, 0, 6) -ne 'LC2RU1') { Fail 'файл патча повреждён' }
$nrec = [BitConverter]::ToUInt32($p, 10)
$o = 14 + 64                      # заголовок + два SHA-256

Info "Вшиваю $nrec реплик..."
$done = 0; $miss = 0; $bad = 0
for ($r = 0; $r -lt $nrec; $r++) {
    $h    = [BitConverter]::ToUInt32($p, $o)
    $size = [BitConverter]::ToUInt32($p, $o + 4)
    $nrun = [BitConverter]::ToUInt32($p, $o + 8)
    $o += 12
    $e = $ents[$h]
    $use = $true
    if (-not $e)            { $use = $false; $miss++ }
    elseif ($e[1] -ne $size) { $use = $false; $bad++ }
    for ($k = 0; $k -lt $nrun; $k++) {
        $delta = [BitConverter]::ToUInt32($p, $o)
        $len   = [BitConverter]::ToUInt32($p, $o + 4)
        $o += 8
        if ($use) {
            $to = $e[0] + $delta
            if ($to + $len -le $d.Length) { [Array]::Copy($p, $o, $d, $to, $len) }
            else { $use = $false; $bad++ }
        }
        $o += $len
    }
    if ($use) { $done++ }
    if (($r % 200) -eq 0) { Write-Progress -Activity 'Вшиваю озвучку' -PercentComplete (100 * $r / $nrec) }
}
Write-Progress -Activity 'Вшиваю озвучку' -Completed

if ($done -eq 0) { Fail 'ни одна реплика не подошла — сборка игры несовместима. Файл не изменён.' }

Info 'Записываю файл игры...'
[System.IO.File]::WriteAllBytes($arc, $d)

Write-Host ''
Ok "Готово: вшито реплик $done из $nrec."
if ($miss) { Write-Host "  не найдено в архиве: $miss" -ForegroundColor Yellow }
if ($bad)  { Write-Host "  не совпал размер записи: $bad" -ForegroundColor Yellow }
if ($sha -eq $SRC_SHA) {
    $now = (Get-FileHash -Path $arc -Algorithm SHA256).Hash
    if ($now -eq $DST_SHA) { Ok 'Контрольная сумма результата совпала — установка точная.' }
    else { Write-Host 'ВНИМАНИЕ: контрольная сумма результата не совпала.' -ForegroundColor Red }
}
Write-Host ''
Write-Host 'Откат: install.ps1 -Restore (или переименуйте .bak обратно).'
Write-Host ''
Halt
