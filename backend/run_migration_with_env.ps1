# Helper to load .env.local into process env and run migration script
Set-Location -Path (Split-Path -Path $MyInvocation.MyCommand.Path)
$envfile = Join-Path (Get-Location) '.env.local'
if (-Not (Test-Path $envfile)) {
    Write-Error "Missing .env.local at $envfile"
    exit 2
}
Get-Content $envfile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith('#')) { return }
    $i = $line.IndexOf('=')
    if ($i -lt 0) { return }
    $k = $line.Substring(0,$i).Trim()
    $v = $line.Substring($i+1).Trim()
    # Remove surrounding quotes if present
    if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Substring(1,$v.Length-2) }
    if ($v.StartsWith("'") -and $v.EndsWith("'")) { $v = $v.Substring(1,$v.Length-2) }
    [System.Environment]::SetEnvironmentVariable($k,$v,'Process')
}
# Run the migration
python migrate_remaining_transcripts_and_covers_to_r2.py
