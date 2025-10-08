# ✅ Stripe Live Migration Checklist

Print this out or keep it open while migrating!

## 📋 Pre-Flight Checklist

- [ ] **Backup current database** (just in case)
- [ ] **Note current subscriber count** (for comparison)
- [ ] **Test in test mode first** (always!)
- [ ] **Review documentation** (STRIPE_QUICK_REFERENCE.md)

---

## 🔑 Step 1: Get Stripe Live Keys (5 minutes)

- [ ] Login to https://dashboard.stripe.com/
- [ ] **Switch to "Live Mode"** (toggle in top-right corner)
- [ ] Go to Developers → API Keys
- [ ] **Copy Secret Key** (`sk_live_...`)
  - Save to: `_____________________________________`
- [ ] **Copy Publishable Key** (`pk_live_...`)
  - Save to: `_____________________________________`
- [ ] Go to Developers → Webhooks
- [ ] Click "Add endpoint"
- [ ] **Endpoint URL**: `https://app.podcastplusplus.com/api/billing/webhook`
- [ ] Select events:
  - [ ] `customer.subscription.created`
  - [ ] `customer.subscription.updated`
  - [ ] `customer.subscription.deleted`
  - [ ] `invoice.payment_succeeded`
  - [ ] `invoice.payment_failed`
- [ ] Click "Add endpoint"
- [ ] **Copy Webhook Secret** (`whsec_...`)
  - Save to: `_____________________________________`

---

## 🏗️ Step 2: Create Products & Prices (2 minutes)

- [ ] Open PowerShell
- [ ] Navigate to project: `cd D:\PodWebDeploy`
- [ ] Activate virtual environment: `.\.venv\Scripts\Activate.ps1`
- [ ] Set live key: `$env:STRIPE_LIVE_SECRET_KEY="sk_live_YOUR_KEY"`
- [ ] Run setup: `python scripts/stripe_setup.py --mode live`
- [ ] **Copy the output** (price IDs):
  ```
  PRICE_PRO_MONTHLY=_____________________
  PRICE_PRO_ANNUAL=______________________
  PRICE_CREATOR_MONTHLY=_________________
  PRICE_CREATOR_ANNUAL=__________________
  ```

---

## ☁️ Step 3: Add Secrets to Google Cloud (10 minutes)

### Set Stripe Keys
- [ ] Secret Key:
  ```powershell
  echo "sk_live_YOUR_KEY" | gcloud secrets versions add STRIPE_SECRET_KEY --data-file=- --project=podcast612
  ```
- [ ] Publishable Key:
  ```powershell
  echo "pk_live_YOUR_KEY" | gcloud secrets versions add STRIPE_PUBLISHABLE_KEY --data-file=- --project=podcast612
  ```
- [ ] Webhook Secret:
  ```powershell
  echo "whsec_YOUR_SECRET" | gcloud secrets versions add STRIPE_WEBHOOK_SECRET --data-file=- --project=podcast612
  ```

### Set Price IDs (from Step 2)
- [ ] Pro Monthly:
  ```powershell
  echo "price_XXX" | gcloud secrets create PRICE_PRO_MONTHLY --data-file=- --project=podcast612
  ```
- [ ] Pro Annual:
  ```powershell
  echo "price_XXX" | gcloud secrets create PRICE_PRO_ANNUAL --data-file=- --project=podcast612
  ```
- [ ] Creator Monthly:
  ```powershell
  echo "price_XXX" | gcloud secrets create PRICE_CREATOR_MONTHLY --data-file=- --project=podcast612
  ```
- [ ] Creator Annual:
  ```powershell
  echo "price_XXX" | gcloud secrets create PRICE_CREATOR_ANNUAL --data-file=- --project=podcast612
  ```

---

## 🎨 Step 4: Configure Customer Portal (3 minutes)

- [ ] Go to https://dashboard.stripe.com/settings/billing/portal
- [ ] Ensure you're in **Live Mode**
- [ ] Click "Activate" (if not already activated)
- [ ] Configuration:
  - [ ] Enable "Customers can cancel subscriptions"
  - [ ] Enable "Customers can switch plans"
  - [ ] Enable "Customers can update payment methods"
- [ ] Add products:
  - [ ] Add "Podcast++ Pro"
  - [ ] Add "Podcast++ Creator"
- [ ] Click "Save changes"

---

## 💻 Step 5: Install Dependencies & Deploy (10 minutes)

### Install Frontend Dependencies
- [ ] `cd frontend`
- [ ] `npm install`
- [ ] Verify `@stripe/stripe-js` installed
- [ ] Verify `@stripe/react-stripe-js` installed
- [ ] `cd ..`

### Validate Configuration (Optional but Recommended)
- [ ] `python scripts/check_stripe_config.py`
- [ ] All checks should pass ✅

