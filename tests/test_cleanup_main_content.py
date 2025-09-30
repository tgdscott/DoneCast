from api.core.paths import MEDIA_DIR
from api.models.podcast import Episode, MediaCategory, MediaItem, Podcast
from api.models.user import User
from worker.tasks.assembly.orchestrator import _cleanup_main_content


def test_cleanup_main_content_removes_file_and_record(session):
    user = User(email="cleanup@example.com", hashed_password="hashed")
    session.add(user)
    session.commit()
    session.refresh(user)

    podcast = Podcast(name="Cleanup Pod", user_id=user.id)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)

    episode = Episode(user_id=user.id, podcast_id=podcast.id, title="Cleanup Episode")
    session.add(episode)
    session.commit()
    session.refresh(episode)

    filename = "cleanup-test-audio.mp3"
    file_path = MEDIA_DIR / filename
    file_path.write_bytes(b"dummy audio data")

    media_item = MediaItem(
        filename=filename,
        friendly_name="Cleanup Test",
        user_id=user.id,
        category=MediaCategory.main_content,
    )
    session.add(media_item)
    session.commit()
    session.refresh(media_item)

    _cleanup_main_content(
        session=session,
        episode=episode,
        main_content_filename=filename,
    )

    assert not file_path.exists()
    assert session.get(MediaItem, media_item.id) is None
