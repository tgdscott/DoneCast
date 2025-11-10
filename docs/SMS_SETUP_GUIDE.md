# SMS Notifications Setup Guide

## Quick Answers

### Where to Find Twilio Credentials

1. **Sign in to Twilio Console**: https://console.twilio.com/
2. **Account SID**: 
   - On the main dashboard (home page)
   - Starts with "AC" (e.g., `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
   - Located in the top-left area of the dashboard
3. **Auth Token**:
   - On the main dashboard, next to Account SID
   - Click "Show" to reveal it
   - Keep this secret! (like a password)
4. **Phone Number**:
   - Go to: Phone Numbers → Manage → Active numbers
   - Or: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
   - Your phone number is listed there (format: +1XXXXXXXXXX)
   - Default provided number: `+18332320424`

### Opt-Out (STOP)

✅ **Implemented**: All user-facing SMS messages include "Reply STOP to opt out."
- Twilio automatically handles STOP replies
- No additional code needed
- Users who reply STOP will not receive future SMS messages
- This is handled automatically by Twilio's compliance features

### Phone Number Verification

✅ **Implemented**: Phone numbers must be verified before use.

**Flow:**
1. User sends phone number → `/api/auth/send-phone-verification`
2. System sends 6-digit code via SMS
3. User submits code → `/api/auth/verify-phone`
4. Phone number is verified and stored
5. User can now enable SMS notifications

## Complete Setup Steps

### 1. Get Twilio Credentials

```bash
# Sign up at https://www.twilio.com/ (if you haven't)
# Log into console: https://console.twilio.com/

# Find on dashboard:
# - Account SID: Starts with "AC"
# - Auth Token: Click "Show" next to it
# - Phone Number: In Phone Numbers section
```

### 2. Set Environment Variables

```bash
# Add to your .env file or environment:
TWILIO_ACCOUNT_SID=ACyour_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+18332320424  # Or your Twilio number
```

### 3. Install Dependencies

```bash
pip install twilio==9.3.5
# Or requirements.txt is already updated
```

### 4. Run Migrations

The migrations will run automatically on startup, or run manually:
```bash
python backend/create_db.py
```

This will create:
- SMS notification fields in user table (migration 035)
- Phone verification table (migration 036)

### 5. Test the Integration

```bash
# 1. Send verification code
curl -X POST http://localhost:8000/api/auth/send-phone-verification \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890"}'

# 2. Verify phone (use code from SMS)
curl -X POST http://localhost:8000/api/auth/verify-phone \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890", "code": "123456"}'

# 3. Enable SMS notifications
curl -X PUT http://localhost:8000/api/users/me/sms-preferences \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sms_notifications_enabled": true,
    "sms_notify_transcription_ready": true,
    "sms_notify_publish": true
  }'
```

## API Endpoints

### Phone Verification
- `POST /api/auth/send-phone-verification` - Send verification code
- `POST /api/auth/verify-phone` - Verify phone number with code

### SMS Preferences
- `GET /api/users/me/sms-preferences` - Get current preferences
- `PUT /api/users/me/sms-preferences` - Update preferences (phone must be verified first)

## Features

✅ Phone number verification (required before use)
✅ Opt-out support (STOP keyword handled by Twilio)
✅ Three notification types:
   - Transcription ready
   - Episode published/scheduled
   - Worker server down (admin only)
✅ Graceful error handling
✅ Phone number normalization (E.164 format)
✅ Message truncation (1600 char limit)

## Security Notes

- Phone numbers are verified before use
- Verification codes expire in 10 minutes
- Codes are single-use only
- Auth Token must be kept secret
- STOP replies are handled automatically by Twilio

## Troubleshooting

### SMS not sending?
- Check Twilio credentials are set correctly
- Verify phone number format (E.164)
- Check Twilio console for error logs
- Ensure account has credits/balance

### Verification code not received?
- Check phone number is correct
- Verify Twilio is configured
- Check SMS service logs
- Ensure phone number can receive SMS

### Can't enable SMS notifications?
- Phone number must be verified first
- Use `/api/auth/verify-phone` endpoint
- Check user has verified phone number

## Twilio Console Links

- **Dashboard**: https://console.twilio.com/us1/develop/console
- **Phone Numbers**: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
- **Logs**: https://console.twilio.com/us1/monitor/logs/sms
- **Account Settings**: https://console.twilio.com/us1/account/settings



