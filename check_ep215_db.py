"""
Query Episode 215 from production database to check Intern data.
Usage: gcloud sql connect --help for connection info
"""
import os

# SQL query to check Episode 215
QUERY = """
SELECT 
    id,
    title,
    status,
    working_audio_name,
    meta_json::json->'ai_features' as ai_features,
    meta_json::json->'intern_overrides' as intern_overrides,
    meta_json::json->'cleanup_options' as cleanup_options,
    meta_json::json->'cleaned_audio' as cleaned_audio,
    meta_json::json->'cleaned_audio_gcs_uri' as cleaned_audio_gcs_uri,
    LENGTH(meta_json::text) as meta_json_size
FROM episode 
WHERE id = 215;
"""

print("=" * 80)
print("EPISODE 215 INTERN DEBUG QUERY")
print("=" * 80)
print("\nRun this query in PGAdmin or via gcloud:")
print("\ngcloud sql connect podcast612-db-prod --user=postgres --database=podcast612")
print("\nThen paste this SQL:\n")
print(QUERY)
print("\n" + "=" * 80)
print("\nWhat to check:")
print("  1. ai_features.intern_enabled - Should be true")
print("  2. ai_features.intents - Should include 'intern'")
print("  3. intern_overrides - Should be an array of objects with:")
print("     - command_id")
print("     - start_s, end_s (timestamps)")
print("     - prompt_text")
print("     - response_text")
print("     - audio_url or voice_id")
print("  4. If intern_overrides is NULL or [], problem is in FRONTEND")
print("  5. If intern_overrides exists, problem is in WORKER execution")
print("=" * 80)
