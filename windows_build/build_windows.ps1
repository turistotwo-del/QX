$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw 'QX Windows installer must be built on Windows 10/11 or Windows Server.'
}

Write-Host '[QX] Installing Python dependencies...'
python -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
python -m pip install --disable-pip-version-check -r requirements.txt -r modern/requirements.txt 'pyinstaller>=6,<7' httpx
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }

# Optional real GGUF inference support. Fails explicitly instead of silently
# compiling missing native DLLs if no compatible prebuilt wheel exists.
if ($env:QX_BUNDLE_GGUF -eq '1') {
    Write-Host '[QX] Installing optional GGUF inference library (prebuilt wheel only)...'
    python -m pip install --only-binary=:all: --extra-index-url 'https://abetlen.github.io/llama-cpp-python/whl/cpu' 'llama-cpp-python==0.3.36'
    if ($LASTEXITCODE -ne 0) { throw 'Prebuilt llama-cpp-python wheel not available for this Windows Python version' }
    python -c "from llama_cpp import Llama; print('GGUF runtime OK')"
    if ($LASTEXITCODE -ne 0) { throw 'GGUF native runtime import failed' }
}

Write-Host '[QX] Checking Python and TypeScript code...'
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tender module tests failed' }
python -m unittest modern.test_modern modern.test_peripheral_choice modern.test_337_regression -v
if ($LASTEXITCODE -ne 0) { throw 'QX engine tests failed' }
# Old Streamlit self_test.py depends on desktop_launcher.py, absent in portable 4.x.
# The QX Modern launcher has its own actual runtime self-check.
python qx_entry.py --selfcheck
if ($LASTEXITCODE -ne 0) { throw 'QX Modern self-check failed' }

Write-Host '[QX] Preparing TypeScript...'
if (-not (Get-Command tsc -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is missing; install Node 22 LTS' }
    npm install -g typescript@5.9.3
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript installation failed' }
}
tsc -p modern/tsconfig.json
if ($LASTEXITCODE -ne 0) { throw 'TypeScript compilation failed' }

Write-Host '[QX] Generating release metadata for installer...'
python windows_build/release_metadata.py
if ($LASTEXITCODE -ne 0) { throw 'Cannot generate release metadata' }
$installerName = (python windows_build/release_metadata.py --print-installer | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve installer filename' }
Write-Host "[QX] Installer: $installerName"

Write-Host '[QX] Building native executable with PyInstaller...'
python -m PyInstaller --noconfirm --clean windows_build/qx.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$exe = Join-Path $root 'dist\QXPodborshchik\QXPodborshchik.exe'
if (-not (Test-Path $exe)) { throw "Executable was not created: $exe" }

Write-Host '[QX] Testing the packaged GUI-subsystem executable (blocking, deadline, real exit code)...'
. (Join-Path $PSScriptRoot 'invoke_checked_exe.ps1')
Invoke-QXCheck -ExePath $exe -Switch '--selfcheck'
Invoke-QXCheck -ExePath $exe -Switch '--api-selfcheck'
Invoke-QXCheck -ExePath $exe -Switch '--version'
if ($env:QX_BUNDLE_GGUF -eq '1') {
    Invoke-QXCheck -ExePath $exe -Switch '--ai-selfcheck'
}

# Do not accidentally reuse an installer left by an earlier local build.
$expectedOutputDir = Join-Path $root 'windows_build\out'
New-Item -ItemType Directory -Force -Path $expectedOutputDir | Out-Null
$previousInstaller = Join-Path $expectedOutputDir $installerName
if (Test-Path $previousInstaller) { Remove-Item -LiteralPath $previousInstaller -Force }
foreach ($staleReport in @('QX_build_manifest.json', 'SHA256SUMS.txt')) {
    $stalePath = Join-Path $expectedOutputDir $staleReport
    if (Test-Path $stalePath) { Remove-Item -LiteralPath $stalePath -Force }
}

$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) {
    $iscc = Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'
}
if (-not (Test-Path $iscc)) { throw 'Inno Setup 6 is required: https://jrsoftware.org/isinfo.php' }
Write-Host '[QX] Creating the installer with Inno Setup...'
& $iscc windows_build\QX_Setup.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
$setup = Join-Path (Join-Path $root 'windows_build\out') $installerName
if (-not (Test-Path $setup)) { throw 'The installer was not created' }
Write-Host "QX installer created: $setup"
