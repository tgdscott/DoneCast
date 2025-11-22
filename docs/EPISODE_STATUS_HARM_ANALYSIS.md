# What Breaks When Episodes Stay "processed" Instead of "published"

## Current Situation

Episodes with past `publish_at` dates but `status = "processed"`:
- ✅ **RSS Feeds** - Work fine (includes both `published` AND `processed`)
- ❌ **Public Websites** - Episodes don't show (only queries `status == published`)
- ❌ **Public Analytics** - Episodes not counted (only queries `status == published`)
- ⚠️ **File Cleanup** - Might delete files prematurely (uses status to determine if files are in use)
- ⚠️ **Billing/Refunds** - Might affect service delivery calculations (uses status)

## The Real Harm

### 1. Public Websites Don't Show Episodes (`sites.py:73`)
```python
.where(Episode.status == EpisodeStatus.published)
```
**Impact**: Episodes with past `publish_at` but `status = "processed"` won't appear on public websites.

### 2. Public Analytics Are Wrong (`public.py:57`)
```python
.where(Episode.status == EpisodeStatus.published)
```
**Impact**: Analytics only count episodes with `status == published`, missing episodes that should be published.

### 3. RSS Feeds Work Fine (`rss_feed.py:676-677`)
```python
.where(
    (Episode.status == EpisodeStatus.published) |
    (Episode.status == EpisodeStatus.processed)  # Includes scheduled episodes
)
```
**Impact**: None - RSS feeds include both, so they work correctly.

## The Duplication Problem

You have **three different ways** to determine if an episode is "published":

1. **Database `status` field** = `"published"` (used in queries)
2. **Database `publish_at` field** = past date (used for scheduling)
3. **Frontend derivation** = `publish_at <= now` (used for display)

This creates inconsistency where:
- Frontend shows "Published" (derived from `publish_at`)
- Database queries miss episodes (filter by `status == published`)
- Episodes appear in RSS but not on public websites

## Unified Solution Options

### Option 1: Make Queries Check `publish_at` Instead of `status` (Recommended)

Change all queries from:
```python
.where(Episode.status == EpisodeStatus.published)
```

To:
```python
.where(
    (Episode.status == EpisodeStatus.published) |
    (Episode.publish_at.isnot(None) & (Episode.publish_at <= now_utc))
)
```

**Pros**:
- Single source of truth (`publish_at`)
- No maintenance job needed
- Episodes automatically "published" when time passes
- Minimal code changes

**Cons**:
- Need to update ~3-4 query locations
- Still need `status` for processing states (`pending`, `processing`, `error`)

### Option 2: Remove `status` Field Entirely

Use only `publish_at` and processing flags.

**Pros**:
- Eliminates duplication completely
- Single source of truth

**Cons**:
- Major refactor
- Lose processing state tracking
- Risky change

### Option 3: Keep Both, Fix Queries to Use Hybrid Logic

Update queries to check both:
```python
.where(
    (Episode.status == EpisodeStatus.published) |
    (Episode.status == EpisodeStatus.processed & Episode.publish_at <= now_utc)
)
```

**Pros**:
- Works with existing data
- No maintenance job needed
- Episodes automatically work when `publish_at` passes

**Cons**:
- Still have duplication
- More complex queries

## Recommendation

**Option 1** - Update queries to check `publish_at` in addition to `status`. This:
- Fixes the immediate problem (episodes show on public sites)
- Eliminates need for maintenance job
- Uses `publish_at` as the source of truth for "published"
- Keeps `status` for processing lifecycle (`pending`, `processing`, `error`)





