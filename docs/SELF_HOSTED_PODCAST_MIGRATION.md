# Self-Hosted Podcast Delivery - Spreaker Migration Plan

## Overview

**Goal**: Move from Spreaker to fully self-hosted podcast delivery while maintaining 100% uptime and keeping Spreaker as a temporary safety net.

**Why?**
- ✅ **Control**: Own your content delivery and user experience
- ✅ **Revenue**: Keep 100% of advertising revenue
- ✅ **Cost**: Eliminate Spreaker platform fees
- ✅ **Analytics**: Better tracking and listener insights
- ✅ **Flexibility**: Custom features, faster iterations

**Timeline**: 2-4 weeks for full migration

---

## Current State Analysis

### What You Already Have ✅
1. **Audio Storage**: Episodes stored in GCS (`gcs_audio_path`)
2. **Cover Images**: Episode covers in GCS (`gcs_cover_path`)
3. **Metadata**: All episode data (title, description, show notes, tags, etc.) in database
4. **Processing Pipeline**: AssemblyAI, ElevenLabs, Vertex AI all working
5. **User Auth & Database**: Solid foundation
6. **Google Cloud Infrastructure**: Cloud Run, Cloud SQL, GCS buckets

### What Spreaker Currently Does
1. **RSS Feed Generation**: Creates podcast feed XML
2. **Audio Hosting**: Serves audio files
3. **CDN Delivery**: Fast worldwide distribution
4. **Directory Integration**: Listed in Apple Podcasts, Spotify, etc.

### What We'll Build
1. ✅ **RSS Feed Generator** - `backend/api/routers/rss_feed.py` (DONE)
2. 🔄 **Public Audio URLs** - GCS signed URLs or public bucket + CDN
3. 🔄 **Analytics Tracking** - Log downloads and plays
4. 🔄 **Directory Migration** - Update feed URLs in Apple/Spotify/etc.

---

## Architecture

### Current Flow (with Spreaker)
```
Your App → Process Episode → Upload to Spreaker → Spreaker RSS Feed → Directories
                                                → Spreaker CDN → Listeners
```

### Target Flow (Self-Hosted)
```
Your App → Process Episode → Upload to GCS → Your RSS Feed → Directories
                                           → GCS + Cloud CDN → Listeners
```

---

## Implementation Plan

### Phase 1: Build Infrastructure (Week 1) 🚧 IN PROGRESS

#### 1.1 ✅ RSS Feed Generation (DONE)
- Created `/api/rss/{podcast_id}/feed.xml` endpoint
- Generates RSS 2.0 with iTunes tags
- Uses existing database episode data
- Feed URL: `https://yoursite.com/api/rss/{podcast_id}/feed.xml`

#### 1.2 🔄 GCS Public Audio Delivery (NEXT)
**Option A: Signed URLs (Easiest - Start Here)**
- Generate 7-day signed URLs for audio files
- No bucket changes needed
- Good for initial testing

**Option B: Public Bucket + Cloud CDN (Production)**
- Make GCS bucket publicly readable (specific paths only)
- Enable Cloud CDN for fast global delivery
- Better performance, lower costs long-term

**Code needed**:
```python
# Add to backend/api/services/gcs_utils.py
from google.cloud import storage
from datetime import timedelta

def generate_signed_url(gcs_path: str, expiration_days: int = 7) -> str:
    """Generate signed URL for GCS object"""
    client = storage.Client()
    # Parse gs://bucket/path
    bucket_name, blob_name = gcs_path[5:].split("/", 1)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(days=expiration_days),
        method="GET",
    )
    return url
```

#### 1.3 🔄 Add Audio File Size to Database
RSS feeds require `<enclosure length="12345678">` attribute.

**Schema change needed**:
```python
# Add to Episode model
audio_file_size: Optional[int] = Field(default=None, description="Audio file size in bytes for RSS enclosure")
```

**Populate during assembly**:
```python
# In backend/worker/tasks/assembly/orchestrator.py after GCS upload
import os
file_size = os.path.getsize(local_audio_path)
episode.audio_file_size = file_size
```

#### 1.4 🔄 iTunes Category Mapping
Map your `category_id` to proper iTunes category names.

**Add to rss_feed.py**:
```python
ITUNES_CATEGORIES = {
    1: "Technology",
    2: "Business",
    3: "Comedy",
    # ... map your Spreaker categories
}
```

