# LLM Metadata Generation Billing Proposal

## Overview

LLM-generated titles, tags, and descriptions incur API costs (Gemini/Groq/OpenAI). While individual costs are small (~$0.001-0.002 per generation), they can accumulate with regenerations and should be tracked in the credit system.

## Cost Analysis

### Current Usage Patterns

Based on code analysis:

1. **Title Generation** (`/api/ai/title`)
   - Input: ~20,000 characters (transcript excerpt + prompt)
   - Output: ~128 tokens max (~512 characters)
   - Estimated tokens: ~5,000 input, ~128 output
   - Cost (Gemini): ~$0.0004 input + $0.00004 output = **~$0.00044**

2. **Description/Notes Generation** (`/api/ai/notes`)
   - Input: ~40,000 characters (longer transcript excerpt)
   - Output: ~768 tokens max (~3,000 characters)
   - Estimated tokens: ~10,000 input, ~500 output
   - Cost (Gemini): ~$0.00075 input + $0.00015 output = **~$0.0009**

3. **Tags Generation** (`/api/ai/tags`)
   - Input: ~20,000 characters (similar to title)
   - Output: ~100 tokens (~400 characters)
   - Estimated tokens: ~5,000 input, ~100 output
   - Cost (Gemini): ~$0.0004 input + $0.00003 output = **~$0.00043**

**Total per episode (all three):** ~$0.00177

### Credit Value Context

- Starter plan: $19/month = 28,800 credits → **$0.00066 per credit**
- Creator plan: $39/month = 72,000 credits → **$0.00054 per credit**
- Pro plan: $79/month = 172,800 credits → **$0.00046 per credit**
- Executive plan: $129/month = 288,000 credits → **$0.00045 per credit**

## Recommended Credit Rates

### Option 1: Flat Rate Per Generation (Recommended)

Simple, predictable, easy to understand:

- **Title generation:** 1 credit
- **Description/Notes generation:** 2 credits
- **Tags generation:** 1 credit

**Rationale:**
- Covers costs with ~2-3x margin (accounts for provider variations, future price increases)
- Simple mental model: "1-2 credits per AI suggestion"
- Low enough that regenerations aren't prohibitive
- High enough to discourage abuse

### Option 2: Token-Based (More Accurate, More Complex)

Calculate based on actual token usage:

```python
# Estimated rates per 1K tokens
INPUT_RATE = 0.1  # credits per 1K input tokens
OUTPUT_RATE = 0.5  # credits per 1K output tokens

# Example: Title generation
input_tokens = 5000  # ~20k chars
output_tokens = 128
credits = (input_tokens / 1000 * INPUT_RATE) + (output_tokens / 1000 * OUTPUT_RATE)
# = 0.5 + 0.064 = ~0.56 credits → round to 1 credit
```

**Pros:** More accurate, scales with actual usage
**Cons:** More complex, requires token counting, harder to explain to users

### Option 3: Tiered Rates (Plan-Based)

Higher tiers get slightly better rates (encourages upgrades):

- **Starter:** Title 1, Notes 2, Tags 1
- **Creator:** Title 1, Notes 2, Tags 1 (same)
- **Pro:** Title 0.5, Notes 1.5, Tags 0.5
- **Executive:** Title 0.5, Notes 1, Tags 0.5

**Pros:** Incentivizes upgrades
**Cons:** More complex, may feel unfair to lower tiers

## Recommendation: Option 1 (Flat Rate)

**Suggested rates:**
- Title: **1 credit**
- Description/Notes: **2 credits**
- Tags: **1 credit**

**Why:**
1. Simple and transparent
2. Covers costs with reasonable margin
3. Easy to implement
4. Easy to explain to users
5. Low enough for experimentation/regeneration
6. High enough to prevent abuse

## Implementation Plan

### 1. Add New Ledger Reason

```python
# backend/api/models/usage.py
class LedgerReason(str, Enum):
    # ... existing reasons ...
    AI_METADATA_GENERATION = "AI_METADATA_GENERATION"  # New
```

### 2. Add Rates to Plans Config

```python
# backend/api/billing/plans.py
RATES_AI_METADATA: Dict[str, int] = {
    "title": 1,
    "description": 2,
    "tags": 1,
}
```

### 3. Create Charging Function

```python
# backend/api/services/billing/credits.py
def charge_for_ai_metadata(
    session: Session,
    user: User,
    metadata_type: str,  # "title", "description", "tags"
    episode_id: Optional[UUID] = None,
    notes: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> ProcessingMinutesLedger:
    """
    Charge credits for AI-generated metadata.
    
    Args:
        session: Database session
        user: User to charge
        metadata_type: Type of metadata ("title", "description", "tags")
        episode_id: Optional episode this is for
        notes: Optional notes
        correlation_id: Optional idempotency key
    
    Returns:
        Ledger entry
    """
    from api.billing.plans import RATES_AI_METADATA
    
    rate = RATES_AI_METADATA.get(metadata_type, 1)
    
    return charge_credits(
        session=session,
        user_id=user.id,
        credits=rate,
        reason=LedgerReason.AI_METADATA_GENERATION,
        episode_id=episode_id,
        notes=notes or f"AI {metadata_type} generation",
        correlation_id=correlation_id
    )
```

### 4. Wire into AI Endpoints

Update the three AI suggestion endpoints to charge credits:

