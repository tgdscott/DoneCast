# 🔍 IMPORTANT: How the Setup Script Works

## Quick Answer to Your Questions

### Q1: Does the script run locally?
**YES** ✅ - The script runs on your local machine (in PowerShell/terminal).

### Q2: Does it set up on Google Cloud automatically?
**NO** ❌ - The script only creates products in **Stripe**, not Google Cloud.

You still need to manually add the generated price IDs to Google Cloud Secret Manager (Step 3).

### Q3: What products are included?
**NOW UPDATED** ✅ - All products included:

**Subscription Plans:**
- ✅ Starter (monthly + annual)
- ✅ Creator (monthly + annual)
- ✅ Pro (monthly + annual)
- ✅ Executive (monthly + annual)

**Add-ons (one-time purchases):**
- ✅ Additional Hour - Starter ($5)
- ✅ Additional Hour - Pro ($5)
- ✅ Additional Hour - Creator ($5)

---

## How It Works: Step-by-Step

### What Happens When You Run the Script

```powershell
python scripts/stripe_setup.py --mode live
```

**Step 1: Script Connects to Stripe API**
- Uses your `STRIPE_SECRET_KEY` (or `STRIPE_LIVE_SECRET_KEY`)
- Connects directly to Stripe's servers
- No Google Cloud involved yet

**Step 2: Script Creates/Updates Products in Stripe**
- Creates 4 subscription products (Starter, Creator, Pro, Executive)
- Creates 8 subscription prices (monthly + annual for each)
- Creates 3 add-on products (additional hours)
- Creates 3 one-time prices for add-ons

**Step 3: Script Generates Environment Variables**
- Displays all the price IDs
- Saves them to `.env.stripe` file locally
- **You copy these to Google Cloud manually**

---

## Complete Product List (Updated!)

### 📦 Subscription Products

#### 1. Starter Plan
- **Monthly**: $19/month (`PRICE_STARTER_MONTHLY`)
- **Annual**: $190/year (`PRICE_STARTER_ANNUAL`)
- Features: 28,800 credits/month, 40 min max episode, basic analytics

#### 2. Creator Plan
- **Monthly**: $39/month (`PRICE_CREATOR_MONTHLY`)
- **Annual**: $390/year (`PRICE_CREATOR_ANNUAL`)
- Features: 72,000 credits/month, 80 min max episode, advanced analytics

#### 3. Pro Plan
- **Monthly**: $79/month (`PRICE_PRO_MONTHLY`)
- **Annual**: $790/year (`PRICE_PRO_ANNUAL`)
- Features: 172,800 credits/month, 120 min max episode, full analytics

#### 4. Executive Plan
- **Monthly**: $129/month (`PRICE_EXECUTIVE_MONTHLY`)
- **Annual**: $1,285/year (`PRICE_EXECUTIVE_ANNUAL`)
- Features: 288,000 credits/month, 240 min max episode (override allowed), full analytics, priority queue

### 🎁 Add-on Products (One-time Purchases)

#### 1. Additional Hour - Starter
- **Price**: $5 one-time (`PRICE_ADDON_HOUR_STARTER`)
- Adds 60 minutes to Starter plan

#### 2. Additional Hour - Pro
- **Price**: $5 one-time (`PRICE_ADDON_HOUR_PRO`)
- Adds 60 minutes to Pro plan

#### 3. Additional Hour - Creator
- **Price**: $5 one-time (`PRICE_ADDON_HOUR_CREATOR`)
- Adds 60 minutes to Creator plan

---

## Complete Workflow

### LOCAL MACHINE (Your Computer)
```powershell
# Step 1: Set your Stripe key
$env:STRIPE_LIVE_SECRET_KEY="sk_live_YOUR_KEY"

# Step 2: Run the setup script
python scripts/stripe_setup.py --mode live

# ✅ This creates products in Stripe
# ✅ This generates price IDs
# ✅ This saves to .env.stripe locally
```

**Output Example:**
```
📋 PRICE MAPPING
================================
PRICE_STARTER_MONTHLY=price_abc123
PRICE_STARTER_ANNUAL=price_def456
PRICE_PRO_MONTHLY=price_ghi789
PRICE_PRO_ANNUAL=price_jkl012
PRICE_CREATOR_MONTHLY=price_mno345
PRICE_CREATOR_ANNUAL=price_pqr678
PRICE_ADDON_HOUR_STARTER=price_stu901
PRICE_ADDON_HOUR_PRO=price_vwx234
PRICE_ADDON_HOUR_CREATOR=price_yz567
```

