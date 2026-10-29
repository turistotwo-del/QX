# Portable QX bootstrap: no system Python installation or administrative rights.
# First start requires access to python.org, bootstrap.pypa.io and PyPI.
# Components live in the extracted QX folder; user tender data lives in LocalAppData.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root '.qx_runtime'
$pyhome = Join-Path $runtime 'python'
$python = Join-Path $pyhome 'python.exe'
$site = Join-Path $pyhome 'Lib\site-packages'
$ready = Join-Path $runtime 'ready-4.0.25.marker'
$aiBase = Join-Path $env:LOCALAPPDATA 'QXPodborshchik\QX_AI'
$aiReady = Join-Path $aiBase 'qx-lite-1.5b.ready'
$aiError = Join-Path $aiBase 'lite-install-error.txt'
$archive = Join-Path $runtime 'python.zip'
$pyUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embeddable-amd64.zip'
# From the official Python Windows release manifest (windows-3.12.10.json).
$pySha256 = '156c7eea90d58cd7e91a23f28a0056616b13e9f4cf4901b7b99b837b7848c6da'

function Download-Https([string]$url, [string]$destination) {
    Write-Host "[QX] Downloading $(($url -split '/')[-1]) ..."
    Invoke-WebRequest -Uri $url -OutFile $destination -UseBasicParsing -MaximumRedirection 4
    if (!(Test-Path $destination) -or (Get-Item $destination).Length -eq 0) {
        throw "Empty download: $url"
    }
}

# Windows embeddable Python reads sys.path ONLY from python312._pth.
# It does not automatically add the directory containing qx_entry.py.
# From .qx_runtime\python, ..\.. points to the portable QX application root.
# Keep paths relative so users may move the extracted QX folder later.
function Repair-QXModulePath {
    $pth = Join-Path $pyhome 'python312._pth'
    $expected = "python312.zip`r`n.`r`nLib\site-packages`r`n..\..`r`nimport site`r`n"
    if (!(Test-Path -LiteralPath $pth) -or
        [IO.File]::ReadAllText($pth) -ne $expected) {
        [IO.File]::WriteAllText($pth, $expected, [Text.Encoding]::ASCII)
        Write-Host '[QX] Repaired private Python module paths (application + libraries).'
        return $true
    }
    return $false
}

