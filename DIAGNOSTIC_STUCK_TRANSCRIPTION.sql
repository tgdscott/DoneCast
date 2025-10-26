"""
Diagnostic script to investigate stuck transcription for wordsdonewrite@gmail.com
Run this to check current state and identify issues.
"""

# Query to run in PostgreSQL:

-- Find the user
SELECT id, email, tier, created_at 
FROM "user" 
WHERE email = 'wordsdonewrite@gmail.com';

-- Find their recent media uploads
SELECT 
    mi.id,
    mi.filename,
    mi.category,
    mi.created_at,
    mi.duration_seconds,
    mi.gcs_path
FROM mediaitem mi
JOIN "user" u ON mi.user_id = u.id
WHERE u.email = 'wordsdonewrite@gmail.com'
ORDER BY mi.created_at DESC
LIMIT 10;

-- Find TranscriptionWatch records for this user
SELECT 
    tw.id,
    tw.filename,
    tw.friendly_name,
    tw.created_at,
    tw.notified_at,
    tw.last_status,
    tw.notify_email,
    EXTRACT(EPOCH FROM (NOW() - tw.created_at))/60 AS age_minutes
FROM transcriptionwatch tw
JOIN "user" u ON tw.user_id = u.id
WHERE u.email = 'wordsdonewrite@gmail.com'
ORDER BY tw.created_at DESC
LIMIT 10;

-- Find MediaTranscript records
SELECT 
    mt.id,
    mt.filename,
    mt.transcript_meta_json,
    mt.created_at,
    mt.updated_at
FROM mediatranscript mt
JOIN mediaitem mi ON mt.media_item_id = mi.id
JOIN "user" u ON mi.user_id = u.id
WHERE u.email = 'wordsdonewrite@gmail.com'
ORDER BY mt.created_at DESC
LIMIT 10;

-- Combined view: Media items with transcription status
SELECT 
    mi.filename,
    mi.category,
    mi.duration_seconds,
    mi.created_at AS uploaded_at,
    tw.last_status AS watch_status,
    tw.notified_at AS transcription_notified,
    mt.transcript_meta_json IS NOT NULL AS has_transcript_meta,
    CASE 
        WHEN tw.notified_at IS NOT NULL THEN 'Complete'
        WHEN tw.id IS NULL THEN 'No Watch'
        WHEN EXTRACT(EPOCH FROM (NOW() - tw.created_at))/60 > 10 THEN 'STUCK'
        ELSE 'Processing'
    END AS status,
    EXTRACT(EPOCH FROM (NOW() - mi.created_at))/60 AS age_minutes
FROM mediaitem mi
LEFT JOIN "user" u ON mi.user_id = u.id
LEFT JOIN transcriptionwatch tw ON tw.filename = mi.filename
LEFT JOIN mediatranscript mt ON mt.media_item_id = mi.id
WHERE u.email = 'wordsdonewrite@gmail.com'
  AND mi.category = 'main_content'
ORDER BY mi.created_at DESC
LIMIT 10;
