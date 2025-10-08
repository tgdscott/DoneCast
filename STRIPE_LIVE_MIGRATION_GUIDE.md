# Stripe Live Migration Guide

## Overview
This guide walks you through migrating from Stripe test mode to live mode with embedded checkout components fully integrated into your site.

## What's Been Implemented

### ✅ Backend Changes
1. **Added Stripe Publishable Key Support** (`config.py`)
   - New `STRIPE_PUBLISHABLE_KEY` setting for frontend
   
2. **New Billing Config Endpoint** (`billing_config.py`)
   - `GET /api/billing/config` - Returns publishable key to frontend
   - Safe to expose publicly (publishable keys are designed for this)

3. **Embedded Checkout Support** (`billing.py`)
   - `POST /api/billing/checkout/embedded` - Returns client_secret for embedded checkout
   - Updated existing checkout to use `ui_mode: 'embedded'`
   - Maintains all existing proration/upgrade logic

4. **Product/Price Setup Script** (`scripts/stripe_setup.py`)
   - Automatically creates products and prices via Stripe API
   - Generates environment variables for price IDs
   - Supports both test and live modes

### ✅ Frontend Changes
1. **New Embedded Billing Page** (`BillingPageEmbedded.jsx`)
   - Uses Stripe.js and `@stripe/react-stripe-js` 
   - Embedded checkout components (no redirect to Stripe)
   - Full UI control on your domain
   - Maintains existing features (usage display, portal access, etc.)

## Migration Steps

### Step 1: Get Your Live Stripe Keys

1. **Log into Stripe Dashboard**: https://dashboard.stripe.com/
2. **Switch to Live Mode** (toggle in top right)
3. **Get API Keys**: https://dashboard.stripe.com/apikeys
   - Copy your **Secret Key** (starts with `sk_live_`)
   - Copy your **Publishable Key** (starts with `pk_live_`)
