# AssemblyAI SSL Error Fix - November 5, 2025

## Problem

User encountered SSL connection error when transcribing audio:
```
urllib3.exceptions.SSLError: EOF occurred in violation of protocol (_ssl.c:2406)
HTTPSConnectionPool(host='api.assemblyai.com', port=443): Max retries exceeded
```

## Root Cause

**Windows SSL/TLS certificate issue** - Common problem on Windows where:
1. Python's SSL library has outdated certificates
2. Windows system certificates may be missing/expired
3. TLS protocol negotiation fails during handshake with AssemblyAI API

## Solution Implemented

### 1. Added Retry Strategy with Backoff
**File:** `backend/api/services/transcription/assemblyai_client.py`

Added urllib3 Retry configuration to HTTPAdapter:
- **3 retries** with exponential backoff (1s, 2s, 4s)
- Retry on SSL errors, connection errors, and 5xx status codes
- Allow retries on POST requests (for uploads)

```python
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["POST", "GET"],
)
```

### 2. Better Error Handling & Diagnostics
Added explicit SSL error catching with helpful messages:

**SSL Error:**
```python
raise AssemblyAITranscriptionError(
    f"SSL connection failed to AssemblyAI (common on Windows). "
    f"Try updating SSL certificates: pip install --upgrade certifi urllib3 requests. "
    f"Error: {ssl_err}"
)
```

**Connection Error:**
```python
raise AssemblyAITranscriptionError(
    f"Network connection failed to AssemblyAI. Check internet connection or firewall. "
    f"Error: {conn_err}"
)
```

## User Actions Required

### Immediate Fix (Most Likely to Work):
```powershell
# In your activated venv
pip install --upgrade certifi urllib3 requests
```

This updates:
- `certifi` - Mozilla's CA certificate bundle
- `urllib3` - HTTP library with updated SSL support
- `requests` - HTTP library that uses urllib3

### Alternative Fixes (If First Doesn't Work):

#### Check Python Version:
```powershell
python --version
```
If using Python 3.7 or older, consider upgrading to Python 3.11+.

#### Check Windows Certificates:
```powershell
# Run as Administrator
certutil -store Root
```
Look for expired certificates.

#### Check Proxy Settings:
```powershell
$env:HTTP_PROXY
$env:HTTPS_PROXY
```
If corporate proxy is set, may need to configure Python to use it.

#### Verify SSL Module:
```powershell
python -c "import ssl; print(ssl.OPENSSL_VERSION)"
```
Should show OpenSSL 1.1.1+ or newer.

## Code Changes Summary

**File Modified:** `backend/api/services/transcription/assemblyai_client.py`

1. Added `from urllib3.util.retry import Retry` import
2. Enhanced `_build_shared_session()` with retry strategy
3. Added SSL-specific error handling in `upload_audio()` with diagnostic messages
4. Added connection error handling with helpful troubleshooting tips

## Testing

After updating packages, retry transcription:
1. Upload audio file
2. Start transcription
3. Check logs for successful AssemblyAI upload
4. If still fails, check Windows Event Viewer → Application logs for SSL/TLS errors

## Fallback Behavior

Code already has fallback to Google Speech-to-Text if AssemblyAI fails:
```
[transcription/pkg] AssemblyAI failed; falling back to Google
```

This means transcription will still work, but:
- ⚠️ User charged for AssemblyAI (34.78 credits already deducted)
- ⚠️ Google fallback may have different quality/features
- ⚠️ Double API costs if fallback happens frequently

## Production Impact

- ✅ **No breaking changes** - purely additive error handling
- ✅ **Better diagnostics** - users get clear SSL error messages
- ✅ **Automatic retries** - transient SSL issues may self-resolve
- ✅ **No config changes** - works with existing API keys/settings

## Status

✅ **CODE FIXED** - Backend now has better retry logic and error messages  
⚠️ **USER ACTION NEEDED** - Must run `pip install --upgrade certifi urllib3 requests`

## Follow-Up

If SSL errors persist after package updates:
1. Check Windows Firewall logs
2. Check antivirus SSL scanning settings
3. Verify no corporate proxy intercepting HTTPS
4. Consider using Windows Subsystem for Linux (WSL) as alternative dev environment
