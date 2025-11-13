#!/usr/bin/env python3
"""
Stripe Product & Price Setup Script
=====================================
Creates or updates products and prices in Stripe (test or live mode).
Run this script to automatically configure your Stripe account with the products/prices
needed for your subscription tiers.

Usage:
    python scripts/stripe_setup.py --mode test    # Setup test mode
    python scripts/stripe_setup.py --mode live    # Setup live mode (PRODUCTION)
    python scripts/stripe_setup.py --dry-run      # Show what would be created
"""

import os
import sys
import argparse
from pathlib import Path

# Add backend to path so we can import stripe
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import stripe


# Product & Price Configuration (ACTUAL PRICING from your site)
PRODUCTS = {
    "starter": {
        "name": "Podcast Plus Plus Starter",
        "description": "Get started with AI-powered podcasting - 28,800 credits/month (40 min max episode)",
        "features": [
            "28,800 credits per month",
            "Max episode length: 40 minutes",
            "Upload & record",
            "Basic cleanup (noise, trim)",
            "Basic analytics",
            "Manual publish",
            "Queue storage: 2 hrs, held 7 days"
        ],
        "prices": {
            "monthly": {
                "amount": 1900,  # $19.00 in cents (YOUR ACTUAL PRICE)
                "interval": "month",
                "lookup_key": "starter_monthly"
            },
            # Starter does not have an annual plan
        }
    },
    "creator": {
        "name": "Podcast Plus Plus Creator",
        "description": "Most popular - 72,000 credits/month (80 min max episode)",
        "features": [
            "72,000 credits per month",
            "Max episode length: 80 minutes",
            "Auto-publish to Spreaker",
            "Flubber (filler removal)",
            "Intern (spoken edits)",
            "Advanced analytics",
            "Queue storage: 10 hrs, held 14 days"
        ],
        "prices": {
            "monthly": {
                "amount": 3900,  # $39.00 in cents (YOUR ACTUAL PRICE)
                "interval": "month",
                "lookup_key": "creator_monthly"
            },
            "annual": {
                "amount": 39900,  # $399.00/year
                "interval": "year",
                "lookup_key": "creator_annual"
            }
        }
    },
    "pro": {
        "name": "Podcast Plus Plus Pro",
        "description": "Professional tier - 172,800 credits/month (120 min max episode)",
        "features": [
            "172,800 credits per month",
            "Max episode length: 120 minutes",
            "Advanced Intern (multi-step edits)",
            "Sound Effects & templates",
            "Full analytics",
            "Queue storage: 25 hrs, held 30 days"
        ],
        "prices": {
            "monthly": {
                "amount": 7900,  # $79.00 in cents (YOUR ACTUAL PRICE)
                "interval": "month",
                "lookup_key": "pro_monthly"
            },
            "annual": {
                "amount": 79900,  # $799.00/year
                "interval": "year",
                "lookup_key": "pro_annual"
            }
        }
    },
    "executive": {
        "name": "Podcast Plus Plus Executive",
        "description": "Executive tier - 288,000 credits/month (240 min max episode, manual override allowed)",
        "features": [
            "288,000 credits per month",
            "Max episode length: 240 minutes (manual override allowed)",
            "All Pro features",
            "Full analytics",
            "Priority queue processing",
            "Queue storage: 50 hrs, held 60 days"
        ],
        "prices": {
            "monthly": {
                "amount": 12900,  # $129.00 in cents (YOUR ACTUAL PRICE)
                "interval": "month",
                "lookup_key": "executive_monthly"
            },
            "annual": {
                "amount": 129900,  # $1,299.00/year
                "interval": "year",
                "lookup_key": "executive_annual"
            }
        }
    }
}

# Add-on Products (10,000 credits - one-time purchases)
# These credits never expire and can be used anytime
ADD_ONS = {
    "addon_credits_starter": {
        "name": "Addon Credits - Starter (10,000 credits)",
        "description": "Purchase 10,000 additional credits for your Starter plan. Credits never expire.",
        "price": {
            "amount": 800,  # $8.00 in cents
            "lookup_key": "addon_credits_starter",
            "metadata": {"credits": "10000"}
        }
    },
    "addon_credits_creator": {
        "name": "Addon Credits - Creator (10,000 credits)",
        "description": "Purchase 10,000 additional credits for your Creator plan. Credits never expire.",
        "price": {
            "amount": 700,  # $7.00 in cents
            "lookup_key": "addon_credits_creator",
            "metadata": {"credits": "10000"}
        }
    },
    "addon_credits_pro": {
        "name": "Addon Credits - Pro (10,000 credits)",
        "description": "Purchase 10,000 additional credits for your Pro plan. Credits never expire.",
        "price": {
            "amount": 600,  # $6.00 in cents
            "lookup_key": "addon_credits_pro",
            "metadata": {"credits": "10000"}
        }
    },
    "addon_credits_executive": {
        "name": "Addon Credits - Executive (10,000 credits)",
        "description": "Purchase 10,000 additional credits for your Executive plan. Credits never expire.",
        "price": {
            "amount": 500,  # $5.00 in cents
            "lookup_key": "addon_credits_executive",
            "metadata": {"credits": "10000"}
        }
    },
    "addon_credits_enterprise": {
        "name": "Addon Credits - Enterprise (10,000 credits)",
        "description": "Purchase 10,000 additional credits for your Enterprise plan. Credits never expire.",
        "price": {
            "amount": 500,  # $5.00 in cents
            "lookup_key": "addon_credits_enterprise",
            "metadata": {"credits": "10000"}
        }
    }
}


