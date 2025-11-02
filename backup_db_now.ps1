# Backup DB now: server-side Cloud SQL export to GCS, then copy locally
# Pre-filled from repo: PROJECT_ID=podcast612, INSTANCE=podcast-db, DB_NAME=podcast

$PROJECT_ID = "podcast612"
$INSTANCE_NAME = "podcast-db"
$DB_NAME = "podcast"
$GCS_BUCKET = "ppp-media-us-west1"
$BACKUP_BASE = "C:\backups\podcastplus"
$BACKUP_DB_DIR = Join-Path $BACKUP_BASE "db"

New-Item -ItemType Directory -Path $BACKUP_DB_DIR -Force | Out-Null

$timeTag = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$gcsExportPath = "gs://$GCS_BUCKET/exports/db-export-$timeTag.sql.gz"
$localCopy = Join-Path $BACKUP_DB_DIR "db-export-$timeTag.sql.gz"

Write-Host "Starting Cloud SQL export: instance=$INSTANCE_NAME project=$PROJECT_ID -> $gcsExportPath"

# Run server-side export (this command will wait until the export operation completes)
$exportCmd = "gcloud sql export sql $INSTANCE_NAME $gcsExportPath --database=$DB_NAME --project=$PROJECT_ID --quiet"
Write-Host $exportCmd

$exportExit = & gcloud sql export sql $INSTANCE_NAME $gcsExportPath --database=$DB_NAME --project=$PROJECT_ID --quiet 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "gcloud export failed. Output:`n$exportExit"
    exit 2
}

Write-Host "Export completed on GCS: $gcsExportPath"
Write-Host "Copying export to local path: $localCopy"

$copyExit = & gsutil cp $gcsExportPath $localCopy 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "gsutil cp failed. Output:`n$copyExit"
    exit 3
}

Write-Host "Local copy complete: $localCopy"
Get-Item $localCopy | Select-Object FullName,Length

Write-Host "Listing recent exports in gs://$GCS_BUCKET/exports/"
& gsutil ls -l gs://$GCS_BUCKET/exports/

Write-Host "Backup finished. Move $BACKUP_BASE to secure storage and encrypt."
