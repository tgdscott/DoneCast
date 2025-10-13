-- Check what audio-related fields these episodes have
SELECT 
    id,
    episode_number,
    title,
    gcs_audio_path,
    final_audio_path,
    spreaker_episode_id,
    status
FROM episode 
WHERE podcast_id = (SELECT id FROM podcast WHERE slug = 'cinema-irl')
    AND episode_number BETWEEN 195 AND 201
ORDER BY episode_number;
