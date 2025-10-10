-- Add iTunes-specific fields to podcast and episode tables
-- Migration: add_itunes_fields
-- Date: 2025-10-10

-- Add is_explicit and itunes_category to podcast table
ALTER TABLE podcast 
ADD COLUMN IF NOT EXISTS is_explicit BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS itunes_category VARCHAR(100) DEFAULT 'Technology';

-- Add episode_type to episode table
ALTER TABLE episode
ADD COLUMN IF NOT EXISTS episode_type VARCHAR(20) DEFAULT 'full';

-- Add check constraint for episode_type
ALTER TABLE episode
ADD CONSTRAINT episode_type_check 
CHECK (episode_type IN ('full', 'trailer', 'bonus') OR episode_type IS NULL);

-- Comment on new columns
COMMENT ON COLUMN podcast.is_explicit IS 'Podcast contains explicit content (iTunes)';
COMMENT ON COLUMN podcast.itunes_category IS 'Primary iTunes category for podcast directory';
COMMENT ON COLUMN episode.episode_type IS 'iTunes episode type: full, trailer, or bonus';
