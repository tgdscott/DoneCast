# Local Intro/Outro Preview Issue - Investigation Results

## Problem
"No audio - Could not determine preview URL" error in Step 7 (Review your intro & outro) of local onboarding.

## Root Cause Found

### Issue #1: Missing Local Media Files
The database has a record for an intro file:
- **ID**: `74679b8cb3c64c288de7da21ae8b453a`
- **Category**: `intro`
- **Filename**: `456779837bc544b099e40d696cf87e1b_bc9d873c81394a719f127b509b2f1c8d_Intro3.mp3`
- **Friendly Name**: `Intro3`

BUT:
- ✅ Database record exists
- ❌ File does NOT exist at `backend/media/{filename}`
- ❌ `backend/media` directory doesn't even exist locally

This happens because:
1. The file was uploaded/created in a previous session
2. Local files are ephemeral (not persisted)
3. The database record persists, but the file is gone

### Issue #2: No GCS Backup
The filename is a local filename, NOT a GCS URL (`gs://...`). This means:
- The file was never uploaded to GCS (or upload failed silently)
- When the local file disappeared, there's no backup to fall back to
- The preview endpoint tries to find the local file and fails with 404

## Why This Doesn't Affect Production
In production (Cloud Run):
- Files SHOULD be uploaded to GCS immediately
- Database stores `gs://bucket/path` URLs instead of local filenames
- Even if container restarts, files are retrieved from GCS

## Local Development Fix Options

### Option 1: Clear the Orphaned Database Records (Quick Fix)
Remove database entries that reference missing local files:
```sql
DELETE FROM mediaitem WHERE category IN ('intro', 'outro') AND filename NOT LIKE 'gs://%';
```

### Option 2: Create the Missing Media Directory
```powershell
New-Item -ItemType Directory -Path "backend\media" -Force
```
Then re-create intro/outro files via TTS in the onboarding flow.

### Option 3: Test with Fresh Database
The intro/outro should work fine when created fresh after:
1. Starting API with new credentials
2. Creating new intro/outro via TTS (should upload to GCS now)

## What I've Done (Non-Breaking)
✅ Added debug logging to `/api/media/preview` endpoint to help diagnose issues
✅ Did NOT modify production code behavior
✅ Did NOT touch any GCS or database production data

## Recommended Next Steps
1. **For immediate testing**: Delete the orphaned database record
2. **Restart API** with new credentials: `.\scripts\dev_start_api.ps1`
3. **Create a new intro/outro** via TTS - should work and upload to GCS
4. **Test preview** - should work with proper signed URLs

## SQL to Clean Up (Safe for Local Only)
```sql
-- View orphaned records
SELECT id, category, filename, friendly_name 
FROM mediaitem 
WHERE category IN ('intro', 'outro', 'music', 'sfx', 'commercial')
AND filename NOT LIKE 'gs://%';

-- Delete orphaned records (after verifying above)
DELETE FROM mediaitem 
WHERE category IN ('intro', 'outro', 'music', 'sfx', 'commercial')
AND filename NOT LIKE 'gs://%';
```
