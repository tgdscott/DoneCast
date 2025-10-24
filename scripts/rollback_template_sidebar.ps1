# Rollback Script - Template Editor Sidebar Redesign
# Date: October 19, 2024
# Purpose: Restore original template editor if sidebar redesign causes issues

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Template Editor Rollback Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$templateEditorDir = "d:\PodWebDeploy\frontend\src\components\dashboard\template-editor"

# Check if backup files exist
$backupFiles = @(
    "TemplateEditor.jsx.backup-oct19-2024",
    "TemplateBasicsCard.jsx.backup-oct19-2024",
    "EpisodeStructureCard.jsx.backup-oct19-2024",
    "MusicTimingSection.jsx.backup-oct19-2024",
    "AIGuidanceCard.jsx.backup-oct19-2024"
)

Write-Host "Checking for backup files..." -ForegroundColor Yellow
$allBackupsExist = $true
foreach ($backup in $backupFiles) {
    $path = Join-Path $templateEditorDir $backup
    if (Test-Path $path) {
        Write-Host "  ✓ Found: $backup" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Missing: $backup" -ForegroundColor Red
        $allBackupsExist = $false
    }
}

if (-not $allBackupsExist) {
    Write-Host ""
    Write-Host "ERROR: Not all backup files found!" -ForegroundColor Red
    Write-Host "Cannot proceed with rollback." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "WARNING: This will:" -ForegroundColor Yellow
Write-Host "  1. Restore original template editor files" -ForegroundColor Yellow
Write-Host "  2. Delete new sidebar layout and page components" -ForegroundColor Yellow
Write-Host "  3. You will lose any changes made to the new files" -ForegroundColor Yellow
Write-Host ""

$confirmation = Read-Host "Are you sure you want to rollback? (yes/no)"

if ($confirmation -ne "yes") {
    Write-Host "Rollback cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Starting rollback..." -ForegroundColor Cyan

# Restore original files
Write-Host ""
Write-Host "Restoring original files..." -ForegroundColor Yellow
try {
    Copy-Item (Join-Path $templateEditorDir "TemplateEditor.jsx.backup-oct19-2024") `
              (Join-Path $templateEditorDir "TemplateEditor.jsx") -Force
    Write-Host "  ✓ Restored: TemplateEditor.jsx" -ForegroundColor Green

    Copy-Item (Join-Path $templateEditorDir "TemplateBasicsCard.jsx.backup-oct19-2024") `
              (Join-Path $templateEditorDir "TemplateBasicsCard.jsx") -Force
    Write-Host "  ✓ Restored: TemplateBasicsCard.jsx" -ForegroundColor Green

    Copy-Item (Join-Path $templateEditorDir "EpisodeStructureCard.jsx.backup-oct19-2024") `
              (Join-Path $templateEditorDir "EpisodeStructureCard.jsx") -Force
    Write-Host "  ✓ Restored: EpisodeStructureCard.jsx" -ForegroundColor Green

    Copy-Item (Join-Path $templateEditorDir "MusicTimingSection.jsx.backup-oct19-2024") `
              (Join-Path $templateEditorDir "MusicTimingSection.jsx") -Force
    Write-Host "  ✓ Restored: MusicTimingSection.jsx" -ForegroundColor Green

    Copy-Item (Join-Path $templateEditorDir "AIGuidanceCard.jsx.backup-oct19-2024") `
              (Join-Path $templateEditorDir "AIGuidanceCard.jsx") -Force
    Write-Host "  ✓ Restored: AIGuidanceCard.jsx" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Error restoring files: $_" -ForegroundColor Red
    exit 1
}

# Remove new sidebar directories
Write-Host ""
Write-Host "Removing sidebar components..." -ForegroundColor Yellow

$layoutDir = Join-Path $templateEditorDir "layout"
$pagesDir = Join-Path $templateEditorDir "pages"

if (Test-Path $layoutDir) {
    Remove-Item -Path $layoutDir -Recurse -Force
    Write-Host "  ✓ Removed: layout/" -ForegroundColor Green
} else {
    Write-Host "  - Not found: layout/ (skip)" -ForegroundColor Gray
}

if (Test-Path $pagesDir) {
    Remove-Item -Path $pagesDir -Recurse -Force
    Write-Host "  ✓ Removed: pages/" -ForegroundColor Green
} else {
    Write-Host "  - Not found: pages/ (skip)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Rollback completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Restart your frontend dev server" -ForegroundColor White
Write-Host "  2. Test the template editor" -ForegroundColor White
Write-Host "  3. Verify all features work" -ForegroundColor White
Write-Host ""
Write-Host "The old template editor has been restored." -ForegroundColor Green
Write-Host ""