4. **Get Webhook Secret** (we'll set this up in Step 3)

### Step 2: Set Up Products & Prices (Automated!)

You can create products/prices automatically via API:

```powershell
# Activate your virtual environment
.\.venv\Scripts\Activate.ps1

# First, set your live secret key temporarily (or add to .env.local as STRIPE_LIVE_SECRET_KEY)
$env:STRIPE_LIVE_SECRET_KEY="sk_live_YOUR_KEY_HERE"

# Run setup script in LIVE mode
python scripts/stripe_setup.py --mode live
```

This will:
- ✅ Create "Podcast++ Pro" product with monthly ($19) and annual ($190) prices
- ✅ Create "Podcast++ Creator" product with monthly ($49) and annual ($490) prices
- ✅ Generate a `.env.stripe` file with all price IDs
- ✅ Display environment variables you need to set

**Output Example:**
```
PRICE_PRO_MONTHLY=price_abc123xyz
PRICE_PRO_ANNUAL=price_def456uvw
PRICE_CREATOR_MONTHLY=price_ghi789rst
PRICE_CREATOR_ANNUAL=price_jkl012mno
```

**Alternative: Manual Setup**
If you prefer to create products manually:
1. Go to https://dashboard.stripe.com/products
2. Create products and note their price IDs
3. Use lookup_keys for easier management (optional but recommended)

### Step 3: Configure Webhook

1. Go to https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. **Endpoint URL**: `https://app.podcastplusplus.com/api/billing/webhook`
4. **Events to listen to**:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Click "Add endpoint"
6. **Copy the Signing Secret** (starts with `whsec_`)

### Step 4: Update Environment Variables

You need to add these to your production environment (Google Cloud Secret Manager):

```bash
# Stripe Keys
STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_LIVE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET

# Price IDs (from Step 2)
PRICE_PRO_MONTHLY=price_YOUR_PRO_MONTHLY_ID
PRICE_PRO_ANNUAL=price_YOUR_PRO_ANNUAL_ID
PRICE_CREATOR_MONTHLY=price_YOUR_CREATOR_MONTHLY_ID
PRICE_CREATOR_ANNUAL=price_YOUR_CREATOR_ANNUAL_ID
```

#### Update Google Cloud Secrets:

```powershell
# Set Stripe keys
gcloud secrets versions add STRIPE_SECRET_KEY --data-file=- --project=podcast612
# (paste your sk_live_ key and press Ctrl+D)

gcloud secrets versions add STRIPE_PUBLISHABLE_KEY --data-file=- --project=podcast612
# (paste your pk_live_ key and press Ctrl+D)

gcloud secrets versions add STRIPE_WEBHOOK_SECRET --data-file=- --project=podcast612
# (paste your whsec_ secret and press Ctrl+D)

# Set price IDs (create if they don't exist)
echo "price_YOUR_PRO_MONTHLY_ID" | gcloud secrets create PRICE_PRO_MONTHLY --data-file=- --project=podcast612
echo "price_YOUR_PRO_ANNUAL_ID" | gcloud secrets create PRICE_PRO_ANNUAL --data-file=- --project=podcast612
echo "price_YOUR_CREATOR_MONTHLY_ID" | gcloud secrets create PRICE_CREATOR_MONTHLY --data-file=- --project=podcast612
echo "price_YOUR_CREATOR_ANNUAL_ID" | gcloud secrets create PRICE_CREATOR_ANNUAL --data-file=- --project=podcast612
```

#### Update Cloud Run to Use Secrets:

Edit your `cloudrun-api-env.yaml` or deployment config to include:

```yaml
- name: STRIPE_PUBLISHABLE_KEY
  valueFrom:
    secretKeyRef:
      name: STRIPE_PUBLISHABLE_KEY
      key: latest

# Add PRICE_* environment variables as needed
```

### Step 5: Update Frontend to Use Embedded Checkout

#### Option A: Replace Existing Billing Page

Replace the import in your dashboard/router:

```jsx
// Before:
import BillingPage from '@/components/dashboard/BillingPage';

// After:
import BillingPage from '@/components/dashboard/BillingPageEmbedded';
```

#### Option B: Test Side-by-Side

Keep both and add a route/flag to test the new embedded version:

```jsx
// In your router
const showEmbedded = true; // or use feature flag

{showEmbedded ? (
  <BillingPageEmbedded token={token} onBack={handleBack} />
) : (
  <BillingPage token={token} onBack={handleBack} />
)}
```

### Step 6: Install Frontend Dependencies

The embedded checkout requires Stripe.js React components:

```powershell
cd frontend
npm install @stripe/stripe-js @stripe/react-stripe-js
```

### Step 7: Configure Stripe Customer Portal

For subscription management (cancel, update payment method, etc.):

1. Go to https://dashboard.stripe.com/settings/billing/portal
2. Click "Activate test link" or "Activate" (for live mode)
3. Configure:
   - ✅ Allow customers to cancel subscriptions
   - ✅ Allow customers to update payment methods
   - ✅ Show pricing table (optional)
   - Add your products (Pro & Creator)
4. **IMPORTANT**: Must configure in LIVE mode separately from test mode

### Step 8: Test in Production

1. **Deploy your changes**
2. **Test with live card** (use your own card first):
   - Card: 4242 4242 4242 4242
   - Expiry: Any future date
   - CVC: Any 3 digits
   - ZIP: Any valid ZIP

   ⚠️ **WARNING**: In live mode, this will create a REAL subscription with REAL charges!

3. **Verify webhook events**:
   - Go to https://dashboard.stripe.com/webhooks
   - Click your webhook endpoint
   - Check recent events - should see `customer.subscription.created`

4. **Check your database**:
   - User's `tier` should update
   - User's `subscription_expires_at` should be set
   - Entry in `subscription` table should exist

### Step 9: Monitor & Verify

- [ ] Webhooks are working (check Stripe dashboard)
- [ ] Subscriptions are being created successfully
- [ ] Users can access paid features
- [ ] Subscription renewals process correctly
- [ ] Cancellations work via customer portal
- [ ] Proration/upgrades calculate correctly

## Testing Checklist

### In Test Mode (Before Going Live)
- [ ] Products and prices created successfully
- [ ] Checkout flow works end-to-end
- [ ] Embedded checkout displays correctly
- [ ] Payment Element loads without errors
- [ ] Successful payment updates user tier
- [ ] Webhooks receive events
- [ ] Customer portal works
- [ ] Subscription cancellation works
- [ ] Upgrade/downgrade with proration works

### In Live Mode (Production)
- [ ] All environment variables set correctly
- [ ] Webhook endpoint configured and receiving events
- [ ] Test with real payment method
- [ ] Verify actual charge in Stripe dashboard
- [ ] Confirm user receives access to paid features
- [ ] Test customer portal in live mode
- [ ] Monitor for errors in logs

## Rollback Plan

If something goes wrong:

1. **Immediate**: Switch `STRIPE_SECRET_KEY` back to test key
2. **Frontend**: Revert to old `BillingPage.jsx` (non-embedded)
3. **Monitor**: Check webhook events and logs
4. **Fix**: Address issues in test mode before re-deploying

## Key Differences: Test vs Live

| Aspect | Test Mode | Live Mode |
|--------|-----------|-----------|
| API Keys | `sk_test_...` / `pk_test_...` | `sk_live_...` / `pk_live_...` |
| Payments | Fake cards, no real money | Real cards, real charges |
| Webhooks | Separate endpoints | Separate endpoints |
| Customer Portal | Separate config | Separate config |
| Products/Prices | Separate catalog | Separate catalog |

⚠️ **IMPORTANT**: Test and live modes are COMPLETELY separate in Stripe. Products, customers, subscriptions, etc. do not transfer between modes.

## Advantages of Embedded Checkout

✅ **Better UX**: Users never leave your site
✅ **Branding**: Full control over checkout appearance
✅ **Trust**: Customers see your domain, not Stripe's
✅ **Conversion**: Less friction = higher conversion rates
✅ **Customization**: Add custom messages, upsells, etc.

## Support & Resources

- **Stripe Docs**: https://docs.stripe.com/billing/subscriptions/build-subscriptions
- **Stripe Dashboard**: https://dashboard.stripe.com/
- **Test Cards**: https://docs.stripe.com/testing
- **Webhook Testing**: Use Stripe CLI in development

## Troubleshooting

### "Stripe not configured" Error
- Check that `STRIPE_SECRET_KEY` is set
- Verify it starts with `sk_live_` for production

### "Invalid client_secret" Error
- Check that `STRIPE_PUBLISHABLE_KEY` matches your secret key mode
- Verify both are from live mode (or both from test mode)

### Webhook Events Not Received
- Verify webhook URL is correct
- Check webhook signing secret matches
- Look for events in Stripe dashboard > Webhooks
- Check your application logs for errors

### Customer Portal Not Working
- Verify portal is configured in live mode
- Check that configuration is saved
- Ensure products are added to portal

### Payment Element Not Loading
- Check browser console for errors
- Verify `@stripe/stripe-js` and `@stripe/react-stripe-js` are installed
- Ensure publishable key is correctly loaded

---

**Questions or Issues?** Check the Stripe Dashboard's event logs and webhook delivery logs first - they're incredibly helpful for debugging!
