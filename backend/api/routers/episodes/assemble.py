import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.database import get_session
from api.routers.auth import get_current_user
from api.models.user import User
from api.services.episodes import assembler as _svc_assembler

router = APIRouter(tags=["episodes"])  # parent episodes router provides '/episodes' prefix
log = logging.getLogger("ppp.episodes.assemble")

@router.post("/assemble", status_code=status.HTTP_202_ACCEPTED)
@router.post("/assemble/", status_code=status.HTTP_202_ACCEPTED)
async def assemble_episode(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    log.info("event=assemble.endpoint.start user_id=%s template_id=%s main_content=%s output=%s", 
             getattr(current_user, 'id', None), 
             payload.get("template_id"),
             payload.get("main_content_filename"),
             payload.get("output_filename"))

    template_id = payload.get("template_id")
    main_content_filename = payload.get("main_content_filename")
    output_filename = payload.get("output_filename")
    tts_values = payload.get("tts_values") or {}
    episode_details = dict(payload.get("episode_details") or {})
    use_auphonic = payload.get("use_auphonic")
    if use_auphonic is None:
        use_auphonic = bool(getattr(current_user, "use_advanced_audio_processing", False))
    else:
        use_auphonic = bool(use_auphonic)
    
    # Include flubber_cuts_ms in episode_details so the assembler can apply them
    if payload.get("flubber_cuts_ms"):
        episode_details["flubber_cuts_ms"] = payload.get("flubber_cuts_ms")
    episode_details["use_auphonic"] = use_auphonic

    if not template_id or not main_content_filename or not output_filename:
        log.error("event=assemble.endpoint.validation_failed missing_fields template_id=%s main_content=%s output=%s",
                 template_id, main_content_filename, output_filename)
        raise HTTPException(status_code=400, detail="template_id, main_content_filename, output_filename are required.")

    try:
        log.info("event=assemble.endpoint.calling_service")
        svc_result = _svc_assembler.assemble_or_queue(
            session=session,
            current_user=current_user,
            template_id=str(template_id),
            main_content_filename=str(main_content_filename),
            output_filename=str(output_filename),
            tts_values=tts_values,
            episode_details=episode_details,
            intents=payload.get('intents') or None,
            use_auphonic=use_auphonic,
        )
        log.info("event=assemble.endpoint.service_complete mode=%s episode_id=%s job_id=%s",
                svc_result.get("mode"), svc_result.get("episode_id"), svc_result.get("job_id"))
    except Exception as e:
        log.exception("event=assemble.endpoint.service_error error=%s", str(e))
        raise

    if svc_result.get("mode") == "eager-inline":
        log.info("event=assemble.endpoint.returning_eager_inline episode_id=%s", svc_result.get("episode_id"))
        return {
            "job_id": "eager-inline",
            "status": "processed",
            "episode_id": svc_result.get("episode_id"),
            "message": "Episode assembled synchronously.",
            "result": svc_result.get("result"),
        }
    elif svc_result.get("mode") == "queued":
        # Episode was queued because worker is down - return friendly message
        log.info("event=assemble.endpoint.returning_queued episode_id=%s job_id=%s", 
                svc_result.get("episode_id"), svc_result.get("job_id"))
        return {
            "job_id": svc_result.get("job_id"),
            "status": "queued",
            "episode_id": svc_result.get("episode_id"),
            "message": svc_result.get("message", "Your episode has been queued for processing. You will receive a notification once it has been published.")
        }
    else:
        # Normal queued/dispatched response
        log.info("event=assemble.endpoint.returning_dispatched episode_id=%s job_id=%s mode=%s", 
                svc_result.get("episode_id"), svc_result.get("job_id"), svc_result.get("mode"))
        return {
            "job_id": svc_result.get("job_id"),
            "status": svc_result.get("status", "queued"),
            "episode_id": svc_result.get("episode_id"),
            "message": svc_result.get("message", "Episode assembly has been queued.")
        }
