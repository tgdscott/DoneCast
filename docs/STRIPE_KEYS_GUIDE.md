# 🔑 Stripe Keys - Simple Guide

## What You Need from Stripe

You need **TWO keys** to get started (the 3rd comes after webhook setup):

---

## Step 1: Get Your API Keys

### Go to: https://dashboard.stripe.com/apikeys

You'll see a screen like this:

```
Publishable key
pk_live_51...xyz123                  [Reveal live key]

Secret key  
sk_live_••••••••••••••••••••         [Reveal live key]
```

### Copy These Two:

1. **Publishable Key** (already visible)
   - Starts with: `pk_live_...`
   - Just copy it directly
   
2. **Secret Key** (hidden)
   - Click the "Reveal live key" button
   - Copy the full value starting with `sk_live_...`
   - ⚠️ This is sensitive - keep it secret!

---

## Step 2: Add Keys to Your Environment

### Add to `backend/.env.local`:

```bash
# Stripe Configuration
STRIPE_SECRET_KEY=sk_live_YOUR_SECRET_KEY_HERE
STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_PUBLISHABLE_KEY_HERE
```

### Add to Google Cloud Secret Manager:

```powershell
# Set the secret key
gcloud secrets versions add STRIPE_SECRET_KEY `
  --data-file=- `
  --project=podcast612 << EOF
sk_live_YOUR_SECRET_KEY_HERE
EOF

# Set the publishable key
gcloud secrets versions add STRIPE_PUBLISHABLE_KEY `
  --data-file=- `
  --project=podcast612 << EOF
pk_live_YOUR_PUBLISHABLE_KEY_HERE
EOF
```

---

## Step 3: Get Webhook Signing Secret (After Setup)

### After you run `stripe_setup.py` and create your webhook:

1. Go to: https://dashboard.stripe.com/webhooks
2. Click on your webhook endpoint
3. Click "Reveal" in the "Signing secret" section
4. Copy the value starting with `whsec_...`

### Add to Environment:

```bash
# Add to backend/.env.local
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET_HERE
```

```powershell
# Add to Google Cloud
gcloud secrets versions add STRIPE_WEBHOOK_SECRET `
  --data-file=- `
  --project=podcast612 << EOF
whsec_YOUR_WEBHOOK_SECRET_HERE
EOF
```

---

## Test vs Live Keys

### Test Keys (for development):
- Publishable: `pk_test_...`
- Secret: `sk_test_...`
- Webhook: `whsec_...` (test mode)

### Live Keys (for production):
- Publishable: `pk_live_...`
- Secret: `sk_live_...`
- Webhook: `whsec_...` (live mode)

⚠️ **Important**: Make sure you're in "Live mode" in the Stripe dashboard (toggle in top-right)

---

## Quick Checklist

- [ ] Got publishable key (`pk_live_...`)
- [ ] Got secret key (`sk_live_...`)
- [ ] Added both to `backend/.env.local`
- [ ] Ready to run `stripe_setup.py`
- [ ] Will get webhook secret (`whsec_...`) after setup

---

## What Each Key Does

| Key | Used By | Purpose | Safe to Share? |
|-----|---------|---------|----------------|
| `pk_live_...` | Frontend | Initialize Stripe.js | ✅ Yes (public) |
| `sk_live_...` | Backend | Create sessions, manage billing | ❌ NO (secret) |
| `whsec_...` | Backend | Verify webhook signatures | ❌ NO (secret) |

---

## Need Help?

If you're stuck:
1. Make sure you're logged into Stripe dashboard
2. Make sure you're in "Live mode" (toggle top-right)
3. Go to Developers → API Keys
4. The publishable key is visible, secret key needs "Reveal"

That's it! Just 2 keys to start. 🎉
