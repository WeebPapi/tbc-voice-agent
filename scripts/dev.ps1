$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null

function Start-BgCommand {
  param(
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [Parameter(Mandatory = $true)][string]$CommandLine
  )
  # cmd.exe is required on Windows so .cmd shims like npm.cmd launch correctly.
  return Start-Process -PassThru -NoNewWindow `
    -FilePath "cmd.exe" `
    -WorkingDirectory $WorkingDirectory `
    -ArgumentList @("/c", $CommandLine)
}

Write-Host "Starting mock TBC on 127.0.0.1:8090"
$mock = Start-BgCommand -WorkingDirectory $root -CommandLine `
  "python -m uvicorn mock_tbc.app:app --host 127.0.0.1 --port 8090"

Write-Host "Starting voice API on 127.0.0.1:8000"
$api = Start-BgCommand -WorkingDirectory $root -CommandLine `
  "python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000"

Write-Host "Starting web console on 127.0.0.1:5173"
$webDir = Join-Path $root "apps\web"
if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
  Push-Location $webDir
  try {
    npm.cmd install
  } finally {
    Pop-Location
  }
}
$web = Start-BgCommand -WorkingDirectory $webDir -CommandLine "npm.cmd run dev"

Write-Host ""
Write-Host "Demo console: http://127.0.0.1:5173"
Write-Host "Voice API:    http://127.0.0.1:8000/health"
Write-Host "Mock TBC:     http://127.0.0.1:8090/health"
Write-Host "Press Ctrl+C to stop (then close leftover processes if needed)."

try {
  Wait-Process -Id $web.Id
} finally {
  foreach ($proc in @($web, $api, $mock)) {
    if ($proc -and -not $proc.HasExited) {
      Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
  }
}
