# Bi-Weekly and Monthly Scheduling Support

## Status: DEFERRED (Post-Launch)

## Overview
The onboarding wizard UI already supports bi-weekly and monthly publishing frequencies, but the backend scheduling system only supports weekly schedules. This document outlines what needs to be implemented to fully support bi-weekly and monthly recurring schedules.

## Current State

### Frontend (Already Supports)
- **File**: `frontend/src/pages/onboarding/steps/PublishCadenceStep.jsx`
  - Dropdown includes: `day`, `week`, `bi-weekly`, `month`, `year`
  - Users can select bi-weekly or monthly frequency

- **File**: `frontend/src/pages/onboarding/steps/PublishScheduleStep.jsx`
  - Shows weekday picker for `freqUnit === "week"`
  - Shows calendar date picker for `freqUnit === "bi-weekly" || freqUnit === "month"`
  - Stores selected dates in `selectedDates` array

- **File**: `frontend/src/pages/onboarding/hooks/useOnboardingWizard.jsx`
  - Collects `freqUnit`, `freqCount`, `selectedWeekdays`, `selectedDates`
  - **ISSUE**: This data is NOT currently saved when finishing onboarding
  - Users must manually set up scheduling later in the template editor

### Backend (Weekly Only)

#### Database Model
- **File**: `backend/api/models/recurring.py`
  - `RecurringScheduleBase` only has:
    - `day_of_week: int` (0=Monday .. 6=Sunday)
    - `time_of_day: time`
  - No fields for schedule type, day of month, or bi-weekly patterns

#### Calculation Logic
- **File**: `backend/api/routers/recurring.py`
  - `_compute_next_occurrence()` function:
    - Only handles weekly schedules (increments by 7 days)
    - Uses `day_of_week` to find next occurrence
    - Line 147-151: Calculates days ahead, then adds 7 days if in past
    - Line 165: Always increments by `timedelta(days=7)`

#### API Endpoints
- **File**: `backend/api/routers/recurring.py`
  - `replace_template_schedules()` expects `day_of_week` in payload
  - No support for different schedule types

## Required Changes

### 1. Database Migration

**New Migration File**: `backend/migrations/042_add_schedule_types.py`

Add columns to `recurring_schedule` table:
```python
- schedule_type: VARCHAR(20) DEFAULT 'weekly'  # 'weekly', 'bi_weekly', 'monthly'
- day_of_month: INTEGER NULL  # 1-31 for monthly schedules
- bi_weekly_start_date: DATE NULL  # Reference date for bi-weekly pattern
```

**Update Model**: `backend/api/models/recurring.py`
- Add fields to `RecurringScheduleBase`:
  ```python
  schedule_type: str = Field(default="weekly", description="weekly|bi_weekly|monthly")
  day_of_month: Optional[int] = Field(default=None, ge=1, le=31)
  bi_weekly_start_date: Optional[date] = None
  ```

### 2. Update Calculation Logic

**File**: `backend/api/routers/recurring.py`

Modify `_compute_next_occurrence()` to handle:
- **Bi-weekly**: Find next occurrence 14 days from last scheduled date
- **Monthly**: Find next occurrence on same day of month (handle month-end edge cases)
  - If day_of_month=31 and month only has 30 days, use last day of month
  - If day_of_month=29 and February in non-leap year, use Feb 28

### 3. Update API Endpoints

**File**: `backend/api/routers/recurring.py`

- Update `ScheduleSlotPayload` model to accept:
  - `schedule_type: Optional[str]`
  - `day_of_month: Optional[int]`
  - `bi_weekly_start_date: Optional[str]`

- Update `replace_template_schedules()` to:
  - Save new fields when creating/updating schedules
  - Validate schedule_type matches the data provided

### 4. Frontend: Save Scheduling Data

**File**: `frontend/src/pages/onboarding/hooks/useOnboardingWizard.jsx`

In `handleFinish()` function (around line 700-720):
- After creating template, create recurring schedules
- Convert `selectedWeekdays` to schedule slots for weekly
- Convert `selectedDates` to schedule slots for bi-weekly/monthly
- Call `/api/recurring/templates/{template_id}/schedules` endpoint

**Example logic needed**:
```javascript
if (freqUnit === "week" && selectedWeekdays.length > 0 && !notSureSchedule) {
  // Create weekly schedules for each selected weekday
  const schedules = selectedWeekdays.map(day => ({
    day_of_week: WEEKDAYS.indexOf(day),
    time_of_day: "09:00", // Default or from user preference
    schedule_type: "weekly"
  }));
  await makeApi(token).put(`/api/recurring/templates/${templateId}/schedules`, {
    schedules,
    timezone: resolvedTimezone
  });
} else if ((freqUnit === "bi-weekly" || freqUnit === "month") && selectedDates.length > 0 && !notSureSchedule) {
  // Create schedules for selected dates
  // For bi-weekly: calculate pattern from first date
  // For monthly: extract day_of_month from dates
}
```

### 5. Template Editor Updates

**File**: `frontend/src/components/dashboard/template-editor/pages/TemplateSchedulePage.jsx`

- Update UI to show schedule type selector
- Show appropriate input (weekday picker vs calendar) based on schedule type
- Allow editing existing schedules with different types

## Edge Cases to Handle

1. **Monthly schedules with day_of_month > 28**:
   - Feb: Use last day if day_of_month > 28
   - 30-day months: Use last day if day_of_month = 31

2. **Bi-weekly pattern**:
   - Need to store reference date or pattern
   - Calculate next occurrence: last_date + 14 days
   - Handle cases where user selects multiple dates (use first as reference?)

3. **Timezone handling**:
   - Ensure day_of_month calculations respect user's timezone
   - Monthly schedules should use local date, not UTC

4. **Migration of existing schedules**:
   - All existing schedules are weekly
   - Set `schedule_type = 'weekly'` for existing records

## Testing Checklist

- [ ] Weekly schedules still work (backward compatibility)
- [ ] Bi-weekly schedules calculate next occurrence correctly
- [ ] Monthly schedules handle month-end edge cases
- [ ] Onboarding wizard saves scheduling data
- [ ] Template editor can create/edit bi-weekly/monthly schedules
- [ ] Next occurrence calculation respects timezone
- [ ] Conflict detection works for all schedule types

## Estimated Effort

- Database migration: 30 minutes
- Model updates: 30 minutes
- Calculation logic: 2-3 hours (edge cases)
- API endpoint updates: 1 hour
- Frontend onboarding save: 1 hour
- Template editor updates: 1-2 hours
- Testing: 1 hour

**Total: 6-8 hours**

## Related Files

### Backend
- `backend/api/models/recurring.py` - Database model
- `backend/api/routers/recurring.py` - API endpoints and calculation logic
- `backend/migrations/` - New migration file needed

### Frontend
- `frontend/src/pages/onboarding/steps/PublishCadenceStep.jsx` - Frequency selection
- `frontend/src/pages/onboarding/steps/PublishScheduleStep.jsx` - Schedule selection UI
- `frontend/src/pages/onboarding/hooks/useOnboardingWizard.jsx` - Onboarding logic (needs save functionality)
- `frontend/src/components/dashboard/template-editor/pages/TemplateSchedulePage.jsx` - Template editor scheduling UI

## Notes

- The UI is already built, so this is primarily backend work
- Consider if "bi-weekly" means "every 2 weeks" or "twice per week" - current UI suggests "every 2 weeks"
- May want to add "twice per week" as a separate option if needed
- Yearly schedules are in the dropdown but not implemented - consider removing or implementing




