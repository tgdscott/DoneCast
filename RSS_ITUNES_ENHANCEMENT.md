# RSS Feed Enhancement - iTunes Compliance ✅

## Date: October 10, 2025

## Summary
Enhanced RSS feed generation with configurable iTunes metadata fields for better podcast directory compliance.

## Changes Made

### 1. Podcast Model Updates (`backend/api/models/podcast.py`)

**Added Fields:**
```python
# iTunes/RSS settings
is_explicit: bool = Field(default=False, description="Podcast contains explicit content (iTunes)")
itunes_category: Optional[str] = Field(default="Technology", description="Primary iTunes category")
```

### 2. Episode Model Updates (`backend/api/models/podcast.py`)

**Added Field:**
```python
episode_type: Optional[str] = Field(default="full", description="iTunes episode type: full, trailer, or bonus")
```

### 3. RSS Feed Generator Updates (`backend/api/routers/rss_feed.py`)

**Enhanced Channel-Level Tags:**
- ✅ `<itunes:explicit>` - Now uses `podcast.is_explicit` (was hardcoded to "no")
- ✅ `<itunes:category>` - Now uses `podcast.itunes_category` (was hardcoded to "Technology")

**Enhanced Episode-Level Tags:**
- ✅ `<itunes:episodeType>` - Now uses `episode.episode_type` with validation for full/trailer/bonus

### 4. Database Migration (`backend/migrations/add_itunes_fields.sql`)

```sql
-- Add iTunes fields
ALTER TABLE podcast 
ADD COLUMN IF NOT EXISTS is_explicit BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS itunes_category VARCHAR(100) DEFAULT 'Technology';

ALTER TABLE episode
ADD COLUMN IF NOT EXISTS episode_type VARCHAR(20) DEFAULT 'full';

-- Add constraint for episode_type
ALTER TABLE episode
ADD CONSTRAINT episode_type_check 
CHECK (episode_type IN ('full', 'trailer', 'bonus') OR episode_type IS NULL);
```

## Benefits

### Before
- ❌ All podcasts marked as non-explicit (hardcoded)
- ❌ All podcasts categorized as "Technology" (hardcoded)
- ❌ All episodes marked as "full" type (hardcoded)

### After
- ✅ Per-podcast explicit content flag
- ✅ Customizable iTunes category per podcast
- ✅ Per-episode type (full/trailer/bonus) for better organization
- ✅ Better iTunes directory compliance
- ✅ More accurate podcast metadata

## iTunes Categories Available

Common categories you can use:
- Arts
- Business
- Comedy
- Education
- Fiction
- Government
- History
- Health & Fitness
- Kids & Family
- Leisure
- Music
- News
- Religion & Spirituality
- Science
- Society & Culture
- Sports
- Technology
- True Crime
- TV & Film

## Usage

### Setting Podcast-Level Metadata

```python
# Via API or database
podcast.is_explicit = True  # If podcast contains explicit content
podcast.itunes_category = "Comedy"  # Set iTunes category
```

### Setting Episode-Level Metadata

```python
# Regular episode
episode.episode_type = "full"  # Default

# Trailer episode
episode.episode_type = "trailer"

# Bonus content
episode.episode_type = "bonus"
```

## RSS Feed Output

### Channel Level
```xml
<channel>
  <title>My Podcast</title>
  <itunes:explicit>yes</itunes:explicit>  <!-- Now dynamic -->
  <itunes:category text="Comedy"/>  <!-- Now dynamic -->
</channel>
```

### Item Level
```xml
<item>
  <title>Episode 1</title>
  <itunes:explicit>no</itunes:explicit>
  <itunes:episodeType>full</itunes:episodeType>  <!-- Now dynamic -->
</item>
```

## Migration Required

Run the migration after deployment:

```bash
# Connect to Cloud SQL
./cloud-sql-proxy.exe podcast612:us-west1:podcast-db --port 5432

# Run migration (in another terminal)
psql -h 127.0.0.1 -U podcast -d podcast -f backend/migrations/add_itunes_fields.sql
```

Or via Cloud Run migration task if available.

## Testing

1. **Check RSS Feed:**
   ```bash
   curl https://api.podcastplusplus.com/v1/rss/cinema-irl/feed.xml
   ```

2. **Verify iTunes Tags:**
   - Look for `<itunes:explicit>`
   - Look for `<itunes:category>`
   - Look for `<itunes:episodeType>` in items

3. **Update Podcast Settings:**
   - Set `is_explicit = true` for a test podcast
   - Set `itunes_category = "Film & TV"` 
   - Verify RSS feed reflects changes

## Backward Compatibility

- ✅ Default values maintain existing behavior
- ✅ NULL handling with fallbacks
- ✅ Validation ensures only valid episode types
- ✅ Existing podcasts/episodes unaffected until explicitly updated

## TODOs Resolved

- ✅ Line 78: Make `itunes:explicit` configurable per podcast
- ✅ Line 103: Map category to iTunes category names (now user-configurable)
- ✅ Line 187: Make `episodeType` configurable per episode

## Next Steps

1. **UI Enhancement:** Add form fields in Podcast Manager to edit these values
2. **Validation:** Add UI dropdown for iTunes categories
3. **Documentation:** Update user guide with new metadata options
4. **Import:** Preserve these fields when importing from Spreaker

---
**Status:** ✅ Complete (pending deployment)
**Database Migration:** Required
**Breaking Changes:** None
**User Impact:** Better iTunes compliance, more control over metadata
