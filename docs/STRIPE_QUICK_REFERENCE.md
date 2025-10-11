# Stripe Integration - Quick Reference

## 🎯 What Was Done

### Backend (Python/FastAPI)
- ✅ Added `STRIPE_PUBLISHABLE_KEY` to settings
- ✅ Created `/api/billing/config` endpoint (returns publishable key)
- ✅ Created `/api/billing/checkout/embedded` endpoint (returns client_secret)
- ✅ Updated `/api/billing/checkout` to use `ui_mode: 'embedded'`
- ✅ Created automated product/price setup script

### Frontend (React)
- ✅ Created `BillingPageEmbedded.jsx` with Stripe.js integration
- ✅ Added `@stripe/stripe-js` and `@stripe/react-stripe-js` dependencies
- ✅ Embedded checkout - no redirect, stays on your domain
- ✅ Full UI control and customization

### Infrastructure
- ✅ Updated Cloud Build to require `STRIPE_PUBLISHABLE_KEY` secret
- ✅ Updated environment restore scripts
- ✅ Created comprehensive migration guide

## 📋 Quick Start Checklist

### 1️⃣ Get Stripe Keys (5 min)
- [ ] Login to https://dashboard.stripe.com/
- [ ] Switch to Live Mode
- [ ] Copy Secret Key (sk_live_...)
- [ ] Copy Publishable Key (pk_live_...)

### 2️⃣ Create Products & Prices (2 min)
```powershell
# Set your live key
$env:STRIPE_LIVE_SECRET_KEY="sk_live_YOUR_KEY"

# Run setup
python scripts/stripe_setup.py --mode live
```

### 3️⃣ Configure Webhook (3 min)
- [ ] Go to https://dashboard.stripe.com/webhooks
- [ ] Add endpoint: `https://app.podcastplusplus.com/api/billing/webhook`
- [ ] Select events: customer.subscription.* and invoice.*
- [ ] Copy webhook secret (whsec_...)

### 4️⃣ Set Environment Variables (5 min)
```powershell
# Add to Google Cloud Secret Manager
echo "sk_live_XXX" | gcloud secrets versions add STRIPE_SECRET_KEY --data-file=- --project=podcast612
echo "pk_live_XXX" | gcloud secrets versions add STRIPE_PUBLISHABLE_KEY --data-file=- --project=podcast612
echo "whsec_XXX" | gcloud secrets versions add STRIPE_WEBHOOK_SECRET --data-file=- --project=podcast612

# Add price IDs (from step 2 output)
echo "price_XXX" | gcloud secrets create PRICE_PRO_MONTHLY --data-file=- --project=podcast612
echo "price_XXX" | gcloud secrets create PRICE_PRO_ANNUAL --data-file=- --project=podcast612
echo "price_XXX" | gcloud secrets create PRICE_CREATOR_MONTHLY --data-file=- --project=podcast612
echo "price_XXX" | gcloud secrets create PRICE_CREATOR_ANNUAL --data-file=- --project=podcast612
```

### 5️⃣ Install Frontend Dependencies (1 min)
```powershell
cd frontend
npm install
```

### 6️⃣ Configure Customer Portal (2 min)
- [ ] Go to https://dashboard.stripe.com/settings/billing/portal
- [ ] Click "Activate"
- [ ] Enable subscription cancellation
- [ ] Add your products
- [ ] Save changes

### 7️⃣ Deploy (5 min)
```powershell
# Build and deploy
gcloud builds submit --config=cloudbuild.yaml --project=podcast612
```

### 8️⃣ Test (10 min)
- [ ] Visit billing page
- [ ] Click subscribe
- [ ] Embedded checkout appears (no redirect!)
- [ ] Complete payment with test card
- [ ] Verify tier updates
- [ ] Check webhook events in Stripe dashboard

## 🔑 Environment Variables Reference

