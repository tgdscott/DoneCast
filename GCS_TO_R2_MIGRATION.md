# GCS to R2 Migration Plan

## Strategy: Keep Spreaker on Spreaker, Migrate YOUR Episodes to R2

**NO LOCAL FILES - Cloud storage or Spreaker only.**

### Episode Types
1. **Spreaker episodes** → Stay on Spreaker (use stream URL)
2. **Your episodes** (GCS) → Migrate to R2
3. **Local files** → NO LONGER SUPPORTED

### Why R2 Over GCS?
- **Zero egress fees** (GCS charges $0.12/GB for downloads)
- **Built-in global CDN** (Cloudflare's edge network)
- **Lower storage costs** ($0.015/GB vs $0.020/GB GCS)
- **S3-compatible API** (industry standard)

## Migration Steps

### 1. Set Up R2 Credentials

Add to your `.env.local` and production secrets:

```bash
# Cloudflare R2 Configuration
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET=ppp-media
```

Get these from Cloudflare dashboard:
1. Go to R2 → Overview
2. Create API token with "Object Read & Write" permissions
3. Copy Account ID, Access Key ID, and Secret Access Key

### 2. Test Migration (Dry Run)

```bash
cd backend
python migrate_gcs_to_r2.py --dry-run
```

This will show what episodes would be migrated without actually moving them.

### 3. Test with Limited Episodes

```bash
python migrate_gcs_to_r2.py --limit 5
```

Migrate just 5 episodes to test the process.

### 4. Full Migration

```bash
python migrate_gcs_to_r2.py
```

This will migrate ALL episodes with `gs://` paths to R2.

### 5. Update Production Environment

After local testing succeeds:

1. **Add R2 secrets to Cloud Run:**
   ```bash
   # Add each secret via Secret Manager
   echo -n "your_account_id" | gcloud secrets create R2_ACCOUNT_ID --data-file=-
   echo -n "your_access_key" | gcloud secrets create R2_ACCESS_KEY_ID --data-file=-
   echo -n "your_secret_key" | gcloud secrets create R2_SECRET_ACCESS_KEY --data-file=-
   ```

2. **Update cloudbuild.yaml** to mount R2 secrets

3. **Deploy updated code:**
   ```bash
   gcloud builds submit --config=cloudbuild.yaml
   ```

4. **Run migration in production:**
   ```bash
   # SSH to Cloud Run instance or run as Cloud Run Job
   python migrate_gcs_to_r2.py
   ```

### 6. Verify Migration

Check that:
- ✅ Episodes load correctly in dashboard
- ✅ Audio plays from R2 URLs (r2:// paths)
- ✅ Spreaker episodes still play from Spreaker
- ✅ No local file warnings in logs

### 7. Optional: Delete GCS Files

Once migration is verified and stable:

```bash
# List GCS files to be deleted
gsutil ls -r gs://your-bucket/

# Delete old GCS files (CAREFUL!)
gsutil -m rm -r gs://your-bucket/audio/
```

## Code Changes Made

### `backend/api/routers/episodes/common.py`
- Updated `compute_playback_info()` to support R2 paths (`r2://bucket/key`)
- Removed ALL local file fallback logic
- Playback types: `"cloud"` (R2/GCS), `"spreaker"`, or `"none"`

### `backend/migrate_gcs_to_r2.py`
- New migration script
- Downloads from GCS, uploads to R2
- Updates `episode.gcs_audio_path` to `r2://` format
- Preserves Spreaker episodes (no migration needed)

### `backend/infrastructure/r2.py`
- Already had full R2 support with `get_signed_url()` function
- Generates 24-hour signed URLs for audio playback
- S3-compatible API via boto3

## Rollback Plan

If something goes wrong:

1. **Immediate rollback:** Episodes with `spreaker_episode_id` will continue working (no changes to Spreaker)
2. **GCS still available:** Original GCS files not deleted until migration verified
3. **Code rollback:** Revert `compute_playback_info()` changes to restore GCS priority

## Database Schema

No schema changes needed! The `episode.gcs_audio_path` field now accepts:
- `gs://bucket/key` (legacy GCS)
- `r2://bucket/key` (new R2)
- Spreaker uses `spreaker_episode_id` (unchanged)

## Cost Savings Estimate

Assuming 100 episodes × 50MB each × 1000 downloads/month:

**GCS costs:**
- Storage: 5GB × $0.020 = $0.10/month
- Egress: 5000GB × $0.12 = $600/month
- **Total: $600.10/month**

**R2 costs:**
- Storage: 5GB × $0.015 = $0.075/month
- Egress: **$0 (free!)**
- **Total: $0.075/month**

**Savings: ~$600/month** 🎉

## Next Steps

1. ✅ Code deployed (removes local file fallback)
2. ⏳ Set up R2 credentials
3. ⏳ Run migration (dry-run first)
4. ⏳ Deploy to production
5. ⏳ Verify migration successful
6. ⏳ Monitor for issues
7. ⏳ Optional: Clean up GCS files after 30 days

---

**Questions? Check the migration script logs or ask for help!**
