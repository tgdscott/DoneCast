$episodes = @{
    195 = "9e4bffb5-c40b-49d2-a725-2f1bbf5a6701"
    196 = "89f84b6b-1d81-4f5d-a40a-17c6c8231d41"
    197 = "217d45fe-d5c9-4c05-89b3-a1a7c04720ec"
    198 = "cbb25ed6-2897-42a6-b392-35172b077fda"
    199 = "1679183d-d2de-4b4b-ad25-be5e7eb6199f"
    200 = "fa933980-ecf1-44e4-935a-5236db1ddccc"
    201 = "768605b6-18ad-4a52-ab85-a05b8c1d321f"
}

$bucket = "ppp-media-us-west1"
$basePath = "podcasts/cinema-irl/episodes"

Write-Host "========================================================================"
Write-Host "CHECKING GCS FOR CINEMA IRL EPISODES 195-201"
Write-Host "========================================================================"
Write-Host ""

$sqlStatements = @()

foreach ($ep in $episodes.GetEnumerator() | Sort-Object Name) {
    $epNum = $ep.Key
    $uuid = $ep.Value
    $gcsPath = "gs://$bucket/$basePath/$uuid/"
    
    Write-Host "Episode $epNum (UUID: $uuid)"
    
    $result = gcloud storage ls $gcsPath 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        $files = $result | Where-Object { $_ -match '\.(mp3|m4a|wav)$' }
        if ($files) {
            $audioFile = $files[0]
            Write-Host "  Found audio: $audioFile" -ForegroundColor Green
            $sqlStatements += "UPDATE episode SET gcs_audio_path = '$audioFile' WHERE id = '$uuid';"
        } else {
            Write-Host "  Folder exists but no audio file found" -ForegroundColor Yellow
            Write-Host "     Files: $result"
        }
    } else {
        Write-Host "  GCS folder not found!" -ForegroundColor Red
    }
    Write-Host ""
}

if ($sqlStatements.Count -gt 0) {
    Write-Host ""
    Write-Host "========================================================================"
    Write-Host "SQL STATEMENTS TO FIX THE AUDIO PATHS:"
    Write-Host "========================================================================"
    Write-Host ""
    foreach ($sql in $sqlStatements) {
        Write-Host $sql
    }
    Write-Host ""
    Write-Host "Copy these SQL statements and run them in pgAdmin to fix the playback!"
    Write-Host ""
    
    $sqlStatements | Out-File -FilePath "fix_episodes_195-201.sql" -Encoding utf8
    Write-Host "SQL statements saved to: fix_episodes_195-201.sql"
} else {
    Write-Host "No audio files found in GCS for any of these episodes!" -ForegroundColor Red
    Write-Host "The files may need to be reassembled or recovered."
}
