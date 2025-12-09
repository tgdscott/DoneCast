from __future__ import annotations

import os
import uuid
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession

# Provide minimal defaults so Settings() can initialize during import
os.environ["INSTANCE_CONNECTION_NAME"] = ""
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

from api.main import app
from api.core.database import engine
from api.core import crud
from api.models.user import UserCreate, User
from api.models.podcast import Podcast
from api.core.auth import get_current_user


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


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
        email=f"dist_{uuid.uuid4().hex[:10]}@example.com",
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
        name="Distribution Demo Show",
        description="Testing distribution checklist",
        spreaker_show_id="1234567",
        user_id=user.id,
    )
    db.add(pod)
    db.commit()
    db.refresh(pod)
    return pod


def _get_item(items: List[Dict], key: str) -> Dict:
    for item in items:
        if item.get("key") == key:
            return item
    raise AssertionError(f"Distribution item {key} not found")


def test_distribution_checklist_includes_defaults(authed_client: TestClient, podcast: Podcast):
    resp = authed_client.get(f"/api/podcasts/{podcast.id}/distribution/checklist")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["podcast_id"] == str(podcast.id)
    assert body["rss_feed_url"].endswith("/feed.xml")

    items = body["items"]
    keys = {item["key"] for item in items}
    assert "spreaker" in keys
    assert "apple_podcasts" in keys

    spreaker = _get_item(items, "spreaker")
    assert spreaker["status"] == "completed"
    assert spreaker["disabled_reason"] is None

    apple = _get_item(items, "apple_podcasts")
    assert body["rss_feed_url"] in " ".join(apple["instructions"])
    assert apple["requires_rss_feed"] is True


def test_distribution_update_status_persists(authed_client: TestClient, podcast: Podcast):
    url = f"/api/podcasts/{podcast.id}/distribution/checklist/spotify"
    resp = authed_client.put(url, json={"status": "completed", "notes": "  published ✅  "})
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["status"] == "completed"
    assert item["notes"] == "published ✅"

    resp2 = authed_client.get(f"/api/podcasts/{podcast.id}/distribution/checklist")
    spotify = _get_item(resp2.json()["items"], "spotify")
    assert spotify["status"] == "completed"
    assert spotify["notes"] == "published ✅"


def test_distribution_without_feed_marks_platforms_disabled(
    authed_client: TestClient, db: DBSession, user: User
):
    pod = Podcast(name="No Feed Yet", user_id=user.id)
    db.add(pod)
    db.commit()
    db.refresh(pod)

    resp = authed_client.get(f"/api/podcasts/{pod.id}/distribution/checklist")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    apple = _get_item(items, "apple_podcasts")
    assert apple["disabled_reason"]
    assert "RSS" in apple["disabled_reason"]
