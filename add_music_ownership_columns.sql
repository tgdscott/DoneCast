-- Add is_global and owner_id columns to musicasset table
-- This fixes the "column musicasset.is_global does not exist" error

-- Add is_global column (defaults to FALSE for existing rows = admin/global assets)
ALTER TABLE musicasset 
ADD COLUMN IF NOT EXISTS is_global BOOLEAN DEFAULT FALSE NOT NULL;

-- Add owner_id column (defaults to NULL = global/admin-owned assets)
ALTER TABLE musicasset 
ADD COLUMN IF NOT EXISTS owner_id UUID DEFAULT NULL;

-- Add foreign key constraint for owner_id
ALTER TABLE musicasset 
ADD CONSTRAINT IF NOT EXISTS fk_musicasset_owner 
FOREIGN KEY (owner_id) REFERENCES "user"(id) ON DELETE SET NULL;

-- Create index on owner_id for performance
CREATE INDEX IF NOT EXISTS ix_musicasset_owner_id ON musicasset(owner_id);

-- Set all existing music assets to global (since they were admin-uploaded before user-owned music existed)
UPDATE musicasset SET is_global = TRUE WHERE is_global = FALSE;

-- Verification queries (run after migration)
-- SELECT COUNT(*) FROM musicasset;
-- SELECT COUNT(*) FROM musicasset WHERE is_global = TRUE;
-- SELECT COUNT(*) FROM musicasset WHERE owner_id IS NOT NULL;
