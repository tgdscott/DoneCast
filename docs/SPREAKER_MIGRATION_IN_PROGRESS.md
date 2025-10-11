# Spreaker to GCS Migration - In Progress

## Status: RUNNING ✅

**Started:** October 9, 2025
**Total Episodes:** 190 episodes
**Estimated Time:** 2-3 hours
**Current Progress:** Episode 1/190 (E188 - Weapons)

## Migration Details

### What's Happening:
1. Downloading audio files from Spreaker API (one at a time)
2. Uploading each file to Google Cloud Storage
3. Updating production PostgreSQL database with:
   - `gcs_audio_path` - full GCS path to audio file
   - `audio_file_size` - file size in bytes for RSS feed

### GCS Structure:
Audio files are being uploaded to:
```
gs://ppp-media-us-west1/b6d5f77e-699e-444b-a31a-e1b4cb15feb4/episodes/{episode_id}/audio/{filename}.mp3
```

### Database Connection:
- Connected to: Production PostgreSQL via Cloud SQL Proxy
- Database: `podcast` on `podcast612:us-west1:podcast612-db-prod`
- Method: Cloud SQL Proxy running on localhost:5432

### Command Running:
```powershell
python migrate_spreaker.py \
  --podcast cinema-irl \
  --user-id b6d5f77e-699e-444b-a31a-e1b4cb15feb4 \
  --live \
  --skip-failures \
  --yes
```

## Monitoring Progress

### Check Terminal Output:
The migration is running in PowerShell terminal ID: `24a66eba-73d5-4598-beac-994cc4ca44e5`

You can monitor by checking the terminal output periodically.

### Expected Output Per Episode:
```
[X/190] Ep N: Episode Title
  Spreaker ID: 12345678
  Downloading...
  Downloaded: XX.X MB
  Uploading...
  ✓ Complete (X done, Y failed)
  Time: X.Xm elapsed, Y.Ym remaining
```

### After Completion:
The script will show:
```
================================================================================
DONE: X success, Y failed
Time: XXX.X minutes
================================================================================

Verify: python backend/check_episode_urls.py --podcast cinema-irl
```

## What Happens After Migration

### 1. RSS Feed Will Work
Once complete, your RSS feed will serve audio from GCS:
- URL: https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml
- Each episode will have `<enclosure>` tags with GCS URLs
- Audio files will be served with signed URLs (7-day expiration currently)

### 2. Verification Steps
```bash
# Check database
python backend/check_episode_urls.py --podcast cinema-irl

# Download and inspect RSS feed
Invoke-WebRequest "https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml" -OutFile "rss_migrated.xml"

# Check for audio enclosures
Select-String -Path "rss_migrated.xml" -Pattern "<enclosure" | Measure-Object
```

### 3. Test in Podcast App
- Add feed URL to podcast app
- Verify episodes show up with audio
- Test playback

## Troubleshooting

### If Migration Stops:
The `--skip-failures` flag means it will continue past errors. If it stops completely:

1. Check how many succeeded:
   ```bash
   python backend/check_episode_urls.py --podcast cinema-irl
   ```

2. Resume from where it left off:
   ```bash
   # If it stopped at episode 150, resume from there
   python migrate_spreaker.py \
     --podcast cinema-irl \
     --user-id b6d5f77e-699e-444b-a31a-e1b4cb15feb4 \
     --start-from 150 \
     --live \
     --skip-failures \
     --yes
   ```

### If Cloud SQL Proxy Disconnects:
Restart it:
```powershell
.\cloud-sql-proxy.exe podcast612:us-west1:podcast612-db-prod
```

### Common Issues:
- **Spreaker API rate limiting**: Script will fail on that episode but continue
- **Network timeout**: Script will retry or skip with --skip-failures
- **Disk space**: Temp files are cleaned up after each upload (~20MB max at a time)

## Files & Locations

### Script Location:
`d:\PodWebDeploy\migrate_spreaker.py`

### Temp Directory:
`d:\PodWebDeploy\temp_migration/`
- Files are downloaded here temporarily
- Automatically cleaned up after upload

### Verification Script:
`d:\PodWebDeploy\backend\check_episode_urls.py`

## Next Steps After Completion

1. ✅ Verify all episodes migrated successfully
2. ✅ Test RSS feed in podcast app
3. ✅ Update RSS feed code to use permanent URLs (remove 7-day expiration)
4. ✅ Migrate cover images (196 episodes still using Spreaker CDN)
5. ✅ Fix Google OAuth redirect issue
6. ✅ Set up Spreaker RSS redirect once fully migrated
7. ✅ Cancel Spreaker account (after confirming everything works)

## Estimated Timeline

- **Migration**: 2-3 hours (190 episodes × ~0.6-1 min each)
- **Verification**: 15 minutes
- **Testing**: 30 minutes
- **Cover image migration**: 1-2 hours (separate script needed)

**Total migration to fully self-hosted**: ~4-6 hours

---

**Last Updated:** October 9, 2025
**Status:** Migration in progress - Episode 1/190
