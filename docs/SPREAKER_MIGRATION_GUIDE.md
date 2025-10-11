# Spreaker to Self-Hosted Migration Guide

## Overview

When migrating from Spreaker to your own hosting, you need to:

1. ✅ **RSS Feed Redirect** - Set up Spreaker redirect (you're doing this now)
2. ⚠️ **Migrate Audio Files** - Download from Spreaker, upload to your GCS
3. ⚠️ **Migrate Cover Images** - Download from Spreaker, upload to your GCS

## Why You Need to Migrate Files

Your RSS feed currently points to:
- Audio files hosted on Spreaker's servers
- Cover images hosted on Spreaker's CDN

**Problem**: If you cancel your Spreaker account or they remove your files, your podcast will break!

**Solution**: Copy all files to your own Google Cloud Storage bucket.

---

## Step 1: Check Current Situation (Dry Run)

First, see what needs to be migrated:

```powershell
python migrate_spreaker_files.py --podcast cinema-irl
```

This will show you:
- Which episodes have Spreaker URLs
- Where files will be uploaded in GCS
- Estimated file sizes
- **No changes will be made**

---

## Step 2: Run the Migration (Live)

Once you've reviewed the dry run output:

```powershell
python migrate_spreaker_files.py --podcast cinema-irl --live
```

This will:
1. Download each audio file from Spreaker
2. Upload to your GCS bucket (`podcast612-media`)
3. Update the database with new GCS paths
4. Download cover images (if needed)
5. Update RSS feed automatically

---

## Step 3: Verify Migration

After migration, check your RSS feed:

```powershell
Invoke-WebRequest -Uri "https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml" -UseBasicParsing | Select-Object -ExpandProperty Content | Out-File rss_after_migration.xml
```

Look for:
- Audio URLs should be signed GCS URLs (starting with `https://storage.googleapis.com/...`)
- Cover images should be from your CDN or GCS

---

## Step 4: Enable Spreaker Redirect

Only AFTER files are migrated:

1. Go to Spreaker RSS Settings
2. Select "Redirected"
3. Enter: `https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml`
4. Save

---

## Timeline

### Recommended Approach:

**Week 1-2**: 
- ✅ Migrate all files to GCS
- ✅ Test new RSS feed with a few test subscribers
- ✅ Verify all episodes play correctly

**Week 3**:
- ✅ Enable Spreaker redirect
- ✅ Monitor podcast platforms for updates

**Week 4-8**:
- ✅ Keep Spreaker redirect active
- ✅ Verify platforms are using new feed

**After 60 days**:
- ✅ Can safely disable Spreaker redirect
- ✅ All platforms should be updated

---

## Important Notes

### File Storage Costs

Storing audio files in GCS costs:
- **Storage**: ~$0.02 per GB/month (Standard class)
- **Bandwidth**: ~$0.12 per GB downloaded (first 1TB free per month)

**Example**: 
- 195 episodes × 50MB average = ~10GB storage = **$0.20/month**
- 1000 downloads/month × 50MB = 50GB = **$0 (within free tier)**

### Keep Spreaker Active During Migration

- ✅ Keep paying for Spreaker for at least 2 months
- ✅ Don't delete episodes from Spreaker yet
- ✅ Let the redirect do its job

### What Happens to Existing Subscribers

- They continue to see your podcast in their app
- Episodes download from new location automatically
- No action required from them
- Reviews/ratings stay intact

---

## Troubleshooting

### If migration script fails:

1. **Check Google Cloud credentials**:
   ```powershell
   gcloud auth application-default login
   ```

2. **Verify GCS bucket exists**:
   ```powershell
   gsutil ls gs://podcast612-media/
   ```

3. **Check database connection**:
   ```powershell
   # Test local DB
   python -c "from api.database import engine; print(engine)"
   ```

### If audio files don't play after migration:

1. **Check GCS bucket permissions** (should be public-read)
2. **Verify signed URLs are being generated** in RSS feed
3. **Check Cloud Run service account** has Storage Object Viewer role

---

## Next Steps

1. **Run dry-run** to see what needs migration
2. **Review output** - make sure paths look correct
3. **Run live migration** when ready
4. **Test RSS feed** before enabling Spreaker redirect
5. **Enable Spreaker redirect** after verification
6. **Monitor** podcast platforms for 2-4 weeks

---

## Questions?

- How many episodes do you have?
- What's the average file size?
- Want to migrate a few test episodes first?
