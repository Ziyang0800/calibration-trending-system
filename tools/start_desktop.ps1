param([switch]$Check)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$database = Join-Path $project 'calibration.db'
if (-not (Test-Path -LiteralPath $database -PathType Leaf)) { throw 'The project calibration database was not found.' }
$dist = Join-Path $project 'dist'
$manifest = Get-Content -LiteralPath (Join-Path $dist 'current-release.json') -Raw | ConvertFrom-Json
$executable = [IO.Path]::GetFullPath((Join-Path $dist $manifest.executable))
if (-not $executable.StartsWith($dist + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid release path.' }
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'Build the Windows release using tools/build_release.ps1 first.' }
if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) { throw 'The release executable failed its integrity check.' }
if ($Check) {
    [PSCustomObject]@{Version=$manifest.version; Database=$database; Executable=$executable} | ConvertTo-Json
    return
}
$previous = $env:CALIBRATION_LOCAL_DB
try {
    $env:CALIBRATION_LOCAL_DB = $database
    Start-Process -FilePath $executable -WorkingDirectory $project -WindowStyle Normal
} finally { $env:CALIBRATION_LOCAL_DB = $previous }