def setup_stripe_products(dry_run=False, verbose=True):
    """
    Create or update products and prices in Stripe.
    Returns a dict mapping lookup_key -> price_id
    """
    if not stripe.api_key:
        print("❌ ERROR: STRIPE_SECRET_KEY not set!")
        sys.exit(1)
    
    mode = "LIVE" if stripe.api_key.startswith("sk_live_") else "TEST"
    print(f"\n{'='*60}")
    print(f"🔧 Stripe Setup - {mode} MODE")
    print(f"{'='*60}\n")
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    price_map = {}
    
    # Create subscription products
    print("📦 SUBSCRIPTION PRODUCTS")
    print("="*60)
    
    for product_key, product_config in PRODUCTS.items():
        print(f"\n📦 Product: {product_config['name']}")
        print(f"   Key: {product_key}")
        print(f"   Description: {product_config['description']}")
        
        if dry_run:
            print(f"   ✓ Would create/update product")
        else:
            # Search for existing product by name
            existing = stripe.Product.search(query=f"name:'{product_config['name']}'")
            
            if existing.data:
                product = existing.data[0]
                print(f"   ✓ Found existing product: {product.id}")
                
                # Update product metadata
                product = stripe.Product.modify(
                    product.id,
                    description=product_config['description'],
                    metadata={
                        "tier": product_key,
                        "features": ", ".join(product_config['features'])
                    }
                )
                if verbose:
                    print(f"   ✓ Updated product metadata")
            else:
                # Create new product
                product = stripe.Product.create(
                    name=product_config['name'],
                    description=product_config['description'],
                    metadata={
                        "tier": product_key,
                        "features": ", ".join(product_config['features'])
                    }
                )
                print(f"   ✅ Created new product: {product.id}")
        
        # Handle prices
        for price_key, price_config in product_config['prices'].items():
            lookup_key = price_config['lookup_key']
            amount = price_config['amount']
            interval = price_config['interval']
            
            print(f"\n   💰 Price: {price_key} (${amount/100:.2f}/{interval})")
            print(f"      Lookup key: {lookup_key}")
            
            if dry_run:
                print(f"      ✓ Would create price")
                price_map[lookup_key] = f"price_DRYRUN_{lookup_key}"
            else:
                # Search for existing price by lookup_key
                existing_prices = stripe.Price.list(lookup_keys=[lookup_key], limit=1)
                
                if existing_prices.data:
                    price = existing_prices.data[0]
                    print(f"      ✓ Found existing price: {price.id}")
                    
                    # Verify it matches our config
                    if price.unit_amount != amount or price.recurring['interval'] != interval:
                        print(f"      ⚠️  Price mismatch! Creating new price...")
                        # Can't modify prices, create new one
                        price = stripe.Price.create(
                            product=product.id,
                            unit_amount=amount,
                            currency='usd',
                            recurring={'interval': interval},
                            lookup_key=f"{lookup_key}_v2",  # New lookup key
                            metadata={
                                "tier": product_key,
                                "cycle": price_key
                            }
                        )
                        print(f"      ✅ Created new price: {price.id} (lookup_key: {lookup_key}_v2)")
                        price_map[lookup_key] = price.id
                    else:
                        price_map[lookup_key] = price.id
                else:
                    # Create new price
                    price = stripe.Price.create(
                        product=product.id,
                        unit_amount=amount,
                        currency='usd',
                        recurring={'interval': interval},
                        lookup_key=lookup_key,
                        metadata={
                            "tier": product_key,
                            "cycle": price_key
                        }
                    )
                    print(f"      ✅ Created new price: {price.id}")
                    price_map[lookup_key] = price.id
    
    # Create add-on products (one-time prices)
    print("\n" + "="*60)
    print("🎁 ADD-ON PRODUCTS (One-time purchases)")
    print("="*60)
    
    for addon_key, addon_config in ADD_ONS.items():
        print(f"\n📦 Add-on: {addon_config['name']}")
        print(f"   Key: {addon_key}")
        print(f"   Description: {addon_config['description']}")
        
        if dry_run:
            print(f"   ✓ Would create/update product")
        else:
            # Search for existing product by name
            existing = stripe.Product.search(query=f"name:'{addon_config['name']}'")
            
            if existing.data:
                product = existing.data[0]
                print(f"   ✓ Found existing product: {product.id}")
                
                # Update product metadata
                product = stripe.Product.modify(
                    product.id,
                    description=addon_config['description'],
                    metadata={"type": "addon", "addon_key": addon_key}
                )
                if verbose:
                    print(f"   ✓ Updated product metadata")
            else:
                # Create new product
                product = stripe.Product.create(
                    name=addon_config['name'],
                    description=addon_config['description'],
                    metadata={"type": "addon", "addon_key": addon_key}
                )
                print(f"   ✅ Created new product: {product.id}")
        
        # Handle one-time price
        price_config = addon_config['price']
        lookup_key = price_config['lookup_key']
        amount = price_config['amount']
        metadata = price_config.get('metadata', {})
        
        print(f"\n   💰 Price: ${amount/100:.2f} (one-time)")
        print(f"      Lookup key: {lookup_key}")
        if metadata.get('credits'):
            print(f"      Credits: {metadata['credits']}")
        
        if dry_run:
            print(f"      ✓ Would create price")
            price_map[lookup_key] = f"price_DRYRUN_{lookup_key}"
        else:
            # Search for existing price by lookup_key
            existing_prices = stripe.Price.list(lookup_keys=[lookup_key], limit=1)
            
            if existing_prices.data:
                price = existing_prices.data[0]
                print(f"      ✓ Found existing price: {price.id}")
                
                # Verify it matches our config (one-time prices don't have recurring)
                if price.unit_amount != amount:
                    print(f"      ⚠️  Price mismatch! Creating new price...")
                    price = stripe.Price.create(
                        product=product.id,
                        unit_amount=amount,
                        currency='usd',
                        lookup_key=f"{lookup_key}_v2",
                        metadata={"type": "addon", "addon_key": addon_key, **metadata}
                    )
                    print(f"      ✅ Created new price: {price.id} (lookup_key: {lookup_key}_v2)")
                    price_map[lookup_key] = price.id
                else:
                    # Update metadata if needed
                    if metadata:
                        stripe.Price.modify(price.id, metadata={"type": "addon", "addon_key": addon_key, **metadata})
                    price_map[lookup_key] = price.id
            else:
                # Create new one-time price (no recurring parameter)
                price = stripe.Price.create(
                    product=product.id,
                    unit_amount=amount,
                    currency='usd',
                    lookup_key=lookup_key,
                    metadata={"type": "addon", "addon_key": addon_key, **metadata}
                )
                print(f"      ✅ Created new price: {price.id}")
                price_map[lookup_key] = price.id
    
    print(f"\n{'='*60}")
    print("📋 PRICE MAPPING (add these to your environment variables)")
    print(f"{'='*60}\n")    # Generate environment variable format
    env_vars = []
    for lookup_key, price_id in price_map.items():
        # Convert lookup_key to env var name
        # e.g., "pro_monthly" -> "PRICE_PRO_MONTHLY"
        env_name = f"PRICE_{lookup_key.upper()}"
        print(f"{env_name}={price_id}")
        env_vars.append(f"{env_name}={price_id}")
    
    print(f"\n{'='*60}")
    print("✅ Setup complete!")
    print(f"{'='*60}\n")
    
    if not dry_run:
        # Save to .env file
        env_file = Path(__file__).parent.parent / "backend" / ".env.stripe"
        with open(env_file, 'w') as f:
            f.write(f"# Stripe Price IDs - {mode} MODE\n")
            f.write(f"# Generated on {__import__('datetime').datetime.now().isoformat()}\n\n")
            for line in env_vars:
                f.write(f"{line}\n")
        
        print(f"💾 Price IDs saved to: {env_file}")
        print(f"\n⚠️  Remember to add these to your production secrets/environment!")
    
    return price_map


