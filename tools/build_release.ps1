param([string]$Python = '.venv/Scripts/python.exe')
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
# Build into a new generation so PyInstaller cannot erase an older release's database.
$releaseRoot = Join-Path $project ('dist/verified-' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
Push-Location -LiteralPath $project
try {
    & $Python -B -m pytest tests -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    & node --test tests/test_ui.cjs
    if ($LASTEXITCODE -ne 0) { throw 'JavaScript tests failed.' }
    & $Python -B -m PyInstaller --noconfirm --distpath $releaseRoot CalibrationSystem.spec
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed.' }
    $executable = Join-Path $releaseRoot 'CalibrationSystem/CalibrationSystem.exe'
    $resultPath = Join-Path $project 'build/release-selftest.json'
    if (Test-Path -LiteralPath $resultPath) { Remove-Item -LiteralPath $resultPath }
    $process = Start-Process -FilePath $executable -ArgumentList ('--self-test-output "' + $resultPath + '"') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Packaged self-test failed.' }
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if (-not $result.ok) { throw 'Packaged resources or calculations failed validation.' }
    foreach ($property in $result.resources.PSObject.Properties) {
        $sourceFile = Join-Path $project $property.Name
        if ((Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) {
            throw ('Packaged asset differs from source: ' + $property.Name)
        }
    }
    if (Test-Path -LiteralPath (Join-Path $releaseRoot 'CalibrationSystem/calibration.db')) {
        throw 'Remove production data from the release before distribution.'
    }
    $dist = Join-Path $project 'dist'
    $relativeExecutable = $executable.Substring($dist.Length).TrimStart('\', '/')
    $manifest = @{
        version = (Get-Content -LiteralPath (Join-Path $project 'VERSION') -Raw).Trim()
        executable = $relativeExecutable
        sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $temporaryManifest = Join-Path $dist ('current-release-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $temporaryManifest -Encoding UTF8
    Move-Item -LiteralPath $temporaryManifest -Destination (Join-Path $dist 'current-release.json') -Force
    Copy-Item -LiteralPath $resultPath -Destination (Join-Path $releaseRoot 'self-test.json')
    Write-Output ('Release build and packaged self-test passed: ' + $executable)
    Write-Output 'Existing releases and their databases were preserved. Complete interactive acceptance checks before distribution.'
} finally { Pop-Location }
