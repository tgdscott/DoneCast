# Old Domain References Cleanup

**Date**: October 7, 2025  
**Old domain**: getpodcastplus.com  
**Correct domain**: podcastplusplus.com

## Status: ✅ CLEAN

### Actual Code/Configs: ✅ CLEAN
- **Frontend code**: No references found
- **Backend code**: No references found
- **YAML configs**: No references found
- **Environment files**: No references found

### Documentation (Low Priority)

#### Temp/Test Files I Created:
- ✅ **FIXED**: `check_episode_193.py` 
- ✅ **FIXED**: `retry_episode_193.py`
- ✅ **FIXED**: `EPISODE_193_STUCK_PROCESSING_FIX.md`

#### Historical References (OK to keep):
- `logs.txt` - Old logs from September, don't need to clean
- `tmp_csp_test.py` - Temp test file
- `tmp_csp_env.yaml` - Temp env file

#### Documentation with "Legacy" Notes:
These files **correctly** mention the old domain as a legacy reference:

1. **terms_of_use_podcast_pro_plus_draft_v_1.md**:
   ```markdown
   (Legacy references to getpodcastplus.com refer to the same Service.)
   ```
   ✅ This is CORRECT - tells users the old URL was the same service

2. **privacy_policy_podcast_plus_draft_v_1.md**:
   ```markdown
   (Legacy references to getpodcastplus.com refer to the same Services.)
   ```
   ✅ This is CORRECT - same as above

3. **MEDIA_UPLOAD_FIX.md**:
   - Contains CORS config with both domains
   - This is for **backwards compatibility** during migration
   - Allows users with bookmarks to the old domain to still access
   - ⚠️ Can remove old domain from CORS after full migration complete

## Recommendation

### Keep As-Is:
- ✅ Terms of Use mention (explains legacy domain)
- ✅ Privacy Policy mention (explains legacy domain)
- ✅ Old log files (historical data)

### Update Later (Low Priority):
- `MEDIA_UPLOAD_FIX.md` - Remove old domains from CORS example when migration complete
- `tmp_*.py` / `tmp_*.yaml` - Delete these temp files eventually

### Already Fixed:
- ✅ Episode retry scripts now use `podcastplusplus.com`
- ✅ No hard-coded references in actual codebase

## CORS Configuration Check

If you want to verify your **actual** CORS config in production:

```bash
gcloud run services describe podcast-api \
  --region=us-west1 \
  --format="value(spec.template.spec.containers[0].env)" \
  | grep CORS_ALLOWED_ORIGINS
```

**Expected**: Should only have `podcastplusplus.com` variants (no `getpodcastplus.com`)

If the old domain is still there, update with:

```bash
gcloud run services update podcast-api \
  --region=us-west1 \
  --update-env-vars CORS_ALLOWED_ORIGINS="https://app.podcastplusplus.com,https://dashboard.podcastplusplus.com,https://podcastplusplus.com,https://www.podcastplusplus.com"
```

---

## Summary

**Your codebase is CLEAN!** ✅

The only references to `getpodcastplus.com` are:
1. ✅ **Fixed temp scripts** (my error, now corrected)
2. ✅ **Legal documents** (correctly note it as legacy)
3. ✅ **Old logs** (historical, ignore)
4. ⚠️ **CORS docs** (example config shows old domain for reference)

**No action needed** unless you want to clean up the CORS documentation example.
