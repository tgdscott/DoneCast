# Bulk Delete Test Users Script
# Usage: 
#   .\bulk_delete_test_users.ps1 -DryRun  # See what would be deleted
#   .\bulk_delete_test_users.ps1          # Actually delete them

param(
    [switch]$DryRun,
    [switch]$Force
)

$API_URL = $env:API_URL
if (-not $API_URL) {
    $API_URL = "https://podcast-api-524304361363.us-west1.run.app"
}

$ADMIN_TOKEN = $env:ADMIN_TOKEN
if (-not $ADMIN_TOKEN) {
    Write-Host "❌ ERROR: ADMIN_TOKEN environment variable not set!" -ForegroundColor Red
    Write-Host "Set it with: `$env:ADMIN_TOKEN='your_token_here'" -ForegroundColor Yellow
    exit 1
}

# Protected accounts (will NEVER be deleted)
$PROTECTED_EMAILS = @(
    "test22@scottgerhardt.com",  # User's current test account
    "tom@pluspluspodcasts.com",
    "tgdscott@gmail.com",
    "scober@scottgerhardt.com"
)

# Test account patterns
$TEST_PATTERNS = @(
    "test",
    "test-",
    "delete",
    "@example.com",
    "@test.com",
    "verify",
    "test1", "test2", "test3", "test4", "test5",
    "test10", "test11", "test12", "test13", "test14", "test15", "test16", "test17", "test18", "test19",
    "test20", "test21"  # Don't include test22
)

function Get-AllUsers {
    Write-Host "📡 Fetching all users from $API_URL/api/admin/users..." -ForegroundColor Cyan
    
    $headers = @{
        "Authorization" = "Bearer $ADMIN_TOKEN"
        "Content-Type" = "application/json"
    }
    
    try {
        $response = Invoke-RestMethod -Uri "$API_URL/api/admin/users" -Headers $headers -Method Get
        $users = $response.users
        Write-Host "✅ Found $($users.Count) total users" -ForegroundColor Green
        return $users
    }
    catch {
        Write-Host "❌ Failed to fetch users: $_" -ForegroundColor Red
        exit 1
    }
}

function Test-IsTestAccount {
    param($user)
    
    $email = $user.email.ToLower()
    
    # Never delete protected accounts
    if ($PROTECTED_EMAILS -contains $email) {
        return $false
    }
    
    # Check for test patterns in email
    foreach ($pattern in $TEST_PATTERNS) {
        if ($email -like "*$pattern*") {
            return $true
        }
    }
    
    # Check if flagged by API
    if ($user.is_test_account -eq $true) {
        return $true
    }
    
    # Check if no content
    if ($user.counts.podcasts -eq 0 -and $user.counts.episodes -eq 0) {
        return $true
    }
    
    return $false
}

function Remove-TestUser {
    param(
        [string]$userId,
        [string]$email,
        [switch]$DryRun
    )
    
    if ($DryRun) {
        Write-Host "  [DRY RUN] Would delete: $email ($userId)" -ForegroundColor Yellow
        return $true
    }
    
    Write-Host "  🗑️  Deleting: $email ($userId)..." -NoNewline -ForegroundColor Cyan
    
    $headers = @{
        "Authorization" = "Bearer $ADMIN_TOKEN"
        "Content-Type" = "application/json"
    }
    
    $body = @{
        confirm_email = $email
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$API_URL/api/admin/users/$userId" -Headers $headers -Method Delete -Body $body
        
        $counts = $response.deleted_items
        Write-Host " ✅ Deleted (P:$($counts.podcasts) E:$($counts.episodes) M:$($counts.media_items))" -ForegroundColor Green
        
        if ($response.gcs_cleanup_command) {
            Write-Host "     GCS cleanup: $($response.gcs_cleanup_command)" -ForegroundColor Gray
        }
        
        return $true
    }
    catch {
        Write-Host " ❌ Failed: $_" -ForegroundColor Red
        return $false
    }
}

# Main script
Write-Host "=" * 70 -ForegroundColor White
Write-Host "🗑️  BULK TEST USER DELETION" -ForegroundColor White
Write-Host "=" * 70 -ForegroundColor White
Write-Host ""

# Fetch all users
$allUsers = Get-AllUsers

# Identify test accounts and protected accounts
$testUsers = @()
$protectedUsers = @()

foreach ($user in $allUsers) {
    if ($PROTECTED_EMAILS -contains $user.email.ToLower()) {
        $protectedUsers += $user
    }
    elseif (Test-IsTestAccount $user) {
        $testUsers += $user
    }
}

Write-Host ""
Write-Host "🔒 PROTECTED ACCOUNTS (will NOT be deleted):" -ForegroundColor Green
if ($protectedUsers.Count -gt 0) {
    foreach ($user in $protectedUsers) {
        Write-Host "  ✓ $($user.email) ($($user.id))" -ForegroundColor Green
    }
}
else {
    Write-Host "  (none found)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "🎯 TEST ACCOUNTS IDENTIFIED:" -ForegroundColor Yellow
if ($testUsers.Count -gt 0) {
    foreach ($user in $testUsers) {
        Write-Host "  • $($user.email) ($($user.id))" -ForegroundColor Yellow
        Write-Host "    Podcasts: $($user.counts.podcasts), Episodes: $($user.counts.episodes), Media: $($user.counts.media_items)" -ForegroundColor Gray
    }
}
else {
    Write-Host "  (none found - nothing to delete)" -ForegroundColor Gray
    exit 0
}

Write-Host ""
Write-Host "📊 SUMMARY:" -ForegroundColor Cyan
Write-Host "  Total users: $($allUsers.Count)" -ForegroundColor White
Write-Host "  Protected: $($protectedUsers.Count)" -ForegroundColor Green
Write-Host "  To delete: $($testUsers.Count)" -ForegroundColor Yellow
Write-Host ""

# Confirmation
if (-not $DryRun -and -not $Force) {
    Write-Host "⚠️  WARNING: This will PERMANENTLY delete these accounts!" -ForegroundColor Red
    Write-Host "   Type 'DELETE' to confirm:" -ForegroundColor Yellow
    $confirmation = Read-Host "> "
    if ($confirmation -ne "DELETE") {
        Write-Host "❌ Cancelled by user" -ForegroundColor Red
        exit 0
    }
    Write-Host ""
}

# Delete users
if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE - No actual deletions will occur:" -ForegroundColor Yellow
}
else {
    Write-Host "🗑️  DELETING TEST ACCOUNTS:" -ForegroundColor Red
}

Write-Host ""

$successCount = 0
$failCount = 0

foreach ($user in $testUsers) {
    if (Remove-TestUser -userId $user.id -email $user.email -DryRun:$DryRun) {
        $successCount++
    }
    else {
        $failCount++
    }
}

Write-Host ""
Write-Host "=" * 70 -ForegroundColor White
Write-Host "✅ COMPLETE" -ForegroundColor Green
Write-Host "=" * 70 -ForegroundColor White

if ($DryRun) {
    Write-Host "Would have deleted $successCount test accounts" -ForegroundColor Yellow
}
else {
    Write-Host "Successfully deleted: $successCount" -ForegroundColor Green
    Write-Host "Failed: $failCount" -ForegroundColor Red
}

Write-Host ""
