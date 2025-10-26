"""Assembly task entry points."""

from __future__ import annotations

try:
    from ..app import celery_app
except ModuleNotFoundError:
    celery_app = None  # type: ignore[assignment]
except Exception:  # pragma: no cover - defensive fallback during startup
    celery_app = None  # type: ignore[assignment]


def _delegate_orchestrator(
    *,
    episode_id: str,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    episode_details: dict,
    user_id: str,
    podcast_id: str,
    intents: dict | None = None,
    skip_charge: bool = False,
):
    """Import the heavy orchestrator lazily and delegate execution to it."""

    try:
        from .orchestrator import orchestrate_create_podcast_episode as _impl
    except Exception as exc:  # pragma: no cover - import errors surfaced on demand
        raise RuntimeError("assembly orchestrator unavailable") from exc

    return _impl(
        episode_id=episode_id,
        template_id=template_id,
        main_content_filename=main_content_filename,
        output_filename=output_filename,
        tts_values=tts_values,
        episode_details=episode_details,
        user_id=user_id,
        podcast_id=podcast_id,
        intents=intents,
        skip_charge=skip_charge,
    )


def orchestrate_create_podcast_episode(
    *,
    episode_id: str,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    episode_details: dict,
    user_id: str,
    podcast_id: str,
    intents: dict | None = None,
    skip_charge: bool = False,
):
    return _delegate_orchestrator(
        episode_id=episode_id,
        template_id=template_id,
        main_content_filename=main_content_filename,
        output_filename=output_filename,
        tts_values=tts_values,
        episode_details=episode_details,
        user_id=user_id,
        podcast_id=podcast_id,
        intents=intents,
        skip_charge=skip_charge,
    )


if celery_app is not None:

    @celery_app.task(name="create_podcast_episode")
    def create_podcast_episode(
        episode_id: str,
        template_id: str,
        main_content_filename: str,
        output_filename: str,
        tts_values: dict,
        episode_details: dict,
        user_id: str,
        podcast_id: str,
        intents: dict | None = None,
        *,
        skip_charge: bool = False,
    ):
        """Celery task wrapper delegating to the orchestrator helper."""

        return _delegate_orchestrator(
            episode_id=episode_id,
            template_id=template_id,
            main_content_filename=main_content_filename,
            output_filename=output_filename,
            tts_values=tts_values,
            episode_details=episode_details,
            user_id=user_id,
            podcast_id=podcast_id,
            intents=intents,
            skip_charge=skip_charge,
        )
else:  # pragma: no cover - exercised indirectly via inline import

    def create_podcast_episode(
        episode_id: str,
        template_id: str,
        main_content_filename: str,
        output_filename: str,
        tts_values: dict,
        episode_details: dict,
        user_id: str,
        podcast_id: str,
        intents: dict | None = None,
        *,
        skip_charge: bool = False,
    ):
        return _delegate_orchestrator(
            episode_id=episode_id,
            template_id=template_id,
            main_content_filename=main_content_filename,
            output_filename=output_filename,
            tts_values=tts_values,
            episode_details=episode_details,
            user_id=user_id,
            podcast_id=podcast_id,
            intents=intents,
            skip_charge=skip_charge,
        )


__all__ = ["create_podcast_episode", "orchestrate_create_podcast_episode"]

