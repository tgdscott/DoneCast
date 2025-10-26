-- Migration: Add user soft deletion fields
-- Created: 2025-10-25
-- Purpose: Enable user self-deletion with grace period

-- Add soft deletion tracking fields
DO $$
BEGIN
    -- deletion_requested_at: When user or admin requested deletion
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_requested_at'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_requested_at TIMESTAMP;
    END IF;

    -- deletion_scheduled_for: When actual deletion will occur (after grace period)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_scheduled_for'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_scheduled_for TIMESTAMP;
    END IF;

    -- deletion_requested_by: 'user' or 'admin' (determines if admin notification sent)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_requested_by'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_requested_by VARCHAR(10);
    END IF;

    -- deletion_reason: Optional reason provided by user
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'deletion_reason'
    ) THEN
        ALTER TABLE "user" ADD COLUMN deletion_reason TEXT;
    END IF;

    -- is_deleted_view: User-facing "deleted" state (blocks login, appears deleted to user)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'is_deleted_view'
    ) THEN
        ALTER TABLE "user" ADD COLUMN is_deleted_view BOOLEAN DEFAULT FALSE;
    END IF;
END$$;

-- Create index for cleanup job performance
-- Only index rows that are pending deletion (scheduled but not yet deleted)
CREATE INDEX IF NOT EXISTS idx_user_deletion_scheduled 
ON "user" (deletion_scheduled_for) 
WHERE deletion_scheduled_for IS NOT NULL AND is_deleted_view = TRUE;

-- Verify migration
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'user' 
AND column_name IN (
    'deletion_requested_at',
    'deletion_scheduled_for', 
    'deletion_requested_by',
    'deletion_reason',
    'is_deleted_view'
)
ORDER BY column_name;

-- Verify index creation
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'user'
AND indexname = 'idx_user_deletion_scheduled';
