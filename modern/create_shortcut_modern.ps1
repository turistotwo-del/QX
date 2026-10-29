# UTF-8 BOM: Windows PowerShell 5.1 must read Russian shortcut names.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $root = Split-Path -Parent $PSScriptRoot
    $launcher = Join-Path $root 'ЗАПУСТИТЬ_QX.cmd'
    $icon = Join-Path $root 'assets\qx_icon.ico'
    if (!(Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "QX launcher not found: $launcher"
    }
    if (!(Test-Path -LiteralPath $icon -PathType Leaf)) {
        throw "QX icon not found: $icon"
    }
    $ws = New-Object -ComObject WScript.Shell
    $desktop = [string]$ws.SpecialFolders.Item('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktop)) {
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    }
    $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\QX Подборщик'
    if (!(Test-Path -LiteralPath $startMenu)) {
        New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
    }
    $locations = @(
        (Join-Path $desktop 'QX Подборщик.lnk'),
        (Join-Path $startMenu 'QX Подборщик.lnk')
    )
    foreach ($path in $locations) {
        $link = $ws.CreateShortcut($path)
        $link.TargetPath = $launcher
        $link.WorkingDirectory = $root
        $link.IconLocation = "$icon,0"
        $link.Description = 'QX Подборщик — управление тендерами и расчётами'
        $link.WindowStyle = 7
        $link.Save()
        $saved = $ws.CreateShortcut($path)
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
            !([string]::Equals([string]$saved.TargetPath, $launcher,
                [StringComparison]::OrdinalIgnoreCase))) {
            throw "Shortcut verification failed: $path"
        }
    }
    Write-Host '[QX] Desktop and Start menu shortcuts updated (original QX icon).'
} catch {
    throw ('[QX] Shortcut not created: ' + $_.Exception.Message)
}
