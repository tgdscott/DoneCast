# Unified Published Status Logic

## Problem

The system had **three different ways** to determine if an episode is "published":
1. Database `status` field = `"published"` (used in queries)
2. Database `publish_at` field = past date (used for scheduling)
3. Frontend derivation = `publish_at <= now` (used for display)

This created inconsistency where:
- Episodes with past `publish_at` but `status = "processed"` showed as "published" in UI
- But database queries filtering by `status == "published"` missed them
- Episodes appeared in RSS feeds but not on public websites

## Solution

Created a unified helper function `is_published_condition()` that checks **both**:
- `status == "published"` (explicitly published), OR
- `status == "processed"` AND `publish_at <= now` (scheduled episode whose time has passed)

This makes `publish_at` the source of truth for published status, eliminating the need for a maintenance job.

## Changes Made

### 1. New Helper Function (`backend/api/routers/episodes/common.py`)

```python
def is_published_condition(now: Optional[datetime] = None):
    """
    Returns a SQLAlchemy condition that matches episodes that are "published".
    
    An episode is considered "published" if:
    1. status == 'published' (explicitly published), OR
    2. status == 'processed' AND publish_at <= now (scheduled episode whose time has passed)
    """
    from api.models.podcast import Episode
    
    if now is None:
        now = datetime.now(timezone.utc)
    
    return or_(
        Episode.status == EpisodeStatus.published,
        and_(
            Episode.status == EpisodeStatus.processed,
            Episode.publish_at.isnot(None),
            Episode.publish_at <= now
        )
    )
```

### 2. Updated Queries

All queries that filtered by `status == "published"` now use `is_published_condition()`:

- **Public Websites** (`sites.py:73`): Episodes now show on public sites when `publish_at` passes
- **Public Analytics** (`public.py:57`): Analytics now count episodes when `publish_at` passes
- **Admin Metrics** (`admin/metrics.py:40`): Published count now includes scheduled episodes
- **User Deletion** (`users/deletion.py:131`): Grace period calculation now includes scheduled episodes
- **Admin Deletions** (`admin/deletions.py:74`): Deletion logic now includes scheduled episodes

### 3. RSS Feeds (No Change Needed)

RSS feeds already included both `published` and `processed` statuses, so they continue to work correctly.

## Benefits

1. **Single Source of Truth**: `publish_at` determines if an episode is published
2. **No Maintenance Job Needed**: Episodes automatically "published" when `publish_at` passes
3. **Consistent Behavior**: All queries use the same logic
4. **Backward Compatible**: Episodes with `status == "published"` still work
5. **Scheduled Episodes Work**: Episodes scheduled for future automatically become published when time passes

## What Still Uses `status` Field

The `status` field is still used for:
- **Processing lifecycle**: `pending` → `processing` → `processed` → `published`
- **Error states**: `error` status for failed processing
- **RSS feeds**: Include both `published` and `processed` (for scheduled episodes)

## Testing

To verify the fix works:
1. Create an episode with `status = "processed"` and `publish_at` in the past
2. Check public website - episode should appear
3. Check public analytics - episode should be counted
4. Check RSS feed - episode should appear (already worked)

## Future Considerations

- The maintenance job (`update_published_episodes.py`) is now **optional** - it can still be run to update `status` field for consistency, but queries will work correctly without it
- Consider deprecating the maintenance job if all queries are updated to use `is_published_condition()`





