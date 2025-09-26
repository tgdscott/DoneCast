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
        "name": "Spreaker (CloudPod Hosting)",
        "summary": "Episodes published from CloudPod are automatically hosted on Spreaker.",
        "automation": "automatic",
        "automation_notes": "We create and update the Spreaker show when you publish episodes.",
        "instructions": [
            "We sync your show details and episodes to Spreaker automatically whenever you publish from CloudPod.",
            "Use the Spreaker dashboard to confirm artwork, categories, and analytics.",
            "If you need the public page, copy it from the button below or Settings → Distribution in CloudPod.",
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
        "automation_notes": "We surface the direct claim flow with your RSS feed pre-filled.",
        "action_label": "Submit to Spotify",
        "action_url_template": "https://podcasters.spotify.com/pod/dashboard/submit?feedUri={rss_feed_encoded}",
        "docs_url": "https://support.spotifyforpodcasters.com/hc/en-us/articles/115003234367-Submit-your-podcast",
        "instructions": [
            "Sign in to Spotify for Podcasters (or create an account).",
            "Follow the claim flow; your RSS feed is pre-filled when you use our link.",
            "Verify ownership via the email sent to your podcast contact address, then complete the show setup.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "We need your CloudPod RSS feed before we can pre-fill the Spotify form.",
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
        "action_url": "https://www.iheart.com/content/submit-your-podcast/",
        "instructions": [
            "Open the submission form and sign in or create a free creator account.",
            "Paste your RSS feed URL ({rss_feed_url}) and complete the required metadata fields.",
            "Submit the form. iHeartRadio reviews feeds manually; approval can take several business days.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Generate your CloudPod RSS feed before applying to iHeartRadio.",
    },
    {
        "key": "tunein",
        "name": "TuneIn",
        "summary": "Distribute to car dashboards, Alexa, and Sonos via TuneIn.",
        "automation": "manual",
        "action_label": "Submit to TuneIn",
        "action_url": "https://podcasters.tunein.com/submit",
        "instructions": [
            "Open TuneIn’s creator submission form.",
            "Provide your show name, contact email, and paste the RSS feed URL: {rss_feed_url}.",
            "Submit the request. TuneIn will email you once the show is approved and listed.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish a CloudPod RSS feed so TuneIn can ingest your show.",
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
        "rss_missing_help": "Once your RSS feed is live we’ll pre-fill this step with your CloudPod URL.",
    },
    {
        "key": "samsung_podcasts",
        "name": "Samsung Free / Samsung Podcasts",
        "summary": "Surface your show on Samsung Galaxy devices via the Samsung Free app.",
        "automation": "manual",
        "action_label": "Submit to Samsung Podcasts",
        "action_url": "https://www.samsung.com/us/apps/samsung-podcasts/podcaster-sign-up/",
        "instructions": [
            "Create or sign in to a Samsung Publishers account.",
            "Fill in the submission form and paste your RSS feed: {rss_feed_url}.",
            "Samsung reviews submissions in batches; approval can take up to two weeks.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Create your CloudPod RSS feed first so Samsung can pull episodes.",
    },
    {
        "key": "podchaser",
        "name": "Podchaser",
        "summary": "Claim your profile on Podchaser to manage credits and cross-promotion.",
        "automation": "assisted",
        "action_label": "Claim on Podchaser",
        "action_url": "https://www.podchaser.com/podcasters",
        "instructions": [
            "Log in to Podchaser (or create an account).",
            "Search for your show using the RSS feed ({rss_feed_url}) or direct link in the dashboard.",
            "Claim ownership to unlock analytics and collaboration tools.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish your CloudPod RSS feed before claiming on Podchaser.",
    },
    {
        "key": "youtube_music",
        "name": "YouTube Music",
        "summary": "List your show in the YouTube Music podcasts directory and YouTube app.",
        "automation": "manual",
        "automation_notes": "YouTube requires channel-level verification before claiming an RSS feed.",
        "action_label": "Open Podcasts Manager",
        "action_url_template": "https://podcastsmanager.google.com/add-feed?feedUrl={rss_feed_encoded}",
        "docs_url": "https://support.google.com/youtubemusic/answer/14226293",
        "instructions": [
            "Sign in with the Google account that manages your YouTube channel.",
            "Use Podcasts Manager to submit your RSS feed ({rss_feed_url}) for distribution on YouTube Music.",
            "Verify ownership via the email sent to your show’s contact address, then publish the podcast listing.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Generate your CloudPod RSS feed so YouTube Music can ingest your show.",
    },
    {
        "key": "podcast_index",
        "name": "Podcast Index",
        "summary": "Make your show discoverable to independent podcast apps powered by Podcast Index.",
        "automation": "manual",
        "action_label": "Submit to Podcast Index",
        "action_url": "https://podcastindex.org/add",
        "docs_url": "https://podcastindex-org.github.io/docs/submit/",
        "instructions": [
            "Visit Podcast Index and paste your RSS feed URL ({rss_feed_url}) into the add form.",
            "Confirm your show details and submit the request.",
            "Most Podcast Index powered apps will list your show within a few minutes of approval.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish your CloudPod RSS feed to appear across the Podcast Index ecosystem.",
    },
    {
        "key": "pocket_casts",
        "name": "Pocket Casts",
        "summary": "Submit to Pocket Casts to reach one of the most popular cross-platform podcast apps.",
        "automation": "manual",
        "action_label": "Submit to Pocket Casts",
        "action_url": "https://www.pocketcasts.com/submit/",
        "docs_url": "https://support.pocketcasts.com/article/submit-a-podcast/",
        "instructions": [
            "Open the Pocket Casts submission form.",
            "Paste your RSS feed URL ({rss_feed_url}) and provide the requested contact details.",
            "Submit the request and monitor your email for confirmation from Pocket Casts.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Your CloudPod RSS feed is required before you can submit to Pocket Casts.",
    },
    {
        "key": "overcast",
        "name": "Overcast",
        "summary": "Get listed in Overcast so iOS listeners can easily follow your show.",
        "automation": "manual",
        "action_label": "Submit to Overcast",
        "action_url": "https://overcast.fm/add",
        "docs_url": "https://overcast.fm/podcasterinfo",
        "instructions": [
            "Open Overcast’s add podcast page.",
            "Paste your RSS feed URL ({rss_feed_url}) and complete the brief submission form.",
            "Overcast usually lists new shows within a few hours.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish your CloudPod RSS feed so Overcast can index your episodes.",
    },
    {
        "key": "castbox",
        "name": "Castbox",
        "summary": "Castbox helps Android and web listeners discover new podcasts globally.",
        "automation": "manual",
        "action_label": "Submit to Castbox",
        "action_url": "https://castbox.fm/podcaster/submit",
        "docs_url": "https://helpcenter.castbox.fm/portal/en/kb/articles/how-to-submit-a-podcast-to-castbox",
        "instructions": [
            "Sign in or create a Castbox Podcaster account.",
            "Submit your RSS feed URL ({rss_feed_url}) and complete the required show information.",
            "Castbox will notify you once the podcast has been approved and published.",
        ],
        "requires_rss_feed": True,
        "rss_missing_help": "Publish your CloudPod RSS feed so Castbox can ingest your show.",
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
