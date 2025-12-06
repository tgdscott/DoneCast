# Manual Editor GCS Support Fix (Dec 5, 2025)

## Problem
The manual editor was failing to apply cuts to episodes.
- **Symptom:** Users reported "manual editor does not seem to work anymore".
- **Root Cause:** The `manual_cut_episode` background task was still relying on local file paths (`FINAL_DIR` / `MEDIA_DIR`) to locate the source audio. Since the migration to GCS-only architecture (Oct 13), production environments do not have local audio files, causing the task to fail with "source file missing".

## Solution
Updated `backend/worker/tasks/manual_cut.py` to support cloud storage (GCS/R2).

### Changes
1.  **Cloud Download:** Added `_download_cloud_file` helper to download the source audio from GCS/R2 to a temporary file.
2.  **Source Resolution:** Modified `manual_cut_episode` to check for cloud URIs (`gs://`, `r2://`) in `final_audio_path` or `gcs_audio_path` and download them.
3.  **Cloud Upload:** After processing the cuts with `pydub`, the result is now uploaded back to cloud storage with a new unique filename (to avoid caching issues).
4.  **Database Update:** The episode's `final_audio_path` and `gcs_audio_path` are updated with the new cloud URI.
5.  **Cleanup:** Temporary files are deleted after processing.

### Files Modified
- `backend/worker/tasks/manual_cut.py`

### Verification
- The manual editor should now successfully apply cuts to episodes stored in GCS/R2.
- The process involves downloading, editing locally (in the worker), and re-uploading.