def main():
    parser = argparse.ArgumentParser(description="Setup Stripe products and prices")
    parser.add_argument(
        '--mode',
        choices=['test', 'live'],
        help='Which Stripe mode to use (test or live)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without making changes'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=True,
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Load environment variables
    env_file = Path(__file__).parent.parent / "backend" / ".env.local"
    if env_file.exists():
        print(f"📂 Loading environment from: {env_file}")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
    
    # Set Stripe API key based on mode
    if args.mode == 'live':
        stripe.api_key = os.getenv('STRIPE_LIVE_SECRET_KEY') or os.getenv('STRIPE_SECRET_KEY')
        if not stripe.api_key or not stripe.api_key.startswith('sk_live_'):
            print("❌ ERROR: STRIPE_LIVE_SECRET_KEY not found or invalid!")
            print("   Set STRIPE_LIVE_SECRET_KEY in your environment or .env.local")
            sys.exit(1)
    else:
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        if not stripe.api_key:
            print("❌ ERROR: STRIPE_SECRET_KEY not found!")
            print("   Set STRIPE_SECRET_KEY in your environment or .env.local")
            sys.exit(1)
    
    # Run setup
    try:
        setup_stripe_products(dry_run=args.dry_run, verbose=args.verbose)
    except stripe.error.StripeError as e:
        print(f"\n❌ Stripe Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
