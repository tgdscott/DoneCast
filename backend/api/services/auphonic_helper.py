from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from api.core.config import settings

log = logging.getLogger("auphonic.helper")


def _map_decision_to_use_auphonic(decision: str) -> bool:
    """Map a decision label to a boolean indicating whether to use Auphonic.

    - 'advanced' => True (use Auphonic)
    - 'standard' => False (use AssemblyAI + local processing)
    - 'ask' => False (do not auto-use Auphonic; surface choice to operator)
    """
    d = (decision or "").strip().lower()
    if d == "advanced":
        return True
    return False


def decide_audio_processing(
    *,
    audio_quality_label: Optional[str] = None,
    current_user_tier: Optional[str] = None,
    media_item_override_use_auphonic: Optional[bool] = None,
) -> Dict[str, Any]:
    """Decide whether to use Auphonic for a media item.

    Priority (highest -> lowest):
    1. `media_item_override_use_auphonic` if explicitly True/False
    2. Pro-tier users always use Auphonic (production rule)
    3. Decision matrix mapping from `audio_quality_label` -> decision
    4. Default: do not use Auphonic

    Returns a dict with keys:
    - `use_auphonic`: bool
    - `decision`: one of 'standard', 'advanced', 'ask'
    - `reason`: human-readable reason for the decision
    """
    # 1) explicit override
    if media_item_override_use_auphonic is not None:
        return {
            "use_auphonic": bool(media_item_override_use_auphonic),
            "decision": "advanced" if media_item_override_use_auphonic else "standard",
            "reason": "explicit_media_override",
        }

    # 2) Pro-tier => always Auphonic
    try:
        tier = (current_user_tier or "").strip().lower()
        if tier == "pro":
            return {"use_auphonic": True, "decision": "advanced", "reason": "pro_tier"}
    except Exception:
        pass

    # 3) Use decision matrix
    matrix = settings.get_audio_processing_matrix() if hasattr(settings, "get_audio_processing_matrix") else {}
    # normalize label
    label = (audio_quality_label or "").strip()
    if label and label in matrix:
        decision = (matrix.get(label) or "standard").strip().lower()
        use_auphonic = _map_decision_to_use_auphonic(decision)
        return {"use_auphonic": use_auphonic, "decision": decision, "reason": f"matrix:{label}"}

    # 4) Default conservative behavior
    return {"use_auphonic": False, "decision": "standard", "reason": "default_fallback"}


def should_use_auphonic_for_media(
    *,
    audio_quality_label: Optional[str] = None,
    current_user_tier: Optional[str] = None,
    media_item_override_use_auphonic: Optional[bool] = None,
) -> bool:
    """Convenience wrapper that returns boolean decision only."""
    result = decide_audio_processing(
        audio_quality_label=audio_quality_label,
        current_user_tier=current_user_tier,
        media_item_override_use_auphonic=media_item_override_use_auphonic,
    )
    log.info("[auphonic.helper] decision=%s reason=%s label=%s tier=%s",
             result.get("decision"), result.get("reason"), audio_quality_label, current_user_tier)
    return bool(result.get("use_auphonic", False))
