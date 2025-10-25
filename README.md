# TRADER (Windows-safe setup)

Local code + cloud data. Polygon Flat Files -> S3; compute later on EC2/SageMaker.
This repo is Windows-native (PowerShell + rclone) with strict safe-mode defaults.

## Quickstart (Windows)
1) `.\scripts\windows\init.ps1` (creates venv, installs deps)
2) `copy .env.example .env` and fill non-secret values
3) Export Polygon secrets in current PowerShell session (DO NOT COMMIT):
   `$env:POLYGON_ACCESS_KEY="..." ; $env:POLYGON_SECRET_KEY="..."`
4) Validate single-file pull: `.\scripts\windows\sample_pull.ps1`
5) Dry-run list/sync with rclone: `.\scripts\windows\sync_dryrun.ps1`
