# 🗑️ USER DELETION GUIDE

**Date**: October 11, 2025  
**Purpose**: Clean up test accounts from the system  
**Status**: ✅ READY TO USE

---

## How To Delete Test Users

### Step 1: List All Users

**Endpoint**: `GET /api/admin/users`

**cURL**:
```bash
curl -X GET "https://podcast-api-524304361363.us-west1.run.app/api/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Response**:
```json
{
  "total_users": 5,
  "users": [
    {
      "id": "b6d5f77e-699e-444b-a31a-e1b4cb15feb4",
      "email": "test@example.com",
      "created_at": "2025-10-10T12:34:56",
      "email_verified": true,
      "counts": {
        "podcasts": 0,
        "episodes": 0,
        "media_items": 0
      },
      "is_test_account": true  ← THIS ONE!
    },
    {
      "id": "...",
      "email": "real.user@gmail.com",
      "counts": {
        "podcasts": 2,
        "episodes": 15,
        "media_items": 47
      },
      "is_test_account": false  ← DON'T DELETE
    }
  ]
}
```

### Step 2: Delete A Test User

**Endpoint**: `DELETE /api/admin/users/{user_id}`

**cURL**:
```bash
curl -X DELETE "https://podcast-api-524304361363.us-west1.run.app/api/admin/users/b6d5f77e-699e-444b-a31a-e1b4cb15feb4" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm_email": "test@example.com"}'
```

**Required**:
- ✅ Must be admin
- ✅ Must provide exact email for confirmation (safety check)
- ✅ Cannot delete admin users

**Response**:
```json
{
  "success": true,
  "deleted_user": {
    "id": "b6d5f77e-699e-444b-a31a-e1b4cb15feb4",
    "email": "test@example.com"
  },
  "deleted_items": {
    "podcasts": 0,
    "episodes": 0,
    "media_items": 3
  },
  "gcs_cleanup_required": true,
  "gcs_path": "gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/",
  "gcs_cleanup_command": "gsutil -m rm -r gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/"
}
```

### Step 3: Clean Up GCS Files (Optional)

**The API deletes database records but NOT GCS files.**

To delete GCS files:
```bash
# Copy the command from the API response
gsutil -m rm -r gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/
```

---

## Using The Dashboard (If Available)

If there's an admin panel at `/admin`, you can:

1. **View Users**: See list of all users with counts
2. **Identify Test Accounts**: Look for `is_test_account: true`
3. **Delete**: Click delete button, confirm email

---

## Safety Features

### Cannot Delete Admin Users
```json
// Error response
{
  "detail": "Cannot delete admin users"
}
```

**Admin emails protected**:
- `tom@pluspluspodcasts.com`
- `tgdscott@gmail.com`
- Whatever is in `ADMIN_EMAIL` env var

### Must Confirm Email
```json
{
  "confirm_email": "exact.email@example.com"
}
```

If email doesn't match:
```json
{
  "detail": "Email confirmation failed. Expected 'test@example.com' but got 'wrong@example.com'"
}
```

### Transaction Rollback
If anything fails during deletion, **all changes are rolled back**.

---

## What Gets Deleted

### ✅ Database Records
- User account
- All podcasts
- All episodes
- All media items
- All related data

### ❌ NOT Deleted (Manual Cleanup)
- GCS files (`gs://ppp-media-us-west1/{user_id}/...`)
  - Use the `gsutil` command from the response
  - Or delete manually in GCS console

---

## Quick Script For Bulk Deletion

```bash
#!/bin/bash
# delete_test_users.sh

TOKEN="your_admin_token_here"
API_URL="https://podcast-api-524304361363.us-west1.run.app"

# Get list of test users
users=$(curl -s -X GET "$API_URL/api/admin/users" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.users[] | select(.is_test_account == true) | "\(.id) \(.email)"')

echo "Found test accounts:"
echo "$users"
echo ""

# Delete each one
while read -r user_id email; do
  echo "Deleting $email ($user_id)..."
  
  response=$(curl -s -X DELETE "$API_URL/api/admin/users/$user_id" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"confirm_email\": \"$email\"}")
  
  success=$(echo "$response" | jq -r '.success')
  
  if [ "$success" = "true" ]; then
    echo "✅ Deleted $email"
    
    # Get GCS cleanup command
    gcs_cmd=$(echo "$response" | jq -r '.gcs_cleanup_command')
    echo "GCS cleanup: $gcs_cmd"
    
    # Optionally run it
    # eval "$gcs_cmd"
  else
    echo "❌ Failed to delete $email"
    echo "$response"
  fi
  
  echo ""
done <<< "$users"

echo "Done!"
```

**Usage**:
```bash
chmod +x delete_test_users.sh
./delete_test_users.sh
```

---

## Testing The Feature

### 1. Create A Test User
```bash
# Via signup endpoint
curl -X POST "https://podcast-api-524304361363.us-west1.run.app/api/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"email": "delete.me@test.com", "password": "test123"}'
```

### 2. Verify It Exists
```bash
curl -X GET "https://podcast-api-524304361363.us-west1.run.app/api/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  | jq '.users[] | select(.email == "delete.me@test.com")'
```

### 3. Delete It
```bash
curl -X DELETE "https://podcast-api-524304361363.us-west1.run.app/api/admin/users/USER_ID_HERE" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm_email": "delete.me@test.com"}'
```

### 4. Verify It's Gone
```bash
curl -X GET "https://podcast-api-524304361363.us-west1.run.app/api/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  | jq '.users[] | select(.email == "delete.me@test.com")'
# Should return nothing
```

---

## Logs

All deletion actions are logged:

```
[ADMIN] User deletion requested by tom@pluspluspodcasts.com for user_id: b6d5f77e-699e-444b-a31a-e1b4cb15feb4
[ADMIN] Confirmed deletion of user: test@example.com (b6d5f77e-699e-444b-a31a-e1b4cb15feb4)
[ADMIN] Deleted 3 media items for user b6d5f77e-699e-444b-a31a-e1b4cb15feb4
[ADMIN] Deleted 0 episodes for user b6d5f77e-699e-444b-a31a-e1b4cb15feb4
[ADMIN] Deleted 0 podcasts for user b6d5f77e-699e-444b-a31a-e1b4cb15feb4
[ADMIN] Deleted user account: test@example.com (b6d5f77e-699e-444b-a31a-e1b4cb15feb4)
[ADMIN] User deletion complete: {...}
```

---

## Important Notes

### This Is Permanent!
- No undo
- No recovery
- All data gone forever

### Use For Test Accounts Only
- Accounts with 0 podcasts
- Accounts with 0 episodes
- Accounts created for testing

### Don't Use For Real Users
- If user has ANY content, think twice
- Better to deactivate than delete
- Contact user first if deleting their work

---

## Future Improvements

### Add Later (If Needed)
1. **Soft Delete**: Mark as deleted, actual deletion after 30 days
2. **Deactivation**: Disable account without deleting data
3. **Bulk Delete**: Select multiple users at once
4. **GCS Auto-Cleanup**: Automatically delete GCS files
5. **Audit Log**: Track who deleted what and when
6. **Data Export**: Allow downloading user data before deletion

---

## Summary

**Added Two Endpoints**:
1. `GET /api/admin/users` - List all users
2. `DELETE /api/admin/users/{user_id}` - Delete a user

**Safety Features**:
- ✅ Admin-only
- ✅ Email confirmation required
- ✅ Cannot delete admin users
- ✅ Transaction rollback on error
- ✅ Comprehensive logging

**Ready to use right now!** 🗑️

Go test the waveform fix, and when you're ready to clean up test accounts, you have the tools! 🎯
