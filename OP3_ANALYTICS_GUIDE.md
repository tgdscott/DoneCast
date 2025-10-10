# OP3 Analytics Guide

## What is OP3?

OP3 (Open Podcast Prefix Project) is an **open-source, privacy-respecting podcast analytics service** that tracks downloads by acting as a redirect proxy.

**How it works:**
1. You prefix your audio URLs with `https://op3.dev/e/`
2. When a podcast app downloads an episode, it hits OP3 first
3. OP3 logs the request (IP hash, user-agent, timestamp)
4. OP3 redirects (HTTP 302) to your actual audio URL
5. The podcast app downloads from your server (GCS)

## Accessing Your OP3 Analytics

### Method 1: OP3 Dashboard (Recommended)
1. Visit: **https://op3.dev**
2. Click "Sign In" (GitHub or email)
3. Once logged in, go to: **https://op3.dev/shows**
4. Search for your podcast show URL or title
5. You'll see:
   - Total downloads
   - Downloads over time (daily/monthly charts)
   - Geographic breakdown (countries)
   - Podcast app breakdown (Apple Podcasts, Overcast, etc.)
   - User-agent analysis

### Method 2: OP3 API (Programmatic)
OP3 provides a REST API to fetch your analytics:

```bash
# Get show analytics
curl "https://op3.dev/api/1/shows/{show_id}/downloads"

# Get episode analytics
curl "https://op3.dev/api/1/episodes/{episode_id}/downloads"
```

**API Docs**: https://op3.dev/api/docs

### Method 3: OP3 Podcast (Meta!)
OP3 publishes analytics as a podcast itself! Subscribe to see your stats read aloud weekly.

---

## Current Status: OP3 NOT Active in Your Feed

Based on our check, your RSS feed at:
- `https://www.podcastplusplus.com/v1/rss/cinema-irl/feed.xml`

**Does NOT have OP3 prefixes** in the audio URLs. The enclosure URLs point directly to GCS signed URLs.

### Why You're Not Seeing Data

If you previously had OP3 prefixes working (when using Spreaker), they're now gone because:
1. You migrated audio to GCS
2. Your RSS feed code generates direct GCS signed URLs
3. No OP3 prefix is added

---

## How to Add OP3 to Your RSS Feed

### Option 1: Server-Side Prefix (Recommended)

Modify `backend/api/routers/rss_feed.py` to wrap audio URLs:

```python
# Around line 145 where audio_url is generated:

if episode.gcs_audio_path:
    audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
    
    # Add OP3 prefix for analytics
    if audio_url and settings.ENABLE_OP3_ANALYTICS:
        audio_url = f"https://op3.dev/e/{audio_url}"
```

Add to `backend/api/core/config.py`:
```python
class Settings(BaseSettings):
    ...
    ENABLE_OP3_ANALYTICS: bool = Field(default=True)
```

**Pros**: 
- Automatic for all episodes
- Can toggle on/off easily
- Works with signed URLs

**Cons**:
- Requires code deployment
- Signed URL in OP3 redirect might expire (7 days)

### Option 2: Client-Side Redirect Route

Create a redirect endpoint in your API:

```python
# backend/api/routers/rss_feed.py

@router.get("/download/{episode_id}/audio")
def download_episode_audio(
    episode_id: UUID,
    session: Session = Depends(get_session),
):
    """Redirect to episode audio with OP3 tracking."""
    episode = session.get(Episode, episode_id)
    if not episode or not episode.gcs_audio_path:
        raise HTTPException(status_code=404, detail="Episode audio not found")
    
    # Generate signed URL
    audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
    
    # Redirect via OP3 for analytics
    op3_url = f"https://op3.dev/e/{audio_url}"
    return RedirectResponse(url=op3_url, status_code=302)
```

Then in RSS feed, use:
```python
audio_url = f"https://podcast-api-533915058549.us-west1.run.app/v1/rss/download/{episode.id}/audio"
```

**Pros**:
- Your own analytics endpoint
- Can add custom tracking
- Signed URL generated fresh on each request

**Cons**:
- Extra redirect hop
- Your server handles every download request

### Option 3: Use OP3's Signed URL Support

OP3 supports signed URLs! The signature params are preserved through the redirect.

Current approach is fine - just need to add the prefix.

---

## Implementation Plan

### Step 1: Add OP3 Prefix to Audio URLs

**File**: `backend/api/routers/rss_feed.py`

```python
# Around line 145 (where audio_url is set)

if episode.gcs_audio_path:
    logger.info(f"RSS Feed: Generating audio URL for episode {episode.episode_number}: {episode.gcs_audio_path}")
    audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
    
    # Add OP3 analytics prefix
    if audio_url:
        audio_url = f"https://op3.dev/e/{audio_url}"
        logger.info(f"RSS Feed: Generated OP3-prefixed URL for episode {episode.episode_number}")
    else:
        logger.warning(f"RSS Feed: Failed to generate audio URL for episode {episode.episode_number}")
```

### Step 2: Deploy

```bash
gcloud builds submit --config=cloudbuild.yaml --project=podcast612
```

### Step 3: Verify

```bash
curl "https://www.podcastplusplus.com/v1/rss/cinema-irl/feed.xml" | grep "op3.dev"
```

Should see OP3 URLs in enclosures.

### Step 4: Access Analytics

1. Go to https://op3.dev
2. Sign in with GitHub or email
3. Search for your podcast
4. View analytics!

---

## Privacy & GDPR Compliance

OP3 is designed to be privacy-respecting:
- **No cookies** or persistent identifiers
- **IP addresses are hashed** (can't reverse to identify users)
- **No personal data collected** (just user-agent, timestamp, country)
- **Open source** - you can review the code
- **Compliant** with GDPR, CCPA

**Note**: If you want even more privacy, you can self-host OP3 (it's open source).

---

## Alternative: Build Your Own Analytics

If you want full control, you can implement download tracking yourself:

1. **Create redirect endpoint** (like Option 2 above)
2. **Log each request** to database:
   ```python
   class EpisodeDownload(SQLModel, table=True):
       id: UUID
       episode_id: UUID
       downloaded_at: datetime
       ip_hash: str  # Hash for privacy
       user_agent: str
       country_code: str  # From GeoIP
       referrer: Optional[str]
   ```
3. **Build analytics dashboard** in frontend
4. **Aggregate daily/monthly** stats

**Pros**: Full control, no third-party
**Cons**: More work, need to maintain, GeoIP database, user-agent parsing

---

## Recommendation

**For now**: Add OP3 prefix (5-minute code change)  
**Later**: Build your own analytics infrastructure (P0 priority from roadmap)

OP3 is a great stopgap solution that gives you analytics immediately without building infrastructure. Then you can migrate to your own system when ready.

---

## Next Steps

1. ✅ Understand OP3 (you're here!)
2. ⏳ Add OP3 prefix to RSS feed code
3. ⏳ Deploy updated code
4. ⏳ Sign in to op3.dev to view analytics
5. ⏳ Later: Build custom analytics infrastructure

Want me to implement the OP3 prefix now?
