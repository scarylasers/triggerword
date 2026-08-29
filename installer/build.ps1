# Builds the TriggerWord Windows installer.
#
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
#
# Stages an ALLOWLISTED payload (never a copy-everything-minus-exclusions
# sweep), bundles the embedded Python runtime, audits the payload for
# anything personal, then compiles with Inno Setup. The audit is a hard
# gate: if it finds something, nothing gets built.

$ErrorActionPreference = 'Stop'

$root     = Split-Path -Parent $PSScriptRoot
$here     = $PSScriptRoot
$build    = Join-Path $here 'build'
$payload  = Join-Path $build 'payload'
$embedZip = Join-Path $build 'python-embed.zip'
$iscc     = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"

# --- what ships -------------------------------------------------------------
# Everything the app needs to run in simple mode, plus the guides and the
# starter pack. Dev files, the personal sound library, servers, routers,
# tests and logs are all absent by construction.
$files = @(
    'index.html',
    'persistence.js',
    'guide.html',
    'routing.html',
    'manifest.json',
    'favicon.ico',
    'CHANGELOG.md',
    'LICENSE',
    'TriggerWord-Starter-Pack.zip'
)

Write-Host "Staging payload..."
if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
New-Item -ItemType Directory -Force $payload | Out-Null

foreach ($f in $files) {
    $src = Join-Path $root $f
    if (-not (Test-Path $src)) { throw "missing required file: $f" }
    Copy-Item $src (Join-Path $payload $f)
}

Copy-Item (Join-Path $here 'launcher.py') (Join-Path $payload 'launcher.py')

# static/, minus the stale standalone copy of the app that lives in there
$staticDst = Join-Path $payload 'static'
New-Item -ItemType Directory -Force $staticDst | Out-Null
Copy-Item (Join-Path $root 'static\*') $staticDst -Recurse -Force
Remove-Item (Join-Path $staticDst 'index.html') -Force -ErrorAction SilentlyContinue

# --- embedded Python --------------------------------------------------------
Write-Host "Unpacking embedded Python..."
if (-not (Test-Path $embedZip)) {
    throw "missing $embedZip - download python-3.11.9-embed-amd64.zip into installer\build\"
}
$pythonDst = Join-Path $payload 'python'
Expand-Archive -Path $embedZip -DestinationPath $pythonDst -Force
# Everything in there is needed - python311.zip IS the standard library for
# the embedded distribution, so do not "clean it up".
if (-not (Test-Path (Join-Path $pythonDst 'python311.zip'))) {
    throw "embedded Python is missing python311.zip (its standard library)"
}

# --- audit ------------------------------------------------------------------
# Nothing personal may leave this machine inside the installer.
Write-Host "Auditing payload..."
$patterns = @(
    'C:\\Users\\',
    '/Users/',
    'wilco',
    'AppData\\Local\\Temp',
    'discord\.com/api/webhooks',
    'api[_-]?key\s*[:=]',
    'secret\s*[:=]',
    'password\s*[:=]',
    'Bearer\s',
    'sk-[A-Za-z0-9]{20}',
    'AKIA[A-Z0-9]{16}',
    '@gmail\.com',
    '@outlook\.com',
    'OneDrive',
    'Resilio'
)
$findings = @()
Get-ChildItem $payload -Recurse -File |
    Where-Object { $_.Extension -in '.html', '.js', '.json', '.py', '.css', '.md', '.txt', '.csv', '' } |
    Where-Object { $_.FullName -notlike "*\python\*" } |
    ForEach-Object {
        $file = $_
        foreach ($p in $patterns) {
            $hits = Select-String -Path $file.FullName -Pattern $p -AllMatches -ErrorAction SilentlyContinue
            foreach ($h in $hits) {
                $findings += "  $($file.Name):$($h.LineNumber)  [$p]  $($h.Line.Trim())"
            }
        }
    }

if ($findings.Count -gt 0) {
    Write-Host ""
    Write-Host "AUDIT FAILED - payload contains personal or sensitive strings:" -ForegroundColor Red
    $findings | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    throw "aborting build"
}
Write-Host "Audit clean." -ForegroundColor Green

$size = (Get-ChildItem $payload -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Payload: {0} files, {1:N1} MB" -f (Get-ChildItem $payload -Recurse -File).Count, $size)

# --- compile ----------------------------------------------------------------
if (-not (Test-Path $iscc)) { throw "Inno Setup not found at $iscc" }
Write-Host "Compiling installer..."
& $iscc /Q (Join-Path $here 'TriggerWord.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

Get-ChildItem (Join-Path $here 'dist') -Filter *.exe |
    ForEach-Object { "{0}  ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB) }
