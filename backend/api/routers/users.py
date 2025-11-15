from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime
from sqlmodel import Session

from ..core.config import settings
from ..models.user import User, UserPublic
from ..core.database import get_session
from ..core import crud
from api.routers.auth import get_current_user

# lowercase tag
router = APIRouter(
    prefix="/users",
    tags=["users"],
)

# --- helper: build a correct UserPublic without importing from auth ---
def _parse_terms_version_date(version_str: str | None) -> datetime | None:
    """Parse TERMS_VERSION string (e.g., '2025-10-22') as a date.
    
    Returns None if version_str is None or cannot be parsed.
    """
    if not version_str:
        return None
    try:
        # TERMS_VERSION is in format 'YYYY-MM-DD', parse as date and convert to datetime at midnight UTC
        from datetime import date
        parsed_date = datetime.strptime(version_str.strip(), "%Y-%m-%d").date()
        return datetime.combine(parsed_date, datetime.min.time()).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _terms_need_acceptance(user: User, current_terms_version: str | None) -> bool:
    """Check if user needs to accept updated terms based on date comparison.
    
    Returns True if:
    - Current terms version date is newer than user's terms_accepted_at date, OR
    - User has never accepted terms (both terms_version_accepted and terms_accepted_at are None), OR
    - Version strings don't match (fallback if date parsing fails or date is missing)
    """
    if not current_terms_version:
        return False
    
    accepted_version = getattr(user, "terms_version_accepted", None)
    user_accepted_at = getattr(user, "terms_accepted_at", None)
    
    # If user has never accepted any version, they need to accept
    if not accepted_version and not user_accepted_at:
        return True
    
    # Try date-based comparison first (most accurate)
    current_terms_date = _parse_terms_version_date(current_terms_version)
    if current_terms_date and user_accepted_at:
        # Both dates are available - compare them
        return current_terms_date > user_accepted_at.replace(tzinfo=None)
    
    # Fallback to version string comparison if:
    # - Date parsing failed, OR
    # - User has version but no date (legacy data)
    if accepted_version:
        return accepted_version != current_terms_version
    
    # If we get here, user has no version string but might have a date (unlikely)
    # Default to requiring acceptance for safety
    return True


def _to_user_public(u: User) -> UserPublic:
    """Convert User model to UserPublic schema with defensive attribute access.
    
    This function safely accesses user attributes even if the user instance is detached
    from the database session, handling potential DetachedInstanceError exceptions.
    """
    from api.core.logging import get_logger
    logger = get_logger("api.routers.users")
    
    try:
        admin_email = getattr(settings, "ADMIN_EMAIL", None)
        
        # Safely get email - handle detached instances
        try:
            user_email = getattr(u, "email", None)
            if user_email:
                user_email = str(user_email).lower()
        except Exception as email_err:
            logger.warning("Failed to access user email attribute: %s", email_err)
            user_email = None
        
        is_admin_email = bool(
            user_email
            and admin_email
            and user_email == str(admin_email).lower()
        )
        
        terms_required = getattr(settings, "TERMS_VERSION", None)
        
        # Try to validate user model - this may fail if attributes are inaccessible
        try:
            public = UserPublic.model_validate(u, from_attributes=True)
        except Exception as validate_err:
            logger.error("Failed to validate UserPublic model: %s", validate_err, exc_info=True)
            # Fallback: try to build UserPublic manually from accessible attributes
            try:
                user_id = getattr(u, "id", None)
                if not user_id:
                    raise ValueError("User ID is required but not accessible")
                
                # Build UserPublic with safe attribute access
                public_data = {
                    "id": user_id,
                    "email": user_email or "",
                    "is_active": getattr(u, "is_active", True),
                    "tier": getattr(u, "tier", "free"),
                    "created_at": getattr(u, "created_at", None),
                    "last_login": getattr(u, "last_login", None),
                    "terms_version_accepted": getattr(u, "terms_version_accepted", None),
                    "terms_accepted_at": getattr(u, "terms_accepted_at", None),
                    "role": getattr(u, "role", None),
                }
                public = UserPublic(**public_data)
            except Exception as fallback_err:
                logger.error("Failed to build UserPublic fallback: %s", fallback_err, exc_info=True)
                raise ValueError(f"Unable to serialize user to UserPublic: {validate_err}") from validate_err
        
        # Use the role from database (don't override it!)
        db_role = None
        try:
            db_role = getattr(u, "role", None)
            if db_role is not None:
                public.role = db_role
        except Exception:
            # If we can't access role, keep the value from model_validate
            db_role = getattr(public, "role", None)
        
        # Set is_admin flag (legacy support) - true if they have any admin role OR match ADMIN_EMAIL
        try:
            user_is_admin = getattr(u, "is_admin", False)
            public.is_admin = is_admin_email or bool(user_is_admin) or (db_role in ("admin", "superadmin") if db_role else False)
        except Exception:
            # If we can't access is_admin, use the value from model_validate or role-based check
            public.is_admin = is_admin_email or (db_role in ("admin", "superadmin") if db_role else False)
        
        # Check if terms need acceptance based on date comparison
        env = (settings.APP_ENV or "dev").strip().lower()
        if env in {"dev", "development", "local", "test", "testing"}:
            # Skip terms enforcement in dev mode
            public.terms_version_required = None
        elif terms_required:
            try:
                if _terms_need_acceptance(u, terms_required):
                    # Terms need to be accepted - set required version
                    public.terms_version_required = terms_required
                else:
                    # Terms are up to date
                    public.terms_version_required = None
            except Exception as terms_err:
                # If terms check fails, don't require terms (safer default)
                logger.warning("Failed to check terms acceptance: %s", terms_err)
                public.terms_version_required = None
        else:
            # No terms version set
            public.terms_version_required = None
        
        return public
    except Exception as e:
        logger.error("Critical error in _to_user_public: %s", e, exc_info=True)
        # Re-raise as a more descriptive error
        raise ValueError(f"Failed to convert user to UserPublic: {e}") from e

