$files = Get-ChildItem 'C:\backups\podcastplus\db' -File
foreach ($f in $files) {
    $h = Get-FileHash -Path $f.FullName -Algorithm SHA256
    Write-Output ("{0} {1}KB {2}" -f $f.Name, [Math]::Round($f.Length/1KB,2), $h.Hash)
}