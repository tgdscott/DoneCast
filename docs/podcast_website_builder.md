# Podcast Website Builder Access Guide

The podcast website builder is exposed through the Podcasts API and serves generated pages via subdomains of the configured base domain.

## API endpoints

All endpoints live under `/api/podcasts/{podcast_id}/website` and require authentication with the owning user account.

| Method & Path | Purpose |
| --- | --- |
| `GET /api/podcasts/{podcast_id}/website` | Fetch the current website metadata, layout JSON, status, and domains. |
| `POST /api/podcasts/{podcast_id}/website` | Invoke Gemini to create or refresh the website layout. |
| `POST /api/podcasts/{podcast_id}/website/chat` | Send a natural-language instruction to the AI builder and receive the updated layout. |
| `PATCH /api/podcasts/{podcast_id}/website/domain` | Set or clear a custom domain (subject to plan tier requirements). |

The JSON response includes the internal `subdomain` and the computed `default_domain` that the static site is served from.

## Viewing the generated site

After generation, the site is available at `https://<subdomain>.{BASE_DOMAIN}` where `{BASE_DOMAIN}` defaults to `podcastplusplus.com` but can be overridden through `PODCAST_WEBSITE_BASE_DOMAIN` in configuration. The API response also includes any configured custom domain when one is attached.

## Saved prompts

Every AI generation request stores the prompt, response, and metadata (when `PODCAST_WEBSITE_GCS_BUCKET` is configured) under the `prompts/` prefix of the `ppp-websites-us-west1` bucket for review.
