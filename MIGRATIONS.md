# Database Schema Migrations

**Manual migration log for Podcast Plus Plus production database**

All migrations are executed manually via PGAdmin. This file documents schema changes for tracking and disaster recovery purposes.

---

## Migration 030 - User Soft Deletion Columns (Oct 25, 2025)

**Status:** ✅ Applied to production  
**Applied:** 2025-10-25  
**Reason:** Support user self-deletion feature with grace period

**Columns Added to `user` table:**
- `deletion_requested_at` (TIMESTAMP WITH TIME ZONE, nullable) - When deletion was requested
- `deletion_scheduled_for` (TIMESTAMP WITH TIME ZONE, nullable) - When actual deletion will occur (after grace period)
- `deletion_requested_by` (VARCHAR(10), nullable) - 'user' or 'admin' - determines if admin notification sent
- `deletion_reason` (TEXT, nullable) - Optional reason provided by user
- `is_deleted_view` (BOOLEAN, default FALSE, NOT NULL) - User-facing deleted state - blocks login

**SQL Executed:**
```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_requested_at'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_requested_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_scheduled_for'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_scheduled_for TIMESTAMP WITH TIME ZONE DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_requested_by'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_requested_by VARCHAR(10) DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_reason'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_reason TEXT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'is_deleted_view'
    ) THEN
        ALTER TABLE "user" ADD COLUMN is_deleted_view BOOLEAN DEFAULT FALSE NOT NULL;
    END IF;
END$$;
```

**Verification:**
```sql
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'user' 
  AND column_name IN ('deletion_requested_at', 'deletion_scheduled_for', 'deletion_requested_by', 'deletion_reason', 'is_deleted_view')
ORDER BY column_name;
```

**Files Modified:**
- `backend/api/models/user.py` - Added soft deletion fields to User model (lines 45-50)

**Incident:** This migration was created retroactively after production crash. Columns were added to model without database migration, causing `UndefinedColumn` errors that crashed all API requests.

**Rollback SQL (if needed):**
```sql
ALTER TABLE "user" DROP COLUMN IF EXISTS deletion_requested_at;
ALTER TABLE "user" DROP COLUMN IF EXISTS deletion_scheduled_for;
ALTER TABLE "user" DROP COLUMN IF EXISTS deletion_requested_by;
ALTER TABLE "user" DROP COLUMN IF EXISTS deletion_reason;
ALTER TABLE "user" DROP COLUMN IF EXISTS is_deleted_view;
```

---

## Template for Future Migrations

```markdown
## Migration XXX - [Description] (MMM DD, YYYY)

**Status:** ✅ Applied / ⏳ Pending / ❌ Rolled back  
**Applied:** YYYY-MM-DD  
**Reason:** [Why this change was needed]

**Changes:**
- [What was changed]

**SQL Executed:**
```sql
[SQL code here]
```

**Verification:**
```sql
[Verification query]
```

**Files Modified:**
- [List of code files that reference these schema changes]

**Rollback SQL (if needed):**
```sql
[Rollback commands]
```
```

---

**Note:** Always test migrations on a dev/staging database before applying to production. Use idempotent SQL (IF NOT EXISTS checks) to allow safe re-runs.
