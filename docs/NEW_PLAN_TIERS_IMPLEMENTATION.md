# New Plan Tiers, Credits, and Debit Rules - Implementation Summary

## Overview

This document summarizes the implementation of new plan tiers, credit system, and debit rules while keeping Stripe integration intact.

## Implementation Status

### ✅ Completed

1. **Plan Definitions** (`backend/api/billing/plans.py`)
   - Added Executive tier ($129/month, 288,000 credits, 240 min max)
   - Updated all plan definitions with new credit amounts and limits
   - Added analytics levels (basic, advanced, full)
   - Added queue priority system
   - Added overlength handling rules

2. **Stripe Setup** (`scripts/stripe_setup.py`)
   - Added Executive tier product and prices (monthly + annual)
   - Updated plan descriptions to reflect credit-based system
   - Kept Enterprise as contact-only (no price)

3. **Credit Wallet System** (`backend/api/models/wallet.py`, `backend/api/services/billing/wallet.py`)
   - Created `CreditWallet` model for tracking credits per billing period
   - Tracks: monthly_credits, rollover_credits, purchased_credits
   - Tracks usage: used_monthly_rollover, used_purchased
   - Implements debit ordering: monthly+rollover first, then purchased
   - Rollover logic: 10% of unused monthly+rollover credits (capped at monthly_credits)

4. **Credit Debit System** (`backend/api/services/billing/credits.py`)
   - Updated to use wallet system for debit ordering
   - New rates:
     - Processing: 1 credit/sec
     - Assembly: 3 credits/sec
     - Auphonic add-on: 1 credit/sec (configurable via AUPHONIC_CREDITS_PER_SEC)
     - Overlength surcharge: 1 credit/sec for portion beyond plan cap
   - ElevenLabs TTS: rounds up to next whole second (e.g., 3.2s → 4s)
   - Per-plan ElevenLabs rates: Starter 15 c/s, Creator 14, Pro 13, Executive 12

5. **Activity Billing Hooks**
   - `charge_for_transcription()`: Uses seconds, applies processing + Auphonic rates
   - `charge_for_assembly()`: Uses seconds, applies assembly rate
   - `charge_for_tts_generation()`: Implements ElevenLabs rounding logic
   - All hooks use wallet debit system

6. **Overlength Surcharge** (`backend/api/services/billing/overlength.py`)
   - Starter: Hard block at 40 min limit
   - Creator/Pro: Allow with surcharge (1 credit/sec for portion beyond limit)
   - Executive/Enterprise/Unlimited: No surcharge, allowed

7. **Analytics Gating** (`backend/api/routers/analytics.py`)
   - Added `assert_analytics_access()` helper
   - Starter: basic analytics
   - Creator: advanced analytics
   - Pro/Executive: full analytics
   - All analytics endpoints now check access level

8. **Unlimited Plan Handling**
   - Bypasses credit checks but still logs usage
   - Returns 999,999 credits for balance checks
   - Wallet debit still tracks usage for reporting

9. **Database Migration** (`backend/migrations/032_add_credit_wallet.py`)
   - Creates `creditwallet` table
   - Adds indexes for user_id and period

### ⚠️ Pending/Notes

1. **Queue Priority**
   - Plan priority system defined in `plans.py`
   - Priority values: Starter=1, Creator=2, Pro=3, Executive=4, Enterprise=5, Unlimited=6
   - **TODO**: Implement priority in task dispatcher/Cloud Tasks configuration
   - Jobs should persist priority field for queue sorting

2. **Billing Router Updates**
   - `backend/api/routers/billing.py` may need updates to use new plans
   - Should reference `api.billing.plans` instead of hard-coded constants

3. **Activity Hook Integration**
   - Need to update call sites to use seconds instead of minutes:
     - Transcription completion hooks
     - Assembly completion hooks
     - TTS generation hooks
   - Need to add overlength surcharge calls at upload/job start

4. **Period Rollover Job** ✅
   - Created `process_monthly_rollover()` in `api.services.billing.wallet`
   - HTTP endpoint: `POST /internal/billing/rollover`
   - Protected with OIDC token, admin auth, or TASKS_AUTH header
   - Idempotency via `WalletPeriodProcessed` table
   - Cloud Scheduler: Run monthly at 00:05 UTC on 1st of month
   - See Cloud Scheduler setup below

