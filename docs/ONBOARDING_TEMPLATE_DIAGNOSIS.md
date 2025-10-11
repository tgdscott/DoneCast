# ONBOARDING WIZARD TEMPLATE CREATION DIAGNOSIS

**Date**: October 7, 2025  
**Issue**: Templates created during onboarding wizard not appearing  
**Related**: Recent audio/cover 404 fixes

## Problem Analysis

User reports that going through the new user wizard creates a template with intro/outro, but it doesn't appear in the template list.

### Possible Causes

#### 1. Template IS created but not visible
- Template created successfully in database
- Template list not refreshing after onboarding completes
- **Check**: Are templates in DB but not showing in UI?

#### 2. Template creation fails silently
- API call fails but error is swallowed (line 686-688 in Onboarding.jsx)
- **Check**: Are there errors in Cloud Run logs during template creation?

#### 3. Related to recent 404 fixes (LIKELY CAUSE)
- Our `_final_url_for()` fix returns `None` when files don't exist
- Template segments reference `intro/outro` filenames
- **BUT**: This shouldn't prevent template CREATION - just playback
- **Check**: Are segment filenames correct in saved templates?

#### 4. File upload/TTS generation failing
- `generateOrUploadTTS()` returns `null`
- `introAsset` / `outroAsset` remain `null`
- Template created with **no intro/outro segments**
- **Check**: Are intro/outro files being created?

## Code Flow Analysis

### Onboarding.jsx Template Creation (Lines 637-687)

```javascript
// Create a default template "My First Template" with intro/outro segments
try {
  const segments = [];
  if (introAsset?.filename) {
    segments.push({ segment_type: 'intro', source: { source_type: 'static', filename: introAsset.filename } });
  }
  segments.push({ segment_type: 'content', source: { source_type: 'tts', script: '', voice_id: 'default' } });
  if (outroAsset?.filename) {
    segments.push({ segment_type: 'outro', source: { source_type: 'static', filename: outroAsset.filename } });
  }
  
  const templatePayload = { name: 'My First Template', podcast_id: chosen?.id, segments, ... };
  await makeApi(token).post('/api/templates/', templatePayload);
} catch (e) {
  // ERROR IS SWALLOWED! Only shows toast
  toast({ title: 'Template not saved', description: e?.message, variant: 'destructive' });
}
```

**KEY ISSUE**: If `introAsset` or `outroAsset` are `null`, the template IS created but with **ONLY a content segment**.

User would see:
- Template exists in list: ✅
- Template has intro: ❌ (missing)
- Template has outro: ❌ (missing)

### Why intro/outro Assets Might Be Null

#### Path 1: TTS Generation
```javascript
async function generateOrUploadTTS(kind, mode, script, file) {
  if (mode === 'upload') { ... }
  else {
    const body = { text: script, category: kind, ... };
    const item = await makeApi(token).post('/api/media/tts', body);
    return item || null;  // Could return null if API fails
  }
}
```

**If TTS API fails**: Returns `null`, no intro/outro added to template

#### Path 2: File Upload
```javascript
if (mode === 'upload') {
  const fd = new FormData();
  fd.append('files', file);
  const data = await makeApi(token).raw(`/api/media/upload/${kind}`, { method: 'POST', body: fd });
  if (Array.isArray(data) && data.length > 0) return data[0];
  return null;  // Returns null if upload fails
}
```

**If upload fails**: Returns `null`, no intro/outro added to template

### Recent Changes Impact

Our recent fixes to `_final_url_for()` and `_cover_url_for()`:
- **NOW**: Return `None` if files don't exist locally
- **BEFORE**: Always returned `/static/media/filename` even if missing

**Impact on Template Creation**: **NONE** - templates are created regardless of file existence

**Impact on Template Display**: **POSSIBLE** - template editor might not show intro/outro segments properly if files don't exist

## Diagnosis Steps

### Step 1: Check Database
```sql
-- Check if templates exist
SELECT id, name, user_id, podcast_id, segments_json 
FROM podcast_templates 
WHERE name = 'My First Template' 
ORDER BY created_at DESC 
LIMIT 5;

-- Check segment structure
SELECT 
  id, 
  name,
  json_extract(segments_json, '$[0].segment_type') as segment_1_type,
  json_extract(segments_json, '$[0].source.filename') as segment_1_file,
  json_extract(segments_json, '$[1].segment_type') as segment_2_type,
  json_extract(segments_json, '$[2].segment_type') as segment_3_type,
  json_extract(segments_json, '$[2].source.filename') as segment_3_file
FROM podcast_templates 
WHERE name = 'My First Template'
ORDER BY created_at DESC LIMIT 1;
```