```python
# backend/api/routers/ai_suggestions.py
from api.services.billing import credits as billing_credits
from api.models.usage import LedgerReason
import uuid

@router.post("/title", response_model=SuggestTitleOut)
def post_title(
    request: Request,
    inp: SuggestTitleIn,
    current_user: User = Depends(get_current_user),  # Add auth
    session: Session = Depends(get_session)
) -> SuggestTitleOut:
    # Generate correlation ID for idempotency
    correlation_id = f"ai_title_{inp.episode_id}_{uuid.uuid4()}"
    
    try:
        result = generate_title(inp, session)
        
        # Charge credits AFTER successful generation
        billing_credits.charge_for_ai_metadata(
            session=session,
            user=current_user,
            metadata_type="title",
            episode_id=inp.episode_id if hasattr(inp, 'episode_id') else None,
            notes=f"AI title generation: {result.title[:50]}",
            correlation_id=correlation_id
        )
        session.commit()
        
        return result
    except Exception as e:
        # Don't charge on errors
        # ... existing error handling ...
```

**Important:** Only charge on successful generation, not on errors.

### 5. Handle Regenerations

**Option A: Charge Every Time (Recommended)**
- User clicks "Regenerate" → new charge
- Simple, fair (they're using the service again)
- Prevents abuse

**Option B: Free Regenerations Within Time Window**
- First generation: charge
- Regenerations within 5 minutes: free
- More complex, may encourage gaming

**Recommendation: Option A** - Charge every time. It's only 1-2 credits, and prevents abuse.

### 6. Idempotency

Use correlation IDs to prevent double-charging on retries:

```python
correlation_id = f"ai_{metadata_type}_{episode_id}_{timestamp}"
```

The ledger already has a unique constraint on `correlation_id` for DEBIT entries.

### 7. Cost Breakdown Metadata

Include metadata in `cost_breakdown_json`:

```python
cost_breakdown = {
    "type": "ai_metadata",
    "metadata_type": "title",  # or "description", "tags"
    "provider": "gemini",  # or "groq", etc.
    "estimated_input_tokens": 5000,
    "estimated_output_tokens": 128,
    "credits_charged": 1
}
```

## Edge Cases

### 1. Failed Generations
- **Don't charge** if generation fails
- Only charge on successful response

### 2. Content Blocked (Gemini Safety)
- If AI blocks content and returns fallback message → **don't charge**
- User didn't get value, shouldn't pay

### 3. Stub Mode / Dev Mode
- If `AI_STUB_MODE=1` or dev environment → **don't charge**
- No actual API call made

### 4. Batch Operations
- If user generates all three at once → charge separately (3 + 2 + 1 = 6 credits total)
- Each is a separate API call with separate costs

### 5. Unlimited Plans
- Still track usage (for reporting)
- Don't block (wallet can go negative)
- Log for admin visibility

## User Experience Considerations

### 1. Transparency
- Show credit cost before generation (optional)
- Show in ledger with clear description
- Include in cost breakdown metadata

### 2. Error Handling
- If insufficient credits, show clear message:
  "You need 1 credit to generate a title. Current balance: 0.5 credits."
- Link to billing/upgrade page

### 3. UI Indicators
- Show credit cost in tooltip/button
- Example: "Generate Title (1 credit)"
- Or: "Regenerate (1 credit)"

### 4. Analytics
- Track in usage breakdown as "AI Metadata"
- Show in admin dashboard
- Help identify heavy users

## Migration Considerations

### Existing Users
- No retroactive charges
- Only charge going forward
- Existing metadata remains free

### Testing
- Unit tests for charging logic
- Integration tests for endpoints
- Test idempotency (same correlation_id twice)
- Test error cases (don't charge on failure)

## Monitoring & Alerts

### Metrics to Track
1. Total AI metadata charges per day/week/month
2. Average credits per user per month for AI metadata
3. Regeneration rate (how often users regenerate)
4. Failed generation rate (shouldn't charge)

### Alerts
- If AI metadata costs spike unexpectedly
- If regeneration rate is suspiciously high (possible abuse)

## Future Enhancements

### 1. Bulk Discounts
- Generate all three at once: 3 credits (instead of 4)
- Encourages using all features

### 2. Free Tier Allowance
- Free tier: 10 free AI generations per month
- Then charge per use
- Encourages trying the feature

### 3. Plan-Based Limits
- Starter: 50 AI generations/month included
- Creator: 100/month
- Pro: Unlimited
- Executive: Unlimited

### 4. Token-Based Pricing (Advanced)
- If costs become significant, switch to token-based
- More accurate but more complex

## Summary

**Recommended Approach:**
- **Title:** 1 credit
- **Description:** 2 credits  
- **Tags:** 1 credit
- Charge every generation (including regenerations)
- Only charge on successful generation
- Use correlation IDs for idempotency
- Track in ledger with clear metadata

**Total cost per episode (all three):** 4 credits
**At $0.00066/credit (Starter):** ~$0.0026 per episode
**Covers actual API costs with ~1.5x margin**

This approach is:
- ✅ Simple to implement
- ✅ Fair to users
- ✅ Covers costs
- ✅ Prevents abuse
- ✅ Easy to explain

---

**Next Steps:**
1. Review and approve rates
2. Implement charging function
3. Wire into AI endpoints
4. Add UI indicators
5. Test thoroughly
6. Deploy and monitor