5. **Auphonic Add-on**
   - Note: Auphonic Pro Path will move to yes/no question on upload
   - All tiers have option to use it (adds 1 credit/sec)
   - Default: no (first time), then remember last choice

## Plan Definitions

| Plan | Price | Monthly Credits | Max Episode | Analytics | Priority |
|------|-------|----------------|-------------|-----------|----------|
| Starter | $19 | 28,800 | 40 min | basic | 1 |
| Creator | $39 | 72,000 | 80 min | advanced | 2 |
| Pro | $79 | 172,800 | 120 min | full | 3 |
| Executive | $129 | 288,000 | 240 min* | full | 4 |
| Enterprise | Contact | Contract | Contract | full | 5 |
| Unlimited | Internal | Unlimited | Unlimited | full | 6 |

*Executive allows manual override of max_minutes

## Credit Rates

- **Processing**: 1 credit/second
- **Assembly**: 3 credits/second
- **Auphonic add-on**: 1 credit/second (configurable, default 1)
- **ElevenLabs TTS**: Plan-specific rates (12-15 credits/second)
- **Overlength surcharge**: 1 credit/second for portion beyond plan cap

## Debit Order

1. Monthly credits + rollover credits (first)
2. Purchased credits (last)

Purchased credits never expire and are transferable.

## Rollover Rules

- Up to 10% of unused monthly+rollover credits roll over
- Capped at monthly_credits amount
- Processed at start of new billing period

## Files Created/Modified

### New Files
- `backend/api/billing/plans.py` - Plan definitions and constants
- `backend/api/models/wallet.py` - Credit wallet model
- `backend/api/services/billing/wallet.py` - Wallet service
- `backend/api/services/billing/overlength.py` - Overlength surcharge logic
- `backend/migrations/032_add_credit_wallet.py` - Wallet table migration

### Modified Files
- `scripts/stripe_setup.py` - Added Executive tier
- `backend/api/services/billing/credits.py` - Updated to use wallet and new rates
- `backend/api/routers/analytics.py` - Added analytics gating

## Testing Checklist

- [ ] Unit tests for debit ordering (monthly+rollover first, then purchased)
- [ ] Unit tests for ElevenLabs rounding (3.2s → 4s)
- [ ] API tests for overlength: Starter blocked at 40 min
- [ ] API tests for overlength: Creator/Pro billed surcharge
- [ ] API tests for overlength: Executive allowed
- [ ] Analytics endpoint tests for gating (Starter=basic, Creator=advanced, Pro/Executive=full)
- [ ] Wallet rollover calculation tests
- [ ] Unlimited plan bypass tests (still logs usage)

## Next Steps

1. Update activity hook call sites to use seconds
2. Add overlength checks at upload/job start
3. Implement queue priority in task dispatcher
4. Create period rollover scheduled job
5. ~~Update billing router to use new plans~~ ✅ Done
6. Run migration to create wallet table
7. Test end-to-end credit flow
8. Run `stripe_setup.py --mode live` to create Executive products in Stripe
9. Add Executive price IDs to Google Cloud Secret Manager
10. Set up Cloud Scheduler for monthly rollover (see below)

## Cloud Scheduler Setup for Monthly Rollover

The monthly credit rollover job runs automatically via Cloud Scheduler. Set it up with:

```bash
gcloud scheduler jobs create http credit-rollover \
  --schedule="5 0 1 * *" \
  --uri="https://api.podcastplusplus.com/internal/billing/rollover" \
  --http-method=POST \
  --oidc-service-account-email=<scheduler-sa>@<project>.iam.gserviceaccount.com \
  --oidc-token-audience="https://api.podcastplusplus.com" \
  --location=us-west1
```

**Schedule**: `5 0 1 * *` means "5 minutes past midnight UTC on the 1st of every month"

**Authentication**: Uses OIDC service account token. The endpoint also accepts:
- Admin JWT tokens (for manual testing)
- `X-Tasks-Auth` header (legacy, matches `TASKS_AUTH` env var)

**Idempotency**: The endpoint automatically prevents double-processing the same period. If a period has already been processed, it returns `{"status": "already_processed"}`.

