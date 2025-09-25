from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .common import AudioSegment, MEDIA_DIR, match_target_dbfs

# We intentionally delegate to existing logic to preserve behavior and logs.
from .commands import extract_ai_commands  # emits [AI_CMD_DETECT] and [SFX]
from .ai_sfx import detect_and_mark_sfx_phrases  # emits [SFX_PHRASE]


def build_intern_prompt(
    mutable_words: List[Dict[str, Any]],
    commands_cfg: Dict[str, Any],
    log: List[str],
    *,
    insane_verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Build Intern command prompts from words using existing extractor.

    Returns the list of ai_commands (only 'intern' entries). Side-effects and
    logging match current behavior by delegating to extract_ai_commands.

    Note: This will also detect SFX markers as today. If you want SFX-only,
    prefer select_sfx_markers below.
    """
    # Work on a shallow copy to avoid unintended mutation if caller reuses words
    tmp_words = [dict(w) for w in (mutable_words or [])]
    ai_cmds, _sfx = extract_ai_commands(tmp_words, commands_cfg or {}, log, insane_verbose=insane_verbose)
    # Keep only intern commands for clarity
    return [c for c in (ai_cmds or []) if (c or {}).get("command_token") == "intern"]


def select_sfx_markers(
    mutable_words: List[Dict[str, Any]],
    commands_cfg: Dict[str, Any],
    log: List[str],
) -> List[Dict[str, Any]]:
    """Detect SFX markers using the same heuristics as today.

    Builds phrase variants from commands_cfg and delegates to ai_sfx to mark
    words and emit the same [SFX_PHRASE] logs. Also handles single-token sfx
    mappings via extract_ai_commands when present.
    """
    # Prefer phrase detection first (multi-word). Build variants like commands.extract_ai_commands
    phrase_variants: List[Dict[str, Any]] = []
    for raw_key, cfg in (commands_cfg or {}).items():
        if (cfg or {}).get("action") != "sfx":
            continue
        keys = {raw_key}
        for alias in (cfg or {}).get("aliases", []) or []:
            keys.add(alias)
        import re as _re
        for k in keys:
            ws = _re.findall(r"\w+", (k or "").lower())
            if not ws:
                continue
            phrase_variants.append({
                "words": ws,
                "file": (cfg or {}).get("file"),
                "key": raw_key,
                "strict_spacing": bool((cfg or {}).get("strict_spacing", False)),
            })

    events: List[Dict[str, Any]] = []
    if phrase_variants:
        try:
            events.extend(detect_and_mark_sfx_phrases(mutable_words, phrase_variants, log) or [])
        except Exception:
            pass

    # Single-token sfx (non-phrase) and placeholders are handled by extract_ai_commands
    # to preserve existing [SFX] logs and placeholder insertion. Run it on a throwaway
    # copy so as not to double-mutate.
    tmp_words = [dict(w) for w in (mutable_words or [])]
    try:
        _ai_cmds, sfx_events = extract_ai_commands(tmp_words, commands_cfg or {}, log, insane_verbose=False)
        for ev in (sfx_events or []):
            events.append(ev)
    except Exception:
        pass

    # Preserve legacy behavior: lightweight placeholder for known single-token triggers
    # even when no explicit SFX config is provided (e.g., 'kaboom').
    try:
        known_defaults = {"kaboom"}
        cfg_keys = set((commands_cfg or {}).keys())
        for i, w in enumerate(mutable_words or []):
            try:
                tok = str((w or {}).get("word") or "").strip().lower()
                norm = __import__("re").sub(r"^[^\w]+|[^\w]+$", "", tok)
                if norm in known_defaults and norm not in cfg_keys:
                    # Insert placeholder directly on the real words list, matching previous behavior
                    if isinstance(w.get("word"), str):
                        w["word"] = f"{{{norm}}}"
            except Exception:
                continue
    except Exception:
        pass
    return events


def annotate_words_with_sfx(
    mutable_words: List[Dict[str, Any]],
    markers: List[Dict[str, Any]],
    log: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Annotate transcript words with SFX placeholders where appropriate.

    Current system already annotates during detection. This function is a
    conservative no-op that ensures the first word at/after each marker time
    bears a visible placeholder if none exists.
    """
    if not mutable_words or not markers:
        return mutable_words

    try:
        for m in (markers or []):
            try:
                mt = float(m.get("time", 0.0))
            except Exception:
                mt = 0.0
            # Find the first word whose start >= marker time
            idx = None
            for i, w in enumerate(mutable_words):
                try:
                    if float((w or {}).get("start") or 0.0) >= mt:
                        idx = i
                        break
                except Exception:
                    continue
            if idx is None:
                continue
            w = mutable_words[idx]
            # If no explicit placeholder, add one, preferring phrase/trigger key over filename (matches legacy)
            txt = str((w or {}).get("word") or "")
            if "{" not in txt and "}" not in txt:
                try:
                    label = None
                    # Prefer human-friendly phrase/trigger name when available
                    if isinstance(m, dict):
                        label = m.get("phrase") or m.get("trigger")
                        if not label:
                            # Fallback to filename without extension
                            fname = m.get("file")
                            if isinstance(fname, str) and fname:
                                from pathlib import Path as _P
                                label = _P(fname).stem
                    if not label:
                        label = "sfx"
                    w["word"] = f"{{{label}}}"
                    if log is not None:
                        log.append(f"[SFX_ANNOTATE] idx={idx} label='{label}' at={mt:.3f}s")
                except Exception:
                    pass
    except Exception:
        pass
    return mutable_words


def apply_sfx(
    base_audio: AudioSegment,
    markers: List[Dict[str, Any]],
    *,
    gain_db: Optional[float] = None,
    log: Optional[List[str]] = None,
) -> AudioSegment:
    """Overlay SFX audio at marker times.

    Behavior: best-effort overlay using MEDIA_DIR/<file>. If a file is missing
    or cannot be loaded, skip it. Loudness is normalized and optional gain
    applied. Emits logs with prefix '[SFX_APPLY]'.
    """
    out = base_audio
    if not markers:
        return out

    for m in (markers or []):
        path = None
        try:
            name = (m or {}).get("file")
            if not name:
                continue
            path = (MEDIA_DIR / str(name))
            if not path.exists():
                # silence if missing
                if log is not None:
                    log.append(f"[SFX_APPLY_SKIP] missing_file='{name}'")
                continue
            clip = AudioSegment.from_file(path)
            # Normalize and apply optional gain
            clip = match_target_dbfs(clip)
            if gain_db is not None:
                try:
                    clip = clip.apply_gain(float(gain_db))
                except Exception:
                    pass
            pos_ms = int(max(0.0, float((m or {}).get("time") or 0.0)) * 1000)
            if pos_ms > len(out):
                pos_ms = len(out)
            out = out.overlay(clip, position=pos_ms)
            if log is not None:
                try:
                    log.append(f"[SFX_APPLY] file='{path.name}' at_ms={pos_ms} dur_ms={len(clip)}")
                except Exception:
                    pass
        except Exception as e:
            if log is not None:
                try:
                    log.append(f"[SFX_APPLY_ERROR] file='{getattr(path,'name',None) or m.get('file')}' err={type(e).__name__}: {e}")
                except Exception:
                    pass
            continue
    return out


__all__ = [
    "build_intern_prompt",
    "select_sfx_markers",
    "annotate_words_with_sfx",
    "apply_sfx",
]
