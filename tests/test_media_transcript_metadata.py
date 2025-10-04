import json
from uuid import uuid4

from sqlmodel import select

from api.models.podcast import MediaCategory, MediaItem
from api.models.transcription import MediaTranscript
from api.models.user import User
from api.services import transcription
from api.services.episodes import assembler


def _create_user(session) -> User:
    user = User(
        email=f"user-{uuid4().hex}@example.com",
        hashed_password="secret",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_store_and_load_media_transcript_metadata(session):
    user = _create_user(session)
    filename = f"gs://media-bucket/{user.id}/main_content/test_file.mp3"

    media_item = MediaItem(
        friendly_name="Test Upload",
        category=MediaCategory.main_content,
        filename=filename,
        user_id=user.id,
    )
    session.add(media_item)
    session.commit()
    session.refresh(media_item)

    transcription._store_media_transcript_metadata(  # type: ignore[attr-defined]
        filename,
        stem="test_file",
        safe_stem="test_file",
        bucket="media-bucket",
        key="transcripts/test_file.json",
        gcs_uri="gs://media-bucket/transcripts/test_file.json",
        gcs_url="https://storage.googleapis.com/media-bucket/transcripts/test_file.json",
    )

    record = session.exec(select(MediaTranscript)).first()
    assert record is not None
    assert record.media_item_id == media_item.id
    stored = json.loads(record.transcript_meta_json)
    assert stored["gcs_json"].endswith("transcripts/test_file.json")
    assert stored["bucket_stem"] == "test_file"

    loaded = transcription.load_media_transcript_metadata_for_filename(session, filename)
    assert loaded and loaded["gcs_json"].endswith("transcripts/test_file.json")

    # Variant lookup using basename should also succeed
    basename_loaded = transcription.load_media_transcript_metadata_for_filename(
        session, "test_file.mp3"
    )
    assert basename_loaded and basename_loaded.get("stem") == "test_file"


def test_merge_transcript_metadata_preserves_existing_fields(session):
    filename = "gs://media-bucket/someuser/main_content/merge_case.mp3"
    meta_payload = {"gcs_json": "gs://media-bucket/transcripts/merge_case.json", "stem": "merge_case"}

    session.add(
        MediaTranscript(
            filename=filename,
            transcript_meta_json=json.dumps(meta_payload),
        )
    )
    session.commit()

    existing_meta = {
        "transcripts": {"gcs_url": "https://existing.example/transcript.json"},
        "other": "value",
    }

    merged = assembler._merge_transcript_metadata_from_upload(session, dict(existing_meta), filename)

    assert merged["transcripts"]["gcs_url"] == "https://existing.example/transcript.json"
    assert merged["transcripts"]["gcs_json"] == meta_payload["gcs_json"]
    assert merged["transcript_stem"] == "merge_case"
