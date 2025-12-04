# Spotify Submission URL Fix (Dec 3, 2025)

## Problem
Users reported that the "Submit to Spotify" button in the Onboarding flow (Step 12) was hanging on a blank page.
The URL being used was `https://podcasters.spotify.com/submit?feed=...`, which redirected to `https://creators.spotify.com/submit?feed=...` and returned a 404.

## Root Cause
Spotify has rebranded "Spotify for Podcasters" to "Spotify for Creators" and changed their URL structure.
The old submission URL is no longer valid and the redirect is broken (leads to a 404).

## Solution
Updated the Spotify distribution configuration to use the new URL format and branding.

### Changes
1.  **Backend Configuration** (`backend/api/services/distribution_directory.py`):
    *   Updated Name: "Spotify for Creators"
    *   Updated Action URL: `https://creators.spotify.com/pod/dashboard/submit?feed={rss_feed_encoded}`
    *   Updated Docs URL: `https://creators.spotify.com/`

2.  **Frontend UI** (`frontend/src/components/onboarding/OnboardingWrapper.jsx`):
    *   Updated text reference to "Spotify for Creators".

3.  **Documentation**:
    *   Updated `docs/RSS_FEED_DEPLOYMENT_SUCCESS.md`.

## Verification
1.  Go to Onboarding Step 12 (Distribution).
2.  Click "Submit to Spotify".
3.  Verify it opens `https://creators.spotify.com/pod/dashboard/submit?feed=...`.
4.  Verify the page loads correctly (Spotify dashboard).
