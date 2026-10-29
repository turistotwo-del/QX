# Optional local AI engine, only after first portable QX run. No admin rights.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.qx_runtime\python\python.exe'
$site = Join-Path $root '.qx_runtime\python\Lib\site-packages'
if (!(Test-Path -LiteralPath $python)) { throw 'Run QX once to install private Python runtime, then close QX before enabling AI.' }
$env:PYTHONNOUSERSITE = '1'
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Write-Host 'Installing local CPU inference runtime (llama-cpp-python) in the private QX folder...'
& $python -m pip install --no-input --disable-pip-version-check --only-binary=:all: --upgrade --target $site --extra-index-url 'https://abetlen.github.io/llama-cpp-python/whl/cpu' 'llama-cpp-python==0.3.36'
if ($LASTEXITCODE -ne 0) { throw 'No compatible prebuilt llama-cpp-python wheel; try Ollama on this Windows PC instead.' }
& $python -c 'from llama_cpp import Llama; print("Local GGUF runtime OK")'
if ($LASTEXITCODE -ne 0) { throw 'The native inference runtime did not load. QX standard parsing is unaffected.' }
Write-Host ''
Write-Host 'GGUF support installed. Restart QX, open Tender Department / Documents,'
Write-Host 'and use Download Qwen (~1.12 GB) to download the optional model.'
