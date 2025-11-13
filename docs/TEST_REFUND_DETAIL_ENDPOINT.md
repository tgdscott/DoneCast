# Testing Refund Request Detail Endpoint

## Endpoint
`GET /api/admin/users/refund-requests/{notification_id}/detail`

## Quick Test (PowerShell)

```powershell
# 1. Get your auth token (from browser localStorage or login)
$token = "your-auth-token-here"

# 2. Get list of refund requests first
$refundRequests = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/users/refund-requests" `
  -Method GET `
  -Headers @{"Authorization" = "Bearer $token"} `
  -ContentType "application/json"

# 3. Get detail for first refund request
$notificationId = $refundRequests[0].notification_id
$detail = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/users/refund-requests/$notificationId/detail" `
  -Method GET `
  -Headers @{"Authorization" = "Bearer $token"} `
  -ContentType "application/json"

# 4. View the comprehensive data
$detail | ConvertTo-Json -Depth 10
```

## What You Get

The endpoint returns a comprehensive `RefundRequestDetail` object with:

### User Context
- Account creation date
- Subscription tier and expiration
- Credit balance and usage (all-time, this month)
- Previous refund history (count, total credits, last refund date)
- Account status

### Episode Context (if applicable)
- Episode title, number, season
- Podcast title
- Episode status and processing timestamps
- Duration and audio file status
- Published status
- Error messages

### Ledger Entries
- All charges being requested for refund
- Cost breakdowns (base credits, multipliers)
- Credit sources (monthly, add-on, rollover)
- Timestamps and correlation IDs
- Notes per charge

### Time Analysis
- Days since charges occurred
- Hours since refund request submitted
- Eligibility warnings based on timing

### Business Context
- Refund eligibility notes (warnings about old charges, high-frequency requests, etc.)
- Credit source breakdown
- Episode processing success status
- Episode restore capability

## Example Response

```json
{
  "notification_id": "123e4567-e89b-12d3-a456-426614174000",
  "request_created_at": "2025-11-10T18:00:00Z",
  "user_reason": "Because I want to.",
  "user": {
    "user_id": "user-id",
    "email": "user@example.com",
    "tier": "pro",
    "account_created_at": "2025-01-01T00:00:00Z",
    "total_credits_used_all_time": 5000.0,
    "total_credits_used_this_month": 1571.9,
    "current_credit_balance": 999999.0,
    "previous_refund_count": 2,
    "previous_refund_total_credits": 100.0
  },
  "episode": {
    "id": "episode-id",
    "title": "My Episode",
    "status": "published",
    "has_final_audio": true,
    "is_published": true
  },
  "ledger_entries": [
    {
      "id": 123,
      "timestamp": "2025-11-10T12:00:00Z",
      "direction": "DEBIT",
      "reason": "TRANSCRIPTION",
      "credits": 1471.9,
      "cost_breakdown": {
        "base_credits": 1471.9,
        "multipliers": {},
        "total": 1471.9
      }
    }
  ],
  "total_credits_requested": 1571.9,
  "days_since_charges": 0.5,
  "hours_since_request": 2.5,
  "refund_eligibility_notes": [
    "Episode is published - refund may impact published content"
  ]
}
```

## Using This Data

With this information, you can:

1. **Check user history**: Is this a repeat requester? New user?
2. **Verify episode status**: Was it successfully processed? Published?
3. **Check timing**: How old are the charges? Recent or weeks old?
4. **Understand impact**: How many credits? What services were used?
5. **Identify risks**: Published episodes, high-frequency requests, etc.
6. **Make informed decision**: Approve, deny, or request more info