class ElevenLabsAPIKeyUpdate(BaseModel):
    api_key: str

class SpreakerTokenUpdate(BaseModel):
    access_token: str

class AudioCleanupSettingsUpdate(BaseModel):
    settings: Dict[str, Any]

class AudioCleanupSettingsPublic(BaseModel):
    settings: Dict[str, Any]

class AudioPipelinePreferenceUpdate(BaseModel):
    use_advanced_audio: bool

class AudioPipelinePreferencePublic(BaseModel):
    use_advanced_audio: bool

class SMSNotificationPreferencesUpdate(BaseModel):
    # Note: phone_number cannot be set via this endpoint - it must be verified via /api/auth/verify-phone first
    sms_notifications_enabled: bool | None = None
    sms_notify_transcription_ready: bool | None = None
    sms_notify_publish: bool | None = None
    sms_notify_worker_down: bool | None = None

class SMSNotificationPreferencesPublic(BaseModel):
    phone_number: str | None = None
    sms_notifications_enabled: bool = False
    sms_notify_transcription_ready: bool = False
    sms_notify_publish: bool = False
    sms_notify_worker_down: bool = False

@router.get("/me", response_model=UserPublic)
async def read_users_me(
    response: Response,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get current user profile.
    
    CRITICAL: Explicitly refresh user from database to ensure terms_version_accepted
    and other fields are current, preventing intermittent ToS re-acceptance bugs.
    """
    from api.core.logging import get_logger
    logger = get_logger("api.routers.users")
    
    # Prevent HTTP caching of user profile data
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    # Always re-query user from database to ensure we have latest committed data
    # get_current_user may return a cached (detached) user instance, so we need
    # to fetch a fresh instance attached to this session to avoid session errors
    try:
        from sqlmodel import select
        from api.models.user import User
        # Get user ID (should always be accessible even from detached instances)
        user_id = current_user.id
        # Re-query user from database to get fresh, attached instance
        refreshed_user = session.exec(select(User).where(User.id == user_id)).first()
        if refreshed_user:
            current_user = refreshed_user
        else:
            logger.error("User %s not found in database after authentication", user_id)
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        # If re-query fails, log and try to use current_user as-is
        logger.error("Failed to re-query user in /me endpoint: %s", e, exc_info=True)
        # Continue and try to serialize - if this also fails, the exception handler will catch it
    
    # Try to serialize user to UserPublic
    try:
        return _to_user_public(current_user)
    except Exception as e:
        logger.error("Failed to serialize user to UserPublic in /me endpoint: %s", e, exc_info=True)
        # Re-raise as HTTPException so it's handled properly
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve user profile. Please try again or contact support if the issue persists."
        )

@router.get("/me/stats", response_model=Dict[str, Any])
async def read_user_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    return crud.get_user_stats(session=session, user_id=current_user.id)

@router.put("/me/elevenlabs-key", response_model=UserPublic)
async def update_elevenlabs_api_key(
    key_update: ElevenLabsAPIKeyUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    current_user.elevenlabs_api_key = key_update.api_key
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return _to_user_public(current_user)

@router.put("/me/spreaker-token", response_model=UserPublic)
async def update_spreaker_access_token(
    token_update: SpreakerTokenUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not token_update.access_token or len(token_update.access_token) < 10:
        raise HTTPException(status_code=400, detail="Invalid Spreaker token")
    current_user.spreaker_access_token = token_update.access_token.strip()
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return _to_user_public(current_user)

@router.put("/me/audio-cleanup-settings", response_model=UserPublic)
async def update_audio_cleanup_settings(
    payload: AudioCleanupSettingsUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    import json
    try:
        json.dumps(payload.settings)
    except Exception:
        raise HTTPException(status_code=400, detail="Settings must be JSON serializable")

    from pydantic import BaseModel
    class _CleanupCore(BaseModel):
        removeFillers: bool = True
        removePauses: bool = True
        maxPauseSeconds: float = 1.5
        targetPauseSeconds: float = 0.5

    s_in = dict(payload.settings or {})
    model = _CleanupCore(
        removeFillers=bool(s_in.get('removeFillers', True)) if 'removeFillers' in s_in else True,
        removePauses=bool(s_in.get('removePauses', True)) if 'removePauses' in s_in else True,
        maxPauseSeconds=float(s_in.get('maxPauseSeconds', 1.5)) if 'maxPauseSeconds' in s_in else 1.5,
        targetPauseSeconds=float(s_in.get('targetPauseSeconds', 0.5)) if 'targetPauseSeconds' in s_in else 0.5,
    )
    if not (model.targetPauseSeconds > 0 and model.maxPauseSeconds >= model.targetPauseSeconds):
        raise HTTPException(status_code=400, detail="Invalid pause settings: require maxPauseSeconds >= targetPauseSeconds > 0")

    s_in.update({
        'removeFillers': model.removeFillers,
        'removePauses': model.removePauses,
        'maxPauseSeconds': float(model.maxPauseSeconds),
        'targetPauseSeconds': float(model.targetPauseSeconds),
    })

    current_user.audio_cleanup_settings_json = json.dumps(s_in)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return _to_user_public(current_user)

@router.get("/me/audio-cleanup-settings", response_model=AudioCleanupSettingsPublic)
async def get_audio_cleanup_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    import json
    raw = getattr(current_user, 'audio_cleanup_settings_json', None)
    defaults = {
        "censorEnabled": False,
        "censorWords": ["fuck", "shit"],
        "censorFuzzy": True,
        "censorMatchThreshold": 0.8,
        "censorBeepMs": 250,
        "censorBeepFreq": 1000,
        "censorBeepGainDb": 0.0,
        "censorBeepFile": None,
        "removeFillers": True,
        "fillerWords": ["um","uh","er","ah"],
        "removePauses": True,
        "maxPauseSeconds": 1.5,
        "targetPauseSeconds": 0.5,
        "autoDeleteRawAudio": False,
        "commands": {
            "flubber": {"action": "rollback_restart", "trigger_keyword": "flubber"},
            "intern": {
                "action": "ai_command",
                "trigger_keyword": "intern",
                "end_markers": ["stop", "stop intern"],
                "remove_end_marker": True,
                "keep_command_token_in_transcript": True,
            },
        },
    }
    if not raw:
        return { 'settings': defaults }
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}
    if isinstance(parsed, dict):
        merged = {**defaults, **parsed}
        try:
            cmds = merged.get("commands") or {}
            if not isinstance(cmds, dict):
                cmds = {}
            cmd_defaults = defaults["commands"]
            out_cmds = {**cmd_defaults, **cmds}
            intern_cfg = dict(out_cmds.get("intern") or {})
            if "end_markers" not in intern_cfg or not isinstance(intern_cfg.get("end_markers"), list):
                intern_cfg["end_markers"] = cmd_defaults["intern"]["end_markers"]
            if "remove_end_marker" not in intern_cfg:
                intern_cfg["remove_end_marker"] = cmd_defaults["intern"]["remove_end_marker"]
            if "keep_command_token_in_transcript" not in intern_cfg:
                intern_cfg["keep_command_token_in_transcript"] = cmd_defaults["intern"]["keep_command_token_in_transcript"]
            out_cmds["intern"] = intern_cfg
            merged["commands"] = out_cmds
        except Exception:
            pass
    else:
        merged = defaults
    return { 'settings': merged }

@router.get("/me/audio-pipeline", response_model=AudioPipelinePreferencePublic)
async def get_audio_pipeline_preference(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Return the user's advanced audio processing preference."""
    return {
        "use_advanced_audio": bool(getattr(current_user, "use_advanced_audio_processing", False))
    }

@router.put("/me/audio-pipeline", response_model=AudioPipelinePreferencePublic)
async def update_audio_pipeline_preference(
    payload: AudioPipelinePreferenceUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Persist the user's preferred audio processing pipeline."""
    current_user.use_advanced_audio_processing = bool(payload.use_advanced_audio)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return {
        "use_advanced_audio": bool(current_user.use_advanced_audio_processing)
    }

@router.get("/me/capabilities", response_model=Dict[str, Any])
async def get_user_capabilities(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    from ..services.tts_google import texttospeech as _gtts  # type: ignore
    from ..core.config import settings as _settings
    from ..models.podcast import MediaItem
    from sqlmodel import select

    has_elevenlabs = bool(getattr(current_user, 'elevenlabs_api_key', None) or getattr(_settings, 'ELEVENLABS_API_KEY', None))
    has_google_tts = _gtts is not None
    try:
        stmt = select(MediaItem).where(
            MediaItem.user_id == current_user.id,
            MediaItem.trigger_keyword != None  # noqa: E711
        )
        items = session.exec(stmt).all()
        has_any_sfx_triggers = any(items)
    except Exception:
        has_any_sfx_triggers = False
    return {
        'has_elevenlabs': bool(has_elevenlabs),
        'has_google_tts': bool(has_google_tts),
        'has_any_sfx_triggers': bool(has_any_sfx_triggers),
    }

@router.get("/me/sms-preferences", response_model=SMSNotificationPreferencesPublic)
async def get_sms_preferences(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get current user's SMS notification preferences."""
    return SMSNotificationPreferencesPublic(
        phone_number=getattr(current_user, 'phone_number', None),
        sms_notifications_enabled=getattr(current_user, 'sms_notifications_enabled', False),
        sms_notify_transcription_ready=getattr(current_user, 'sms_notify_transcription_ready', False),
        sms_notify_publish=getattr(current_user, 'sms_notify_publish', False),
        sms_notify_worker_down=getattr(current_user, 'sms_notify_worker_down', False),
    )

@router.put("/me/sms-preferences", response_model=SMSNotificationPreferencesPublic)
async def update_sms_preferences(
    preferences: SMSNotificationPreferencesUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update current user's SMS notification preferences.
    
    Note: Phone number must be verified separately using /api/auth/verify-phone endpoint
    before it can be used for SMS notifications. Phone number is set automatically when verified.
    """
    changed = False
    
    # Check if SMS columns exist (safe migration handling)
    try:
        from sqlalchemy import inspect as sql_inspect
        inspector = sql_inspect(session.get_bind())
        user_columns = {col['name'] for col in inspector.get_columns('user')}
        has_sms_columns = all(col in user_columns for col in [
            'sms_notifications_enabled', 'sms_notify_transcription_ready', 
            'sms_notify_publish', 'sms_notify_worker_down', 'phone_number'
        ])
    except Exception:
        # If we can't check, assume columns don't exist and return error
        has_sms_columns = False
    
    if not has_sms_columns:
        raise HTTPException(
            status_code=503,
            detail="SMS notifications are not yet available. Database migration is pending."
        )
    
    # Update notification preferences (only if columns exist)
    if preferences.sms_notifications_enabled is not None:
        phone_number = getattr(current_user, 'phone_number', None)
        if preferences.sms_notifications_enabled and not phone_number:
            raise HTTPException(
                status_code=400,
                detail="Phone number must be verified before enabling SMS notifications. Please verify your phone number first using /api/auth/verify-phone"
            )
        setattr(current_user, 'sms_notifications_enabled', preferences.sms_notifications_enabled)
        changed = True
    
    if preferences.sms_notify_transcription_ready is not None:
        setattr(current_user, 'sms_notify_transcription_ready', preferences.sms_notify_transcription_ready)
        changed = True
    
    if preferences.sms_notify_publish is not None:
        setattr(current_user, 'sms_notify_publish', preferences.sms_notify_publish)
        changed = True
    
    # Only allow admins to enable worker down notifications
    if preferences.sms_notify_worker_down is not None:
        from api.routers.auth.utils import is_admin
        if preferences.sms_notify_worker_down and not is_admin(current_user):
            raise HTTPException(
                status_code=403,
                detail="Only admins can enable worker down notifications"
            )
        setattr(current_user, 'sms_notify_worker_down', preferences.sms_notify_worker_down)
        changed = True
    
    if changed:
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
    
    return SMSNotificationPreferencesPublic(
        phone_number=getattr(current_user, 'phone_number', None),
        sms_notifications_enabled=getattr(current_user, 'sms_notifications_enabled', False),
        sms_notify_transcription_ready=getattr(current_user, 'sms_notify_transcription_ready', False),
        sms_notify_publish=getattr(current_user, 'sms_notify_publish', False),
        sms_notify_worker_down=getattr(current_user, 'sms_notify_worker_down', False),
    )
