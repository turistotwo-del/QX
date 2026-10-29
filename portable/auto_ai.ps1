# QX AI Lite: one-time local install, zero admin rights, without Ollama/GPU libraries.
# Reuses and never removes any QX AI engine/model from prior versions.
param([switch]$Retry)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$base = Join-Path $env:LOCALAPPDATA 'QXPodborshchik\QX_AI'
$engineDir = Join-Path $base 'lite-engine'
$modelDir = Join-Path $base 'lite-models'
$logDir = Join-Path $base 'logs'
$exe = Join-Path $engineDir 'llama-server.exe'
$modelFile = Join-Path $modelDir 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
$readyFile = Join-Path $base 'qx-lite-1.5b.ready'
$errorFile = Join-Path $base 'lite-install-error.txt'
$releaseTag = 'b11815'
$assetName = 'llama-b11815-bin-win-cpu-x64.zip'
$engineUrl = 'https://github.com/ggml-org/llama.cpp/releases/download/b11815/llama-b11815-bin-win-cpu-x64.zip'
$engineArchive = Join-Path $base $assetName
$modelUrl = 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf?download=true'
$tempModel = $modelFile + '.download'

function Log([string]$message) {
    Write-Host ('[QX AI Lite] ' + $message)
    try { Add-Content -LiteralPath (Join-Path $logDir 'setup-lite.log') -Value ((Get-Date -Format s) + ' ' + $message) -Encoding UTF8 } catch {}
}
function Assert-FreeSpace([long]$bytes) {
    $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($base)))
    if ($drive.AvailableFreeSpace -lt $bytes) {
        throw ('Для компактной установки AI нужно около ' + [math]::Ceiling($bytes / 1GB) + ' ГБ свободного места на время загрузки.')
    }
}
function Check-Model([string]$path) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
    $file = Get-Item -LiteralPath $path
    if ($file.Length -lt 700MB -or $file.Length -gt 1500MB) { return $false }
    $stream = [IO.File]::OpenRead($path)
    try {
        $bytes = New-Object byte[] 4
        if ($stream.Read($bytes,0,4) -ne 4) { return $false }
        return [Text.Encoding]::ASCII.GetString($bytes) -eq 'GGUF'
    } finally { $stream.Dispose() }
}
function Download-Engine {
    Assert-FreeSpace (2.5GB)
    Log 'Скачиваю компактный CPU-движок llama.cpp с официального GitHub.'
    # GitHub supplies SHA-256 digests of release assets. Fail closed if unavailable.
    $meta = Invoke-RestMethod -Uri ('https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/' + $releaseTag) -TimeoutSec 30
    $asset = @($meta.assets | Where-Object { $_.name -eq $assetName }) | Select-Object -First 1
    if ($null -eq $asset -or [string]$asset.digest -notmatch '^sha256:[0-9a-fA-F]{64}$') {
        throw 'Не удалось подтвердить SHA-256 релиза llama.cpp. Установка остановлена.'
    }
    if (Test-Path -LiteralPath $engineArchive) { Remove-Item -LiteralPath $engineArchive -Force }
    Invoke-WebRequest -Uri $engineUrl -UseBasicParsing -OutFile $engineArchive -MaximumRedirection 8 -TimeoutSec 1200
    $hash = (Get-FileHash -LiteralPath $engineArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne ([string]$asset.digest).Substring(7).ToLowerInvariant()) {
        throw 'SHA-256 скачанного llama.cpp не совпадает с официальным релизом.'
    }
    $tempDir = Join-Path $base 'lite-engine.unpacking'
    if (Test-Path -LiteralPath $tempDir) { Remove-Item -LiteralPath $tempDir -Recurse -Force }
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    try {
        Expand-Archive -LiteralPath $engineArchive -DestinationPath $tempDir -Force
        $binary = Get-ChildItem -LiteralPath $tempDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
        if ($null -eq $binary) { throw 'В релизе llama.cpp не найден llama-server.exe.' }
        if (Test-Path -LiteralPath $engineDir) { Remove-Item -LiteralPath $engineDir -Recurse -Force }
        Move-Item -LiteralPath $binary.Directory.FullName -Destination $engineDir
        if (!(Test-Path -LiteralPath $exe)) { throw 'Ошибка распаковки CPU-движка.' }
    } finally {
        if (Test-Path -LiteralPath $tempDir) { Remove-Item -LiteralPath $tempDir -Recurse -Force }
        if (Test-Path -LiteralPath $engineArchive) { Remove-Item -LiteralPath $engineArchive -Force }
    }
}
function Download-Model {
    Assert-FreeSpace (2GB)
    Log 'Скачиваю Qwen2.5 1.5B Q4_K_M (~1,1 ГБ); после установки интернет нейросети не нужен.'
    if (Test-Path -LiteralPath $tempModel) { Remove-Item -LiteralPath $tempModel -Force }
    Invoke-WebRequest -Uri $modelUrl -UseBasicParsing -OutFile $tempModel -MaximumRedirection 8 -TimeoutSec 3600
    if (!(Check-Model $tempModel)) { throw 'Скачанный GGUF повреждён или не соответствует ожидаемому размеру.' }
    Move-Item -LiteralPath $tempModel -Destination $modelFile -Force
}
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or ![Environment]::Is64BitOperatingSystem) {
        throw 'Для QX AI Lite требуется Windows 10/11 x64.'
    }
    New-Item -ItemType Directory -Path $base,$engineDir,$modelDir,$logDir -Force | Out-Null
    if ($env:QX_DISABLE_AUTO_AI -eq '1') { Log 'Отключено настройкой QX_DISABLE_AUTO_AI'; exit 0 }
    if ((Test-Path -LiteralPath $exe) -and (Check-Model $modelFile)) {
        Set-Content -LiteralPath $readyFile -Value 'qx-lite:1.5b' -Encoding ASCII
        if (Test-Path -LiteralPath $errorFile) { Remove-Item -LiteralPath $errorFile -Force }
        Log 'AI Lite уже установлен. Повторная загрузка не требуется.'
        exit 0
    }
    if (!(Test-Path -LiteralPath $exe)) { Download-Engine }
    if (!(Check-Model $modelFile)) { Download-Model }
    if (!(Test-Path -LiteralPath $exe) -or !(Check-Model $modelFile)) { throw 'Установка AI Lite неполная.' }
    Set-Content -LiteralPath $readyFile -Value 'qx-lite:1.5b' -Encoding ASCII
    if (Test-Path -LiteralPath $errorFile) { Remove-Item -LiteralPath $errorFile -Force }
    Log 'Готово! QX AI Lite доступен для проверки ТЗ и краткого анализа контрактов.'
} catch {
    $message = [string]$_.Exception.Message
    Log ('AI Lite пока не установлен: ' + $message)
    try { Set-Content -LiteralPath $errorFile -Value $message -Encoding UTF8 } catch {}
    Write-Host '[QX AI Lite] Основные функции QX продолжают работать. Повторите установку позже.' -ForegroundColor Yellow
} finally {
    # The new light installation does not kill or modify existing Ollama/models.
    if (Test-Path -LiteralPath $tempModel) { Remove-Item -LiteralPath $tempModel -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $engineArchive) { Remove-Item -LiteralPath $engineArchive -Force -ErrorAction SilentlyContinue }
}
exit 0
