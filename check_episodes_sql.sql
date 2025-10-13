-- Check Cinema IRL episodes 195-201 audio paths
-- Run this in your Cloud SQL console or via psql

WITH cinema_podcast AS (
    SELECT id FROM podcast WHERE slug = 'cinema-irl'
)
SELECT 
    e.episode_number,
    LEFT(e.title, 50) as title,
    e.status,
    e.publish_at,
    e.spreaker_episode_id,
    e.final_audio_path,
    e.gcs_audio_path,
    e.gcs_cover_path,
    CASE 
        WHEN e.gcs_audio_path IS NOT NULL THEN 'GCS'
        WHEN e.final_audio_path IS NOT NULL THEN 'Local'
        WHEN e.spreaker_episode_id IS NOT NULL THEN 'Spreaker'
        ELSE '❌ NONE'
    END as audio_source
FROM episode e
JOIN cinema_podcast cp ON e.podcast_id = cp.id
WHERE e.episode_number BETWEEN 195 AND 201
ORDER BY e.episode_number;
