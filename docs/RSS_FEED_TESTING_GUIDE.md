# RSS Feed Testing Guide

## Quick Start - Test Your RSS Feed

### 1. Start Your API Locally

```powershell
# Navigate to project directory
cd D:\PodWebDeploy

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start the API
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Find Your Podcast ID

**Option A: Check your database**
```powershell
# Connect to your local SQLite database
sqlite3 database.db

# Query for podcasts
SELECT id, name FROM podcast;

# Copy the UUID for your podcast
```

**Option B: Check your production database**
- Login to your app
- Go to dashboard
- The podcast ID is in the URL or can be found in browser dev tools

### 3. Visit Your Feed URL

Open in browser:
```
http://localhost:8000/api/rss/{YOUR_PODCAST_ID}/feed.xml
```

Example:
```
http://localhost:8000/api/rss/abc123-def456-ghi789/feed.xml
```

You should see XML that looks like:
```xml
<?xml version="1.0" ?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Your Podcast Name</title>
    <description>Your podcast description</description>
    <language>en</language>
    ...
    <item>
      <title>Episode 1</title>
      <description>Episode description</description>
      <enclosure url="https://storage.googleapis.com/..." type="audio/mpeg" length="0"/>
      ...
    </item>
  </channel>
</rss>
```

### 4. Validate Your Feed

**Online Validators:**

1. **Cast Feed Validator** (Best for podcasts)
   - Visit: https://castfeedvalidator.com/
   - Enter your feed URL
   - Click "Validate"
   - Fix any errors shown

2. **PodBase Validator**
   - Visit: https://podba.se/validate/
   - Enter your feed URL
   - Check for warnings/errors

3. **Apple Podcasts Validator** (When ready for production)
   - Login to: https://podcastsconnect.apple.com
   - Create a test show
   - Submit your feed URL
   - Apple will validate it

### 5. Test in a Podcast App

**Easiest: Overcast (iOS) or Pocket Casts**

1. Copy your feed URL
2. Open podcast app
3. Search/Add by URL
4. Paste your feed URL
5. Verify:
   - [ ] Podcast title displays
   - [ ] Cover art shows
   - [ ] Episodes are listed
   - [ ] Episode descriptions show
   - [ ] Audio plays when clicked

**Desktop Testing: Apple Podcasts (Mac)**

1. Open Apple Podcasts app
2. File → Add a Show by URL
3. Paste your feed URL
4. Subscribe
5. Test playback

## Common Issues & Fixes

### Issue: "Feed not found" or 404 error

**Fix:**
- Verify the podcast ID is correct
- Check that the podcast exists in your database
- Ensure the API is running

### Issue: "Invalid XML" error

**Fix:**
- Check for special characters in titles/descriptions
- Look at the raw XML for syntax errors
- Common culprits: `&`, `<`, `>` need to be escaped

### Issue: "No episodes found"

**Fix:**
- Verify episodes have `status = "published"`
- Check that episodes have `gcs_audio_path` set
- Query your database:
  ```sql
  SELECT id, title, status, gcs_audio_path 
  FROM episode 
  WHERE podcast_id = 'YOUR_PODCAST_ID';
  ```

### Issue: Audio won't play

**Fix 1: Check GCS path**
```sql
-- Verify GCS paths exist
SELECT title, gcs_audio_path FROM episode;
```

**Fix 2: Test signed URL directly**
- Copy an audio URL from the feed
- Paste into browser
- Should download/play the MP3

**Fix 3: Check GCS permissions**
```powershell
# Test GCS access
gsutil ls gs://your-bucket/episodes/

# If permission denied, check service account
```

### Issue: Cover images not showing

**Fix:**
- Check podcast `remote_cover_url` or `cover_path`
- Verify episode `remote_cover_url` or `gcs_cover_path`
- Ensure URLs are publicly accessible
- Validate image format (JPG/PNG) and size (min 1400x1400 for Apple)

## Production Deployment

### 1. Deploy Updated Code

```powershell
# Commit changes
git add .
git commit -m "Add self-hosted RSS feed generation"
git push origin main

# Trigger Cloud Build (if automatic)
# Or manually deploy to Cloud Run
```

### 2. Get Production Feed URL

Your production feed URL will be:
```
https://your-production-domain.com/api/rss/{podcast_id}/feed.xml
```

### 3. Test Production Feed

```powershell
# Test from command line
curl https://your-production-domain.com/api/rss/{podcast_id}/feed.xml

# Or open in browser
```

### 4. Validate Production Feed

Run through all validators again with production URL:
- https://castfeedvalidator.com/
- https://podba.se/validate/

### 5. Monitor Logs

```powershell
# Watch Cloud Run logs
gcloud run services logs read YOUR-SERVICE-NAME --follow

# Or view in Cloud Console
# https://console.cloud.google.com/run
```

## Feed URL Formats

### By Podcast ID (Most Common)
```
/api/rss/{podcast_id}/feed.xml
```

### First/Primary Podcast (Convenience)
```
/api/rss/user/feed.xml
```
- Useful if you only have one podcast
- Returns feed for your first podcast

## Troubleshooting Checklist

Before migrating directories, verify:

- [ ] Feed validates with no errors on 2+ validators
- [ ] All published episodes appear in feed
- [ ] Audio URLs are accessible (test 3+ episodes)
- [ ] Cover art displays correctly
- [ ] Episode descriptions render properly
- [ ] Duration shows for each episode
- [ ] Podcast metadata is correct (title, author, email)
- [ ] Feed loads in at least 2 different podcast apps
- [ ] Audio plays in those apps without errors
- [ ] Production feed works (not just local)
- [ ] Signed URLs remain valid for 7+ days

## Performance Notes

### Feed Caching
- Feed is cached for 5 minutes (see `Cache-Control` header)
- Podcast apps typically check every 1-24 hours
- Changes may take time to propagate

### Signed URL Expiration
- Default: 7 days
- Podcast apps cache feed, so URLs must stay valid
- If you see expired URL errors, increase expiration days

### Large Podcasts
- Feeds with 100+ episodes may be slow to generate
- Consider pagination or limiting feed to recent 100 episodes
- Add an index on `episode.publish_at` if not present

## Next Steps

Once feed is working locally:

1. ✅ Test thoroughly locally
2. ✅ Deploy to production
3. ✅ Validate production feed
4. ✅ Test with real podcast app
5. → Submit to one test directory (PodcastIndex.org)
6. → Monitor for 1 week
7. → Migrate primary directories (Apple, Spotify)
8. → Deprecate Spreaker

## Need Help?

Check the main migration guide:
- `SELF_HOSTED_PODCAST_MIGRATION.md`

Common error messages:
- **"Invalid enclosure URL"**: Audio URL not accessible
- **"Missing required iTunes tags"**: Add owner email and author
- **"Image too small"**: Minimum 1400x1400px for Apple Podcasts
- **"Invalid pubDate"**: Check datetime formatting in RFC 2822
