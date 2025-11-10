# Credit Viewing Guide

This document explains how users and admins can view credit usage in the system.

## For Users: Viewing Your Own Credits

### 1. Credit Balance & Usage Summary

**Endpoint:** `GET /api/billing/usage`

**Frontend:** Billing Page (`/billing`)

**What it shows:**
- Current credit balance
- Credits used this month
- Monthly breakdown by activity type:
  - Transcription
  - Assembly
  - TTS Generation
  - Auphonic Processing
  - Storage

**Example Response:**
```json
{
  "credits_balance": 15000.5,
  "credits_used_this_month": 5000.0,
  "credits_breakdown": {
    "transcription": 2000.0,
    "assembly": 1500.0,
    "tts_generation": 1000.0,
    "auphonic_processing": 500.0,
    "storage": 0.0
  }
}
```

### 2. Detailed Credit Ledger (Invoice View)

**Endpoint:** `GET /api/billing/ledger/summary?months_back=1`

**Frontend:** Credit Ledger Component (available in billing section)

**What it shows:**
- Episode-grouped charges (each episode like an invoice)
- Account-level charges (not tied to episodes)
- Detailed line items with:
  - Timestamp
  - Activity type
  - Credits charged/refunded
  - Notes
  - Cost breakdown (metadata)
- Summary stats:
  - Monthly allocation
  - Used this month
  - Remaining credits

**Features:**
- Expandable episode invoices
- Refund request functionality
- Filter by time period (1, 3, 6 months)

**Example Response:**
```json
{
  "total_credits_available": 28800.0,
  "total_credits_used_this_month": 5000.0,
  "total_credits_remaining": 23800.0,
  "episode_invoices": [
    {
      "episode_id": "uuid",
      "episode_title": "My Episode",
      "total_credits_charged": 150.0,
      "line_items": [
        {
          "timestamp": "2025-01-15T10:00:00Z",
          "reason": "TRANSCRIPTION",
          "credits": 60.0,
          "notes": "Transcription (60.0s processed)",
          "cost_breakdown": {
            "provider": "assemblyai",
            "duration_seconds": 60.0,
            "rate_per_sec": 1.0
          }
        }
      ]
    }
  ],
  "account_charges": []
}
```

### 3. Individual Episode Invoice

**Endpoint:** `GET /api/billing/ledger/episode/{episode_id}`

**What it shows:**
- All charges for a specific episode
- Line-by-line breakdown
- Total credits charged/refunded

---

## For Admins: Viewing Any User's Credits

### 1. Admin Credit Viewer

**Endpoint:** `GET /api/admin/users/{user_id}/credits`

**Frontend:** Admin Dashboard → Users Tab → "Credits" Button

**What it shows:**
- User information (email, name, tier)
- Current credit balance
- Monthly allocation (based on tier)
- Credits used this month
- Monthly breakdown by activity type
- Recent charges (last 20 transactions)

**How to Access:**
1. Go to Admin Dashboard
2. Navigate to "Users" tab
3. Find the user in the table
4. Click the "Credits" button (with coin icon)
5. Dialog will open showing credit details

**Example Response:**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tier": "pro",
  "credits_balance": 15000.5,
  "credits_allocated": 172800.0,
  "credits_used_this_month": 5000.0,
  "credits_breakdown": {
    "transcription": 2000.0,
    "assembly": 1500.0,
    "tts_generation": 1000.0,
    "auphonic_processing": 500.0,
    "storage": 0.0
  },
  "recent_charges": [
    {
      "id": 123,
      "timestamp": "2025-01-15T10:00:00Z",
      "episode_id": "uuid",
      "episode_title": "My Episode",
      "reason": "TRANSCRIPTION",
      "credits": 60.0,
      "direction": "DEBIT",
      "notes": "Transcription (60.0s processed)"
    }
  ]
}
```

### 2. Admin Dialog Features

The admin credit viewer dialog displays:
- **Summary Cards:**
  - Credit Balance
  - Monthly Allocation
  - Used This Month (with percentage)
  
- **Monthly Breakdown:**
  - Transcription credits
  - Assembly credits
  - TTS Generation credits
  - Auphonic Processing credits
  - Storage credits

- **Recent Charges Table:**
  - Date
  - Activity type (badge)
  - Episode title (if applicable)
  - Credits charged/refunded
  - Color-coded (red for debits, green for credits)

---

## API Endpoints Summary

### User Endpoints (Requires Authentication)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/billing/usage` | GET | Get credit balance and monthly usage summary |
| `/api/billing/ledger/summary` | GET | Get detailed ledger (invoice view) |
| `/api/billing/ledger/episode/{episode_id}` | GET | Get invoice for specific episode |

### Admin Endpoints (Requires Admin Role)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/users/{user_id}/credits` | GET | Get credit details for any user |

---

## Frontend Components

### User Components

1. **BillingPageEmbedded.jsx**
   - Shows credit balance
   - Monthly usage summary
   - Breakdown by activity type

2. **CreditLedger.jsx**
   - Detailed invoice view
   - Episode-grouped charges
   - Account-level charges
   - Refund request functionality

### Admin Components

1. **UsersTab.jsx**
   - User table with "Credits" button
   - Opens credit viewer dialog

2. **AdminDashboard.jsx**
   - Credit viewer dialog
   - Displays user credit details
   - Recent charges table

---

## Credit Breakdown by Activity

### Transcription
- **Rate:** 1 credit per second
- **Reason:** `TRANSCRIPTION`
- **Notes:** Includes processing time

### Assembly
- **Rate:** 3 credits per second
- **Reason:** `ASSEMBLY`
- **Notes:** Episode final assembly

### TTS Generation
- **Rate:** Varies by plan and provider
  - Standard TTS: 1 credit/second
  - ElevenLabs: 12-15 credits/second (plan-dependent)
- **Reason:** `TTS_GENERATION`
- **Notes:** Includes rounding for ElevenLabs (sum durations, then ceil)

### Auphonic Processing
- **Rate:** 1 credit per second (configurable)
- **Reason:** `AUPHONIC_PROCESSING`
- **Notes:** Additional processing add-on

### Storage
- **Rate:** 2 credits per GB per month
- **Reason:** `STORAGE`
- **Notes:** Cloud storage charges

---

## Cost Breakdown Metadata

Each ledger entry includes a `cost_breakdown` field with detailed metadata:

```json
{
  "provider": "elevenlabs",
  "raw_seconds": 3.2,
  "billed_seconds": 4,
  "rate_per_sec": 12,
  "total_credits": 48,
  "clip_count": 1
}
```

This allows users and admins to see:
- Actual duration vs billed duration (for rounding)
- Per-second rates
- Provider information
- Number of clips (for batched operations)

---

## Notes

- **Unlimited Plans:** Show balance as 999,999 credits (unlimited)
- **Free Tier:** No monthly allocation, credits can be purchased
- **Rollover:** Up to 10% of unused monthly credits roll over
- **Purchased Credits:** Never expire, used last (after monthly and rollover)

---

## Troubleshooting

### User can't see credits
- Check if user is authenticated
- Verify user has a tier assigned
- Check wallet exists (created automatically on first credit operation)

### Admin can't view user credits
- Verify admin role is assigned
- Check user exists
- Verify endpoint permissions

### Credits not updating
- Check if wallet service is running
- Verify ledger entries are being created
- Check database for `ProcessingMinutesLedger` entries

---

**Last Updated:** 2025-01-15



