import uuid
from datetime import datetime, timezone, timedelta

import types


def test_unpublish_cancels_scheduled(monkeypatch):
    # Lazy import to access module under test
    from api.services.episodes import publisher as mod

    # Stub episode object with future publish_at
    class StubEp:
        def __init__(self):
            self.id = uuid.uuid4()
            self.status = 'processed'
            self.final_audio_path = 'finals/foo.mp3'
            self.spreaker_episode_id = '999'
            self.is_published_to_spreaker = False
            self.publish_at = datetime.now(timezone.utc) + timedelta(hours=2)
            self.publish_at_local = '2025-12-31 10:00'

    stub_ep = StubEp()

    # Stub user/session
    class StubUser:
        def __init__(self):
            self.id = uuid.uuid4()
            self.spreaker_access_token = 'token'
            # trial fields to satisfy trial_service guards
            self.trial_started_at = None
            self.trial_expires_at = None

    class StubSess:
        def add(self, _):
            pass

        def commit(self):
            pass

        def refresh(self, _):
            pass

        def rollback(self):
            pass

    sess = StubSess()
    user = StubUser()

    # Monkeypatch repo.get_episode_by_id to return our stub
    monkeypatch.setattr(mod.repo, 'get_episode_by_id', lambda session, episode_id, user_id=None: stub_ep)

    # Monkeypatch SpreakerClient to avoid network
    class DummyResp:
        status_code = 404
        text = 'not found'

    class DummyClient:
        BASE_URL = 'https://api.test'

        def __init__(self, token):
            self.session = types.SimpleNamespace(delete=lambda url: DummyResp())

    monkeypatch.setattr(mod, 'SpreakerClient', DummyClient)

    # Call
    out = mod.unpublish(session=sess, current_user=user, episode_id=uuid.uuid4())

    # Assert scheduled cancel path
    assert out['was_scheduled'] is True
    assert out['message'].lower().startswith('scheduled publish canceled')
    assert out['removed_remote'] is True
    assert out['within_retention_window'] is True
    assert out['forced'] is False

    # Local fields cleared
    assert stub_ep.publish_at is None
    assert stub_ep.spreaker_episode_id is None
    assert stub_ep.is_published_to_spreaker is False
