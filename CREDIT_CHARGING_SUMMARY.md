# Credit Charging Mechanisms - Complete Documentation

Based on code analysis, here's how credits are charged throughout the system:

## 1. Transcription/Processing Charge

**Location:** `backend/api/services/transcription/__init__.py`

**When:** Charged **AFTER successful transcription** (not upfront)
- **Rate:** 1 credit per second of audio
- **Auphonic add-on:** +1 credit per second if advanced audio processing is enabled
- **Episode ID:** `None` (transcription happens before episode is created)
- **Charged for:** Both Auphonic and AssemblyAI transcription paths
- **NOT charged if:** Transcription fails (failures are on us)

**Implementation:**
- Helper function `_charge_for_successful_transcription()` called after successful transcription
- Charged in two places:
  1. After Auphonic transcription succeeds (line ~615)
  2. After AssemblyAI transcription succeeds (line ~915)

## 2. Assembly Charge

**Location:** `backend/worker/tasks/assembly/orchestrator.py` (in `_finalize_episode()`)

**When:** Charged **AFTER assembly completes successfully**
- **Rate:** 3 credits per second of final episode duration
- **Episode ID:** Set (episode exists at this point)
- **Based on:** Final episode duration (`episode.duration_ms / 1000.0`)

**Implementation:**
- Called in `_finalize_episode()` after episode is successfully assembled
- Uses `credits.charge_for_assembly()` function

## 3. TTS Generation Charge

**Location:** `backend/api/routers/media_tts.py`

**When:** Charged **AFTER TTS audio is successfully generated**
- **Google TTS (standard):** 1 credit per second (no rounding)
  - Provider: `"google"` 
  - ⚠️ **NOT YET IMPLEMENTED** - Currently raises error if used
- **ElevenLabs TTS:** Plan-based rate per second (rounded up to next whole second)
  - Provider: `"elevenlabs"` (default)
  - Starter: 15 credits/sec
  - Creator: 14 credits/sec
  - Pro: 13 credits/sec
  - Executive: 12 credits/sec
  - Enterprise: 12 credits/sec
- **Batch TTS:** Sums all durations first, then rounds up (ElevenLabs only)

**Provider Selection Mechanism:**
- Users choose provider via `provider` field in TTS request body (`"elevenlabs"` or `"google"`)
- Default is `"elevenlabs"` if not specified
- `/api/users/me/capabilities` endpoint indicates availability:
  - `has_elevenlabs`: True if user has `elevenlabs_api_key` OR global `ELEVENLABS_API_KEY` exists
  - `has_google_tts`: True if Google TTS module available (currently always False - not implemented)
- Tier config has `tts_provider` feature ("standard" or "elevenlabs") but it's not enforced at API level
- **Current state:** Only ElevenLabs TTS works; Google TTS raises "not yet implemented" error

**Implementation:**
- Charged after audio file is successfully created
- Uses `credits.charge_for_tts_generation()` or `credits.charge_for_tts_batch()`
- Provider determined by `body.provider` field in request

## 4. Overlength Surcharge

**Location:** `backend/api/services/billing/overlength.py`

**When:** Charged if episode exceeds plan `max_minutes` limit
- **Rate:** 1 credit per second for portion beyond plan limit
- **Plan Limits:**
  - Starter: 40 minutes max (hard cap - episodes over 40 min are blocked)
  - Creator: 80 minutes max (surcharge applies if exceeded)
  - Pro: 120 minutes max (surcharge applies if exceeded)
  - Executive+: 240+ minutes (no surcharge, allowed)
- **Example:** Creator plan (80 min max), 90 min episode = 10 min × 60 sec × 1 credit/sec = 600 credits surcharge

**Implementation:**
- ⚠️ **ISSUE FOUND:** Function `apply_overlength_surcharge()` exists but is **NOT being called anywhere** in the codebase
- Should be called after episode duration is known (in `_finalize_episode()` after assembly completes)
- Currently, overlength episodes may be processed without the surcharge being applied
- Starter plan allows up to 40 minutes (not blocked); only episodes exceeding 40 minutes are blocked

## 5. AI Metadata Generation Charge

**Location:** `backend/api/routers/ai_suggestions.py`

**When:** Charged **AFTER AI successfully generates metadata**
- **Charged for:** Title, description, tags generation
- **Rate:** Plan-based (see `get_ai_metadata_rate()` in `backend/api/billing/plans.py`)

**Implementation:**
- Uses `credits.charge_for_ai_metadata()` function
- Charged separately for each metadata type generated

## 6. Storage Charge

**Location:** `backend/api/services/billing/credits.py`

**When:** Monthly storage usage charge
- **Rate:** 2 credits per GB per month
- **Implementation:** `charge_for_storage()` function exists but needs verification of when it's called

## Wallet Debit Order

When `charge_credits()` is called, it debits from wallet in this order:
1. Monthly allocation credits (from subscription)
2. Rollover credits (10% of unused monthly credits)
3. Purchased credits (one-time purchases)

## Idempotency

All charges support `correlation_id` for idempotency:
- If a charge with the same `correlation_id` already exists, it returns the existing entry
- Prevents double-charging on retries

## Summary of Charge Timing

1. **Transcription:** AFTER success ✅ (FIXED - was charging upfront)
2. **Assembly:** AFTER completion ✅
3. **TTS:** AFTER generation ✅
4. **Overlength:** ⚠️ **NOT IMPLEMENTED** - Function exists but is never called
5. **AI Metadata:** AFTER generation ✅
6. **Storage:** Needs verification ⚠️

## Notes

- **Double charge is intentional:** Users are charged separately for transcription (1 credit/sec) and assembly (3 credits/sec). This allows users to delete files before assembly without paying assembly costs.
- **Transcription failures:** Users are NOT charged if transcription fails (failures are on us).
- **Deletion:** Users are charged for transcription even if they delete the file later (they used the service).