### Phase 2: Testing & Validation (Week 2)

#### 2.1 🔄 Test RSS Feed Locally
```bash
# Start your API
# Visit: http://localhost:8000/api/rss/{your_podcast_id}/feed.xml
# Validate with: https://podba.se/validate/
```

#### 2.2 🔄 Test with Podcast App
- Copy your RSS feed URL
- Add to a podcast app as a "private feed"
- Verify episodes load and play correctly
- Check artwork displays properly

#### 2.3 🔄 Test in Production (Shadow Mode)
- Deploy your RSS feed to production
- **Don't tell directories yet** - just have the URL live
- Monitor logs for any errors
- Verify signed URLs work from different locations

### Phase 3: Soft Launch (Week 3)

#### 3.1 🔄 Submit to ONE Directory First
Pick a small directory to test with (not Apple/Spotify yet):
- **PodcastIndex.org** - Easy submission, fast approval
- Or create a "test" show on Apple Podcasts

**What you'll do**:
1. Submit your RSS feed URL
2. Wait for approval (1-3 days)
3. Verify it works end-to-end
4. Check analytics - are downloads being logged?

#### 3.2 🔄 Add Analytics Tracking
Track episode downloads and plays:

```python
# Add endpoint to log plays
@router.post("/track/play/{episode_id}")
def track_episode_play(episode_id: UUID, user_agent: str, ip: str):
    # Log to database or analytics service
    # Track: episode, datetime, user location, client app
    pass
```

**Alternative**: Use your GCS bucket's Cloud Storage logs or Cloud CDN logs.

### Phase 4: Full Migration (Week 4)

#### 4.1 🔄 Update Directory Feed URLs
**One by one**, update your RSS feed URL in:

1. **Apple Podcasts Connect**
   - Login to podcastsconnect.apple.com
   - Update RSS feed URL
   - Submit for review (usually approved in 24-48hrs)

2. **Spotify for Creators**
   - Login to creators.spotify.com  
   - Update RSS feed URL
   - Changes take effect within hours

3. **Google Podcasts Manager**
   - Login to podcastsmanager.google.com
   - Update feed URL

4. **Other directories** (Stitcher, TuneIn, etc.)

**Important**: The transition is seamless because:
- Episode GUIDs remain the same
- Listeners won't notice any change
- Their apps will just pull from new feed URL

#### 4.2 🔄 Monitor for 7 Days
- Check directory status daily
- Monitor server logs for errors
- Verify listener counts match expectations
- Keep Spreaker running as backup

#### 4.3 🔄 Deprecate Spreaker
Once confident (7-30 days):
1. Stop publishing new episodes to Spreaker
2. Keep Spreaker account for 30 more days (just in case)
3. Download any Spreaker analytics you want to keep
4. Cancel Spreaker subscription 💰

---

## Technical Todos

### Backend Changes Needed

- [ ] **Add GCS signed URL generation service**
  - File: `backend/api/services/gcs_utils.py`
  - Function: `generate_signed_url(gcs_path, expiration_days=7)`
  
- [ ] **Update RSS feed to use signed URLs**
  - File: `backend/api/routers/rss_feed.py`
  - Replace `_get_gcs_public_url()` with signed URL generator

- [ ] **Add audio_file_size to Episode model**
  - File: `backend/api/models/podcast.py`
  - Add: `audio_file_size: Optional[int]`

- [ ] **Populate file size during assembly**
  - File: `backend/worker/tasks/assembly/orchestrator.py`
  - After GCS upload, get file size and save to episode

- [ ] **Add duration_ms to Episode model** (if not present)
  - Needed for `<itunes:duration>` tag

- [ ] **Map iTunes categories**
  - File: `backend/api/routers/rss_feed.py`
  - Add category ID → name mapping

- [ ] **Add analytics/tracking endpoint** (optional)
  - File: `backend/api/routers/analytics.py`
  - Track episode plays and downloads

### Database Migrations

```sql
-- Add audio file size
ALTER TABLE episode ADD COLUMN audio_file_size INTEGER;

-- Add duration if missing
ALTER TABLE episode ADD COLUMN duration_ms INTEGER;
```

### Infrastructure Changes

- [ ] **GCS Bucket Configuration**
  - Option A: Nothing needed (use signed URLs)
  - Option B: Make bucket publicly readable + enable Cloud CDN
  
