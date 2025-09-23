from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File, Form
from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy import inspect as sa_inspect

from ..core.config import settings
from ..models.user import User, UserPublic
from ..core.database import get_session
from ..core import crud
from ..core.paths import MEDIA_DIR
from .auth import get_current_user
from ..models.podcast import Podcast, PodcastTemplate, TemplateSegment, StaticSegmentSource, SegmentTiming, BackgroundMusicRule, PodcastTemplateCreate
from ..models.podcast import Episode, MusicAsset, MusicAssetSource
from pydantic import BaseModel
from uuid import uuid4, UUID
import json
import logging
from sqlalchemy import text as _sql_text
from ..models.settings import AppSetting, AdminSettings, load_admin_settings, save_admin_settings
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import uuid
import shutil
import requests
try:
    import stripe as _stripe
except Exception:  # pragma: no cover
    _stripe = None

# Whitelisted tables for admin DB explorer (avoid arbitrary SQL injection surface)
DB_EXPLORER_TABLES = ["user", "podcast", "episode", "podcasttemplate", "podcast_template"]


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

# --- Admin Dependency ---
def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency that checks if the current user is the admin.
    If not, it raises an HTTP 403 Forbidden error.
    """
    # Allow admin by any of: configured admin email, is_admin flag, or role='admin'
    try:
        email_ok = bool(current_user.email and current_user.email.lower() == settings.ADMIN_EMAIL.lower())
    except Exception:
        email_ok = False
    is_flag = bool(getattr(current_user, "is_admin", False))
    has_role = (str(getattr(current_user, "role", "")).lower() == "admin")
    if not (email_ok or is_flag or has_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have permissions to access this resource.",
        )
    return current_user

# --- Admin Endpoints ---
@router.get("/users", response_model=List[UserPublic])
async def get_all_users(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Get a list of all users. Only accessible by the admin.
    """
    return crud.get_all_users(session=session)





