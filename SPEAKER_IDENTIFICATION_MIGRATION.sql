-- Speaker Identification Feature Migration
-- Adds support for voice-based speaker identification in transcripts
-- 
-- User flow:
-- 1. Hosts record "Hi, my name is Scott" intros (stored in podcast.speaker_intros)
-- 2. Guests record similar intros per-episode (stored in episode.guest_intros)
-- 3. System prepends these intros before main content for transcription
-- 4. AssemblyAI diarization learns voices from intros
-- 5. Post-processing maps "Speaker A/B/C" to actual names
--
-- Date: October 27, 2025

-- ============================================================
-- Add speaker identification columns to podcast table
-- ============================================================

DO $$
BEGIN
    -- Add has_guests flag
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'podcast' AND column_name = 'has_guests'
    ) THEN
        ALTER TABLE podcast ADD COLUMN has_guests BOOLEAN DEFAULT FALSE NOT NULL;
        COMMENT ON COLUMN podcast.has_guests IS 'True if this podcast regularly features guests (enables per-episode guest configuration)';
    END IF;

    -- Add speaker_intros JSONB column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'podcast' AND column_name = 'speaker_intros'
    ) THEN
        ALTER TABLE podcast ADD COLUMN speaker_intros JSONB DEFAULT NULL;
        COMMENT ON COLUMN podcast.speaker_intros IS 'Voice intro files for host speaker identification - format: {"hosts": [{"name": "Scott", "gcs_path": "gs://...", "duration_ms": 2000}]}';
    END IF;
END$$;

-- ============================================================
-- Add speaker identification columns to episode table
-- ============================================================

DO $$
BEGIN
    -- Add guest_intros JSONB column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'episode' AND column_name = 'guest_intros'
    ) THEN
        ALTER TABLE episode ADD COLUMN guest_intros JSONB DEFAULT NULL;
        COMMENT ON COLUMN episode.guest_intros IS 'Per-episode guest voice intros for speaker identification - format: [{"name": "Sarah", "gcs_path": "gs://...", "duration_ms": 2000}]';
    END IF;
END$$;

-- ============================================================
-- Verification Queries
-- ============================================================

-- Verify podcast columns
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'podcast' 
  AND column_name IN ('has_guests', 'speaker_intros')
ORDER BY column_name;

-- Verify episode columns
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'episode' 
  AND column_name = 'guest_intros'
ORDER BY column_name;

-- ============================================================
-- Sample Data Queries (for testing)
-- ============================================================

-- Check if any podcasts have speaker intros configured
SELECT 
    id,
    name,
    has_guests,
    speaker_intros IS NOT NULL as has_speaker_config,
    speaker_intros
FROM podcast
WHERE speaker_intros IS NOT NULL
LIMIT 5;

-- Check if any episodes have guest intros
SELECT 
    e.id,
    e.title,
    p.name as podcast_name,
    e.guest_intros IS NOT NULL as has_guests,
    e.guest_intros
FROM episode e
JOIN podcast p ON e.podcast_id = p.id
WHERE e.guest_intros IS NOT NULL
LIMIT 5;

-- ============================================================
-- Rollback (if needed)
-- ============================================================

-- CAUTION: Only run this if you need to completely remove the feature
-- This will delete all speaker configuration data!

/*
DO $$
BEGIN
    -- Remove podcast columns
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'podcast' AND column_name = 'has_guests'
    ) THEN
        ALTER TABLE podcast DROP COLUMN has_guests;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'podcast' AND column_name = 'speaker_intros'
    ) THEN
        ALTER TABLE podcast DROP COLUMN speaker_intros;
    END IF;

    -- Remove episode columns
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'episode' AND column_name = 'guest_intros'
    ) THEN
        ALTER TABLE episode DROP COLUMN guest_intros;
    END IF;
END$$;
*/
