-- Database Migration 100: Add Persistent Audio Quality Columns
-- Date: December 9, 2025
-- Status: Ready for production deployment
--
-- PURPOSE:
--   Add three new JSONB columns to mediaitem table for durable persistence
--   of audio quality analysis metrics and routing decisions.
--
-- COLUMNS:
--   1. audio_quality_metrics_json (jsonb) - Analyzer metrics (LUFS, SNR, dnsmos, duration, etc.)
--   2. audio_quality_label (varchar) - Quality tier (good, slightly_bad, ..., abysmal)
--   3. audio_processing_decision_json (jsonb) - Decision helper output {use_auphonic, decision, reason}
--
-- SAFETY:
--   - Idempotent (IF NOT EXISTS checks)
--   - Safe to run multiple times
--   - No data loss
--   - Backward compatible (columns default to NULL)

-- ============================================================================
-- APPLY THIS MIGRATION
-- ============================================================================

-- Add audio quality metrics column (JSON blob with analyzer output)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_metrics_json'
    ) THEN
        ALTER TABLE mediaitem ADD COLUMN audio_quality_metrics_json jsonb DEFAULT NULL;
        COMMENT ON COLUMN mediaitem.audio_quality_metrics_json IS 
            'JSON output from audio quality analyzer: {lufs, snr, dnsmos, duration, bit_depth, sample_rate, channels}';
    END IF;
END$$;

-- Add audio quality label column (tier label)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_label'
    ) THEN
        ALTER TABLE mediaitem ADD COLUMN audio_quality_label varchar(50) DEFAULT NULL;
        COMMENT ON COLUMN mediaitem.audio_quality_label IS 
            'Audio quality tier: good, slightly_bad, fairly_bad, very_bad, incredibly_bad, abysmal, unknown';
    END IF;
END$$;

-- Add audio processing decision column (full decision output)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_processing_decision_json'
    ) THEN
        ALTER TABLE mediaitem ADD COLUMN audio_processing_decision_json jsonb DEFAULT NULL;
        COMMENT ON COLUMN mediaitem.audio_processing_decision_json IS 
            'JSON output from decision helper: {use_auphonic: bool, decision: "standard"|"advanced"|"ask", reason: string}';
    END IF;
END$$;

-- ============================================================================
-- VERIFICATION: Confirm columns exist
-- ============================================================================

SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'mediaitem'
AND column_name IN ('audio_quality_metrics_json', 'audio_quality_label', 'audio_processing_decision_json')
ORDER BY ordinal_position;

-- Expected output:
-- column_name | data_type | is_nullable | column_default
-- ------------|-----------|-------------|---------------
-- audio_quality_metrics_json | jsonb | YES | NULL
-- audio_quality_label | character varying | YES | NULL
-- audio_processing_decision_json | jsonb | YES | NULL

-- ============================================================================
-- SAMPLE QUERY: View audio quality metrics for recent uploads
-- ============================================================================

SELECT 
    id,
    filename,
    friendly_name,
    audio_quality_label,
    audio_quality_metrics_json->>'lufs' AS lufs,
    audio_quality_metrics_json->>'duration' AS duration_seconds,
    audio_processing_decision_json->>'decision' AS decision,
    audio_processing_decision_json->>'reason' AS reason,
    created_at
FROM mediaitem
WHERE audio_quality_label IS NOT NULL
ORDER BY created_at DESC
LIMIT 20;

-- ============================================================================
-- SAMPLE QUERY: Audit Auphonic routing decisions
-- ============================================================================

SELECT 
    audio_quality_label,
    audio_processing_decision_json->>'use_auphonic' AS use_auphonic,
    audio_processing_decision_json->>'reason' AS decision_reason,
    COUNT(*) AS count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS percentage
FROM mediaitem
WHERE audio_quality_label IS NOT NULL
GROUP BY audio_quality_label, audio_processing_decision_json->>'use_auphonic', audio_processing_decision_json->>'reason'
ORDER BY count DESC;

-- ============================================================================
-- SAMPLE QUERY: Find all bad quality audio routed to Auphonic
-- ============================================================================

SELECT 
    id,
    filename,
    friendly_name,
    audio_quality_label,
    audio_quality_metrics_json->>'lufs' AS lufs,
    created_at
FROM mediaitem
WHERE audio_quality_label IN ('very_bad', 'incredibly_bad', 'abysmal')
AND audio_processing_decision_json->>'use_auphonic' = 'true'
ORDER BY created_at DESC
LIMIT 50;

-- ============================================================================
-- SAMPLE QUERY: Performance impact - check index usage
-- ============================================================================

-- Note: Consider adding indexes on quality_label and decision fields if queries slow
-- CREATE INDEX idx_mediaitem_quality_label ON mediaitem(audio_quality_label);
-- CREATE INDEX idx_mediaitem_decision ON mediaitem USING gin(audio_processing_decision_json);

-- ============================================================================
-- ROLLBACK (EMERGENCY ONLY - NOT RECOMMENDED)
-- ============================================================================
--
-- DO NOT run unless instructed. This will DELETE all audio quality data.
--
-- DO $$
-- BEGIN
--     IF EXISTS (
--         SELECT 1 FROM information_schema.columns
--         WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_metrics_json'
--     ) THEN
--         ALTER TABLE mediaitem DROP COLUMN audio_quality_metrics_json;
--     END IF;
--     
--     IF EXISTS (
--         SELECT 1 FROM information_schema.columns
--         WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_label'
--     ) THEN
--         ALTER TABLE mediaitem DROP COLUMN audio_quality_label;
--     END IF;
--     
--     IF EXISTS (
--         SELECT 1 FROM information_schema.columns
--         WHERE table_name = 'mediaitem' AND column_name = 'audio_processing_decision_json'
--     ) THEN
--         ALTER TABLE mediaitem DROP COLUMN audio_processing_decision_json;
--     END IF;
-- END$$;

-- ============================================================================
-- Migration Status
-- ============================================================================
-- Last verified: 2025-12-09
-- Environment: production (Cloud SQL Postgres 14+)
-- Idempotent: YES (safe to re-run)
-- Rollback: Available (see above)
-- Duration: < 1 second
-- Impact: Zero (adds NULL columns, no data migration needed)
