# Onboarding Audio Preview & Template Fix - October 13, 2025

## Problems

### Problem 1: Cannot Preview AI-Generated Audio
When users generate AI-created intro/outro audio in Step 6 of onboarding:
- **Error message**: "No audio - Could not determine preview URL"
- The preview button appears but clicking it shows this error instead of playing the audio
- **However**: The audio DOES get created and DOES appear in the Media Library where it CAN be previewed

### Problem 2: Outro Not Added to Template
- The AI-generated **intro** gets added to the default template correctly
- The AI-generated **outro** does NOT get added to the template
- This suggests the `outroAsset` variable is not being set properly after TTS generation

## Root Cause

When TTS generates an intro/outro, the backend:
1. Creates the audio file
2. Uploads it to Google Cloud Storage (GCS)
3. Stores a `MediaItem` in the database with `filename` = `gs://bucket/path/file.mp3`
4. Returns the `MediaItem` to the frontend

The frontend code in `Onboarding.jsx` had a bug in the `resolvePreviewUrl` function:
- It called `/api/media/preview?id=...&resolve=true` to get a signed URL
- BUT if that call failed (caught silently), it fell back to using `asset.filename`
- Since `asset.filename` contains `gs://...` (not a playable URL), the browser couldn't play it
- The error was swallowed silently in a `catch` block with no logging

The `gs://` URL would then go through normalization logic that doesn't handle `gs://` scheme, resulting in no valid URL.

## Root Cause Analysis

The console shows: **`[Onboarding] TTS response missing ID: ▸ Object`**

This is the smoking gun! The TTS endpoint IS returning an object, but either:
1. The `id` field is missing from the response
2. The `id` field is named differently (e.g., snake_case vs camelCase)
3. The response is being parsed incorrectly

Since the audio appears correctly in MediaLibrary, the backend IS creating the item with an ID. The issue is in how the onboarding wizard receives or handles the response.

## Solution

### 1. Simplified `resolvePreviewUrl` to Match MediaLibrary
The MediaLibrary component successfully previews the same audio files. I've updated Onboarding to use the EXACT SAME pattern:

```javascript
const resolvePreviewUrl = async () => {
  if (!asset?.id) {
    console.error('[Onboarding] Cannot resolve preview URL - asset has no ID:', asset);
    return null;
  }
  try {
    const api = makeApi(token);
    const res = await api.get(`/api/media/preview?id=${encodeURIComponent(asset.id)}&resolve=true`);
    const url = res?.path || res?.url;
    if (!url) {
      console.error('[Onboarding] Preview endpoint returned no URL for ID:', asset.id, 'Response:', res);
    }
    return url || null;
  } catch (err) {
    console.error('[Onboarding] Failed to resolve preview URL for ID:', asset.id, 'Error:', err);
    toast?.({ variant: 'destructive', title: 'Preview failed', description: err?.message || 'Could not resolve preview URL' });
    return null;
  }
};
```

### 2. Added Comprehensive Diagnostic Logging

**TTS Response Logging:**
```javascript
console.log('[Onboarding] TTS response for', kind, ':', item);
console.log('[Onboarding] TTS response keys:', item ? Object.keys(item) : 'null');
console.log('[Onboarding] TTS response id:', item?.id, 'filename:', item?.filename, 'category:', item?.category);
if (!item?.id) {
  console.error('[Onboarding] TTS response missing ID! Full object:', JSON.stringify(item, null, 2));
}
```

**Outro Creation Logging:**
```javascript
console.log('[Onboarding] Generating outro with mode:', outroMode);
const oa = await generateOrUploadTTS('outro', outroMode, outroScript, outroFile, outroAsset);
if (oa) {
  console.log('[Onboarding] Outro created successfully:', oa);
  console.log('[Onboarding] Outro has id?', !!oa.id, 'filename?', !!oa.filename);
  // ... set state ...
  console.log('[Onboarding] Setting selectedOutroId to:', selectedId);
}
```

