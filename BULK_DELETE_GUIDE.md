# 🗑️ BULK TEST USER DELETION GUIDE

## Quick Start

### Step 1: Set Your Admin Token

```powershell
$env:ADMIN_TOKEN = "your_admin_jwt_token_here"
```

**How to get your admin token:**
1. Open DevTools in production (F12)
2. Go to Application/Storage → Local Storage
3. Copy the value of `authToken`

---

### Step 2: Preview What Will Be Deleted (Dry Run)

```powershell
.\bulk_delete_test_users.ps1 -DryRun
```

This will show you:
- ✅ Which accounts are PROTECTED (will NOT be deleted)
- 🎯 Which accounts will be deleted
- 📊 Summary of total users, protected, and to-be-deleted

**Example output:**
```
🔒 PROTECTED ACCOUNTS (will NOT be deleted):
  ✓ test22@scottgerhardt.com (abc-123-def)
  ✓ tom@pluspluspodcasts.com (xyz-456-uvw)
  ✓ scober@scottgerhardt.com (lmn-789-opq)

🎯 TEST ACCOUNTS IDENTIFIED:
  • test@example.com (user-id-here)
    Podcasts: 0, Episodes: 0, Media: 3
  • test10@scottgerhardt.com (user-id-here)
    Podcasts: 1, Episodes: 2, Media: 5
  • verify-test@test.com (user-id-here)
    Podcasts: 0, Episodes: 0, Media: 0

📊 SUMMARY:
  Total users: 15
  Protected: 3
  To delete: 3

[DRY RUN] Would delete: test@example.com (user-id-here)
[DRY RUN] Would delete: test10@scottgerhardt.com (user-id-here)
[DRY RUN] Would delete: verify-test@test.com (user-id-here)

✅ COMPLETE
Would have deleted 3 test accounts
```

---

### Step 3: Actually Delete Them

```powershell
.\bulk_delete_test_users.ps1
```

You'll be prompted to type `DELETE` to confirm.

**Example output:**
```
⚠️  WARNING: This will PERMANENTLY delete these accounts!
   Type 'DELETE' to confirm:
> DELETE

🗑️  DELETING TEST ACCOUNTS:

  🗑️  Deleting: test@example.com (user-id)... ✅ Deleted (P:0 E:0 M:3)
     GCS cleanup: gsutil -m rm -r gs://ppp-media-us-west1/user-id/
  🗑️  Deleting: test10@scottgerhardt.com (user-id)... ✅ Deleted (P:1 E:2 M:5)
     GCS cleanup: gsutil -m rm -r gs://ppp-media-us-west1/user-id/

✅ COMPLETE
Successfully deleted: 2
Failed: 0
```

---

### Step 4: Skip Confirmation (Optional)

```powershell
.\bulk_delete_test_users.ps1 -Force
```

This will delete without asking for confirmation. **Use with caution!**

---

## What Accounts Are Protected?

The script will **NEVER** delete these accounts:

1. ✅ `test22@scottgerhardt.com` (your current test account)
2. ✅ `tom@pluspluspodcasts.com` (admin)
3. ✅ `tgdscott@gmail.com` (admin)
4. ✅ `scober@scottgerhardt.com` (your main account)

---

## What Accounts Will Be Deleted?

Accounts matching ANY of these criteria:

### 1. Email contains test patterns:
- `test`, `test-`, `test1`, `test2`, ..., `test21` (NOT test22)
- `delete`
- `verify`
- `@example.com`
- `@test.com`

### 2. Flagged by API:
- `is_test_account: true`

### 3. No content:
- 0 podcasts AND 0 episodes

---

## Safety Features

✅ **Protected accounts list** - Hard-coded safeguards  
✅ **Dry run mode** - Preview before deleting  
✅ **Confirmation prompt** - Type "DELETE" to confirm  
✅ **API-level protection** - Backend won't delete admin accounts  
✅ **Email confirmation** - Each deletion requires exact email match  
✅ **Transaction rollback** - If anything fails, all changes are rolled back  
✅ **Detailed logging** - See exactly what was deleted  

---

## Troubleshooting

### Error: "ADMIN_TOKEN environment variable not set"

**Solution:**
```powershell
$env:ADMIN_TOKEN = "your_token_here"
```

### Error: "Failed to fetch users: 401 Unauthorized"

**Solution:** Your token expired. Get a fresh one:
1. Log in to production
2. Open DevTools (F12)
3. Application → Local Storage → Copy `authToken`
4. Set it again: `$env:ADMIN_TOKEN = "new_token"`

### Error: "Cannot delete admin users"

**Good!** This means the safety checks are working. Admin accounts are protected.

### Some deletions failed

Check the error messages in the output. Common causes:
- Database foreign key issues (shouldn't happen but might)
- Network timeout
- User has active subscription (edge case)

---

## What Gets Deleted?

For each user deleted, the following are **PERMANENTLY REMOVED**:

1. ❌ User account
2. ❌ All podcasts
3. ❌ All episodes
4. ❌ All media items (database records)
5. ⚠️ **GCS files require MANUAL cleanup** (script prints command)

---

## Manual GCS Cleanup

After deletion, you'll see output like:
```
GCS cleanup: gsutil -m rm -r gs://ppp-media-us-west1/abc-123-def/
```

To clean up GCS files (optional):

1. **Install gcloud CLI** (if not already)
2. **Authenticate**: `gcloud auth login`
3. **Run the command** shown in the output

Or run all at once (after dry run):
```powershell
.\bulk_delete_test_users.ps1 | Select-String "gsutil" | ForEach-Object { 
    Invoke-Expression $_.Line.Split("GCS cleanup: ")[1] 
}
```

---

## Example Workflow

```powershell
# 1. Set token
$env:ADMIN_TOKEN = "your_admin_token_here"

# 2. Preview what will be deleted
.\bulk_delete_test_users.ps1 -DryRun

# 3. Review the list carefully
# Make sure test22@scottgerhardt.com is in PROTECTED list

# 4. Actually delete them
.\bulk_delete_test_users.ps1

# 5. Type "DELETE" when prompted

# 6. Done! 🎉
```

---

## Testing The Script

If you want to test the script without deleting anything:

```powershell
# Always use -DryRun for testing
.\bulk_delete_test_users.ps1 -DryRun
```

This is **completely safe** and shows you exactly what would happen.

---

## Need Help?

The script includes comprehensive error messages. If something goes wrong:

1. ✅ Check the error message
2. ✅ Make sure your token is valid
3. ✅ Try dry run mode first: `-DryRun`
4. ✅ Check backend logs if API calls fail

---

## Summary

```powershell
# Preview only (safe)
.\bulk_delete_test_users.ps1 -DryRun

# Delete with confirmation
.\bulk_delete_test_users.ps1

# Delete without confirmation (dangerous)
.\bulk_delete_test_users.ps1 -Force
```

**Protected accounts will NEVER be deleted:**
- ✅ test22@scottgerhardt.com
- ✅ tom@pluspluspodcasts.com
- ✅ tgdscott@gmail.com
- ✅ scober@scottgerhardt.com

**Ready to clean up test accounts! 🗑️**

---

*Last Updated: October 13, 2025*
