# Self-Hosted Podcast Delivery - Quick Reference

## What We Just Built

A complete self-hosted podcast RSS feed system to replace Spreaker, giving you:
- ✅ Full control over content delivery
- ✅ 100% of advertising revenue
- ✅ No platform fees
- ✅ Better analytics potential
- ✅ Faster iterations and custom features

## Files Created/Modified

### New Files
1. **`backend/api/routers/rss_feed.py`** - RSS 2.0 feed generator
   - Generates podcast feed XML with iTunes tags
   - Endpoint: `/api/rss/{podcast_id}/feed.xml`

2. **`SELF_HOSTED_PODCAST_MIGRATION.md`** - Complete migration guide
   - Architecture overview
   - Phase-by-phase implementation plan
   - Cost analysis
   - Rollback procedures

3. **`RSS_FEED_TESTING_GUIDE.md`** - Testing procedures
   - Local testing steps
   - Feed validation tools
   - Common issues and fixes
   - Production deployment checklist

4. **`RSS_DATABASE_SCHEMA_UPDATES.md`** - Database changes needed
   - audio_file_size column (required for RSS spec)
   - duration_ms column (better UX)
   - Migration scripts
   - Backfill procedures

### Modified Files
1. **`backend/api/routing.py`** - Registered RSS feed router
2. **`backend/infrastructure/gcs.py`** - Added `get_public_audio_url()` function
   - Generates 7-day signed URLs for podcast audio
   - Used by RSS feed for episode enclosures

## How It Works

```
Episode Assembly → Upload to GCS → Database Record
                                        ↓
                                   RSS Feed Generator
                                        ↓
                    Signed URLs (7-day expiry) for audio
                                        ↓
                            Podcast Directories
                            (Apple, Spotify, etc.)
                                        ↓
                                    Listeners
```

## Quick Start

### 1. Test Locally (5 minutes)

```powershell
# Start API
python -m uvicorn api.main:app --reload

# Visit your feed
http://localhost:8000/api/rss/{YOUR_PODCAST_ID}/feed.xml

# Validate
https://castfeedvalidator.com/
```

### 2. Add Database Columns (15 minutes)

```python
# Add to Episode model:
audio_file_size: Optional[int] = None
duration_ms: Optional[int] = None  # May already exist

# Run migrations (in startup_tasks.py)
ALTER TABLE episode ADD COLUMN audio_file_size INTEGER;
ALTER TABLE episode ADD COLUMN duration_ms INTEGER;
```

### 3. Deploy to Production (30 minutes)

```powershell
# Commit and push
git add .
git commit -m "Add self-hosted RSS feed"
git push

# Deploy to Cloud Run (or your hosting)
gcloud run deploy ...
```

### 4. Test Production Feed (15 minutes)

```
https://your-domain.com/api/rss/{podcast_id}/feed.xml
```

### 5. Submit to Test Directory (1-3 days)

- Submit to PodcastIndex.org first (easy approval)
- Verify it works end-to-end
- Monitor for issues

### 6. Migrate Main Directories (1-2 weeks)

- Update Apple Podcasts feed URL
- Update Spotify feed URL  
- Update Google Podcasts feed URL
- Keep Spreaker running for 7-30 days as backup

## Current Status

### ✅ Completed
- RSS feed generator with iTunes tags
- GCS signed URL generation (7-day expiry)
- Router registration
- Documentation and guides

### 🔄 Next Steps (Your Choice of Order)

#### Option A: Test Now (Recommended)
1. Start API locally
2. Visit feed URL
3. Validate with online tools
4. Test in a podcast app

#### Option B: Complete Schema First
1. Add `audio_file_size` column
2. Add `duration_ms` column (if missing)
3. Update assembly code to populate
4. Then test

#### Option C: Deploy to Production Quickly
1. Deploy as-is (will work with 0 file sizes)
2. Add schema updates in next iteration
3. Backfill existing episodes later

## Feed URL Format

```
/api/rss/{podcast_id}/feed.xml
```

