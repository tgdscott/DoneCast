from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Tuple, Optional, Set

import json
import re

from sqlmodel import Session, select

from api.models.podcast import Episode, EpisodeStatus


_STATUS_PRIORITY = {
    EpisodeStatus.published: 5,
    EpisodeStatus.processed: 4,
    EpisodeStatus.processing: 3,
    EpisodeStatus.pending: 2,
    EpisodeStatus.error: 1,
}


def normalize_title(title: str | None) -> str:
    """Return a normalised episode title for duplicate detection."""

    if not title:
        return ""
    return re.sub(r"\s+", " ", title).strip().lower()


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _normalize_publish_datetime(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    tz = getattr(dt, "tzinfo", None)
    if tz is not None:
        try:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return dt.replace(tzinfo=None)
    return dt


def _coerce_datetime(value: Any) -> datetime | None:
    candidate: datetime | None = None
    if isinstance(value, datetime):
        candidate = value
    elif isinstance(value, str) and value:
        text = value.strip()
        if text:
            try:
                # Accept ISO8601 (with or without trailing Z)
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                candidate = datetime.fromisoformat(text)
            except Exception:
                try:
                    candidate = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    candidate = None
    return _normalize_publish_datetime(candidate)


def _coerce_status(value: Any) -> EpisodeStatus | None:
    if value is None:
        return None
    if isinstance(value, EpisodeStatus):
        return value
    try:
        if isinstance(value, str):
            return EpisodeStatus(value)
    except ValueError:
        pass
    return None


def _load_meta(episode: Episode) -> Dict[str, Any]:
    try:
        data = json.loads(episode.meta_json or "{}")
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_meta(episode: Episode, data: Dict[str, Any]) -> None:
    try:
        episode.meta_json = json.dumps(data)
    except Exception:
        episode.meta_json = json.dumps({})


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        try:
            if value.tzinfo and value.tzinfo.utcoffset(value) is not None:
                return value.isoformat()
            return value.replace(tzinfo=None).isoformat()
        except Exception:
            return str(value)
    if isinstance(value, EpisodeStatus):
        return value.value
    return value


def episode_to_payload(episode: Episode) -> Dict[str, Any]:
    """Convert an Episode model into a dict suitable for merge checks."""

    payload: Dict[str, Any] = {
        "title": episode.title,
        "show_notes": episode.show_notes,
        "final_audio_path": episode.final_audio_path,
        "cover_path": episode.cover_path,
        "remote_cover_url": episode.remote_cover_url,
        "season_number": episode.season_number,
        "episode_number": episode.episode_number,
        "spreaker_episode_id": episode.spreaker_episode_id,
        "is_published_to_spreaker": episode.is_published_to_spreaker,
        "publish_at": episode.publish_at,
        "publish_at_local": episode.publish_at_local,
        "status": episode.status,
        "tags": episode.tags(),
        "is_explicit": episode.is_explicit,
        "meta": _load_meta(episode),
        "original_guid": episode.original_guid,
        "source_media_url": episode.source_media_url,
        "source_published_at": episode.source_published_at,
        "source_checksum": episode.source_checksum,
        "processed_at": episode.processed_at,
        "created_at": episode.created_at,
    }
    return payload


def _record_conflicts(episode: Episode, conflicts: List[Dict[str, Any]]) -> None:
    if not conflicts:
        return
    meta = _load_meta(episode)
    bucket = meta.setdefault("merge_conflicts", [])
    timestamp = datetime.utcnow().isoformat() + "Z"
    for conflict in conflicts:
        conflict = dict(conflict)
        conflict.setdefault("episode_id", str(episode.id))
        conflict.setdefault("title", episode.title)
        conflict.setdefault("timestamp", timestamp)
        bucket.append(conflict)
    _save_meta(episode, meta)


def merge_into_episode(
    episode: Episode,
    incoming: Mapping[str, Any],
    *,
    source: str,
    overwrite_fields: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Merge incoming values into an existing episode, recording conflicts."""

    conflicts: List[Dict[str, Any]] = []
    applied_fields: List[str] = []
    meta_changed = False

    def _text(val: Any) -> str:
        if val is None:
            return ""
        return str(val).strip()

    def _apply_text(field: str) -> None:
        new_val = incoming.get(field)
        if new_val is None:
            return
        current_val = getattr(episode, field)
        # If caller prefers remote for this field, overwrite regardless
        if overwrite_fields and field in overwrite_fields:
            setattr(episode, field, new_val)
            applied_fields.append(field)
        elif not _text(current_val):
            setattr(episode, field, new_val)
            applied_fields.append(field)
        elif _text(current_val) != _text(new_val):
            conflicts.append({
                "field": field,
                "existing": _serialize(current_val),
                "incoming": _serialize(new_val),
                "source": source,
            })

    for field in ("show_notes", "final_audio_path", "cover_path", "remote_cover_url", "original_guid", "source_media_url", "source_checksum"):
        _apply_text(field)

    # Publish at timestamps
    incoming_publish_at = _coerce_datetime(incoming.get("publish_at"))
    if incoming_publish_at:
        existing_publish_at = _coerce_datetime(getattr(episode, "publish_at", None))
        if not existing_publish_at:
            episode.publish_at = incoming_publish_at
            applied_fields.append("publish_at")
        elif abs((existing_publish_at - incoming_publish_at).total_seconds()) > 1:
            conflicts.append({
                "field": "publish_at",
                "existing": _serialize(existing_publish_at),
                "incoming": _serialize(incoming_publish_at),
                "source": source,
            })

    incoming_publish_local = incoming.get("publish_at_local")
    if incoming_publish_local:
        if not getattr(episode, "publish_at_local", None):
            episode.publish_at_local = str(incoming_publish_local)
            applied_fields.append("publish_at_local")
        elif str(episode.publish_at_local) != str(incoming_publish_local):
            conflicts.append({
                "field": "publish_at_local",
                "existing": _serialize(episode.publish_at_local),
                "incoming": _serialize(incoming_publish_local),
                "source": source,
            })

    # Season/Episode numbers: NEVER auto-overwrite from Spreaker sync
    # Spreaker auto-assigns these based on show's total episode count,
    # which conflicts with user-set numbering. Only apply if explicitly requested.
    for field in ("season_number", "episode_number"):
        incoming_num = _coerce_int(incoming.get(field))
        if incoming_num is None:
            continue
        current_num = getattr(episode, field)
        
        # Only apply if field is in explicit overwrite list AND user wants remote values
        if overwrite_fields and field in overwrite_fields:
            if current_num is None or int(current_num) != incoming_num:
                setattr(episode, field, incoming_num)
                applied_fields.append(field)
        # Otherwise: only set if current is None (for truly new episodes)
        elif current_num is None:
            setattr(episode, field, incoming_num)
            applied_fields.append(field)
        # If numbers differ, log as conflict but DON'T overwrite
        elif int(current_num) != incoming_num:
            conflicts.append({
                "field": field,
                "existing": _serialize(current_num),
                "incoming": incoming_num,
                "source": source,
                "note": "Spreaker auto-assigns episode numbers; local value preserved",
            })

    incoming_guid = incoming.get("original_guid")
    if incoming_guid:
        if not getattr(episode, "original_guid", None):
            episode.original_guid = incoming_guid
            applied_fields.append("original_guid")
        elif str(episode.original_guid) != str(incoming_guid):
            conflicts.append({
                "field": "original_guid",
                "existing": _serialize(episode.original_guid),
                "incoming": incoming_guid,
                "source": source,
            })

    # Status handling (prefer higher priority)
    incoming_status = _coerce_status(incoming.get("status"))
    if incoming_status:
        current_status = _coerce_status(getattr(episode, "status", None))
        if not current_status or _STATUS_PRIORITY.get(incoming_status, 0) > _STATUS_PRIORITY.get(current_status, 0):
            episode.status = incoming_status
            applied_fields.append("status")

    # Spreaker linkage
    incoming_spreaker_id = incoming.get("spreaker_episode_id")
    if incoming_spreaker_id:
        incoming_spreaker_id = str(incoming_spreaker_id)
        if not getattr(episode, "spreaker_episode_id", None):
            episode.spreaker_episode_id = incoming_spreaker_id
            episode.is_published_to_spreaker = bool(incoming.get("is_published_to_spreaker", True))
            applied_fields.append("spreaker_episode_id")
        elif str(episode.spreaker_episode_id) != incoming_spreaker_id:
            conflicts.append({
                "field": "spreaker_episode_id",
                "existing": _serialize(episode.spreaker_episode_id),
                "incoming": incoming_spreaker_id,
                "source": source,
            })

    if bool(incoming.get("is_published_to_spreaker")) and not episode.is_published_to_spreaker:
        episode.is_published_to_spreaker = True
        applied_fields.append("is_published_to_spreaker")

    # Explicit flag – favour True (safer)
    if bool(incoming.get("is_explicit")) and not getattr(episode, "is_explicit", False):
        episode.is_explicit = True
        applied_fields.append("is_explicit")

    # Tags – union of sets
    incoming_tags = incoming.get("tags") or []
    if incoming_tags:
        if overwrite_fields and "tags" in overwrite_fields:
            # Replace with remote tags
            normalized = []
            for tag in incoming_tags:
                norm = str(tag).strip()
                if norm and norm not in normalized:
                    normalized.append(norm)
            try:
                episode.set_tags(normalized)
            except Exception:
                pass
            applied_fields.append("tags")
        else:
            try:
                existing_tags = set(episode.tags())
            except Exception:
                existing_tags = set()
            merged = list(existing_tags)
            changed = False
            for tag in incoming_tags:
                norm = str(tag).strip()
                if not norm:
                    continue
                if norm not in existing_tags:
                    existing_tags.add(norm)
                    merged.append(norm)
                    changed = True
            if changed:
                try:
                    episode.set_tags(merged)
                except Exception:
                    pass
                applied_fields.append("tags")

    # Meta merge (shallow)
    incoming_meta = incoming.get("meta")
    if isinstance(incoming_meta, Mapping) and incoming_meta:
        current_meta = _load_meta(episode)
        for key, value in incoming_meta.items():
            if key not in current_meta or current_meta[key] in (None, "", [], {}):
                current_meta[key] = value
                meta_changed = True
            elif current_meta[key] != value:
                conflicts.append({
                    "field": f"meta.{key}",
                    "existing": _serialize(current_meta[key]),
                    "incoming": _serialize(value),
                    "source": source,
                })
        if meta_changed:
            _save_meta(episode, current_meta)

    # Processed/created timestamps – take the earliest available
    for field in ("processed_at", "created_at"):
        incoming_dt = _coerce_datetime(incoming.get(field))
        if not incoming_dt:
            continue
        current_dt = _coerce_datetime(getattr(episode, field, None))
        if not current_dt or incoming_dt < current_dt:
            setattr(episode, field, incoming_dt)
            applied_fields.append(field)

    # Source published timestamp – prefer earliest known
    incoming_source_pub = _coerce_datetime(incoming.get("source_published_at"))
    if incoming_source_pub:
        current_source_pub = _coerce_datetime(getattr(episode, "source_published_at", None))
        if not current_source_pub or incoming_source_pub < current_source_pub:
            episode.source_published_at = incoming_source_pub
            applied_fields.append("source_published_at")
        elif abs((incoming_source_pub - current_source_pub).total_seconds()) > 1:
            conflicts.append({
                "field": "source_published_at",
                "existing": _serialize(current_source_pub),
                "incoming": _serialize(incoming_source_pub),
                "source": source,
            })

    _record_conflicts(episode, conflicts)

    return {
        "changed": bool(applied_fields or meta_changed),
        "conflicts": conflicts,
        "applied_fields": applied_fields,
    }


def _episode_priority_score(ep: Episode) -> Tuple[int, datetime]:
    score = 0
    if getattr(ep, "spreaker_episode_id", None):
        score += 8
    if getattr(ep, "final_audio_path", None):
        score += 4
    if getattr(ep, "show_notes", None):
        score += 2
    try:
        if ep.tags():
            score += 1
    except Exception:
        pass
    created = getattr(ep, "created_at", None) or datetime.utcnow()
    return (-score, created)


def merge_podcast_episode_duplicates(session: Session, podcast_id: Any) -> Dict[str, Any]:
    """Merge duplicate episodes (matching normalised title) within a podcast."""

    episodes = session.exec(
        select(Episode).where(Episode.podcast_id == podcast_id)
    ).all()
    groups: Dict[str, List[Episode]] = defaultdict(list)
    for ep in episodes:
        groups[normalize_title(ep.title)].append(ep)

    total_groups = 0
    merged_records = 0
    conflicts: List[Dict[str, Any]] = []

    for norm_title, members in groups.items():
        if not norm_title or len(members) <= 1:
            continue
        total_groups += 1
        members.sort(key=_episode_priority_score)
        primary = members[0]
        duplicates = members[1:]
        for dup in duplicates:
            result = merge_into_episode(primary, episode_to_payload(dup), source="duplicate")
            conflicts.extend(result["conflicts"])
            merged_records += 1
            session.delete(dup)
        session.add(primary)

    return {
        "merged_groups": total_groups,
        "merged_records": merged_records,
        "conflicts": conflicts,
        "changed": bool(total_groups),
    }

