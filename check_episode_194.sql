-- Check episode 194 to see if it has spreaker_episode_id and needs migration
SELECT 
    id,
    episode_number,
    title,
    spreaker_episode_id,
    gcs_audio_path,
    gcs_cover_path,
    spreaker_image_id,
    status
FROM episode 
WHERE podcast_id = (SELECT id FROM podcast WHERE slug = 'cinema-irl')
    AND episode_number = 194;
