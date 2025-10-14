#!/usr/bin/env python3
"""
Bulk delete test user accounts (except protected ones).

Usage:
    python bulk_delete_test_users.py --dry-run  # See what would be deleted
    python bulk_delete_test_users.py            # Actually delete them
"""

import argparse
import requests
import json
import sys
import os
from typing import List, Dict, Any

# API Configuration
API_URL = os.getenv("API_URL", "https://podcast-api-524304361363.us-west1.run.app")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # Set via environment variable

# Protected accounts (will NEVER be deleted)
PROTECTED_EMAILS = {
    "test22@scottgerhardt.com",  # User's current test account
    "tom@pluspluspodcasts.com",
    "tgdscott@gmail.com",
    "scober@scottgerhardt.com",
}

# Test account patterns to identify
TEST_PATTERNS = [
    "test",
    "test-",
    "delete",
    "@example.com",
    "@test.com",
    "verify",
]


def get_headers() -> Dict[str, str]:
    """Get request headers with auth token."""
    if not ADMIN_TOKEN:
        print("❌ ERROR: ADMIN_TOKEN environment variable not set!")
        print("Set it with: $env:ADMIN_TOKEN='your_token_here'")
        sys.exit(1)
    
    return {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json",
    }


def list_all_users() -> List[Dict[str, Any]]:
    """Fetch all users from the API."""
    print(f"📡 Fetching all users from {API_URL}/api/admin/users...")
    
    response = requests.get(
        f"{API_URL}/api/admin/users",
        headers=get_headers()
    )
    
    if not response.ok:
        print(f"❌ Failed to fetch users: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    users = data.get("users", [])
    print(f"✅ Found {len(users)} total users")
    return users


def is_test_account(user: Dict[str, Any]) -> bool:
    """Determine if a user is a test account."""
    email = user.get("email", "").lower()
    
    # Never delete protected accounts
    if email in PROTECTED_EMAILS:
        return False
    
    # Check for test patterns in email
    for pattern in TEST_PATTERNS:
        if pattern in email:
            return True
    
    # Mark as test if flagged by API
    if user.get("is_test_account") is True:
        return True
    
    # Mark as test if no content
    counts = user.get("counts", {})
    if counts.get("podcasts", 0) == 0 and counts.get("episodes", 0) == 0:
        return True
    
    return False


def delete_user(user_id: str, email: str, dry_run: bool = False) -> bool:
    """Delete a single user account."""
    if dry_run:
        print(f"  [DRY RUN] Would delete: {email} ({user_id})")
        return True
    
    print(f"  🗑️  Deleting: {email} ({user_id})...", end=" ")
    
    try:
        response = requests.delete(
            f"{API_URL}/api/admin/users/{user_id}",
            headers=get_headers(),
            json={"confirm_email": email}
        )
        
        if response.ok:
            result = response.json()
            deleted_counts = result.get("deleted_items", {})
            print(f"✅ Deleted (P:{deleted_counts.get('podcasts', 0)} E:{deleted_counts.get('episodes', 0)} M:{deleted_counts.get('media_items', 0)})")
            
            # Log GCS cleanup command if provided
            if result.get("gcs_cleanup_command"):
                print(f"     GCS cleanup: {result['gcs_cleanup_command']}")
            
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"     {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Bulk delete test user accounts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    
    print("=" * 70)
    print("🗑️  BULK TEST USER DELETION")
    print("=" * 70)
    print()
    
    # Fetch all users
    all_users = list_all_users()
    
    # Identify test accounts
    test_users = [u for u in all_users if is_test_account(u)]
    protected_users = [u for u in all_users if u.get("email", "").lower() in PROTECTED_EMAILS]
    
    print()
    print("🔒 PROTECTED ACCOUNTS (will NOT be deleted):")
    if protected_users:
        for user in protected_users:
            print(f"  ✓ {user.get('email')} ({user.get('id')})")
    else:
        print("  (none found)")
    
    print()
    print("🎯 TEST ACCOUNTS IDENTIFIED:")
    if test_users:
        for user in test_users:
            counts = user.get("counts", {})
            print(f"  • {user.get('email')} ({user.get('id')})")
            print(f"    Podcasts: {counts.get('podcasts', 0)}, Episodes: {counts.get('episodes', 0)}, Media: {counts.get('media_items', 0)}")
    else:
        print("  (none found - nothing to delete)")
        return
    
    print()
    print(f"📊 SUMMARY:")
    print(f"  Total users: {len(all_users)}")
    print(f"  Protected: {len(protected_users)}")
    print(f"  To delete: {len(test_users)}")
    print()
    
    # Confirmation
    if not args.dry_run and not args.force:
        print("⚠️  WARNING: This will PERMANENTLY delete these accounts!")
        print("   Type 'DELETE' to confirm:")
        confirmation = input("> ").strip()
        if confirmation != "DELETE":
            print("❌ Cancelled by user")
            return
        print()
    
    # Delete users
    if args.dry_run:
        print("🔍 DRY RUN MODE - No actual deletions will occur:")
    else:
        print("🗑️  DELETING TEST ACCOUNTS:")
    
    print()
    
    success_count = 0
    fail_count = 0
    
    for user in test_users:
        user_id = user.get("id")
        email = user.get("email")
        
        if delete_user(user_id, email, dry_run=args.dry_run):
            success_count += 1
        else:
            fail_count += 1
    
    print()
    print("=" * 70)
    print("✅ COMPLETE")
    print("=" * 70)
    
    if args.dry_run:
        print(f"Would have deleted {success_count} test accounts")
    else:
        print(f"Successfully deleted: {success_count}")
        print(f"Failed: {fail_count}")
    
    print()


if __name__ == "__main__":
    main()
