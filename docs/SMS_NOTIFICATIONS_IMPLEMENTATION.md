# SMS Notifications Implementation

## Overview

SMS notifications have been implemented using Twilio to notify users about important events. Users must opt-in to receive SMS notifications.

## Features Implemented

### 1. User Notifications
- **Transcription Ready**: Notifies users when their episode is ready to assemble (after transcription completes)
- **Episode Published/Scheduled**: Notifies users when their episode has been published or scheduled (includes publish date/time)

### 2. Admin Notifications
- **Worker Server Down**: Notifies admin users when the worker server is down and needs to be fixed

## Implementation Details

### Database Changes
- Added `phone_number` field to User model (VARCHAR(20))
- Added `sms_notifications_enabled` field (BOOLEAN, default FALSE)
- Added `sms_notify_transcription_ready` field (BOOLEAN, default FALSE)
- Added `sms_notify_publish` field (BOOLEAN, default FALSE)
- Added `sms_notify_worker_down` field (BOOLEAN, default FALSE, admin only)

**Migration**: `backend/migrations/035_add_sms_notification_fields.py`

### API Endpoints

#### Get SMS Preferences
```
GET /api/users/me/sms-preferences
```
Returns current user's SMS notification preferences.

#### Update SMS Preferences
```
PUT /api/users/me/sms-preferences
```
Request body:
```json
{
  "phone_number": "+1234567890",  // Optional, E.164 format recommended
  "sms_notifications_enabled": true,  // Optional, master toggle
  "sms_notify_transcription_ready": true,  // Optional
  "sms_notify_publish": true,  // Optional
  "sms_notify_worker_down": false  // Optional, admin only
}
```

### SMS Service
**File**: `backend/api/services/sms.py`

The SMS service:
- Uses Twilio to send SMS messages
- Normalizes phone numbers to E.164 format
- Handles errors gracefully (doesn't fail if SMS service is unavailable)
- Supports message truncation for long messages (max 1600 characters)

### Integration Points

1. **Transcription Completion** (`backend/api/services/transcription/watchers.py`)
   - Sends SMS when transcription completes and episode is ready to assemble
   - Only sends if user has opted in

2. **Episode Publishing** (`backend/api/services/episodes/publisher.py` and `backend/api/routers/episodes/publish.py`)
   - Sends SMS when episode is published or scheduled
   - Includes publish date/time in notification
   - Works for both RSS-only and Spreaker publishing

3. **Worker Server Down** (`backend/api/services/slack_alerts.py`)
   - Sends SMS to all admin users who have opted in
   - Checks for admin role, legacy is_admin flag, and ADMIN_EMAIL match
   - Only sends to admins with `sms_notify_worker_down` enabled

## Configuration

### Required Environment Variables

```bash
# Twilio Account SID (from Twilio Console)
TWILIO_ACCOUNT_SID=your_account_sid_here

# Twilio Auth Token (from Twilio Console)
TWILIO_AUTH_TOKEN=your_auth_token_here

# Twilio Phone Number (defaults to +18332320424 if not set)
TWILIO_PHONE_NUMBER=+18332320424
```

### Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install twilio==9.3.5
   ```
   Or update `requirements.txt` (already done)

2. **Get Twilio Credentials**
   - Sign up at https://www.twilio.com/
   - Log into your Twilio Console: https://console.twilio.com/
   - **Account SID**: Found on the main dashboard (starts with "AC")
   - **Auth Token**: Click "Show" next to Auth Token on the dashboard (starts with your auth token)
   - **Phone Number**: Go to Phone Numbers → Manage → Active numbers (you can use the provided number: (833) 232-0424)
   
   **Where to find in Twilio Console:**
   - Dashboard: https://console.twilio.com/us1/develop/console
   - Account SID and Auth Token are displayed on the main dashboard
   - Phone Numbers: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming

3. **Set Environment Variables**
   - Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` to your environment
   - For Cloud Run, add these to Secret Manager or environment variables

4. **Run Migration**
   - The migration will run automatically on startup
   - Or run manually: `python backend/create_db.py`

5. **Test the Integration**
   - Update a user's SMS preferences via the API
   - Trigger a transcription completion or episode publish
   - Verify SMS is received

## Phone Number Format

Phone numbers are normalized to E.164 format:
- US numbers: `+1` followed by 10 digits
- International numbers: `+` followed by country code and number
- The service automatically normalizes common formats:
  - `(833) 232-0424` → `+18332320424`
  - `833-232-0424` → `+18332320424`
  - `8332320424` → `+18332320424`

## User Opt-In Flow

1. **Send Verification Code**: User sends phone number to `/api/auth/send-phone-verification`
   - System sends a 6-digit code via SMS to the phone number
   - Code expires in 10 minutes
2. **Verify Phone Number**: User submits code to `/api/auth/verify-phone`
   - System verifies the code and stores the verified phone number
   - Phone number is now available for SMS notifications
3. **Enable SMS Notifications**: User enables SMS notifications via `/api/users/me/sms-preferences`
   - Set `sms_notifications_enabled: true`
   - Enable specific notification types:
     - `sms_notify_transcription_ready`: For transcription completion
     - `sms_notify_publish`: For episode publishing
     - `sms_notify_worker_down`: For admin worker alerts (admin only)

**Important**: Phone numbers must be verified before they can be used for SMS notifications. The phone number cannot be set directly via the SMS preferences endpoint - it must be verified first.

## Error Handling

- SMS failures are logged but don't fail the main operation
- If Twilio is not configured, SMS service gracefully disables itself
- Invalid phone numbers are logged and skipped
- Database errors are caught and logged (doesn't block notifications)

## Testing

### Test SMS Service Directly
```python
from api.services.sms import sms_service

# Test sending an SMS
sms_service.send_sms(
    to="+1234567890",
    message="Test message",
    user_id="test-user-id"
)
```

### Test Phone Verification
```bash
# Step 1: Send verification code
curl -X POST http://localhost:8000/api/auth/send-phone-verification \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890"
  }'

# Step 2: Verify phone number (use code received via SMS)
curl -X POST http://localhost:8000/api/auth/verify-phone \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "code": "123456"
  }'
```

### Test User Preferences
```bash
# Get preferences
curl -X GET http://localhost:8000/api/users/me/sms-preferences \
  -H "Authorization: Bearer YOUR_TOKEN"

# Update preferences (phone number must be verified first)
curl -X PUT http://localhost:8000/api/users/me/sms-preferences \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sms_notifications_enabled": true,
    "sms_notify_transcription_ready": true,
    "sms_notify_publish": true
  }'
```

## Notes

- SMS notifications are opt-in only
- **Phone numbers must be verified before use** (verification code sent via SMS)
- Admin notifications for worker down require admin role
- Phone numbers are normalized to E.164 format (e.g., +18332320424)
- Messages are truncated to 1600 characters if too long
- SMS service degrades gracefully if Twilio is not configured
- All SMS sends are logged for debugging
- Users can opt out by replying "STOP" to any SMS (handled by Twilio automatically)

## Future Enhancements

- Add SMS verification for phone numbers
- Add rate limiting for SMS sends
- Add SMS delivery status tracking
- Add support for international phone numbers with better validation
- Add SMS templates for different notification types

