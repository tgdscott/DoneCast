from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.database import get_session
from api.models.user import User
from api.routers.auth import get_current_user
from api.services.episodes import assembler as _svc_assembler

router = APIRouter(tags=["episodes"])  # parent provides '/episodes' prefix
log = logging.getLogger("ppp.episodes.precheck")


@router.post("/precheck/minutes", status_code=status.HTTP_200_OK)
async def precheck_minutes(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    template_id = payload.get("template_id")
    main_content_filename = payload.get("main_content_filename")

    if not template_id or not main_content_filename:
        raise HTTPException(status_code=400, detail="template_id and main_content_filename are required.")

    try:
        return _svc_assembler.minutes_precheck(
            session=session,
            current_user=current_user,
            template_id=str(template_id),
            main_content_filename=str(main_content_filename),
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("minutes precheck failed")
        raise HTTPException(status_code=500, detail="Failed to evaluate minutes precheck.")
