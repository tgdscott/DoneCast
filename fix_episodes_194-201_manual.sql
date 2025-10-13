-- SQL to manually populate gcs_audio_path for episodes 194-201
-- These audio files can be downloaded from Spreaker using the episode IDs below

-- Episode 194: spreaker_episode_id 68051934
-- Download from: https://api.spreaker.com/v2/episodes/68051934/download.mp3
-- Then upload to GCS and run:
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/070b8922-93ce-42f9-9b35-f7a374c9cb51/audio/e194---the-toxic-avenger---what-would-you-do-.mp3'
WHERE id = '070b8922-93ce-42f9-9b35-f7a374c9cb51';

-- Episode 195: spreaker_episode_id 68097103
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/9e4bffb5-c40b-49d2-a725-2f1bbf5a6701/audio/test110346---e195----e195---the-roses---what-would-you-do.mp3'
WHERE id = '9e4bffb5-c40b-49d2-a725-2f1bbf5a6701';

-- Episode 196: spreaker_episode_id 68097454
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/89f84b6b-1d81-4f5d-a40a-17c6c8231d41/audio/test110517---e196---the-threesome---what-would-you-do.mp3'
WHERE id = '89f84b6b-1d81-4f5d-a40a-17c6c8231d41';

-- Episode 197: spreaker_episode_id 68097567
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/217d45fe-d5c9-4c05-89b3-a1a7c04720ec/audio/test110549---e197---the-baltimorons---what-would-you-do.mp3'
WHERE id = '217d45fe-d5c9-4c05-89b3-a1a7c04720ec';

-- Episode 198: spreaker_episode_id 68097596  
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/cbb25ed6-2897-42a6-b392-35172b077fda/audio/test110604---e202---the-man-in-my-basement---what-would-you-do.mp3'
WHERE id = 'cbb25ed6-2897-42a6-b392-35172b077fda';

-- Episode 199: spreaker_episode_id 68097614
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/1679183d-d2de-4b4b-ad25-be5e7eb6199f/audio/test110608---e199---twinless---what-would-you-do.mp3'
WHERE id = '1679183d-d2de-4b4b-ad25-be5e7eb6199f';

-- Episode 200: spreaker_episode_id 68098218
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/fa933980-ecf1-44e4-935a-5236db1ddccc/audio/test110803---e200---the-long-walk---what-would-you-do.mp3'
WHERE id = 'fa933980-ecf1-44e4-935a-5236db1ddccc';

-- Episode 201: spreaker_episode_id 68098741
UPDATE episode 
SET gcs_audio_path = 'gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/768605b6-18ad-4a52-ab85-a05b8c1d321f/audio/e201---a-big-bold-beautiful-journey---what-would-you-do-.mp3'
WHERE id = '768605b6-18ad-4a52-ab85-a05b8c1d321f';

-- Verify the updates
SELECT id, episode_number, title, gcs_audio_path 
FROM episode 
WHERE id IN (
    '070b8922-93ce-42f9-9b35-f7a374c9cb51',
    '9e4bffb5-c40b-49d2-a725-2f1bbf5a6701',
    '89f84b6b-1d81-4f5d-a40a-17c6c8231d41',
    '217d45fe-d5c9-4c05-89b3-a1a7c04720ec',
    'cbb25ed6-2897-42a6-b392-35172b077fda',
    '1679183d-d2de-4b4b-ad25-be5e7eb6199f',
    'fa933980-ecf1-44e4-935a-5236db1ddccc',
    '768605b6-18ad-4a52-ab85-a05b8c1d321f'
)
ORDER BY episode_number;
