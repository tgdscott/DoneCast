from __future__ import annotations

from typing import Any, Dict, List, NotRequired, TypedDict


class UploadResp(TypedDict, total=False):
    upload_url: str


class StartResp(TypedDict, total=False):
    id: str
    status: str


class TranscriptResp(TypedDict, total=False):
    id: NotRequired[str]
    status: str
    text: NotRequired[str]
    words: NotRequired[List[Dict[str, Any]]]
    filter_profanity: NotRequired[bool]
    punctuate: NotRequired[bool]
    format_text: NotRequired[bool]
    disfluencies: NotRequired[bool]
    speech_model: NotRequired[str]
    utterances: NotRequired[List[Dict[str, Any]]]


class PollingCfg(TypedDict, total=False):
    interval_s: float
    timeout_s: float
    backoff: float


class RunnerCfg(TypedDict, total=False):
    api_key: str
    base_url: str
    polling: PollingCfg
    params: Dict[str, Any]


class NormalizedResult(TypedDict):
    words: List[Dict[str, Any]]


__all__ = [
    "UploadResp",
    "StartResp",
    "TranscriptResp",
    "PollingCfg",
    "RunnerCfg",
    "NormalizedResult",
]
