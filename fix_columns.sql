-- Add missing columns to episode table
ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_audio_path VARCHAR;
ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_cover_path VARCHAR;
ALTER TABLE episode ADD COLUMN IF NOT EXISTS has_numbering_conflict BOOLEAN DEFAULT FALSE;
