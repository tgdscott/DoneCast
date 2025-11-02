param(
    [string]$ScriptToRun = ''
)

# Load .env.local into process environment and run a given Python script (from backend/)
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
    if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Substring(1,$v.Length-2) }
    if ($v.StartsWith("'") -and $v.EndsWith("'")) { $v = $v.Substring(1,$v.Length-2) }
    [System.Environment]::SetEnvironmentVariable($k,$v,'Process')
}

if (-not $ScriptToRun) {
    Write-Error "Usage: .\run_with_env.ps1 <script.py>"
    exit 3
}

python $ScriptToRun
