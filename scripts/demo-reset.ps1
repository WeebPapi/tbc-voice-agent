$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

try {
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/admin/reset" | Out-Null
  Write-Host "Demo state reset via voice API."
} catch {
  Write-Host "Voice API not running; clearing local sqlite files instead."
  Remove-Item -Force -ErrorAction SilentlyContinue "data/voice_agent.sqlite", "data/mock_tbc.sqlite"
  New-Item -ItemType Directory -Force -Path "data" | Out-Null
}