try {
    if ([Environment]::Is64BitOperatingSystem -ne $true) {
        throw 'QX Portable requires Windows 10/11 x64.'
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Use this launcher on Windows.'
    }
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    Set-Location $root
    # Persistent profile: updating/replacing the source directory cannot wipe data.
    $env:QX_DATA_DIR = Join-Path $env:LOCALAPPDATA 'QXPodborshchik'
    $env:QX_PORTABLE_DATA_DIR = Join-Path $env:QX_DATA_DIR 'QX_UserData'
    New-Item -ItemType Directory -Force -Path $env:QX_DATA_DIR | Out-Null

    # A previous QX 4.0.27 launch may already have downloaded all libraries,
    # then failed selfcheck because the application root was missing from _pth.
    # Repair and validate that runtime before deciding to download anything.
    $modulePathRepaired = $false
    if (Test-Path -LiteralPath $python) {
        $modulePathRepaired = Repair-QXModulePath
    }
    $needsSetup = !(Test-Path -LiteralPath $ready) -or !(Test-Path -LiteralPath $python)
    if ((Test-Path -LiteralPath $python) -and ($needsSetup -or $modulePathRepaired)) {
        Write-Host '[QX] Checking the existing runtime before downloading libraries ...'
        & $python (Join-Path $root 'qx_entry.py') --selfcheck
        if ($LASTEXITCODE -eq 0) {
            [IO.File]::WriteAllText($ready, 'QX Portable runtime verified')
            $needsSetup = $false
            Write-Host '[QX] Reusing installed Python and dependencies.'
        } else {
            $needsSetup = $true
            if (Test-Path -LiteralPath $ready) { Remove-Item -Force $ready }
        }
    }
    if ($needsSetup) {
        Write-Host '[QX] Setting up the private Python runtime. Internet is required.'
        if (!(Test-Path $python)) {
            Download-Https $pyUrl $archive
            $actual = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $pySha256) {
                Remove-Item -Force $archive
                throw 'Python archive checksum mismatch; stopping for safety.'
            }
            if (Test-Path $pyhome) { Remove-Item -Recurse -Force $pyhome }
            New-Item -ItemType Directory -Force -Path $pyhome | Out-Null
            Expand-Archive -Path $archive -DestinationPath $pyhome -Force
            Remove-Item -Force $archive
        }
        if (!(Test-Path $python)) { throw 'Python runtime did not unpack correctly.' }
        New-Item -ItemType Directory -Force -Path $site | Out-Null
        $null = Repair-QXModulePath
        $pipBootstrap = Join-Path $runtime 'get-pip.py'
        Download-Https 'https://bootstrap.pypa.io/get-pip.py' $pipBootstrap
        & $python $pipBootstrap --no-input --no-warn-script-location --disable-pip-version-check --target $site
        if ($LASTEXITCODE -ne 0) { throw 'Unable to initialize pip in the private runtime.' }
        Remove-Item -Force $pipBootstrap
        Write-Host '[QX] Installing QX libraries into the private runtime ...'
        & $python -m pip install --no-input --disable-pip-version-check --only-binary=:all: --upgrade --target $site -r (Join-Path $PSScriptRoot 'requirements_portable.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Unable to install required QX libraries.' }
        & $python (Join-Path $root 'qx_entry.py') --selfcheck
        if ($LASTEXITCODE -ne 0) { throw 'QX runtime installed, but the app self-check failed.' }
        [IO.File]::WriteAllText($ready, 'QX Portable runtime verified')
    }

    # 4.0.29: validate the native GUI with an actual Python SCRIPT.
    # On Windows PowerShell 5.1, double quotes inside a -c Python expression
    # can be stripped when passing native-process arguments (NameError).
    # A .py file avoids PowerShell/native-argument quoting entirely.
    # Reprobe on every launch, even if a previous marker exists: it must not
    # mask interrupted/broken installs. Do not touch the QX core or AI runtime.
    $desktopReady = Join-Path $runtime 'desktop-webview2-4.0.29.marker'
    $desktopProbe = Join-Path $PSScriptRoot 'desktop_probe.py'
    if (!(Test-Path -LiteralPath $desktopProbe -PathType Leaf)) {
        throw 'QX desktop verification script is missing. Reapply the 4.0.29 update.'
    }
    Write-Host '[QX] Checking the native QX window (WebView2 + pywebview) ...'
    & $python $desktopProbe --check
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[QX] Installing the desktop window into the EXISTING private Python ...'
        # Hotfix 4.0.36.1: QX uses python-3.12 embeddable with an _pth file.
        # pip's temporary isolated PEP 517 build environment cannot import
        # setuptools.build_meta from this runtime (BackendUnavailable).
        # Install wheel + setuptools into OUR private runtime first, then build
        # the tiny source-only proxy-tools dependency without build isolation.
        # Do not touch system Python, persistent QX data or the AI installation.
        Write-Host '[QX] Preparing build tools in private QX Python (setuptools + wheel) ...'
        & $python -m pip install --no-input --disable-pip-version-check --only-binary=:all: --upgrade --target $site 'setuptools>=70,<85' 'wheel>=0.45,<1'
        if ($LASTEXITCODE -ne 0) {
            throw 'Cannot install setuptools/wheel into private QX Python. Check PyPI connectivity and rerun QX.'
        }
        # Probe the actual interpreter now instead of waiting for an opaque
        # pip stack trace to discover that setuptools.build_meta is unavailable.
        & $python $desktopProbe --build-check
        if ($LASTEXITCODE -ne 0) {
            throw 'QX private Python cannot import setuptools.build_meta or wheel after installation.'
        }
        Write-Host '[QX] Installing pywebview (no isolated build, compatible with embeddable Python) ...'
        # proxy-tools 0.1.0 is source-only on PyPI; use wheels for everything
        # else, but build this one via the verified local setuptools backend.
        & $python -m pip install --no-input --disable-pip-version-check --no-build-isolation --prefer-binary --upgrade --target $site -r (Join-Path $PSScriptRoot 'requirements_desktop.txt')
        if ($LASTEXITCODE -ne 0) {
            throw 'QX desktop dependency installation failed. Verify internet access or retry setup; user data and AI remain unchanged.'
        }
        & $python $desktopProbe --check
        if ($LASTEXITCODE -ne 0) {
            throw 'QX desktop components installed but failed import check. See Python diagnostic above.'
        }
    }
    [IO.File]::WriteAllText($desktopReady, 'QX 4.0.29 Windows desktop imports verified')

    # Update QX's own desktop and Start menu shortcuts. This is deliberately
    # nonfatal (OneDrive redirected/read-only desktops may deny shortcut writes).
    try {
        & (Join-Path $root 'modern\create_shortcut_modern.ps1')
    } catch {
        Write-Warning ('[QX] Shortcut update failed: ' + $_.Exception.Message)
    }

    # QX AI is installed on the first launch, with no manual Ollama steps.
    # On offline failure, regular QX stays usable; retry automatically the next day
    # or via the separate 'УСТАНОВИТЬ_QX_AI.cmd' helper.
    $shouldAttemptAi = !(Test-Path -LiteralPath $aiReady)
    if ($shouldAttemptAi -and (Test-Path -LiteralPath $aiError)) {
        $errorAge = ((Get-Date) - (Get-Item -LiteralPath $aiError).LastWriteTime).TotalHours
        if ($errorAge -lt 12) { $shouldAttemptAi = $false }
    }
    if ($shouldAttemptAi -and $env:QX_DISABLE_AUTO_AI -ne '1') {
        Write-Host '[QX] First-run QX AI Lite installation: llama.cpp + Qwen2.5 1.5B.'
        & (Join-Path $PSScriptRoot 'auto_ai.ps1')
        # The script is intentionally nonfatal; QX still launches when AI is offline.
    }
    Write-Host '[QX] Opening QX desktop window (WebView2, blue QX taskbar icon) ...'
    # Avoid inherited PYTHONPATH/PYTHONHOME influencing the isolated runtime.
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    & $python (Join-Path $root 'qx_entry.py')
    if ($LASTEXITCODE -ne 0) { throw "QX terminated with exit code $LASTEXITCODE" }
} catch {
    Write-Host ('[QX ERROR] ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'QX user data were not intentionally changed by the runtime bootstrap.' -ForegroundColor Yellow
    exit 1
}
