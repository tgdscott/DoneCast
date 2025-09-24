"""Utilities for detecting command keywords inside transcript word lists.

The front-end wizard uses this information to decide whether it needs to ask
the creator about flubber, intern, or sound-effect cues.  The helpers here
mirror the normalization already performed inside the audio pipeline (see
`api.services.audio.commands`) but run in a lightweight, read-only fashion so
we can respond quickly once a transcript JSON file is available.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


_WORD_RE = re.compile(r"\w+")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def _normalize_token(token: str) -> str:
    """Return a lowercase alphanumeric token stripped of punctuation."""

    if not token:
        return ""
    return _NON_ALNUM.sub("", token.lower())


def _tokenize_phrase(phrase: str) -> List[str]:
    """Split a phrase into normalized word tokens.

    Empty phrases yield an empty list which callers should ignore.
    """

    if not isinstance(phrase, str):
        return []
    return [t for t in (_WORD_RE.findall(phrase.lower())) if t]


def _split_variants(raw: Any) -> Iterable[str]:
    """Yield cleaned variants from trigger keyword inputs.

    Settings may specify comma or pipe separated alternatives, or supply a list
    directly.  This helper flattens those cases and yields trimmed strings.
    """

    if not raw:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[|,]", raw)
        return [p.strip() for p in parts if p and p.strip()]
    if isinstance(raw, (list, tuple, set)):
        out: List[str] = []
        for item in raw:
            if not item:
                continue
            if isinstance(item, str):
                out.extend([p.strip() for p in re.split(r"[|,]", item) if p and p.strip()])
            else:
                out.append(str(item).strip())
        return [p for p in out if p]
    return [str(raw).strip()]


@dataclass(frozen=True)
class SFXVariant:
    tokens: Tuple[str, ...]
    label: str
    source: str


def _gather_command_variants(
    commands_cfg: Optional[Dict[str, Any]],
) -> Tuple[List[List[str]], List[List[str]], List[SFXVariant]]:
    """Return (flubber_tokens, intern_tokens, sfx_variants)."""

    flubber_variants: List[List[str]] = []
    intern_variants: List[List[str]] = []
    sfx_variants: List[SFXVariant] = []

    commands_cfg = commands_cfg or {}

    def _ensure_default(name: str, default: str) -> None:
        if name not in commands_cfg:
            commands_cfg[name] = {"trigger_keyword": default}

    _ensure_default("flubber", "flubber")
    _ensure_default("intern", "intern")

    for name, cfg in commands_cfg.items():
        cfg = cfg or {}
        variants = set()
        variants.update(_split_variants(cfg.get("trigger_keyword")))
        variants.update(_split_variants(cfg.get("trigger_keywords")))
        variants.update(_split_variants(cfg.get("keywords")))
        variants.update(_split_variants(cfg.get("phrases")))
        variants.update(_split_variants(cfg.get("alias")))
        variants.update(_split_variants(cfg.get("aliases")))

        tokenized = [tuple(_tokenize_phrase(v)) for v in variants if _tokenize_phrase(v)]

        if name == "flubber":
            if not tokenized:
                tokenized = [tuple(_tokenize_phrase("flubber"))]
            flubber_variants.extend([list(t) for t in tokenized if t])
            continue
        if name == "intern":
            if not tokenized:
                tokenized = [tuple(_tokenize_phrase("intern"))]
            intern_variants.extend([list(t) for t in tokenized if t])
            continue

        if str(cfg.get("action") or "").lower() == "sfx":
            if not tokenized:
                continue
            label = str(cfg.get("label") or name or "sfx").strip() or "sfx"
            for tokens in tokenized:
                if not tokens:
                    continue
                sfx_variants.append(
                    SFXVariant(tokens=tuple(tokens), label=label, source=f"command:{name}")
                )

    return flubber_variants, intern_variants, sfx_variants


def _count_phrase(tokens: Sequence[str], phrase: Sequence[str]) -> int:
    """Return how many times *phrase* appears in order within *tokens*."""

    if not phrase or not tokens or len(phrase) > len(tokens):
        return 0
    count = 0
    phrase_len = len(phrase)
    i = 0
    while i <= len(tokens) - phrase_len:
        if tokens[i : i + phrase_len] == list(phrase):
            count += 1
            i += phrase_len
        else:
            i += 1
    return count


def analyze_intents(
    words: Iterable[Dict[str, Any]],
    commands_cfg: Optional[Dict[str, Any]] = None,
    extra_sfx_entries: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Inspect transcript words and count command keywords.

    Args:
        words: Sequence of transcript word dictionaries (AssemblyAI/Google
            compatible).
        commands_cfg: Audio cleanup command configuration for the user.
        extra_sfx_entries: Optional iterable describing additional word cues
            that should count as sound effects.  Each entry may provide
            ``phrase``/``keyword`` and a human-friendly ``label``.

    Returns a dictionary with three keys (``flubber``, ``intern``, ``sfx``),
    each containing count metadata and any detected labels.
    """

    transcript_tokens: List[str] = []
    for w in words or []:
        token = _normalize_token(str((w or {}).get("word") or ""))
        if token:
            transcript_tokens.append(token)

    flubber_variants, intern_variants, sfx_variants = _gather_command_variants(commands_cfg)

    if extra_sfx_entries:
        for entry in extra_sfx_entries:
            if not isinstance(entry, dict):
                continue
            phrase = (
                entry.get("phrase")
                or entry.get("keyword")
                or entry.get("trigger")
                or entry.get("trigger_keyword")
            )
            tokens = _tokenize_phrase(str(phrase or ""))
            if not tokens:
                continue
            label = str(entry.get("label") or entry.get("name") or "sfx").strip() or "sfx"
            source = str(entry.get("source") or "media").strip() or "media"
            sfx_variants.append(SFXVariant(tokens=tuple(tokens), label=label, source=source))

    def _aggregate(phrases: Sequence[Sequence[str]]) -> Tuple[int, List[Dict[str, Any]]]:
        total = 0
        details: List[Dict[str, Any]] = []
        for phrase in phrases:
            phrase = [t for t in phrase if t]
            if not phrase:
                continue
            c = _count_phrase(transcript_tokens, phrase)
            if c:
                total += c
                details.append({"phrase": " ".join(phrase), "count": c})
        return total, details

    flubber_count, flubber_matches = _aggregate(flubber_variants)
    intern_count, intern_matches = _aggregate(intern_variants)

    sfx_total = 0
    sfx_matches: List[Dict[str, Any]] = []
    for variant in sfx_variants:
        count = _count_phrase(transcript_tokens, variant.tokens)
        if not count:
            continue
        sfx_total += count
        sfx_matches.append(
            {
                "phrase": " ".join(variant.tokens),
                "count": count,
                "label": variant.label,
                "source": variant.source,
            }
        )

    return {
        "flubber": {"count": flubber_count, "matches": flubber_matches},
        "intern": {"count": intern_count, "matches": intern_matches},
        "sfx": {"count": sfx_total, "matches": sfx_matches},
    }


def get_user_commands(user: Any) -> Dict[str, Any]:
    """Return the merged audio-cleanup command configuration for *user*.

    Falls back to defaults when the user has not saved custom settings.
    """

    defaults = {
        "flubber": {"trigger_keyword": "flubber"},
        "intern": {"trigger_keyword": "intern"},
    }
    raw = getattr(user, "audio_cleanup_settings_json", None)
    if not raw:
        return dict(defaults)
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        parsed = {}
    commands = parsed.get("commands") if isinstance(parsed, dict) else {}
    merged: Dict[str, Any] = dict(defaults)
    if isinstance(commands, dict):
        for name, cfg in commands.items():
            if not isinstance(cfg, dict):
                continue
            base = dict(merged.get(name, {}))
            base.update(cfg)
            merged[name] = base
    return merged

