# Stripe Executive Tier - Setup Guide

## Overview

The Executive tier has been added to the Stripe setup script. This guide covers how to create the Executive products and prices in Stripe.

## What Was Updated

### Files Modified
- `scripts/stripe_setup.py` - Added Executive tier with monthly ($129) and annual ($1,285) pricing
- `backend/api/routers/billing.py` - Added Executive to PRICE_MAP
- `docs/STRIPE_SETUP_EXPLAINED.md` - Updated product list
- `docs/STRIPE_INDEX.md` - Updated pricing table

### Executive Tier Details
- **Monthly**: $129/month (`PRICE_EXECUTIVE_MONTHLY`)
- **Annual**: $1,285/year (`PRICE_EXECUTIVE_ANNUAL`) - saves ~17%
- **Features**: 288,000 credits/month, 240 min max episode (override allowed), full analytics, priority queue

## Setup Instructions

### Step 1: Run Stripe Setup Script

```powershell
# For test mode (recommended first)
$env:STRIPE_SECRET_KEY="sk_test_YOUR_KEY"
python scripts/stripe_setup.py --mode test

# For live mode (production)
$env:STRIPE_LIVE_SECRET_KEY="sk_live_YOUR_KEY"
python scripts/stripe_setup.py --mode live
```

### Step 2: Copy Price IDs

The script will output price IDs like:
```
PRICE_EXECUTIVE_MONTHLY=price_abc123...
PRICE_EXECUTIVE_ANNUAL=price_def456...
```

These will also be saved to `backend/.env.stripe`.

### Step 3: Add to Google Cloud Secret Manager

```powershell
# Executive monthly price
echo "price_abc123..." | gcloud secrets create PRICE_EXECUTIVE_MONTHLY --data-file=- --project=podcast612

# Executive annual price
echo "price_def456..." | gcloud secrets create PRICE_EXECUTIVE_ANNUAL --data-file=- --project=podcast612
```

Or if secrets already exist:
```powershell
echo "price_abc123..." | gcloud secrets versions add PRICE_EXECUTIVE_MONTHLY --data-file=- --project=podcast612
echo "price_def456..." | gcloud secrets versions add PRICE_EXECUTIVE_ANNUAL --data-file=- --project=podcast612
```

## Verification

After setup, verify the products exist in Stripe:

1. Go to Stripe Dashboard → Products
2. Look for "Podcast Plus Plus Executive"
3. Verify both monthly and annual prices exist
4. Check that lookup keys match: `executive_monthly` and `executive_annual`

## Environment Variables

After setup, ensure these are set in Google Cloud:

```bash
PRICE_STARTER_MONTHLY
PRICE_STARTER_ANNUAL
PRICE_CREATOR_MONTHLY
PRICE_CREATOR_ANNUAL
PRICE_PRO_MONTHLY
PRICE_PRO_ANNUAL
PRICE_EXECUTIVE_MONTHLY    # NEW
PRICE_EXECUTIVE_ANNUAL     # NEW
```

## Testing

1. **Test Mode**: Use test cards to verify checkout flow
2. **Live Mode**: Test with real card (will charge!)
3. **Verify**: Check that Executive tier appears in billing page
4. **Checkout**: Complete a test subscription to Executive tier

## Notes

- Enterprise tier remains contact-only (no Stripe products/prices)
- Executive annual pricing follows the same ~17% savings pattern as other tiers
- All tiers now use credit-based system (see `NEW_PLAN_TIERS_IMPLEMENTATION.md`)

## Related Documentation

- [Stripe Setup Explained](STRIPE_SETUP_EXPLAINED.md) - Complete setup guide
- [Stripe Index](STRIPE_INDEX.md) - All Stripe documentation
- [New Plan Tiers Implementation](NEW_PLAN_TIERS_IMPLEMENTATION.md) - Credit system details

