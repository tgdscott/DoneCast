# Check API Service Environment Variables
# This script verifies that all required environment variables are set correctly

$project = "podcast612"
$service = "podcast-api"
$region = "us-west1"

Write-Host "🔍 Checking API Service Environment Variables" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Fetching environment variables from Cloud Run service..." -ForegroundColor Yellow
$envVars = gcloud run services describe $service --region=$region --project=$project --format=json 2>&1 | ConvertFrom-Json

$container = $envVars.spec.template.spec.containers[0]
$envVarsList = @{}
$secretsList = @{}

# Parse environment variables
if ($container.env) {
    foreach ($env in $container.env) {
        if ($env.name) {
            if ($env.value) {
                $envVarsList[$env.name] = $env.value
            } elseif ($env.valueFrom -and $env.valueFrom.secretKeyRef) {
                $secretName = $env.valueFrom.secretKeyRef.name
                $secretKey = $env.valueFrom.secretKeyRef.key
                $secretsList[$env.name] = "$secretName/$secretKey"
            }
        }
    }
}

Write-Host ""
Write-Host "=== Required Cloud Tasks Configuration ===" -ForegroundColor Green
Write-Host ""

$requiredVars = @{
    "GOOGLE_CLOUD_PROJECT" = "podcast612"
    "TASKS_LOCATION" = "us-west1"
    "TASKS_QUEUE" = "ppp-queue"
    "TASKS_URL_BASE" = "https://api.podcastplusplus.com"
    "WORKER_URL_BASE" = "https://assemble.podcastplusplus.com"
    "APP_ENV" = "production"
}

$allGood = $true

foreach ($var in $requiredVars.Keys) {
    $expected = $requiredVars[$var]
    if ($envVarsList.ContainsKey($var)) {
        $actual = $envVarsList[$var]
        if ($actual -eq $expected) {
            Write-Host "✅ $var = $actual" -ForegroundColor Green
        } else {
            Write-Host "⚠️  $var = $actual (expected: $expected)" -ForegroundColor Yellow
            $allGood = $false
        }
    } elseif ($secretsList.ContainsKey($var)) {
        Write-Host "🔐 $var = $($secretsList[$var]) (secret)" -ForegroundColor Cyan
    } else {
        Write-Host "❌ $var = NOT SET" -ForegroundColor Red
        $allGood = $false
    }
}

Write-Host ""
Write-Host "=== Required Secrets ===" -ForegroundColor Green
Write-Host ""

$requiredSecrets = @("TASKS_AUTH")

foreach ($secret in $requiredSecrets) {
    if ($secretsList.ContainsKey($secret)) {
        Write-Host "✅ $secret = $($secretsList[$secret]) (configured)" -ForegroundColor Green
    } else {
        Write-Host "❌ $secret = NOT CONFIGURED" -ForegroundColor Red
        $allGood = $false
    }
}

Write-Host ""
Write-Host "=== Optional but Important ===" -ForegroundColor Green
Write-Host ""

$optionalVars = @("ENABLE_LOCAL_WORKER", "ENABLE_CELERY")

foreach ($var in $optionalVars) {
    if ($envVarsList.ContainsKey($var)) {
        $value = $envVarsList[$var]
        if ($var -eq "ENABLE_LOCAL_WORKER" -and $value -eq "false") {
            Write-Host "✅ $var = $value" -ForegroundColor Green
        } elseif ($var -eq "ENABLE_CELERY" -and $value -eq "false") {
            Write-Host "✅ $var = $value" -ForegroundColor Green
        } else {
            Write-Host "⚠️  $var = $value (should be 'false' in production)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "ℹ️  $var = NOT SET (optional)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""

if ($allGood) {
    Write-Host "✅ All required environment variables are set correctly!" -ForegroundColor Green
} else {
    Write-Host "❌ Some environment variables are missing or incorrect" -ForegroundColor Red
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Redeploy the API service with correct environment variables" -ForegroundColor White
    Write-Host "2. Verify TASKS_AUTH secret exists: gcloud secrets describe TASKS_AUTH --project=$project" -ForegroundColor White
    Write-Host "3. Check cloudbuild.yaml to ensure all variables are set correctly" -ForegroundColor White
}

Write-Host ""
Write-Host "=== Full Environment Variable List ===" -ForegroundColor Green
Write-Host ""

Write-Host "Environment Variables:" -ForegroundColor Cyan
$envVarsList.GetEnumerator() | Sort-Object Name | ForEach-Object {
    $value = $_.Value
    # Mask sensitive values
    if ($_.Key -match "PASS|SECRET|KEY|AUTH|TOKEN") {
        $value = "***MASKED***"
    }
    Write-Host "  $($_.Key) = $value" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Secrets:" -ForegroundColor Cyan
$secretsList.GetEnumerator() | Sort-Object Name | ForEach-Object {
    Write-Host "  $($_.Key) = $($_.Value)" -ForegroundColor Gray
}

