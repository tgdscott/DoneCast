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

After generation, the site is published at a brand-facing domain (no app/api prefixes):

- Default URL: `https://<subdomain>.<BASE_DOMAIN>`
	- Example: if the subdomain is `myshow` and the base domain is the default, your site will be at `https://myshow.podcastplusplus.com`.
	- You can change the base domain via the `PODCAST_WEBSITE_BASE_DOMAIN` setting (defaults to `podcastplusplus.com`).

The API response for `GET /api/podcasts/{podcast_id}/website` includes:

- `subdomain`: The internal identifier allocated to the site (e.g., `myshow`).
- `default_domain`: The fully-qualified host we serve by default (e.g., `myshow.podcastplusplus.com`).
- `custom_domain` (optional): A user-attached custom hostname when configured.
- `status`: Current publish state.

### Custom domains

If your plan allows custom domains (minimum tier is controlled by `PODCAST_WEBSITE_CUSTOM_DOMAIN_MIN_TIER`), you can attach one via:

- `PATCH /api/podcasts/{podcast_id}/website/domain` with `{ "custom_domain": "yourdomain.com" }`.

DNS setup (high-level):

- Create a CNAME record for your custom host that points to the `default_domain` returned by the API (e.g., `CNAME www.yourdomain.com -> myshow.podcastplusplus.com`).
- Allow time for DNS and TLS issuance to complete (typically a few minutes, can be up to an hour depending on DNS TTLs).

Notes:

- The service intentionally avoids exposing `app.` or `api.` subdomains for public websites; visitors see the brand apex (`<subdomain>.<BASE_DOMAIN>`) or your custom domain.
- During the rebrand transition, existing sites on the legacy base domain may continue to resolve (e.g., `*.getpodcastplus.com`), but new deployments use `podcastplusplus.com` by default.

## Saved prompts

Every AI generation request stores the prompt, response, and metadata (when `PODCAST_WEBSITE_GCS_BUCKET` is configured) under the `prompts/` prefix of the `ppp-websites-us-west1` bucket for review.
