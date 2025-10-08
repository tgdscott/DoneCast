#!/usr/bin/env python3
"""
Stripe Configuration Checker
=============================
Validates your Stripe setup before going live.

Usage:
    python scripts/check_stripe_config.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    import stripe
except ImportError:
    print("❌ ERROR: Stripe package not installed!")
    print("   Run: pip install stripe")
    sys.exit(1)


def check_env_var(name, required=True, starts_with=None):
    """Check if environment variable is set and valid."""
    value = os.getenv(name)
    
    if not value:
        if required:
            print(f"❌ {name}: NOT SET (required)")
            return False
        else:
            print(f"⚠️  {name}: NOT SET (optional)")
            return True
    
    if starts_with and not value.startswith(starts_with):
        print(f"❌ {name}: Invalid format (should start with '{starts_with}')")
        return False
    
    # Mask sensitive values
    if 'SECRET' in name or 'KEY' in name:
        masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
        print(f"✅ {name}: {masked}")
    else:
        print(f"✅ {name}: {value}")
    
    return True


def check_stripe_connection(api_key):
    """Test connection to Stripe API."""
    try:
        stripe.api_key = api_key
        # Try to list a customer (will work even if empty)
        stripe.Customer.list(limit=1)
        mode = "LIVE" if api_key.startswith("sk_live_") else "TEST"
        print(f"✅ Stripe API connection successful ({mode} mode)")
        return True
    except stripe.error.AuthenticationError:
        print(f"❌ Stripe API authentication failed (invalid key)")
        return False
    except stripe.error.StripeError as e:
        print(f"❌ Stripe API error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def check_products_and_prices(api_key):
    """Check if products and prices exist."""
    try:
        stripe.api_key = api_key
        
        # Check for products
        products = stripe.Product.search(query="name:'Podcast++'", limit=10)
        
        if not products.data:
            print("⚠️  No products found with 'Podcast++' in name")
            print("   Run: python scripts/stripe_setup.py --mode [test|live]")
            return False
        
        print(f"✅ Found {len(products.data)} product(s)")
        
        for product in products.data:
            print(f"   • {product.name} ({product.id})")
            
            # Check prices for this product
            prices = stripe.Price.list(product=product.id, limit=10)
            if prices.data:
                for price in prices.data:
                    amount = price.unit_amount / 100 if price.unit_amount else 0
                    interval = price.recurring.get('interval', 'N/A') if price.recurring else 'one-time'
                    lookup = price.lookup_key or 'N/A'
                    print(f"     - ${amount:.2f}/{interval} (lookup_key: {lookup}, id: {price.id})")
        
        return True
    except Exception as e:
        print(f"❌ Error checking products: {e}")
        return False


def check_webhook_configuration():
    """Check webhook endpoint configuration."""
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        print("⚠️  STRIPE_WEBHOOK_SECRET not set")
        print("   Configure webhook at: https://dashboard.stripe.com/webhooks")
        return False
    
    if not webhook_secret.startswith('whsec_'):
        print("❌ STRIPE_WEBHOOK_SECRET invalid format (should start with 'whsec_')")
        return False
    
    masked = webhook_secret[:10] + "..." + webhook_secret[-4:]
    print(f"✅ STRIPE_WEBHOOK_SECRET: {masked}")
    return True


def main():
    print("\n" + "="*60)
    print("🔧 Stripe Configuration Checker")
    print("="*60 + "\n")
    
    # Load .env.local if exists
    env_file = Path(__file__).parent.parent / "backend" / ".env.local"
    if env_file.exists():
        print(f"📂 Loading environment from: {env_file}\n")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
    
    all_checks = []
    
    # Check environment variables
    print("\n📋 Environment Variables")
    print("-" * 60)
    all_checks.append(check_env_var('STRIPE_SECRET_KEY', required=True, starts_with='sk_'))
    all_checks.append(check_env_var('STRIPE_PUBLISHABLE_KEY', required=True, starts_with='pk_'))
    all_checks.append(check_env_var('STRIPE_WEBHOOK_SECRET', required=True, starts_with='whsec_'))
    
    print("\n📋 Price IDs")
    print("-" * 60)
    all_checks.append(check_env_var('PRICE_PRO_MONTHLY', required=False, starts_with='price_'))
    all_checks.append(check_env_var('PRICE_PRO_ANNUAL', required=False, starts_with='price_'))
    all_checks.append(check_env_var('PRICE_CREATOR_MONTHLY', required=False, starts_with='price_'))
    all_checks.append(check_env_var('PRICE_CREATOR_ANNUAL', required=False, starts_with='price_'))
    
    # Check Stripe connection
    secret_key = os.getenv('STRIPE_SECRET_KEY')
    if secret_key:
        print("\n🔌 Stripe API Connection")
        print("-" * 60)
        all_checks.append(check_stripe_connection(secret_key))
        
        # Check products and prices
        print("\n📦 Products & Prices")
        print("-" * 60)
        all_checks.append(check_products_and_prices(secret_key))
    
    # Check webhook
    print("\n🪝 Webhook Configuration")
    print("-" * 60)
    all_checks.append(check_webhook_configuration())
    
    # Key matching check
    print("\n🔑 Key Consistency")
    print("-" * 60)
    pub_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
    if secret_key and pub_key:
        secret_mode = "live" if secret_key.startswith('sk_live_') else "test"
        pub_mode = "live" if pub_key.startswith('pk_live_') else "test"
        
        if secret_mode == pub_mode:
            print(f"✅ Keys match ({secret_mode} mode)")
            all_checks.append(True)
        else:
            print(f"❌ Key mismatch! Secret is {secret_mode}, Publishable is {pub_mode}")
            all_checks.append(False)
    
    # Summary
    print("\n" + "="*60)
    passed = sum(all_checks)
    total = len(all_checks)
    
    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        print("="*60)
        print("\n🎉 Your Stripe configuration looks good!")
        print("\nNext steps:")
        print("1. Test checkout in your application")
        print("2. Verify webhook events are received")
        print("3. Test customer portal")
        print("4. Monitor Stripe dashboard for events")
        return 0
    else:
        print(f"⚠️  SOME CHECKS FAILED ({passed}/{total} passed)")
        print("="*60)
        print("\n❌ Please fix the issues above before going live.")
        print("\nCommon fixes:")
        print("• Set missing environment variables")
        print("• Run: python scripts/stripe_setup.py --mode [test|live]")
        print("• Configure webhook at: https://dashboard.stripe.com/webhooks")
        print("• Ensure test/live keys match")
        return 1


if __name__ == '__main__':
    sys.exit(main())