@router.get("/summary", status_code=200)
def admin_summary(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Simple platform summary for admin dashboard MVP."""
    user_count = session.exec(select(func.count(User.id))).one()
    podcast_count = session.exec(select(func.count(Podcast.id))).one()
    template_count = session.exec(select(func.count(PodcastTemplate.id))).one()
    episode_count = session.exec(select(func.count(Episode.id))).one()
    published_count = session.exec(select(func.count(Episode.id)).where(Episode.status == "published")).one()
    return {
        "users": user_count,
        "podcasts": podcast_count,
        "templates": template_count,
        "episodes": episode_count,
        "published_episodes": published_count,
    }


# ---------------- Admin Metrics ----------------

def _date_range_30d() -> List[str]:
    """Returns list of ISO dates (YYYY-MM-DD) for the last 30 days inclusive, oldest first."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=29)
    return [(start + timedelta(days=i)).isoformat() for i in range(30)]


@router.get("/metrics", status_code=200)
def admin_metrics(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Operational metrics for the last 30 days. Fast and resilient; Stripe is optional.

    - daily_signups_30d: list[{date, count}] from User.created_at
    - daily_active_users_30d: list[{date, count}] unique Episode.user_id with processed_at on each date
    - mrr_cents, arr_cents: from Stripe (active subscriptions), None if unavailable
    - revenue_30d_cents: from Stripe charges/refunds net last 30d, None if unavailable
    """
    # Build date buckets
    days = _date_range_30d()
    # Signups: fetch and bucket in Python (avoids dialect-specific func/date typing issues)
    since_dt = datetime.strptime(days[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    signup_map: Dict[str, int] = {d: 0 for d in days}
    signup_users = session.exec(select(User).where(User.created_at >= since_dt)).all()
    for u in signup_users:
        try:
            d = u.created_at.date().isoformat()
            if d in signup_map:
                signup_map[d] += 1
        except Exception:
            continue
    daily_signups_30d = [{"date": d, "count": signup_map[d]} for d in days]

    # Active users: distinct user_ids per day with processed episodes
    active_sets: Dict[str, set] = {d: set() for d in days}
    eps = session.exec(
        select(Episode).where((Episode.processed_at != None) & (Episode.processed_at >= since_dt))  # noqa: E711
    ).all()
    for ep in eps:
        try:
            d = ep.processed_at.date().isoformat()
            if d in active_sets:
                active_sets[d].add(ep.user_id)
        except Exception:
            continue
    daily_active_users_30d = [{"date": d, "count": len(active_sets[d])} for d in days]

    # Stripe-derived metrics (optional)
    mrr_cents: Optional[int] = None
    arr_cents: Optional[int] = None
    revenue_30d_cents: Optional[int] = None

    try:
        if _stripe and (os.getenv("STRIPE_SECRET_KEY") or getattr(_stripe, "api_key", None)):
            # Ensure api key set
            if not getattr(_stripe, "api_key", None):
                _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
            # Subscriptions -> normalized monthly revenue
            monthly_total = 0.0
            try:
                subs = _stripe.Subscription.list(status="active", limit=100, expand=["data.items.data.price"])  # type: ignore
                for s in subs.auto_paging_iter():  # type: ignore[attr-defined]
                    items = getattr(s, "items", {}).get("data", []) if hasattr(s, "items") else []
                    for it in items:
                        price = getattr(it, "price", None)
                        qty = int(getattr(it, "quantity", 1) or 1)
                        unit = None
                        interval = None
                        if price:
                            unit = getattr(price, "unit_amount", None)
                            recurring = getattr(price, "recurring", None)
                            if recurring:
                                interval = getattr(recurring, "interval", None)
                        if unit is None or interval is None:
                            continue
                        amt = float(unit) * qty
                        if interval == "month":
                            monthly_total += amt
                        elif interval == "year":
                            monthly_total += amt / 12.0
                        else:
                            # Unknown cadence; skip to avoid skew
                            continue
                mrr_cents = int(round(monthly_total))
                arr_cents = int(round(monthly_total * 12.0))
            except Exception:
                # Leave as None if subscription fetch fails
                mrr_cents = None
                arr_cents = None

            # Revenue last 30 days (charges - refunds)
            try:
                since_ts = int(since_dt.timestamp())
                net = 0
                charges = _stripe.Charge.list(created={"gte": since_ts}, limit=100)
                for ch in charges.auto_paging_iter():  # type: ignore[attr-defined]
                    if getattr(ch, "status", "") == "succeeded":
                        amount = int(getattr(ch, "amount", 0) or 0)
                        refunded = int(getattr(ch, "amount_refunded", 0) or 0)
                        net += max(amount - refunded, 0)
                revenue_30d_cents = int(net)
            except Exception:
                revenue_30d_cents = None
    except Exception:
        # Any Stripe import/config error: keep None values
        mrr_cents = mrr_cents if mrr_cents is not None else None
        arr_cents = arr_cents if arr_cents is not None else None
        revenue_30d_cents = revenue_30d_cents if revenue_30d_cents is not None else None

    return {
        "daily_signups_30d": daily_signups_30d,
        "daily_active_users_30d": daily_active_users_30d,
        "mrr_cents": mrr_cents,
        "arr_cents": arr_cents,
        "revenue_30d_cents": revenue_30d_cents,
    }

# ---------------- Admin Music Library ----------------

class MusicAssetPayload(BaseModel):
    display_name: str
    url: Optional[str] = None
    preview_url: Optional[str] = None  # ignored server-side; derived from url/filename by public router
    mood_tags: Optional[list[str]] = None
    license: Optional[str] = None
    attribution: Optional[str] = None
    source_type: Optional[MusicAssetSource] = None


@router.get("/music/assets", status_code=200)
def admin_list_music_assets(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    rows = session.exec(select(MusicAsset)).all()
    out = []
    for a in rows:
        try:
            tags = a.mood_tags()
        except Exception:
            tags = []
        out.append({
            "id": str(a.id),
            "display_name": a.display_name,
            "filename": a.filename,
            "url": a.filename,
            "duration_s": a.duration_s,
            "mood_tags": tags,
            "source_type": a.source_type,
            "license": a.license,
            "attribution": a.attribution,
            "select_count": a.user_select_count,
            "created_at": a.created_at.isoformat() if getattr(a, 'created_at', None) else None,
        })
    return {"assets": out}


@router.post("/music/assets", status_code=201)
def admin_create_music_asset(
    payload: MusicAssetPayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    if not payload.display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    filename = (payload.url or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="url is required")
    try:
        asset = MusicAsset(
            display_name=payload.display_name.strip(),
            filename=filename,
            mood_tags_json=json.dumps(payload.mood_tags or []),
            source_type=payload.source_type or MusicAssetSource.external,
            license=payload.license,
            attribution=payload.attribution,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id)}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create asset: {e}")


@router.put("/music/assets/{asset_id}", status_code=200)
def admin_update_music_asset(
    asset_id: str,
    payload: MusicAssetPayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    # Coerce to UUID to avoid type mismatch causing 404 on valid IDs
    try:
        key = UUID(str(asset_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset = session.get(MusicAsset, key)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        if payload.display_name is not None:
            asset.display_name = payload.display_name.strip()
        if payload.url is not None and payload.url.strip():
            asset.filename = payload.url.strip()
        if payload.mood_tags is not None:
            asset.mood_tags_json = json.dumps(payload.mood_tags)
        if payload.source_type is not None:
            asset.source_type = payload.source_type
        if payload.license is not None:
            asset.license = payload.license
        if payload.attribution is not None:
            asset.attribution = payload.attribution
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id)}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update asset: {e}")


@router.delete("/music/assets/{asset_id}", status_code=200)
def admin_delete_music_asset(
    asset_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    # Coerce to UUID to avoid type mismatch causing 404 on valid IDs
    try:
        key = UUID(str(asset_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset = session.get(MusicAsset, key)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        session.delete(asset)
        session.commit()
        return {"ok": True}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete asset: {e}")

def _sanitize_filename(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "").strip())
    return base or uuid.uuid4().hex

def _ensure_music_dir() -> Path:
    music_dir = MEDIA_DIR / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    return music_dir

def _unique_path(dirpath: Path, base: str) -> Path:
    candidate = dirpath / base
    if not candidate.exists():
        return candidate
    stem = Path(base).stem
    suf = Path(base).suffix
    for i in range(1, 10000):
        p = dirpath / f"{stem}-{i}{suf}"
        if not p.exists():
            return p
    return dirpath / f"{stem}-{uuid.uuid4().hex}{suf}"

@router.post("/music/assets/upload", status_code=201)
def admin_upload_music_asset(
    file: UploadFile = File(...),
    display_name: Optional[str] = Form(None),
    mood_tags: Optional[str] = Form(None),  # comma-separated or JSON
    license: Optional[str] = Form(None),
    attribution: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        music_dir = _ensure_music_dir()
        orig = file.filename or "uploaded.mp3"
        base = _sanitize_filename(orig)
        if "." not in base:
            base += ".mp3"
        out_path = _unique_path(music_dir, base)
        with out_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        rel_url = f"/static/media/music/{out_path.name}"
        tags_list: list[str] = []
        if mood_tags:
            try:
                if mood_tags.strip().startswith("["):
                    tags_list = [t for t in (json.loads(mood_tags) or []) if t]
                else:
                    tags_list = [t.strip() for t in mood_tags.split(",") if t.strip()]
            except Exception:
                tags_list = []
        asset = MusicAsset(
            display_name=(display_name or Path(orig).stem),
            filename=rel_url,
            mood_tags_json=json.dumps(tags_list or []),
            source_type=MusicAssetSource.external,
            license=license,
            attribution=attribution,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id), "filename": rel_url}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

class MusicAssetImportUrl(BaseModel):
    display_name: str
    source_url: str
    mood_tags: Optional[list[str]] = None
    license: Optional[str] = None
    attribution: Optional[str] = None

@router.post("/music/assets/import-url", status_code=201)
def admin_import_music_asset_by_url(
    payload: MusicAssetImportUrl,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    url = (payload.source_url or "").strip()
    if not url or not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        raise HTTPException(status_code=400, detail="source_url must be http(s)")
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        # Guess extension from content-type or URL
        ext = None
        ct = (r.headers.get("content-type", "") or "").lower()
        if "audio/" in ct:
            ext = "." + ct.split("/", 1)[-1].split(";")[0].strip()
            if ext == ".mpeg":
                ext = ".mp3"
        if not ext:
            try:
                from urllib.parse import urlparse
                p = Path(urlparse(url).path)
                ext = p.suffix or ".mp3"
            except Exception:
                ext = ".mp3"
        safe_name = _sanitize_filename((payload.display_name or "track") + ext)
        music_dir = _ensure_music_dir()
        out_path = _unique_path(music_dir, safe_name)
        with out_path.open("wb") as f:
            shutil.copyfileobj(r.raw, f)
        rel_url = f"/static/media/music/{out_path.name}"
        asset = MusicAsset(
            display_name=payload.display_name.strip(),
            filename=rel_url,
            mood_tags_json=json.dumps(payload.mood_tags or []),
            source_type=MusicAssetSource.external,
            license=payload.license,
            attribution=payload.attribution,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id), "filename": rel_url}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")

# ---------------- Tier Editor (placeholder storage) ----------------

class TierFeature(BaseModel):
    key: str
    label: str
    type: str  # 'boolean' | 'number'
    values: Dict[str, Any]


class TierConfig(BaseModel):
    tiers: list[str]
    features: list[TierFeature]


def _default_tier_config() -> TierConfig:
    return TierConfig(
        tiers=["Free", "Creator", "Pro"],
        features=[
            TierFeature(
                key="can_use_elevenlabs",
                label="Can use ElevenLabs",
                type="boolean",
                values={"Free": False, "Creator": True, "Pro": True},
            ),
            TierFeature(
                key="can_use_flubber",
                label="Can use Flubber",
                type="boolean",
                values={"Free": False, "Creator": False, "Pro": True},
            ),
            TierFeature(
                key="processing_minutes",
                label="Processing minutes allowed",
                type="number",
                values={"Free": 30, "Creator": 300, "Pro": 3000},
            ),
        ],
    )


@router.get("/tiers", response_model=TierConfig)
def get_tier_config(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """Return the current Tier configuration. If missing, seed defaults."""
    rec = session.get(AppSetting, "tier_config")
    if not rec:
        # Seed default config
        cfg = _default_tier_config()
        try:
            rec = AppSetting(key="tier_config", value_json=cfg.model_dump_json())
            session.add(rec)
            session.commit()
        except Exception:
            session.rollback()
            # Return defaults without persisting if DB write fails
            return cfg
        return cfg
    try:
        data = json.loads(rec.value_json or "{}")
        return TierConfig(**data)
    except Exception:
        return _default_tier_config()


@router.put("/tiers", response_model=TierConfig)
def update_tier_config(
    cfg: TierConfig,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """Update and store the Tier configuration (placeholder only)."""
    rec = session.get(AppSetting, "tier_config")
    payload = cfg.model_dump_json()
    try:
        if rec:
            rec.value_json = payload
            rec.updated_at = datetime.utcnow()
            session.add(rec)
        else:
            rec = AppSetting(key="tier_config", value_json=payload)
            session.add(rec)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save tier config: {e}")
    return cfg

# ---------------- Admin Billing Overview ----------------

@router.get("/billing/overview", status_code=200)
def admin_billing_overview(
    session: Session = Depends(get_session),  # kept for parity/future use
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Return minimal billing overview derived from Stripe.

    Fields:
    - active_subscriptions: count of active subscriptions
    - trialing: count of subscriptions in trial
    - canceled_last_30d: count of subs canceled in the last 30 days
    - trial_expiring_7d: count of trialing subs whose trial ends within 7 days
    - gross_mrr_cents: sum of monthly-equivalent recurring revenue (active subs)

    Behavior without Stripe (no library or API key): counts are 0 and gross_mrr_cents is null.
    Also returns optional dashboard_url if STRIPE_DASHBOARD_URL is set in the environment.
    """
    # Defaults for the no-Stripe case
    out: Dict[str, Any] = {
        "active_subscriptions": 0,
        "trialing": 0,
        "canceled_last_30d": 0,
        "trial_expiring_7d": 0,
        "gross_mrr_cents": None,
    }
    dash_url = os.getenv("STRIPE_DASHBOARD_URL")
    if dash_url:
        out["dashboard_url"] = dash_url

    # Stripe missing or not configured -> return defaults
    if not _stripe or not (os.getenv("STRIPE_SECRET_KEY") or getattr(_stripe, "api_key", None)):
        return out

    # Ensure API key set
    try:
        if not getattr(_stripe, "api_key", None):
            _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    except Exception:
        return out

    # Time windows
    now = datetime.now(timezone.utc)
    since_30 = int((now - timedelta(days=30)).timestamp())
    in_7d = int((now + timedelta(days=7)).timestamp())

    # Counts and MRR
    try:
        # Active subscriptions and MRR
        active_count = 0
        monthly_total = 0.0
        try:
            subs = _stripe.Subscription.list(status="active", limit=100, expand=["data.items.data.price"])  # type: ignore
            for s in subs.auto_paging_iter():  # type: ignore[attr-defined]
                active_count += 1
                items = getattr(s, "items", {}).get("data", []) if hasattr(s, "items") else []
                for it in items:
                    price = getattr(it, "price", None)
                    qty = int(getattr(it, "quantity", 1) or 1)
                    unit = None
                    interval = None
                    if price:
                        unit = getattr(price, "unit_amount", None)
                        recurring = getattr(price, "recurring", None)
                        if recurring:
                            interval = getattr(recurring, "interval", None)
                    if unit is None or interval is None:
                        continue
                    amt = float(unit) * qty
                    if interval == "month":
                        monthly_total += amt
                    elif interval == "year":
                        monthly_total += amt / 12.0
        except Exception:
            pass

        out["active_subscriptions"] = int(active_count)
        out["gross_mrr_cents"] = int(round(monthly_total)) if monthly_total > 0 else 0 if active_count > 0 else None

        # Trialing count and trial-expiring-in-7-days
        trialing = 0
        trial_expiring = 0
        try:
            trials = _stripe.Subscription.list(status="trialing", limit=100)
            for t in trials.auto_paging_iter():  # type: ignore[attr-defined]
                trialing += 1
                try:
                    te = int(getattr(t, "trial_end", 0) or 0)
                    # trial_end is a unix timestamp in seconds
                    if te and te <= in_7d and te >= int(now.timestamp()):
                        trial_expiring += 1
                except Exception:
                    continue
        except Exception:
            pass
        out["trialing"] = int(trialing)
        out["trial_expiring_7d"] = int(trial_expiring)

        # Canceled in last 30 days (use canceled_at when available)
        canceled_30d = 0
        try:
            canceled = _stripe.Subscription.list(status="canceled", limit=100)
            for c in canceled.auto_paging_iter():  # type: ignore[attr-defined]
                try:
                    ca = int(getattr(c, "canceled_at", 0) or 0)
                    if ca and ca >= since_30:
                        canceled_30d += 1
                except Exception:
                    continue
        except Exception:
            pass
        out["canceled_last_30d"] = int(canceled_30d)
    except Exception:
        # On any Stripe error return the defaults (possibly with partial fields already set)
        return out

    return out


# ---------------- Admin Podcasts Listing ----------------

@router.get("/podcasts", status_code=200)
def admin_list_podcasts(
    owner_email: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """List podcasts for admins with optional owner email filter and pagination.
    Returns { items, total, limit, offset } where each item has:
      id, name, owner_email, episode_count, created_at, last_episode_at
    """
    # Total count with optional filter
    like = None
    if owner_email:
        like = f"%{owner_email.strip()}%"
    count_stmt = select(func.count(Podcast.id)).select_from(Podcast).join(User, Podcast.user_id == User.id)
    if like:
        try:
            from sqlalchemy import or_  # noqa: F401
            count_stmt = count_stmt.where(User.email.ilike(like))
        except Exception:
            # Fallback to case-insensitive compare via lower()
            count_stmt = count_stmt.where(func.lower(User.email).like((owner_email or '').lower()))
    total = session.exec(count_stmt).one() or 0

    # Page data query
    data_stmt = select(Podcast, User.email).join(User, Podcast.user_id == User.id)
    if like:
        data_stmt = data_stmt.where(User.email.ilike(like))
    # Order by created_at desc if available, else id desc
    try:
        data_stmt = data_stmt.order_by(Podcast.created_at.desc())
    except Exception:
        data_stmt = data_stmt.order_by(Podcast.id.desc())
    data_stmt = data_stmt.offset(offset).limit(limit)
    rows = session.exec(data_stmt).all()

    # Normalize rows
    page_podcasts = []  # list[Podcast]
    owner_map: Dict[str, str] = {}
    for row in rows:
        try:
            pod, email = row  # select(Podcast, User.email)
        except Exception:
            # Fallback if row is RowMapping
            pod = row[0]
            email = row[1]
        page_podcasts.append(pod)
        owner_map[str(pod.id)] = email

    # Episode aggregates for page podcasts only
    ids = [p.id for p in page_podcasts]
    count_map: Dict[str, int] = {str(pid): 0 for pid in ids}
    last_map: Dict[str, Optional[datetime]] = {str(pid): None for pid in ids}
    if ids:
        eps = session.exec(select(Episode).where(Episode.podcast_id.in_(ids))).all()
        for ep in eps:
            pid = str(ep.podcast_id)
            if pid not in count_map:
                continue
            count_map[pid] += 1
            ts = getattr(ep, 'processed_at', None) or getattr(ep, 'created_at', None)
            cur = last_map.get(pid)
            if ts and (cur is None or ts > cur):
                last_map[pid] = ts

    items = []
    for p in page_podcasts:
        pid = str(p.id)
        created_iso = None
        last_iso = None
        try:
            if getattr(p, 'created_at', None):
                created_iso = p.created_at.isoformat()
        except Exception:
            created_iso = None
        try:
            lm = last_map.get(pid)
            last_iso = lm.isoformat() if lm else None
        except Exception:
            last_iso = None
        items.append({
            "id": pid,
            "name": getattr(p, 'name', None),
            "owner_email": owner_map.get(pid),
            "episode_count": int(count_map.get(pid, 0)),
            "created_at": created_iso,
            "last_episode_at": last_iso,
        })

    return {"items": items, "total": int(total or 0), "limit": limit, "offset": offset}


class UserAdminOut(BaseModel):
    id: str
    email: str
    tier: Optional[str]
    is_active: bool
    created_at: str
    episode_count: int
    last_activity: Optional[str] = None
    subscription_expires_at: Optional[str] = None
    last_login: Optional[str] = None

class UserAdminUpdate(BaseModel):
    tier: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_expires_at: Optional[str] = None  # ISO8601 string

@router.get("/users/full", response_model=List[UserAdminOut])
def admin_users_full(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    # Preload episode counts grouped by user
    counts = dict(
        session.exec(select(Episode.user_id, func.count(Episode.id)).group_by(Episode.user_id)).all()
    )
    # Latest activity per user (max processed_at)
    latest = dict(
        session.exec(select(Episode.user_id, func.max(Episode.processed_at)).group_by(Episode.user_id)).all()
    )
    users = crud.get_all_users(session)
    out: List[UserAdminOut] = []
    for u in users:
        last_activity = latest.get(u.id) or u.created_at
        out.append(UserAdminOut(
            id=str(u.id),
            email=u.email,
            tier=u.tier,
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
            episode_count=int(counts.get(u.id, 0)),
            last_activity=last_activity.isoformat() if last_activity else None,
            subscription_expires_at=u.subscription_expires_at.isoformat() if getattr(u,'subscription_expires_at', None) else None,
            last_login=u.last_login.isoformat() if getattr(u,'last_login', None) else None,
        ))
    return out

@router.patch("/users/{user_id}", response_model=UserAdminOut)
def admin_update_user(
    user_id: UUID,
    update: UserAdminUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    # Log raw incoming update for debugging (cast UUID to str for readability)
    logging.getLogger(__name__).debug("admin_update_user payload user_id=%s %s", str(user_id), update.model_dump())
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    changed = False
    if update.tier is not None:
        try:
            norm_tier = update.tier.strip().lower()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid tier value")
        user.tier = norm_tier
        changed = True
    if update.is_active is not None:
        user.is_active = update.is_active
        changed = True
    if update.subscription_expires_at is not None:
        from datetime import datetime as _dt
        raw = update.subscription_expires_at.strip()
        if raw == "":
            user.subscription_expires_at = None
            changed = True
        else:
            try:
                # Accept date-only (YYYY-MM-DD) or full ISO. Replace trailing Z with +00:00 for fromisoformat.
                if len(raw) == 10 and raw.count('-') == 2:  # date-only
                    user.subscription_expires_at = _dt.fromisoformat(raw + "T23:59:59")
                else:
                    if raw.endswith('Z'):
                        raw = raw[:-1] + "+00:00"
                    user.subscription_expires_at = _dt.fromisoformat(raw)
                # Sanity check year to catch malformed inputs (e.g., 0002) before commit
                if user.subscription_expires_at.year < 1900 or user.subscription_expires_at.year > 2100:
                    raise HTTPException(status_code=400, detail="subscription_expires_at year out of acceptable range (1900-2100)")
                changed = True
            except Exception as e:
                logger.warning("Bad subscription_expires_at '%s' for user %s: %s", raw, user_id, e)
                raise HTTPException(status_code=400, detail="Invalid subscription_expires_at format; use YYYY-MM-DD or ISO8601")
    if changed:
        logger.info("Admin %s updating user %s; fields changed tier=%s is_active=%s subscription_expires_at=%s", admin_user.email, user_id, update.tier is not None, update.is_active is not None, update.subscription_expires_at is not None)
        session.add(user)
        session.commit()
        session.refresh(user)
    # compute counts/activity
    episode_count = session.exec(select(func.count(Episode.id)).where(Episode.user_id==user.id)).scalar_one_or_none() or 0
    last_activity = session.exec(select(func.max(Episode.processed_at)).where(Episode.user_id==user.id)).scalar_one_or_none() or user.created_at
    return UserAdminOut(
        id=str(user.id),
        email=user.email,
        tier=user.tier,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        episode_count=int(episode_count),
        last_activity=last_activity.isoformat() if last_activity else None,
        subscription_expires_at=user.subscription_expires_at.isoformat() if getattr(user,'subscription_expires_at', None) else None,
    last_login=user.last_login.isoformat() if getattr(user,'last_login', None) else None,
    )

# ---------------- Admin Settings ----------------


@router.get("/settings", response_model=AdminSettings)
def get_admin_settings(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    return load_admin_settings(session)


@router.put("/settings", response_model=AdminSettings)
def update_admin_settings(
    payload: AdminSettings,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    return save_admin_settings(session, payload)



# --- DB Explorer helpers ---

def _db_get_columns(session: Session, table_name: str) -> list[str]:
    bind = session.get_bind()
    dialect = bind.dialect.name.lower() if bind else ''
    if 'sqlite' in dialect:
        cols_res = session.exec(_sql_text(f"PRAGMA table_info({table_name})"))
        return [c[1] for c in cols_res]
    inspector = sa_inspect(bind)
    return [col['name'] for col in inspector.get_columns(table_name)]


def _db_rows_to_dicts(result) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in result.mappings().all()]
    except Exception:
        rows = result.fetchall()
        keys = result.keys() if hasattr(result, 'keys') else []
        return [dict(zip(keys, row)) for row in rows]

# ---------------- DB Explorer Endpoints ----------------

@router.get("/db/tables", status_code=200)
def admin_db_tables(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """List whitelisted tables available for browsing/editing."""
    # Filter only existing tables among whitelist
    existing = []
    for t in DB_EXPLORER_TABLES:
        try:
            session.exec(_sql_text(f"SELECT 1 FROM {t} LIMIT 1"))
            existing.append(t)
        except Exception:
            continue
    return {"tables": existing}


@router.get("/db/table/{table_name}", status_code=200)
def admin_db_table_rows(
    table_name: str,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Return paginated rows for a whitelisted table.

    Orders newest-first by created_at DESC if that column exists, else by id DESC.
    Returns: { table, columns, rows, total, offset, limit }
    """
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    # Normalize and clamp pagination
    if limit <= 0:
        limit = 50
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0
    try:
        # Columns
        columns = _db_get_columns(session, table_name)
        if not columns:
            return {"table": table_name, "columns": [], "rows": [], "total": 0, "offset": offset, "limit": limit}
        # Ordering: special-case 'episode' to use publish_at DESC per request.
        if table_name == "episode" and "publish_at" in columns:
            order_clause = "publish_at DESC"
        else:
            preferred_order_cols = [
                "created_at",
                "processed_at",
                "publish_at",
                "published_at",
                "id",
            ]
            chosen_col = None
            for c in preferred_order_cols:
                if c in columns:
                    chosen_col = c
                    break
            if not chosen_col:
                chosen_col = columns[0]
            order_clause = f"{chosen_col} DESC"
        total_res = session.exec(_sql_text(f"SELECT COUNT(*) FROM {table_name}"))
        total = total_res.first()[0]
        stmt = _sql_text(f"SELECT * FROM {table_name} ORDER BY {order_clause} LIMIT :lim OFFSET :off").bindparams(lim=limit, off=offset)
        res = session.exec(stmt)
        rows = _db_rows_to_dicts(res)
        return {"table": table_name, "columns": columns, "rows": rows, "total": total, "offset": offset, "limit": limit}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")



@router.get("/db/table/{table_name}/{row_id}", status_code=200)
def admin_db_table_row_detail(
    table_name: str,
    row_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    pk_col = "id"  # convention
    try:
        stmt = _sql_text(f"SELECT * FROM {table_name} WHERE {pk_col} = :rid").bindparams(rid=row_id)
        res = session.exec(stmt)
        row_map = res.mappings().first()
        if not row_map:
            raise HTTPException(status_code=404, detail="Row not found")
        return {"table": table_name, "row": dict(row_map)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {e}")


class RowUpdatePayload(BaseModel):
    updates: dict


@router.patch("/db/table/{table_name}/{row_id}", status_code=200)
def admin_db_table_row_update(
    table_name: str,
    row_id: str,
    payload: RowUpdatePayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    updates = payload.updates or {}
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    # Fetch columns & filter allowed (exclude id & obvious system fields)
    column_names = _db_get_columns(session, table_name)
    protected = {"id", "created_at", "processed_at", "publish_at", "published_at", "spreaker_episode_id"}
    set_parts = []
    params = {"rid": row_id}
    for k, v in updates.items():
        if k not in column_names:
            continue
        if k in protected:
            continue
        param_name = f"val_{k}"
        set_parts.append(f"{k} = :{param_name}")
        params[param_name] = v
    if not set_parts:
        raise HTTPException(status_code=400, detail="No permissible fields to update")
    sql = f"UPDATE {table_name} SET {', '.join(set_parts)} WHERE id = :rid"
    try:
        stmt = _sql_text(sql).bindparams(**params)
        session.exec(stmt)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    return admin_db_table_row_detail(table_name, row_id, session, admin_user)


class RowInsertPayload(BaseModel):
    values: dict


@router.post("/db/table/{table_name}", status_code=201)
def admin_db_table_row_insert(
    table_name: str,
    payload: RowInsertPayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    values = payload.values or {}
    if not isinstance(values, dict) or not values:
        raise HTTPException(status_code=400, detail="No values provided")
    # Fetch columns & filter allowed
    column_names = _db_get_columns(session, table_name)
    if not column_names:
        raise HTTPException(status_code=400, detail="Unknown table or no columns")
    protected = {"created_at", "processed_at", "publish_at", "published_at", "spreaker_episode_id"}
    params = {}
    insert_cols = []
    for k, v in values.items():
        if k not in column_names:
            continue
        if k in protected:
            continue
        insert_cols.append(k)
        params[f"val_{k}"] = v
    # Ensure id present if column exists
    if "id" in cols and "id" not in values:
        new_id = str(uuid4())
        insert_cols.append("id")
        params["val_id"] = new_id
    row_id = values.get("id") or params.get("val_id")
    if not insert_cols:
        raise HTTPException(status_code=400, detail="No permissible fields to insert")
    placeholders = ", ".join([f":val_{c}" for c in insert_cols])
    cols_sql = ", ".join(insert_cols)
    sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES ({placeholders})"
    try:
        stmt = _sql_text(sql).bindparams(**params)
        session.exec(stmt)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Insert failed: {e}")
    # Return inserted row if id exists
    if row_id is not None:
        return admin_db_table_row_detail(table_name, str(row_id), session, admin_user)
    # Fallback: return a minimal payload
    return {"table": table_name, "inserted": True, "values": {k: values.get(k) for k in insert_cols}}


@router.delete("/db/table/{table_name}/{row_id}", status_code=200)
def admin_db_table_row_delete(
    table_name: str,
    row_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user)
):
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    try:
        stmt = _sql_text(f"DELETE FROM {table_name} WHERE id = :rid").bindparams(rid=row_id)
        session.exec(stmt)
        session.commit()
        # SQLite cursor rowcount accessible via underlying; we won't rely—assume success if no exception
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    return {"deleted": True, "table": table_name, "id": row_id}
