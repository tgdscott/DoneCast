# Podcast Website Builder Guide

Whether you are a seasoned producer or helping a 70-year-old first-time podcaster, the builder is designed to be conversational and forgiving. The steps below walk through both the point-and-click flow and the supporting APIs.

## No-code quick start

1. **Sign in** to Podcast Plus Plus and open the podcast you want to publish.
2. **Click “Website Builder”** in the left navigation. A friendly chat panel opens next to a live preview of the site.
3. **Press “Create my site.”** The AI looks at your show description, hosts, and recent episodes, then drafts a complete page with hero copy, an About section, host bios, and a playable episode grid.
4. **Talk to the AI like a helper.** Examples:
   - “Make the hero photo brighter and add a bigger play button.”
   - “Add a section inviting people to join my newsletter.”
   - “Change the colors to navy and gold.”
   Each message is remembered so you can iteratively refine the page.
5. **Share immediately.** The builder publishes to `https://<yourshow>.podcastplusplus.com` as soon as the first draft is ready.
6. **Use your own domain (Pro tier and above).** Type “Help me use my custom domain.” The assistant walks the user through adding a CNAME record and confirms when DNS has finished propagating.

### Tips for non-technical hosts

- **Plain language works best.** There are no commands to memorize; just describe what you want to see.
- **Undo is built in.** Say “Undo that change” or “Go back to the version from this morning.” The AI reloads the saved layout.
- **Accessibility checks run automatically.** The builder keeps text large and color contrast compliant.
- **Help bubble videos.** Tooltips include short recordings that demonstrate each step—ideal for clients who prefer visual guidance.

## Admin & support workflow

- **Saved prompt history.** Every chat turn is stored with timestamps under the `prompts/` prefix of the `ppp-websites-us-west1` bucket, so customer support can review what the AI changed.
- **One-click restore.** Support agents can select an earlier prompt in the dashboard to roll the site back if a user gets stuck.
- **Email summaries.** When a site is published, we send the owner a recap with the live URL, DNS instructions (if applicable), and a copy of the final prompt transcript.

## API endpoints

The same workflow is available programmatically. All endpoints live under `/api/podcasts/{podcast_id}/website` and require authentication with the owning user account.

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
