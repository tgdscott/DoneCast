"""Migration 100: Add persistent audio quality & decision columns to mediaitem.

Adds three new columns to support durable persistence of audio quality analysis
and Auphonic routing decisions:
  - audio_quality_metrics_json (jsonb): Analyzer output (LUFS, SNR, dnsmos, etc.)
  - audio_quality_label (varchar): Quality tier (good, slightly_bad, ..., abysmal)
  - audio_processing_decision_json (jsonb): Full decide_audio_processing() output

Idempotent: Uses IF NOT EXISTS; safe to run multiple times.
Rollback: DROP COLUMN statements included at bottom.
"""

MIGRATION_SQL = """
-- Add three new columns to mediaitem table for audio quality and routing decisions
DO $$
BEGIN
    -- audio_quality_metrics_json: JSON blob with analyzer output
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_metrics_json'
    ) THEN
        ALTER TABLE mediaitem ADD COLUMN audio_quality_metrics_json jsonb DEFAULT NULL;
        COMMENT ON COLUMN mediaitem.audio_quality_metrics_json IS 'JSON output from audio quality analyzer: LUFS, SNR, dnsmos, duration, etc.';
    END IF;
    
    -- audio_quality_label: Quality tier (good, slightly_bad, fairly_bad, very_bad, incredibly_bad, abysmal)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_label'
    ) THEN
        ALTER TABLE mediaitem ADD COLUMN audio_quality_label varchar(50) DEFAULT NULL;
        COMMENT ON COLUMN mediaitem.audio_quality_label IS 'Audio quality tier label: good, slightly_bad, fairly_bad, very_bad, incredibly_bad, abysmal, unknown';
    END IF;
    
    -- audio_processing_decision_json: Full output from decide_audio_processing()
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_processing_decision_json'
    ) THEN
        ALTER TABLE mediaitem ADD COLUMN audio_processing_decision_json jsonb DEFAULT NULL;
        COMMENT ON COLUMN mediaitem.audio_processing_decision_json IS 'JSON output from audio processing decision helper: {use_auphonic: bool, decision: string, reason: string}';
    END IF;
END$$;

-- Verify the columns were created
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'mediaitem'
AND column_name IN ('audio_quality_metrics_json', 'audio_quality_label', 'audio_processing_decision_json')
ORDER BY column_name;
"""

ROLLBACK_SQL = """
-- Rollback: Remove the three audio quality columns if needed
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_metrics_json'
    ) THEN
        ALTER TABLE mediaitem DROP COLUMN audio_quality_metrics_json;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_quality_label'
    ) THEN
        ALTER TABLE mediaitem DROP COLUMN audio_quality_label;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mediaitem' AND column_name = 'audio_processing_decision_json'
    ) THEN
        ALTER TABLE mediaitem DROP COLUMN audio_processing_decision_json;
    END IF;
END$$;
"""
