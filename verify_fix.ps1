try {
    $rss = Invoke-WebRequest -Uri 'https://podcastplusplus.com/rss/cardiac-cowboys/feed.xml' -Method Head
    "RSS Status: " + $rss.StatusCode | Out-File -FilePath verification_result.txt -Append
    "RSS Type: " + $rss.Headers['Content-Type'] | Out-File -FilePath verification_result.txt -Append
} catch {
    "RSS Failed: " + $_.Exception.Message | Out-File -FilePath verification_result.txt -Append
}

try {
    $sub = Invoke-WebRequest -Uri 'https://cardiac-cowboys.podcastplusplus.com/' -Method Head
    "Subdomain Status: " + $sub.StatusCode | Out-File -FilePath verification_result.txt -Append
} catch {
    "Subdomain Failed: " + $_.Exception.Message | Out-File -FilePath verification_result.txt -Append
}
