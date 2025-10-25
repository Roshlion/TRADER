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
  aws s3api create-bucket --bucket $Bucket --region $Region --create-bucket-configuration LocationConstraint=$Region
}

aws s3api put-bucket-encryption --bucket $Bucket --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-versioning --bucket $Bucket --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket $Bucket --lifecycle-configuration '{
  "Rules":[
    {"ID":"expire-mpu-7d","Status":"Enabled","AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}},
    {"ID":"glacier-90d","Status":"Enabled","Filter":{"Prefix":""},"Transitions":[{"Days":90,"StorageClass":"GLACIER"}]}
  ]
}'
Write-Host "S3 bucket hardened. To rollback: delete lifecycle + versioning, then remove bucket when empty."
