param(
    [Parameter(Mandatory = $true)][string]$Replay,
    [string]$Python = "python",
    [double]$Speed = 1,
    [switch]$VerifyOnly
)
$ErrorActionPreference = "Stop"
$demoFile = (Resolve-Path -LiteralPath $Replay).Path
$gameSource = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "../src")).Path
$previousPythonPath = $env:PYTHONPATH
$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
try {
    # Use this checkout's reader without changing an installed training package.
    $env:PYTHONPATH = $gameSource
    $env:PYTHONDONTWRITEBYTECODE = "1"
    if ($VerifyOnly) {
        & $Python -m pvz_game replay $demoFile
    } else {
        & $Python -m pvz_game replay $demoFile --watch --speed $Speed
    }
    if ($LASTEXITCODE -ne 0) { throw "Replay reader exited with code $LASTEXITCODE" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
}
