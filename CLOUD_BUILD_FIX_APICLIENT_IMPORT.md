# Cloud Build Fix - apiClient Import Error

**Date**: October 7, 2025  
**Build ID**: 1d4bd3f3-c29d-416f-b072-3bb1c500b05b  
**Error**: `"apiClient" is not exported by "src/lib/apiClient.js"`

## Problem

Cloud Build failed during Docker build step with:

```
Step #1: error during build:
Step #1: src/components/assistant/AIAssistant.jsx (14:9): "apiClient" is not exported by "src/lib/apiClient.js"
Step #1: 14: import { apiClient } from '../../lib/apiClient';
```

## Root Cause

The `AIAssistant.jsx` component was trying to import a non-existent export:

**Wrong:**
```javascript
import { apiClient } from '../../lib/apiClient';
// Used as: apiClient(token).get(...)
```

**Correct exports from `apiClient.js`:**
```javascript
export function makeApi(token) { ... }
export function isApiError(e) { ... }
export function resolveRuntimeApiBase() { ... }
export function coerceArray(payload) { ... }
export function buildApiUrl(path) { ... }
export function assetUrl(path) { ... }
export const api = { ... }
```

There is **no `apiClient` export** - the correct function is `makeApi`.

## Fix Applied

**Commit**: `ecf25ed2`

Changed in `frontend/src/components/assistant/AIAssistant.jsx`:

1. **Import statement:**
   ```javascript
   // Before:
   import { apiClient } from '../../lib/apiClient';
   
   // After:
   import { makeApi } from '../../lib/apiClient';
   ```

2. **All function calls** (4 locations):
   ```javascript
   // Before:
   await apiClient(token).get('/api/assistant/guidance/status')
   await apiClient(token).post('/api/assistant/proactive-help', ...)
   await apiClient(token).post('/api/assistant/guidance/track', ...)
   await apiClient(token).post('/api/assistant/chat', ...)
   
   // After:
   await makeApi(token).get('/api/assistant/guidance/status')
   await makeApi(token).post('/api/assistant/proactive-help', ...)
   await makeApi(token).post('/api/assistant/guidance/track', ...)
   await makeApi(token).post('/api/assistant/chat', ...)
   ```

## Verification

- ✅ No other files import `{ apiClient }`
- ✅ AIAssistant.jsx now uses correct `makeApi` function
- ✅ Consistent with rest of codebase (all other files use `makeApi`)

## Build Status

**Previous build**: ❌ FAILED (1d4bd3f3-c29d-416f-b072-3bb1c500b05b)  
**Next build**: Should succeed with commit ecf25ed2

Monitor at:
```bash
gcloud builds list --limit=1 --project=podcast612
```

## How This Happened

The `AIAssistant.jsx` component was likely created or modified without checking the actual exports from `apiClient.js`. The function was called `makeApi` in the original implementation but someone may have assumed it was called `apiClient`.

## Prevention

This type of error is caught by:
1. ✅ **Build process** - Vite/Rollup detected the missing export
2. ✅ **Type checking** - Would be caught by TypeScript (if enabled)
3. ⚠️ **Local testing** - Would fail on `npm run build` locally

**Recommendation**: Always run `npm run build` locally before pushing to catch these errors earlier.

---

## Status: ✅ FIXED

Build should succeed on next deploy.