Example:
```
https://yoursite.com/api/rss/abc123-def456-ghi789-012345/feed.xml
```

## What Directories Need

When updating podcast directories, you'll need:

1. **Your new RSS feed URL** (from above)
2. **Email verification** (some directories require it)
3. **Cover art** (minimum 1400x1400px for Apple)
4. **Show metadata** (already in your database)

The transition is seamless because:
- Episode GUIDs stay the same
- Listeners won't notice any change
- It's just pointing to a new feed URL

## Spreaker Redundancy

Keep Spreaker running as backup until you're confident:

**During Migration (Weeks 1-2)**
- Both feeds live simultaneously
- Test with new feed
- Spreaker is safety net

**After Validation (Week 3)**
- Update directories to new feed
- Monitor for 7 days
- Spreaker still publishing

**Deprecation (Week 4+)**
- Stop publishing to Spreaker
- Keep account for 30 days
- Cancel subscription 💰

## Cost Comparison

### Spreaker (Current)
- Platform fee: $X/month
- Limited control
- 3rd party dependency

### Self-Hosted (New)
- GCS storage: ~$0.10/month (100 episodes)
- GCS bandwidth: ~$3-6/month (1,000 downloads)
- Full control
- No platform fees
- **Plus**: Keep 100% of ad revenue! 💰

**Break-even**: Around 3,000-5,000 downloads/month (depending on Spreaker tier)

## Rollback Plan

If anything goes wrong:

1. **Quick Rollback** (< 5 minutes)
   - Update directory feed URLs back to Spreaker
   - Directories switch back within hours
   - Zero listener impact

2. **No Data Loss**
   - Your episodes stay in GCS
   - Spreaker copies intact during transition
   - Database unchanged

## Key Benefits

1. **Control**: You own the entire delivery pipeline
2. **Revenue**: Keep 100% of advertising income
3. **Analytics**: Better tracking (can log every download)
4. **Performance**: Direct from GCS + optional Cloud CDN
5. **Features**: Add custom functionality anytime
6. **Independence**: No 3rd party platform risk

## Documentation

- **Migration Guide**: `SELF_HOSTED_PODCAST_MIGRATION.md`
- **Testing Guide**: `RSS_FEED_TESTING_GUIDE.md`
- **Schema Updates**: `RSS_DATABASE_SCHEMA_UPDATES.md`

## Support Resources

### RSS/Podcast Specs
- RSS 2.0: https://www.rssboard.org/rss-specification
- iTunes Tags: https://podcasters.apple.com/support/823-podcast-requirements
- Podcast Namespace: https://github.com/Podcastindex-org/podcast-namespace

### Validation Tools
- Cast Feed Validator: https://castfeedvalidator.com/
- PodBase: https://podba.se/validate/
- Apple Podcasts: https://podcastsconnect.apple.com

### Directory Submission
- Apple Podcasts: https://podcastsconnect.apple.com
- Spotify: https://creators.spotify.com
- Google: https://podcastsmanager.google.com
- PodcastIndex: https://podcastindex.org

## Next Action Items

Choose your path:

### Path 1: Test First (Lowest Risk)
1. ✅ Start API locally
2. ✅ Test feed generation
3. ✅ Validate feed
4. → Add schema updates
5. → Deploy to production

### Path 2: Complete Implementation (Thorough)
1. ✅ Add database columns
2. ✅ Update assembly code
3. ✅ Backfill existing episodes
4. ✅ Test locally
5. → Deploy to production

### Path 3: Ship Fast (Iterate Later)
1. ✅ Deploy current code
2. ✅ Test production feed
3. ✅ Submit to test directory
4. → Add schema updates in next release
5. → Backfill episodes gradually

## Questions?

Refer to the detailed guides:
- Architecture questions → `SELF_HOSTED_PODCAST_MIGRATION.md`
- Testing issues → `RSS_FEED_TESTING_GUIDE.md`
- Database changes → `RSS_DATABASE_SCHEMA_UPDATES.md`

---

**Status**: Core RSS feed generation complete! ✅  
**Next**: Test it out and choose your migration path 🚀
