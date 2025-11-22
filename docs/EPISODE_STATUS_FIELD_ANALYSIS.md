# Episode Status Field Analysis

## What the `status` Field Does

The `status` field is **NOT just for display** - it's used in critical database queries and business logic:

### 1. **RSS Feed Generation** (`rss_feed.py:676-677`)
```python
.where(
    (Episode.status == EpisodeStatus.published) |
    (Episode.status == EpisodeStatus.processed)  # Includes scheduled episodes
)
```
- Only includes episodes with `status == published` OR `status == processed`
- **Impact**: If status isn't updated, episodes won't appear in RSS feeds

### 2. **Public Website Episodes** (`sites.py:73`)
```python
.where(Episode.status == EpisodeStatus.published)
```
- Only shows episodes with `status == published` on public websites
- **Impact**: Episodes with past `publish_at` but `status != published` won't show on public sites

### 3. **Public Analytics** (`public.py:57`)
```python
.where(Episode.status == EpisodeStatus.published)
```
- Only counts published episodes for analytics
- **Impact**: Analytics will be incorrect if status isn't updated

### 4. **File Cleanup Logic** (`maintenance.py:65-69`)
```python
incomplete_statuses = {
    EpisodeStatus.pending,
    EpisodeStatus.processing,
    EpisodeStatus.error,
}
```
- Files are kept if episode status is `pending`, `processing`, or `error`
- Files can be deleted if status is `processed` or `published`
- **Impact**: Wrong status could cause files to be deleted prematurely or kept too long

### 5. **Billing/Refunds** (`admin/users.py:1827`)
```python
service_delivered = episode.status in ["processed", "published"]
```
- Determines if service was delivered for refund calculations
- **Impact**: Incorrect status could affect refund eligibility

### 6. **User Deletion** (`users/deletion.py:131`)
```python
.where(Episode.status == EpisodeStatus.published)
```
- Only counts published episodes when calculating what to delete
- **Impact**: Could affect data retention policies

## The Duplication Problem

You're right - there IS duplication:

1. **`status` field** (database) - Used for queries and business logic
2. **`publish_at` field** (database) - Timestamp for when episode should be published  
3. **Frontend derivation** - Derives "published" from `publish_at` for display

### Current Behavior

- **Frontend**: Shows "published" if `publish_at` is in past (derived, not from DB)
- **Database queries**: Filter by `status == published` (actual DB field)
- **Problem**: When `publish_at` passes, `status` doesn't auto-update, so queries miss those episodes

## Why Both Exist

The `status` field tracks the **processing/publishing lifecycle**:
- `pending` → `processing` → `processed` → `published`
- Also: `error` state for failed processing

The `publish_at` field tracks **when** an episode should be published (for scheduling).

## The Real Issue

The system was designed with the assumption that:
- Episodes are published immediately → `status` set to `published`
- Scheduled episodes → `status` stays `processed` until publish time, then background job updates it

But the background job to update status when `publish_at` passes **doesn't exist**, so:
- Scheduled episodes show as "published" in UI (derived from `publish_at`)
- But database queries filtering by `status == published` miss them
- This breaks RSS feeds, public websites, analytics, etc.

## Solution Options

### Option 1: Keep Both, Fix the Maintenance Job (Recommended)
- Keep `status` field for queries
- Keep `publish_at` for scheduling
- Run maintenance job periodically to update `status` when `publish_at` passes
- **Pros**: Minimal code changes, maintains existing query logic
- **Cons**: Requires scheduled job, slight delay in status update

### Option 2: Remove Status Field, Use Only `publish_at`
- Change all queries to check `publish_at <= now` instead of `status == published`
- Remove `status` field entirely
- **Pros**: Single source of truth, no duplication
- **Cons**: Major refactor, breaks existing logic, loses processing state tracking

### Option 3: Hybrid - Derive Status in Queries
- Keep `status` field but make queries smarter
- Query: `(status == published) OR (status == processed AND publish_at <= now)`
- **Pros**: Works with existing data, no maintenance job needed
- **Cons**: More complex queries, still have duplication

## Recommendation

**Option 1** is best because:
1. `status` field is used in many places - changing would be risky
2. Processing states (`pending`, `processing`, `error`) are still needed
3. Maintenance job is simple and reliable
4. Minimal code changes required

The maintenance job (`update_published_episodes.py`) should run every 5-15 minutes to keep status in sync.





