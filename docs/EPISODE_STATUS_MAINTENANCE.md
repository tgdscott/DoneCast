# Episode Status Maintenance

## Problem

Episodes scheduled for future publication have `status='processed'` and `publish_at` set to a future date. When `publish_at` passes, the frontend derives "published" status for display, but the database status remains `processed`.

## Current Behavior

- **Frontend**: Derives "published" status when `publish_at` is in the past (see `backend/api/routers/episodes/read.py:509-511`)
- **Database**: Status remains `processed` unless manually updated
- **Issue**: Database queries filtering by `status='published'` won't include these episodes

## Solution

### 1. One-Time Fix (Historical Data)

Run the fix script to update episodes that should already be published:

```bash
# Dry run first
python backend/fix_episode_status_and_covers.py --fix-status --dry-run

# Apply fixes
python backend/fix_episode_status_and_covers.py --fix-status
```

### 2. Ongoing Maintenance (Automated)

Run the maintenance job periodically to update episodes when their `publish_at` time passes:

```bash
python backend/maintenance/update_published_episodes.py
```

**Recommended Schedule**: Every 5-15 minutes via cron or task scheduler.

**Example Cron Job** (runs every 15 minutes):
```
*/15 * * * * cd /path/to/PodWebDeploy && python backend/maintenance/update_published_episodes.py >> /var/log/episode_status_updates.log 2>&1
```

### 3. Future Episodes

Episodes scheduled for the future will:
- ✅ Show as "scheduled" in the UI (correct)
- ✅ Automatically update to "published" when maintenance job runs after `publish_at` passes
- ✅ Database status will be updated from `processed` → `published`

## Status Logic Summary

- **`status='processed'` + `publish_at` in future** → UI shows "scheduled"
- **`status='processed'` + `publish_at` in past** → UI shows "published" (derived), but DB still `processed` (needs maintenance job)
- **`status='published'`** → UI shows "published" (correct)

## Fix Script Logic

The fix script (`fix_episode_status_and_covers.py`) only updates episodes where:
- `publish_at` is in the **past** (already published)
- OR has `spreaker_episode_id` AND `publish_at` is null or in past

It **excludes** episodes with future `publish_at` dates (they should remain `scheduled`/`processed`).





