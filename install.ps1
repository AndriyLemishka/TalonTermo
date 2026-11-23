[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoZip = 'https://github.com/AndriyLemishka/TalonTermo/archive/refs/heads/main.zip'
$baseDir = Join-Path $env:LOCALAPPDATA 'TalonTermo'
$extDest = Join-Path $baseDir 'extension'
$tmpZip  = Join-Path $env:TEMP 'TalonTermo.zip'
$tmpDir  = Join-Path $env:TEMP ('TalonTermo_extract_' + [Guid]::NewGuid().ToString('N'))

Write-Host '==> Завантаження TalonTermo з GitHub...' -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoZip -OutFile $tmpZip -UseBasicParsing

Write-Host '==> Розпакування файлів...' -ForegroundColor Cyan
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($tmpZip, $tmpDir)
$extractedExt = Join-Path $tmpDir 'TalonTermo-main\extension'
if (-not (Test-Path $extractedExt)) {
    throw "Не знайдено папку extension в архіві ($extractedExt)"
}

$isUpdate = Test-Path $extDest
New-Item -ItemType Directory -Force -Path $extDest | Out-Null
Copy-Item -Path (Join-Path $extractedExt '*') -Destination $extDest -Recurse -Force

Remove-Item -Path $tmpZip -Force -ErrorAction SilentlyContinue
Remove-Item -Path $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

# Створення скрипта швидкого оновлення
$updaterContent = @"
@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/AndriyLemishka/TalonTermo/main/install.ps1 | iex"
pause
"@
$localCmd = Join-Path $baseDir 'Оновити_TalonTermo.cmd'
Set-Content -Path $localCmd -Value $updaterContent -Encoding Ascii

$desktop = [Environment]::GetFolderPath('Desktop')
if ($desktop -and (Test-Path $desktop)) {
    $desktopCmd = Join-Path $desktop 'Оновити_TalonTermo.cmd'
    Set-Content -Path $desktopCmd -Value $updaterContent -Encoding Ascii -ErrorAction SilentlyContinue
}

# Реєстрація протоколу talontermo://extensions для відкриття chrome://extensions за посиланням
try {
    $vbsPath = Join-Path $baseDir 'open_chrome_ext.vbs'
    $vbsCode = "Set sh = CreateObject(`"WScript.Shell`")`r`nsh.Run `"chrome.exe `"`"chrome://extensions`"`"`", 1, False"
    Set-Content -Path $vbsPath -Value $vbsCode -Encoding Ascii

    $protoKey = 'HKCU:\Software\Classes\talontermo'
    New-Item -Path $protoKey -Force | Out-Null
    Set-ItemProperty -Path $protoKey -Name '(Default)' -Value 'URL:TalonTermo Protocol'
    Set-ItemProperty -Path $protoKey -Name 'URL Protocol' -Value ''
    $cmdKey = Join-Path $protoKey 'shell\open\command'
    New-Item -Path $cmdKey -Force | Out-Null
    Set-ItemProperty -Path $cmdKey -Name '(Default)' -Value "wscript.exe `"$vbsPath`""
} catch {
    # Не критично, якщо реєстр обмежений політиками
}

try {
    Set-Clipboard -Value $extDest
    $copiedNote = ' (шлях вже скопійовано в буфер обміну!)'
} catch {
    $copiedNote = ''
}

$manifest = Get-Content (Join-Path $extDest 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host ''
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  TalonTermo v$($manifest.version) успішно встановлено/оновлено!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Папка розширення: $extDest$copiedNote"
Write-Host "Ярлик оновлення:  $localCmd (та на Робочому столі)"
Write-Host ''

if ($isUpdate) {
    Write-Host 'Оновлення завершено!' -ForegroundColor Yellow
    Write-Host '1. Відкрий chrome://extensions та натисни іконку оновлення біля TalonAuto (або просто натисни F5 на сторінці CRM).'
} else {
    Write-Host 'Перше налаштування у Google Chrome (1 раз):' -ForegroundColor Yellow
    Write-Host '1. Відкрий у Chrome: chrome://extensions'
    Write-Host '2. Праворуч вгорі увімкни "Режим розробника" (Developer mode).'
    Write-Host '3. Натисни "Завантажити розпаковане" (Load unpacked).'
    Write-Host '4. Натисни Ctrl+V (шлях уже в буфері) та Enter.'
    Write-Host '5. Онови сторінку https://driver.tun.com.ua/admin/tickets — з''явиться кнопка "📄 Імпорт з PDF".'
}
Write-Host ''