### Step 2: Check Cloud Run Logs
```bash
gcloud logging read "
  resource.type=cloud_run_revision 
  AND textPayload=~'template' 
  AND (severity>=WARNING OR textPayload=~'TTS')
" --limit=100 --project=podcast612
```

Look for:
- `POST /api/templates/` errors
- `POST /api/media/tts` failures
- `POST /api/media/upload/intro` failures
- `POST /api/media/upload/outro` failures

### Step 3: Check Media Files
```sql
-- Check if intro/outro files exist in media library
SELECT id, filename, category, display_name, created_at
FROM media_files
WHERE category IN ('intro', 'outro')
ORDER BY created_at DESC
LIMIT 10;
```

### Step 4: Frontend Console
During onboarding, check browser console for:
- Failed API calls to `/api/media/tts`
- Failed API calls to `/api/media/upload/intro` or `/outro`
- Toast notifications about "Template not saved"
- Network errors during template creation

## Likely Root Causes (Ranked)

### 1. TTS/Upload Failing (70% likely)
- ElevenLabs API issues
- File upload size limits
- Missing API keys
- **Symptom**: Template exists but has only content segment

### 2. Template List Not Refreshing (20% likely)
- User completes onboarding
- Template created successfully
- Dashboard doesn't refetch templates
- **Symptom**: Template exists in DB but not visible until refresh

### 3. Template Creation Error (10% likely)
- Validation error in backend
- Database constraint violation
- **Symptom**: No template in database at all

## Fix Recommendations

### Fix 1: Better Error Reporting in Onboarding

**File**: `frontend/src/pages/Onboarding.jsx`

```javascript
// BEFORE (lines 681-687):
try {
  await makeApi(token).post('/api/templates/', templatePayload);
} catch (e) {
  toast({ title: 'Template not saved', description: e?.message, variant: 'destructive' });
}

// AFTER (with logging):
try {
  const createdTemplate = await makeApi(token).post('/api/templates/', templatePayload);
  console.log('[Onboarding] Template created:', createdTemplate.id);
  console.log('[Onboarding] Template segments:', segments.length, segments);
} catch (e) {
  console.error('[Onboarding] Template creation failed:', e);
  toast({ title: 'Template not saved', description: e?.message, variant: 'destructive' });
}
```

### Fix 2: Log intro/outro Asset Status

```javascript
// After generateOrUploadTTS calls (line 1377-1382):
console.log('[Onboarding] Intro asset:', introAsset);
console.log('[Onboarding] Outro asset:', outroAsset);
if (!introAsset) console.warn('[Onboarding] No intro asset available');
if (!outroAsset) console.warn('[Onboarding] No outro asset available');
```

### Fix 3: Ensure Template List Refreshes

Check where user is redirected after onboarding completes. Should trigger template list refresh.

### Fix 4: Don't Swallow Errors

```javascript
// Make template creation failure more obvious
} catch (e) {
  console.error('[Onboarding] Template creation failed:', e);
  toast({ 
    title: 'Template not saved', 
    description: e?.message || 'Unknown error',
    variant: 'destructive' 
  });
  // Consider blocking progress if template creation is critical
  throw e; // Or set an error state that prevents finishing
}
```

## Testing Plan

1. **Start fresh onboarding flow**
2. **Monitor browser console** for logs
3. **Choose TTS mode** for intro/outro
4. **Complete wizard**
5. **Check template manager** immediately
6. **Query database** for template
7. **Check Cloud Run logs** for errors

## User Questions to Ask

1. **Did you see any error toasts** during onboarding?
2. **What mode did you choose** for intro/outro? (TTS, upload, or existing)
3. **Do you see ANY template** in template manager after onboarding?
4. **If you see a template**, does it have intro/outro segments when you edit it?
5. **Can you check browser console** for errors during onboarding?

## Status

**Needs User Input** to determine:
- Is template created but empty?
- Is template not created at all?
- Is template created but not visible in UI?

Once we know which scenario, we can apply the appropriate fix.

---

**Next Action**: Ask user to provide specific details about what they're seeing (or not seeing) in template manager.
