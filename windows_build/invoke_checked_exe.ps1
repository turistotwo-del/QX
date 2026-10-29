# Both the bundled PyInstaller EXE and the Inno-installed EXE are built with
# console=False (Windows GUI subsystem). PowerShell invocation via `& $exe` is
# not a reliable *blocking* acceptance test for GUI applications.
# Start-Process + Process.WaitForExit verifies the actual exit code, with a
# deadline so an accidental desktop startup can't hang the CI runner forever.
function Invoke-QXCheck {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$ExePath,
        [Parameter(Mandatory=$true)][string]$Switch,
        [int]$TimeoutSeconds = 90
    )
    if ($TimeoutSeconds -lt 5 -or $TimeoutSeconds -gt 600) {
        throw 'Invalid selfcheck timeout (5..600 seconds)'
    }
    if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
        throw "QX executable does not exist: $ExePath"
    }
    $proc = Start-Process -FilePath $ExePath -ArgumentList $Switch -PassThru -ErrorAction Stop
    try {
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch { }
            throw "QX executable check timed out after ${TimeoutSeconds}s: $Switch"
        }
        if ($proc.ExitCode -ne 0) {
            throw "QX executable check FAILED (exit $($proc.ExitCode)): $Switch"
        }
        Write-Host "[QX] Executable check OK: $Switch"
    }
    finally {
        $proc.Dispose()
    }
}