### GOOGLE CLOUD (Manual Step)
```powershell
# Step 3: Copy each price ID to Google Cloud Secret Manager

# Subscription prices
echo "price_abc123" | gcloud secrets create PRICE_STARTER_MONTHLY --data-file=- --project=podcast612
echo "price_def456" | gcloud secrets create PRICE_STARTER_ANNUAL --data-file=- --project=podcast612
echo "price_ghi789" | gcloud secrets create PRICE_PRO_MONTHLY --data-file=- --project=podcast612
echo "price_jkl012" | gcloud secrets create PRICE_PRO_ANNUAL --data-file=- --project=podcast612
echo "price_mno345" | gcloud secrets create PRICE_CREATOR_MONTHLY --data-file=- --project=podcast612
echo "price_pqr678" | gcloud secrets create PRICE_CREATOR_ANNUAL --data-file=- --project=podcast612

# Add-on prices
echo "price_stu901" | gcloud secrets create PRICE_ADDON_HOUR_STARTER --data-file=- --project=podcast612
echo "price_vwx234" | gcloud secrets create PRICE_ADDON_HOUR_PRO --data-file=- --project=podcast612
echo "price_yz567" | gcloud secrets create PRICE_ADDON_HOUR_CREATOR --data-file=- --project=podcast612
```

---

## Why It Works This Way

### Why Not Automate Google Cloud Setup?
1. **Security** - Requires Google Cloud authentication
2. **Permissions** - Needs specific IAM permissions
3. **Control** - You verify each secret before adding
4. **Safety** - Manual step prevents accidental overwrites

### Benefits of This Approach
✅ **Stripe Setup Automated** - Products/prices created instantly  
✅ **Google Cloud Manual** - You control what goes where  
✅ **Transparent** - You see exactly what's being created  
✅ **Safe** - No accidental changes to production secrets  

---

## Environment Variables You'll Need

After running the script, you'll need to add these to Google Cloud:

### Subscription Plans (8 total)
```bash
PRICE_STARTER_MONTHLY     # $19/month
PRICE_STARTER_ANNUAL      # $190/year
PRICE_CREATOR_MONTHLY     # $39/month
PRICE_CREATOR_ANNUAL      # $390/year
PRICE_PRO_MONTHLY         # $79/month
PRICE_PRO_ANNUAL          # $790/year
PRICE_EXECUTIVE_MONTHLY   # $129/month
PRICE_EXECUTIVE_ANNUAL    # $1,285/year
```

### Add-ons (3 total)
```bash
PRICE_ADDON_HOUR_STARTER  # $5
PRICE_ADDON_HOUR_PRO      # $5
PRICE_ADDON_HOUR_CREATOR  # $5
```

### Stripe Keys (already have these)
```bash
STRIPE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET
```

**Total: 14 new environment variables** (11 prices + 3 Stripe keys)

---

## Testing Locally First

Before going live, test with test mode:

```powershell
# Use test key
$env:STRIPE_SECRET_KEY="sk_test_YOUR_KEY"

# Run in test mode
python scripts/stripe_setup.py --mode test

# Or dry run (shows what would happen)
python scripts/stripe_setup.py --dry-run
```

This creates everything in Stripe's **test mode** so you can verify it works.

---

## Summary

| What | Where | How |
|------|-------|-----|
| **Products** | Stripe | Automated (script) |
| **Prices** | Stripe | Automated (script) |
| **Price IDs** | Google Cloud | Manual (copy/paste) |
| **Stripe Keys** | Google Cloud | Manual (copy/paste) |

**Script does**: Creates products in Stripe  
**You do**: Copy price IDs to Google Cloud  

---

## Next Steps

1. ✅ Run script: `python scripts/stripe_setup.py --mode live`
2. ✅ Copy output (price IDs)
3. ✅ Add to Google Cloud Secret Manager
4. ✅ Deploy your app
5. ✅ Test billing page

**Questions?** The script is now updated with all 4 subscription plans (8 prices) plus add-ons!