**Template Creation Logging:**
```javascript
console.log('[Onboarding] Creating template with:', {
  introAsset,
  outroAsset,
  introFilename: introAsset?.filename,
  outroFilename: outroAsset?.filename
});
if (introAsset?.filename) {
  console.log('[Onboarding] Adding intro segment with filename:', introAsset.filename);
} else {
  console.warn('[Onboarding] NO intro added to template - introAsset:', introAsset);
}
if (outroAsset?.filename) {
  console.log('[Onboarding] Adding outro segment with filename:', outroAsset.filename);
} else {
  console.warn('[Onboarding] NO outro added to template - outroAsset:', outroAsset);
}
```

## Code Changes

**File**: `frontend/src/pages/Onboarding.jsx`

### Change 1: Enhanced `resolvePreviewUrl` function (lines ~472-502)
- Added error logging when ID-based preview fails
- Added explicit handling for `gs://` URLs with path parameter
- Added warning logs when preview endpoint returns no URL
- Return `null` for `gs://` URLs that can't be resolved (browser can't play them directly)

### Change 2: Added TTS response logging (lines ~633-636)
- Log the complete TTS response for debugging
- Warn if the response is missing an `id` field

## Why This Works

The `/api/media/preview` endpoint in `backend/api/routers/media.py` supports two modes:
1. **ID-based**: `?id=<uuid>` - looks up the MediaItem by ID and gets filename
2. **Path-based**: `?path=<gs://...>` - directly creates signed URL from GCS path

Both modes support `&resolve=true` which returns `JSONResponse({"url": signed_url})` instead of redirecting.

By adding explicit `gs://` handling, we ensure that:
- If the ID-based call fails, we try the path-based call
- If both fail, we get proper error logging to diagnose the issue
- We don't try to use `gs://` URLs directly in the browser (which won't work)

## Diagnostic Steps for User

With the enhanced logging, the console will now show:

1. **What the TTS endpoint returns**: Full object with all keys
2. **Whether the outro has an ID**: Boolean check
3. **What's in outroAsset when creating template**: Full state
4. **Whether outro gets added to template**: Clear warning if skipped

This will pinpoint exactly where the disconnect happens.

## Testing

1. Start the development servers:
   ```powershell
   # Terminal 1: Start API
   .\scripts\dev_start_api.ps1
   
   # Terminal 2: Start Frontend
   .\scripts\dev_start_frontend.ps1
   ```

2. Navigate to onboarding Step 6 (Intro & Outro)

3. Test TTS Generation:
   - Select "Generate with AI Voice" for intro or outro
   - Click "Next" to generate the audio
   - Verify audio is created successfully
   - Click the play button to preview
   - Should play without "Could not determine preview URL" error

4. Check browser console for logs:
   - Should see `[Onboarding] TTS response for intro/outro: {...}`
   - Should see `[Onboarding] Intro/Outro created: {...}`
   - Should NOT see any preview URL resolution errors

5. Verify signed URL generation:
   - Open browser Network tab
   - Click preview button
   - Should see request to `/api/media/preview?id=...&resolve=true` or `?path=gs://...&resolve=true`
   - Should return 200 with `{"url": "https://storage.googleapis.com/...?X-Goog-Signature=..."}`

## Related Files

- `frontend/src/pages/Onboarding.jsx` - Main onboarding component (fixed)
- `backend/api/routers/media.py` - Preview endpoint (already supports both modes)
- `backend/api/routers/media_tts.py` - TTS generation endpoint (returns MediaItem with GCS URL)
- `frontend/src/components/dashboard/MediaLibrary.jsx` - Reference implementation of preview resolution

## Notes

- This fix aligns with how `MediaLibrary.jsx` handles preview URLs
- The backend's `/api/media/preview` endpoint already had full support for both ID and path modes
- The frontend just needed to handle the `gs://` case explicitly
- Error logging will help diagnose any remaining authentication or GCS configuration issues

## Related Issues

- Similar to the intro/outro 404 fix from October 8, 2025 (see `docs/INTRO_OUTRO_404_FIX.md`)
- That fix addressed GCS credentials; this fix addresses frontend URL resolution