- [ ] **Cloud CDN Setup** (optional, recommended)
  - Enable Cloud CDN on your GCS bucket
  - Configure caching rules
  - Reduces bandwidth costs significantly

- [ ] **Custom Domain** (optional)
  - Instead of: `storage.googleapis.com/bucket/file.mp3`
  - Use: `cdn.yourpodcast.com/file.mp3`

---

## Cost Analysis

### Current Spreaker Costs
- Platform fee: $? per month
- Hosting: Included
- Bandwidth: Included

### Self-Hosted Costs (Estimated)
- **GCS Storage**: ~$0.02/GB/month
  - Example: 100 episodes × 50MB = 5GB = $0.10/month
  
- **GCS Bandwidth** (egress):
  - First 1TB/month: $0.12/GB
  - Example: 1,000 downloads/month × 50MB = 50GB = $6/month
  
- **Cloud CDN** (if enabled):
  - Reduces bandwidth costs by ~60-80%
  - Caching: $0.08/GB (cheaper than direct GCS)
  - Example with CDN: 50GB = ~$3/month

**Total Estimated**: $3-10/month depending on volume

### Break-Even Analysis
If Spreaker costs $X/month:
- You break even at: `X / $0.12` = Y GB bandwidth/month
- Example: $20/month = profitable above ~160GB = ~3,200 downloads/month

**Plus**: You keep 100% of ad revenue! 💰

---

## RSS Feed URLs

### Your New Feed URL
```
Production: https://your-site.com/api/rss/{podcast_id}/feed.xml
Local Dev:  http://localhost:8000/api/rss/{podcast_id}/feed.xml
```

### How to Find Your Podcast ID
```bash
# Query your database or check your dashboard
# It's the UUID in your database podcasts table
```

### Feed Validation Tools
- **PodBase Validator**: https://podba.se/validate/
- **Cast Feed Validator**: https://castfeedvalidator.com/
- **Apple Podcasts**: https://podcastsconnect.apple.com (built-in validator)

---

## Rollback Plan

If anything goes wrong:

### Quick Rollback (< 5 minutes)
1. Update directory feed URLs back to Spreaker
2. Directories pull from Spreaker again within hours
3. No listener impact

### Data Safety
- Your episodes remain in GCS
- Spreaker copies remain during transition period
- Database unchanged

### Zero Downtime Guarantee
- Both feeds work simultaneously during transition
- Directories update independently
- Listeners experience no interruption

---

## Success Metrics

### Week 1 (Infrastructure)
- ✅ RSS feed generates valid XML
- ✅ Feed passes validation tools
- ✅ Audio URLs resolve and play

### Week 2 (Testing)
- ✅ Feed loads in podcast apps
- ✅ Episodes play correctly
- ✅ Artwork displays properly
- ✅ Production feed works globally

### Week 3 (Soft Launch)
- ✅ One directory approved and working
- ✅ Analytics tracking functional
- ✅ Zero errors in logs

### Week 4 (Full Migration)
- ✅ All directories updated
- ✅ Listener counts stable or growing
- ✅ No error reports
- ✅ Spreaker deprecated

---

## Support & Resources

### RSS 2.0 Spec
- https://www.rssboard.org/rss-specification

### iTunes Podcast Tags
- https://podcasters.apple.com/support/823-podcast-requirements

### Podcast Namespace
- https://github.com/Podcastindex-org/podcast-namespace

### GCS Signed URLs
- https://cloud.google.com/storage/docs/access-control/signed-urls

---

## Next Steps

1. **TODAY**: Test your RSS feed endpoint locally
   ```bash
   # Start API and visit:
   http://localhost:8000/api/rss/{your_podcast_id}/feed.xml
   ```

2. **THIS WEEK**: Add GCS signed URL generation

3. **NEXT WEEK**: Deploy to production and validate feed

4. **WEEK 3**: Submit to test directory

5. **WEEK 4**: Full migration!

---

## Questions & Decisions Needed

- [ ] Which GCS bucket are your audio files in?
- [ ] Do you want Cloud CDN enabled? (recommended)
- [ ] Custom domain for audio URLs? (optional)
- [ ] Which analytics solution? (GCS logs, custom DB, or 3rd party)
- [ ] Keep Spreaker for how long after migration? (recommend 30 days)

---

**Status**: Phase 1 (RSS Feed) completed ✅  
**Next**: Implement GCS signed URL generation 🔄