### Required for Live Mode
```bash
# Stripe Keys
STRIPE_SECRET_KEY=sk_live_YOUR_SECRET_KEY
STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET

# Price IDs (from stripe_setup.py output)
PRICE_PRO_MONTHLY=price_abc123
PRICE_PRO_ANNUAL=price_def456
PRICE_CREATOR_MONTHLY=price_ghi789
PRICE_CREATOR_ANNUAL=price_jkl012
```

## 🚀 API Endpoints

### New Endpoints
- `GET /api/billing/config` - Returns Stripe publishable key
- `POST /api/billing/checkout/embedded` - Creates embedded checkout session

### Updated Endpoints
- `POST /api/billing/checkout` - Now uses `ui_mode: 'embedded'`

### Request Example
```javascript
// Get config
const config = await fetch('/api/billing/config');
// { publishable_key: "pk_live_...", mode: "live" }

// Create checkout session
const session = await fetch('/api/billing/checkout/embedded', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({
    plan_key: 'pro',
    billing_cycle: 'monthly',
    success_path: '/billing',
    cancel_path: '/billing'
  })
});
// { client_secret: "cs_test_...", session_id: "cs_..." }
```

## 📦 Products & Pricing

### Pro Plan
- **Monthly**: $19/month
- **Annual**: $190/year (save ~17%)
- **Features**: Unlimited episodes, AI enhancement, priority processing, branding, analytics

### Creator Plan
- **Monthly**: $49/month
- **Annual**: $490/year (save ~17%)
- **Features**: Everything in Pro + unlimited minutes, AI voice training, white-label, support, API

## 🧪 Testing

### Test Cards (Test Mode Only)
- Success: `4242 4242 4242 4242`
- Requires Auth: `4000 0025 0000 3155`
- Declined: `4000 0000 0000 9995`

### Live Testing
⚠️ Use real card - creates real charges!
- Test with small amount first
- Cancel immediately if needed
- Monitor Stripe dashboard

## 🔧 Troubleshooting

### "Stripe not configured"
→ Check `STRIPE_SECRET_KEY` is set and starts with `sk_live_`

### "Invalid publishable key"
→ Ensure `STRIPE_PUBLISHABLE_KEY` matches your secret key mode (both live or both test)

### Checkout not loading
→ Check browser console for errors
→ Verify Stripe.js dependencies installed (`npm install`)

### Webhook not receiving events
→ Check webhook URL is correct
→ Verify webhook secret matches
→ Look in Stripe dashboard > Webhooks for delivery attempts

### Customer portal "not configured"
→ Must configure portal separately in live mode
→ Visit https://dashboard.stripe.com/settings/billing/portal

## 📚 Documentation Links

- **Full Migration Guide**: `STRIPE_LIVE_MIGRATION_GUIDE.md`
- **Stripe Docs**: https://docs.stripe.com/billing/subscriptions/build-subscriptions
- **Test Cards**: https://docs.stripe.com/testing
- **Webhooks**: https://docs.stripe.com/webhooks

## 🎨 UI Changes

### Before (Redirect Checkout)
1. User clicks "Subscribe"
2. Redirected to Stripe's domain
3. Completes payment on Stripe
4. Redirected back to your site

### After (Embedded Checkout)
1. User clicks "Subscribe"
2. Checkout form appears on YOUR site
3. Completes payment without leaving
4. Success message shown immediately

**Benefits**: Better UX, higher conversion, full branding control!

## 💡 Pro Tips

1. **Test First**: Always test in test mode before going live
2. **Monitor Webhooks**: Check Stripe dashboard for webhook delivery
3. **Log Everything**: Enable detailed logging for debugging
4. **Graceful Degradation**: Keep old checkout as fallback
5. **Customer Communication**: Notify users about improved checkout experience

## 🆘 Need Help?

1. Check `STRIPE_LIVE_MIGRATION_GUIDE.md` for detailed steps
2. Review Stripe dashboard event logs
3. Check application logs for errors
4. Verify all environment variables are set
5. Test webhook delivery manually from Stripe dashboard

---

**Remember**: Test mode and live mode are completely separate in Stripe. Always test thoroughly in test mode before switching to live!
