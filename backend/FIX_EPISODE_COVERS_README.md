# Fix Episode Cover Image URLs

This script fixes broken episode cover images by matching R2 objects with database records.

## Problem

Episodes are showing broken cover images because:
1. `gcs_cover_path` is missing or null
2. `gcs_cover_path` has `r2://` format instead of `https://` URL
3. Cover images exist in R2 but database doesn't have the correct path

## Solution

The script `fix_episode_cover_r2_urls.py`:
1. Scans all episodes for missing/invalid cover URLs
2. Searches R2 bucket for cover images matching episode IDs
3. Converts `r2://` paths to `https://` URLs
4. Updates database with correct R2 URLs

## Usage

### Dry Run (Recommended First)

```bash
cd backend
python fix_episode_cover_r2_urls.py --dry-run
```

This will show what would be fixed without making any changes.

### Fix All Episodes

```bash
cd backend
python fix_episode_cover_r2_urls.py
```

### Fix Specific Episode

```bash
cd backend
python fix_episode_cover_r2_urls.py --episode-id <EPISODE_UUID>
```

### Limit Number of Episodes

```bash
cd backend
python fix_episode_cover_r2_urls.py --limit 100
```

## Requirements

- Environment variables:
  - `DATABASE_URL` - Database connection string
  - `R2_BUCKET` - R2 bucket name (default: "ppp-media")
  - `R2_ACCOUNT_ID` - Cloudflare R2 account ID
  - `R2_ACCESS_KEY_ID` - R2 access key
  - `R2_SECRET_ACCESS_KEY` - R2 secret key

## How It Works

1. **Checks existing cover URLs**: Uses `compute_cover_info()` to verify if cover URL is valid
2. **Converts r2:// paths**: If `gcs_cover_path` has `r2://` format, converts to HTTPS URL
3. **Searches R2**: Looks for covers in multiple path patterns:
   - `{user_id}/episodes/{episode_id}/cover/` (from orchestrator)
   - `covers/episode/{episode_id}/` (from migration)
4. **Updates database**: Sets `gcs_cover_path` to the correct HTTPS URL

## Output

The script will log:
- Episodes with valid cover URLs (skipped)
- Episodes that need fixing
- R2 URLs found for each episode
- Summary of fixes applied

## Example Output

```
2025-01-XX 12:00:00 - INFO - Found 217 episodes to check
2025-01-XX 12:00:01 - INFO - Episode abc-123 already has valid cover URL: https://ppp-media...
2025-01-XX 12:00:02 - INFO - Episode def-456 needs cover URL fix. Current: None
2025-01-XX 12:00:03 - INFO - ✅ Found cover at path 2: https://ppp-media.../covers/episode/def-456/cover.jpg
2025-01-XX 12:00:04 - INFO - ✅ Successfully updated episode def-456 cover URL
...
2025-01-XX 12:05:00 - INFO - ================================================================================
2025-01-XX 12:05:00 - INFO - Summary:
2025-01-XX 12:05:00 - INFO -   Fixed: 150
2025-01-XX 12:05:00 - INFO -   Skipped: 67
2025-01-XX 12:05:00 - INFO -   Errors: 0
2025-01-XX 12:05:00 - INFO -   Total: 217
```

