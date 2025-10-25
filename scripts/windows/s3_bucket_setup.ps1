# Creates secure S3 bucket with encryption, versioning, lifecycle
param(
  [Parameter(Mandatory=$true)][string]$Bucket,
  [Parameter(Mandatory=$true)][string]$Region
)
$ErrorActionPreference = "Stop"

# Check existence
try {
  aws s3api head-bucket --bucket $Bucket 1>$null 2>$null
  Write-Host "Bucket exists: $Bucket (skipping create)"
} catch {
  Write-Host "Creating bucket: $Bucket in $Region"
  if ($Region -eq "us-east-1") {
    aws s3api create-bucket --bucket $Bucket --region $Region
  } else {
    aws s3api create-bucket --bucket $Bucket --region $Region --create-bucket-configuration LocationConstraint=$Region
  }
}

# Create temp JSON files to avoid PowerShell mangling
$encryptionJson = @"
{
  "Rules": [{
    "ApplyServerSideEncryptionByDefault": {
      "SSEAlgorithm": "AES256"
    }
  }]
}
"@
$encryptionJson | Out-File -FilePath "$env:TEMP\s3-encryption.json" -Encoding ascii -NoNewline

$lifecycleJson = @"
{
  "Rules": [
    {
      "ID": "expire-mpu-7d",
      "Status": "Enabled",
      "Filter": {},
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    },
    {
      "ID": "glacier-90d",
      "Status": "Enabled",
      "Filter": {},
      "Transitions": [{
        "Days": 90,
        "StorageClass": "GLACIER"
      }]
    }
  ]
}
"@
$lifecycleJson | Out-File -FilePath "$env:TEMP\s3-lifecycle.json" -Encoding ascii -NoNewline

aws s3api put-bucket-encryption --bucket $Bucket --server-side-encryption-configuration "file://$env:TEMP\s3-encryption.json"
aws s3api put-bucket-versioning --bucket $Bucket --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket $Bucket --lifecycle-configuration "file://$env:TEMP\s3-lifecycle.json"

# Clean up temp files
Remove-Item "$env:TEMP\s3-encryption.json" -ErrorAction SilentlyContinue
Remove-Item "$env:TEMP\s3-lifecycle.json" -ErrorAction SilentlyContinue
Write-Host "S3 bucket hardened. To rollback: delete lifecycle + versioning, then remove bucket when empty."