### Deploy
- [ ] `gcloud builds submit --config=cloudbuild.yaml --project=podcast612`
- [ ] Wait for build to complete
- [ ] Note the Cloud Run URL: `_____________________________________`

---

## 🧪 Step 6: Test in Production (15 minutes)

### Initial Smoke Test
- [ ] Visit https://app.podcastplusplus.com/billing
- [ ] Page loads without errors
- [ ] "Subscribe" buttons visible

### Test Embedded Checkout
- [ ] Click "Subscribe to Pro"
- [ ] Embedded checkout appears (NO redirect!)
- [ ] Checkout form loads properly
- [ ] Stripe logo visible at bottom

### Complete Test Purchase
⚠️ **WARNING**: This creates a REAL subscription with a REAL charge!

- [ ] Enter test card: `4242 4242 4242 4242`
- [ ] Expiry: `12/34`
- [ ] CVC: `123`
- [ ] ZIP: `12345`
- [ ] Click "Subscribe"
- [ ] Wait for processing
- [ ] Success message appears
- [ ] User tier updates to "Pro"
- [ ] Usage limits reflect Pro tier

### Verify Backend
- [ ] Check Stripe dashboard for new subscription
- [ ] Go to Dashboard → Payments
- [ ] See successful payment
- [ ] Check customer details

### Verify Webhooks
- [ ] Go to Developers → Webhooks
- [ ] Click your webhook endpoint
- [ ] See recent events
- [ ] Events show as "succeeded"
- [ ] No delivery failures

### Test Customer Portal
- [ ] On billing page, click "Manage Subscription"
- [ ] Portal opens (new tab)
- [ ] Can view subscription details
- [ ] Can update payment method
- [ ] Can cancel subscription (don't actually cancel yet!)

### Cancel Test Subscription
- [ ] In Stripe dashboard, find test subscription
- [ ] Cancel it
- [ ] Wait 30 seconds
- [ ] Refresh billing page
- [ ] Tier should revert to "Free"
- [ ] Webhook event received

---

## 📊 Step 7: Monitor (24 hours)

### Immediate (First Hour)
- [ ] Check error logs for issues
- [ ] Monitor webhook delivery rate
- [ ] Watch for failed payments
- [ ] Verify new signups work

### Short Term (First Day)
- [ ] Check subscription count matches Stripe
- [ ] Monitor conversion rates
- [ ] Review any user-reported issues
- [ ] Check webhook success rate (should be >99%)

### Medium Term (First Week)
- [ ] Review first renewal cycle
- [ ] Check proration accuracy
- [ ] Monitor upgrade/downgrade flows
- [ ] Review cancellation flow

---

## 🚨 Rollback Plan (If Needed)

If something goes wrong:

- [ ] **Option 1**: Switch back to test keys temporarily
  ```powershell
  echo "sk_test_YOUR_OLD_KEY" | gcloud secrets versions add STRIPE_SECRET_KEY --data-file=- --project=podcast612
  ```

- [ ] **Option 2**: Revert frontend to old checkout
  - Change import back to `BillingPage` (not `BillingPageEmbedded`)
  - Deploy: `gcloud builds submit --config=cloudbuild.yaml --project=podcast612`

- [ ] **Option 3**: Disable Stripe temporarily
  - Comment out billing routes in `routing.py`
  - Deploy

---

## ✅ Success Criteria

You know it's working when:
- [ ] Users can subscribe without leaving your site
- [ ] Embedded checkout appears (no Stripe redirect)
- [ ] Payments process successfully
- [ ] User tiers update immediately
- [ ] Webhooks show as "succeeded" in dashboard
- [ ] Customer portal is accessible
- [ ] No errors in application logs
- [ ] Stripe dashboard shows live subscriptions

---

## 📞 Support Resources

If you need help:

1. **Check the guides**:
   - Quick reference: `STRIPE_QUICK_REFERENCE.md`
   - Detailed guide: `STRIPE_LIVE_MIGRATION_GUIDE.md`

2. **Run diagnostic tools**:
   - `python scripts/check_stripe_config.py`
   - `python scripts/test_stripe_endpoints.py`

3. **Check Stripe Dashboard**:
   - Events log: https://dashboard.stripe.com/events
   - Webhook logs: https://dashboard.stripe.com/webhooks
   - Payment logs: https://dashboard.stripe.com/payments

4. **Review logs**:
   - Cloud Run logs in Google Cloud Console
   - Browser console for frontend errors
   - Network tab for API calls

---

## 🎉 Post-Migration

After successful migration:
- [ ] Document live keys location (secret manager)
- [ ] Update team on new checkout flow
- [ ] Monitor for 48 hours
- [ ] Review conversion metrics vs old flow
- [ ] Celebrate! 🎊

---

**Date Started**: _______________
**Date Completed**: _______________
**Notes**: 

_______________________________________________
_______________________________________________
_______________________________________________
_______________________________________________
