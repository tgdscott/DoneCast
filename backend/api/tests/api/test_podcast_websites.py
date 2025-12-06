import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession, select

# Ensure required settings for Settings() initialization
os.environ.setdefault("INSTANCE_CONNECTION_NAME", "")
_REQUIRED_KEYS = [
    "DB_USER",
    "DB_PASS",
    "DB_NAME",
    "GEMINI_API_KEY",
    "ELEVENLABS_API_KEY",
    "ASSEMBLYAI_API_KEY",
    "SPREAKER_API_TOKEN",
    "SPREAKER_CLIENT_ID",
    "SPREAKER_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
]
for key in _REQUIRED_KEYS:
    os.environ.setdefault(key, "test")

from api.app import app
from api.core.database import engine
from api.core import crud
from api.models.user import UserCreate, User
from api.models.podcast import Podcast, Episode
from api.models.website import PodcastWebsite
from api.routers.auth import get_current_user
from api.services import podcast_websites
from api.core.config import settings


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


@pytest.fixture(autouse=True)
def disable_prompt_upload(monkeypatch):
    monkeypatch.setattr(settings, "PODCAST_WEBSITE_GCS_BUCKET", "", raising=False)
    monkeypatch.setattr(podcast_websites, "_PROMPT_BUCKET", "", raising=False)
    monkeypatch.setattr(podcast_websites, "storage", None, raising=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> DBSession:
    with DBSession(engine) as session:
        yield session


@pytest.fixture
def user(db: DBSession) -> User:
    uc = UserCreate(
        email=f"builder_{uuid.uuid4().hex[:10]}@example.com",
        password="Password123!",
    )
    return crud.create_user(session=db, user_create=uc)


@pytest.fixture
def authed_client(client: TestClient, user: User) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return client


@pytest.fixture
def podcast(db: DBSession, user: User) -> Podcast:
    pod = Podcast(
        name="AI Builder Podcast",
        description="A show exploring AI tooling.",
        user_id=user.id,
    )
    db.add(pod)
    db.commit()
    db.refresh(pod)
    return pod


@pytest.fixture
def episode(db: DBSession, podcast: Podcast, user: User) -> Episode:
    ep = Episode(
        title="Kickoff Episode",
        show_notes="We talk about the new website builder.",
        podcast_id=podcast.id,
        user_id=user.id,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return ep


def _base_layout_for(episode: Episode) -> dict:
    return {
        "hero_title": "AI Builder Central",
        "hero_subtitle": "Launch your site in minutes.",
        "hero_image_url": "https://example.com/cover.jpg",
        "about": {
            "heading": "About the show",
            "body": "We cover automation for podcasters.",
        },
        "hosts": [
            {"name": "Taylor", "bio": "Host"},
        ],
        "episodes": [
            {
                "episode_id": str(episode.id),
                "title": "Kickoff Episode",
                "description": "Highlights of the builder.",
                "cta_label": "Play episode",
                "cta_url": None,
            }
        ],
        "call_to_action": {
            "heading": "Subscribe",
            "body": "Never miss an update.",
            "button_label": "Listen now",
            "button_url": "https://example.com",
        },
        "section_suggestions": [
            {
                "type": "newsletter",
                "label": "Join the newsletter",
                "description": "Fans get new episode drops via email.",
                "include_by_default": True,
            },
            {
                "type": "press",
                "label": "Press kit",
                "description": "A quick overview for collaborators.",
                "include_by_default": False,
            },
        ],
        "additional_sections": [],
        "theme": {
            "primary_color": "#123456",
            "secondary_color": "#ffffff",
            "accent_color": "#abcdef",
        },
    }


def test_generate_website_creates_record(authed_client: TestClient, db: DBSession, podcast: Podcast, episode: Episode, monkeypatch):
    layout = _base_layout_for(episode)

    def _fake_generate(prompt: str, **_kwargs: object) -> str:
        return json.dumps(layout)

    monkeypatch.setattr(podcast_websites.ai_client, "generate", _fake_generate)
    # Force production env to test domain generation
    monkeypatch.setattr(settings, "APP_ENV", "production")

    missing = authed_client.get(f"/api/podcasts/{podcast.id}/website")
    assert missing.status_code == 404

    resp = authed_client.post(f"/api/podcasts/{podcast.id}/website")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "draft"
    assert body["subdomain"].startswith("ai-builder-podcast")
    assert body["default_domain"].endswith("donecast.com")
    assert body["layout"]["hero_title"] == "AI Builder Central"
    assert body["layout"]["episodes"][0]["episode_id"] == str(episode.id)
    assert body["layout"]["hero_image_url"] == "https://example.com/cover.jpg"
    assert len(body["layout"].get("section_suggestions", [])) >= 2

    site = db.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    assert site is not None
    assert site.subdomain == body["subdomain"]
    assert "AI Builder Central" in site.layout_json


def test_chat_endpoint_updates_layout(authed_client: TestClient, db: DBSession, podcast: Podcast, episode: Episode, monkeypatch):
    def _initial_generate(prompt: str, **_kwargs: object) -> str:
        return json.dumps(_base_layout_for(episode))

    monkeypatch.setattr(podcast_websites.ai_client, "generate", _initial_generate)
    create_resp = authed_client.post(f"/api/podcasts/{podcast.id}/website")
    assert create_resp.status_code == 200, create_resp.text

    def _update_generate(prompt: str, **_kwargs: object) -> str:
        updated = _base_layout_for(episode)
        updated["hero_title"] = "AI Builder Hub"
        updated["call_to_action"]["button_label"] = "Join the Hub"
        return json.dumps(updated)

    monkeypatch.setattr(podcast_websites.ai_client, "generate", _update_generate)

    resp = authed_client.post(
        f"/api/podcasts/{podcast.id}/website/chat",
        json={"message": "Make the hero more energetic."},
    )
    assert resp.status_code == 200, resp.text
    layout = resp.json()["layout"]
    assert layout["hero_title"] == "AI Builder Hub"
    assert layout["call_to_action"]["button_label"] == "Join the Hub"
    assert layout["section_suggestions"][0]["include_by_default"] is True

    site = db.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    assert site is not None
    assert "AI Builder Hub" in site.layout_json


def test_update_domain_requires_plan(authed_client: TestClient, db: DBSession, user: User, podcast: Podcast, episode: Episode, monkeypatch):
    monkeypatch.setattr(
        podcast_websites.ai_client,
        "generate",
        lambda prompt, **_: json.dumps(_base_layout_for(episode)),
    )
    create_resp = authed_client.post(f"/api/podcasts/{podcast.id}/website")
    assert create_resp.status_code == 200, create_resp.text

    resp = authed_client.patch(
        f"/api/podcasts/{podcast.id}/website/domain",
        json={"custom_domain": "myshow.fm"},
    )
    assert resp.status_code == 400

    site_before = db.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    assert site_before is not None
    assert site_before.custom_domain is None

    user.tier = "pro"
    db.add(user)
    db.commit()
    db.refresh(user)

    resp2 = authed_client.patch(
        f"/api/podcasts/{podcast.id}/website/domain",
        json={"custom_domain": "myshow.fm"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["custom_domain"] == "myshow.fm"

    resp3 = authed_client.patch(
        f"/api/podcasts/{podcast.id}/website/domain",
        json={"custom_domain": None},
    )
    assert resp3.status_code == 200, resp3.text
    assert resp3.json()["custom_domain"] is None


def test_generate_css_from_theme_respects_colors():
    theme = {
        "primary_color": "#123456",
        "secondary_color": "#abcdef",
        "accent_color": "#fedcba",
        "background_color": "#0f172a",
        "text_color": "#ffffff",
        "mood": "professional",
    }

    css = podcast_websites._generate_css_from_theme(theme, "Test Podcast")

    assert "/* Auto-generated CSS for Test Podcast */" in css
    assert "--color-primary: #123456;" in css
    assert "--color-secondary: #abcdef;" in css
    assert "--color-accent: #fedcba;" in css
    assert "--color-background: #0f172a;" in css
    assert "--color-text-primary:" in css
    assert "color: var(--color-text-primary);" in css
