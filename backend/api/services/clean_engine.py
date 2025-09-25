"""Compatibility façade for the Clean Engine.

This module used to contain the monolithic implementation. It now re-exports
the canonical API from the package `api.services.clean_engine` (engine/models),
so external imports remain stable.
"""

from __future__ import annotations

from api.services.clean_engine.engine import run_all  # noqa: F401
from api.services.clean_engine.models import Word, UserSettings, SilenceSettings, InternSettings, CensorSettings  # noqa: F401
from api.services.clean_engine.features import apply_censor_beep  # kept exported previously; maintain surface

__all__ = [
    "run_all",
    "Word",
    "UserSettings",
    "SilenceSettings",
    "InternSettings",
    "CensorSettings",
    "apply_censor_beep",
]



