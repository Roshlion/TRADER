# Loads .env (non-secret) into $env: for current session
if (Test-Path ".env") {
  Get-Content ".env" | ForEach-Object {
    if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
    $parts = $_ -split "=", 2
    if ($parts.Length -eq 2) {
      $name = $parts[0].Trim()
      $value = $parts[1].Trim()
      [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
  Write-Host "Loaded .env into session."
} else {
  Write-Host "No .env found; skip."
}
