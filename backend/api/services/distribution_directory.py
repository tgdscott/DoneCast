"""Central directory of podcast distribution platforms and helper metadata.

The frontend uses this to render guidance for submitting RSS feeds to the
most common directories. Each entry describes:

* user-facing labels and summary text
* the primary call-to-action link (optionally formatted with feed/show data)
* documentation links and detailed instructions
* requirements (RSS feed, Spreaker show, etc.)
* the default automation level/status we can provide

The data lives in one place so the API router can stay lean and we can update
instructions without touching business logic.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional


# NOTE: Keep platform keys kebab- or snake-case (letters, digits, underscores)
# so they can be safely used in URLs and database unique constraints.
_PLATFORMS: List[Dict[str, object]] = [
    {
        "key": "spreaker",
        "name": "Spreaker (Plus Plus Hosting)",
        "summary": "Episodes published from Plus Plus are automatically hosted on Spreaker.",
        "automation": "automatic",
        "automation_notes": "We create and update the Spreaker show when you publish episodes.",
        "instructions": [
            "We sync your show details and episodes to Spreaker automatically whenever you publish from Plus Plus.",
            "Use the Spreaker dashboard to confirm artwork, categories, and analytics.",
            "If you need the public page, copy it from the button below or Settings → Distribution in Plus Plus.",
        ],
        "action_label": "Open Spreaker dashboard",
        "action_url_template": "https://www.spreaker.com/show/{spreaker_show_id}",
        "default_status": "completed",
        "requires_spreaker_show": True,
        "spreaker_missing_help": "Connect a Spreaker show in Settings or via the Manage Podcasts screen to generate this link.",
    },
    {
        "key": "apple_podcasts",
        "name": "Apple Podcasts",
        "summary": "The largest podcast directory — required for Siri and the iOS Podcasts app.",
        "automation": "manual",
        "automation_notes": "Apple requires the creator to submit and accept updated terms directly.",
        "action_label": "Open Podcasts Connect",
        "action_url": "https://podcastsconnect.apple.com/",
        "docs_url": "https://support.apple.com/en-us/HT204164",
        "instructions": [
            "Sign in with the Apple ID that will manage the show in Podcasts Connect.",
            "Click the plus (+) button and choose ‘New Show’. Select ‘Add a show with an RSS feed’.",
            "Paste your RSS feed URL: {rss_feed_url}.",
            "Validate the feed, resolve any warnings, then click Submit. Apple usually reviews within 24–48 hours.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish at least one episode and link your show to Spreaker so we can generate your RSS feed.",
    },
    {
        "key": "spotify",
        "name": "Spotify for Podcasters",
        "summary": "Submit to Spotify to reach Android, desktop, and smart speaker listeners.",
        "automation": "assisted",
        "automation_notes": "We provide a pre-filled submission link with your RSS feed.",
        "action_label": "Submit to Spotify",
        "action_url_template": "https://podcasters.spotify.com/submit?feed={rss_feed_encoded}",
        "docs_url": "https://podcasters.spotify.com/",
        "instructions": [
            "Sign in to Spotify for Podcasters (or create an account).",
            "Follow the claim flow; your RSS feed is pre-filled when you use our link.",
            "Verify ownership via the email sent to your podcast contact address, then complete the show setup.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "We need your Plus Plus RSS feed before we can pre-fill the Spotify form.",
    },
    {
        "key": "amazon_music",
        "name": "Amazon Music & Audible",
        "summary": "List your show on Amazon Music, Audible, and Alexa devices.",
        "automation": "manual",
        "action_label": "Open Amazon Music for Podcasters",
        "action_url": "https://podcasters.amazon.com/",
        "docs_url": "https://podcasters.amazon.com/faq",
        "instructions": [
            "Sign in with your Amazon account at Amazon Music for Podcasters.",
            "Choose ‘Add or Claim a Podcast’, then paste your RSS feed URL: {rss_feed_url}.",
            "Confirm the regions where you want the show to appear and submit. Approval typically happens within a day.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Link your Spreaker show so we can surface the RSS feed for Amazon.",
    },
    {
        "key": "iheart",
        "name": "iHeartRadio",
        "summary": "Reach listeners across the iHeartRadio app, smart speakers, and radio sites.",
        "automation": "manual",
        "action_label": "Apply on iHeartRadio",
        "action_url": "https://www.iheart.com/podcast-submissions/",
        "instructions": [
            "Open the submission form and sign in or create a free creator account.",
            "Paste your RSS feed URL ({rss_feed_url}) and complete the required metadata fields.",
            "Submit the form. iHeartRadio reviews feeds manually; approval can take several business days.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Generate your Plus Plus RSS feed before applying to iHeartRadio.",
    },
    {
        "key": "tunein",
        "name": "TuneIn",
        "summary": "Distribute to car dashboards, Alexa, and Sonos via TuneIn.",
        "automation": "manual",
        "action_label": "Submit to TuneIn",
        "action_url": "https://broadcaster-help.tunein.com/en/support/solutions/articles/151000172121-how-do-i-add-my-podcast-to-tunein-",
        "instructions": [
            "Open TuneIn’s podcast submission form.",
            "Provide your show name, contact email, and paste the RSS feed URL: {rss_feed_url}.",
            "Submit the request. TuneIn will email you once the show is approved and listed.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish a Plus Plus RSS feed so TuneIn can ingest your show.",
    },
    {
        "key": "pandora",
        "name": "Pandora for Podcasters",
        "summary": "Get featured on Pandora’s podcast genome for music-friendly audiences.",
        "automation": "manual",
        "action_label": "Open Pandora AMP",
        "action_url": "https://podcasters.pandora.com/submit",
        "instructions": [
            "Sign in or create a Pandora AMP account.",
            "Submit your RSS feed ({rss_feed_url}) via the ‘Submit Podcast’ flow.",
            "Pandora performs a manual review focused on audio quality and metadata completeness.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Once your RSS feed is live we’ll pre-fill this step with your Plus Plus URL.",
    },
    {
        "key": "podchaser",
        "name": "Podchaser",
        "summary": "Claim your profile on Podchaser to manage credits and cross-promotion.",
        "automation": "assisted",
        "action_label": "Claim on Podchaser",
        "action_url": "https://www.podchaser.com/add",
        "instructions": [
            "Log in to Podchaser (or create an account).",
            "Search for your show or use the submit flow to add it.",
            "Claim ownership to unlock analytics and collaboration tools.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish your Plus Plus RSS feed before claiming on Podchaser.",
    },
]


def get_distribution_hosts() -> List[Dict[str, object]]:
    """Return a deepcopy so callers can mutate safely."""

    return deepcopy(_PLATFORMS)


def get_distribution_host(key: str) -> Optional[Dict[str, object]]:
    for entry in _PLATFORMS:
        if entry.get("key") == key:
            return deepcopy(entry)
    return None


__all__ = ["get_distribution_hosts", "get_distribution_host"]
