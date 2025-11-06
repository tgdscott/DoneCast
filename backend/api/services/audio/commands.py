from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

from .common import AudioSegment, match_target_dbfs
import re
_NONWORD = re.compile(r'\W+')
def _norm_key(s: str) -> str:
    return _NONWORD.sub('', (s or '').lower())
def _collapse(seq: list) -> str:
    return _NONWORD.sub('', ''.join([str((w or {}).get('word') or '') for w in seq]).lower())
def _phrase_words(k: str):
    return re.findall(r'\w+', (k or '').lower())
from .ai_intern import execute_intern_commands
from .ai_flubber import handle_flubber
from .ai_sfx import detect_and_mark_sfx_phrases


def extract_ai_commands(
    mutable_words: List[Dict[str, Any]],
    commands_cfg: Dict[str, Any],
    log: List[str],
    *,
    insane_verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract AI commands (e.g., 'intern') and multi-word SFX phrases.
    Returns (ai_commands, sfx_events) while also mutating mutable_words to remove command tokens.
    Minimal version to keep existing behavior; complex flubber logic stays in cleanup module.
    """
    ai_commands: List[Dict[str, Any]] = []
    sfx_events: List[Dict[str, Any]] = []

    # Build a normalization map for direct command token lookups (ignore punctuation and case)
    commands_norm_map: Dict[str, str] = {}
    for k in (commands_cfg or {}).keys():
        try:
            commands_norm_map[_NONWORD.sub('', (k or '').lower())] = k
        except Exception:
            pass

    # Precompute SFX phrase variants (with aliases and normalized forms) and mark them upfront
    sfx_phrase_variants: List[Dict[str, Any]] = []
    for raw_key, cfg in (commands_cfg or {}).items():
        if (cfg or {}).get('action') != 'sfx':
            continue
        keys = {raw_key}
        for alias in (cfg or {}).get('aliases', []):
            keys.add(alias)
        for k in keys:
            ws = _phrase_words(k)
            if ws:
                sfx_phrase_variants.append({
                    'words': ws,
                    'file': (cfg or {}).get('file'),
                    'key': raw_key,
                    'strict_spacing': bool((cfg or {}).get('strict_spacing', False)),
                })
    if sfx_phrase_variants:
        try:
            _events = detect_and_mark_sfx_phrases(mutable_words, sfx_phrase_variants, log)
            if _events:
                sfx_events.extend(_events)
        except Exception:
            pass

    intern_cfg = (commands_cfg or {}).get('intern') or {}
    END_MARKERS = [m for m in (intern_cfg.get('end_markers') or [])]
    RM_END = bool(intern_cfg.get('remove_end_marker'))
    # Hard bounds to avoid pathological scans on huge transcripts
    MAX_END_SCAN_WORDS = int((intern_cfg.get('max_end_marker_scan_words') or 48))
    MAX_END_PHRASE_LEN = 4  # e.g., "stop", "stop intern", up to 4 tokens
    def _find_end_marker_window(start_idx: int) -> Tuple[int, int]:
        """Return (start_idx, end_idx_exclusive) for the first matching end marker window after start_idx.
        If none found within the bounded window, return (-1, -1).
        """
        if not END_MARKERS:
            return -1, -1
        try:
            # Normalize targets once
            targets = set(_NONWORD.sub('', m.lower()) for m in END_MARKERS)
        except Exception:
            targets = set()
        if not targets:
            return -1, -1

        end_idx_cap = min(len(mutable_words), start_idx + MAX_END_SCAN_WORDS)
        # Precompute normalized word tokens in the scan window for speed
        norm_tokens: List[str] = []
        for k in range(start_idx, end_idx_cap):
            try:
                t = _NONWORD.sub('', str((mutable_words[k] or {}).get('word') or '').lower())
            except Exception:
                t = ''
            norm_tokens.append(t)

        # Scan phrases up to MAX_END_PHRASE_LEN tokens
        for rel_i in range(0, len(norm_tokens)):
            for L in range(1, MAX_END_PHRASE_LEN + 1):
                rel_j = rel_i + L
                if rel_j > len(norm_tokens):
                    break
                if ''.join(norm_tokens[rel_i:rel_j]) in targets:
                    i2 = start_idx + rel_i
                    j2 = start_idx + rel_j
                    return i2, j2
        return -1, -1

    i = 0
    while i < len(mutable_words):
        w = mutable_words[i]
        raw_tok = str(w.get('word') or '').lower()
        # Normalize token: both trim-only (legacy) and full removal (robust)
        tok = re.sub(r'^[^\w]+|[^\w]+$', '', raw_tok)
        tok_full = _NONWORD.sub('', raw_tok)
        if insane_verbose:
            try:
                log.append(f"[TOK] i={i} raw='{raw_tok}' norm='{tok}' start={w.get('start', 0):.3f}s end={w.get('end', 0):.3f}s")
            except Exception:
                pass
        # Lightweight default placeholder for known SFX triggers when no explicit command is provided
        if tok in {"kaboom"} and tok not in (commands_cfg or {}):
            try:
                mutable_words[i]['word'] = f"{{{tok}}}"
            except Exception:
                pass
        # Skip words that have been consumed by a previously marked SFX phrase
        if w.get('_sfx_consumed') or w.get('_sfx_file'):
            i += 1
            continue

        # Resolve config via robust normalization first, then fallback to legacy exact token
        cfg_key = commands_norm_map.get(tok_full)
        if cfg_key is None and tok in (commands_cfg or {}):
            cfg_key = tok
        if cfg_key is not None:
            cfg = (commands_cfg or {}).get(cfg_key) or {}
            if cfg.get('action') == 'ai_command' or cfg.get('action') == 'intern':
                command_start_time = w['start']
                forward_words: List[str] = []
                last_context_end = w['end']
                # Allow gap-based termination of the prompt context (default 2.5s)
                gap_terminate_s = float(cfg.get('gap_terminate_s', 2.5))
                end_s, end_e = _find_end_marker_window(i + 1)
                # If not found ahead, also allow an end-marker that includes the current token (e.g., "stop intern")
                if end_s == -1 and END_MARKERS:
                    try:
                        bs_min = max(0, i - 3)
                        for bs in range(i, bs_min - 1, -1):
                            j2 = i + 1
                            if any(_NONWORD.sub('', m.lower()) == _collapse(mutable_words[bs:j2]) for m in END_MARKERS):
                                end_s, end_e = bs, j2
                                break
                    except Exception:
                        pass
                max_idx = end_s if end_s != -1 else (i + 80)
                for fw_idx, fw in enumerate(mutable_words[i+1:max_idx], start=i+1):
                    if fw.get('word'):
                        # ✅ NEW: Stop at end_marker position (don't include words after user's mark)
                        if end_s != -1 and fw_idx >= end_s:
                            break
                        
                        # Stop if total window is too large (hard cap)
                        if fw['start'] - command_start_time > 15.0:
                            break
                        # Respect punctuation when looking ahead for a new command; normalize similarly
                        next_tok_raw = str(fw.get('word') or '').lower()
                        next_tok_norm = re.sub(r'^[^\w]+|[^\w]+$', '', next_tok_raw)
                        next_tok_full = _NONWORD.sub('', next_tok_raw)
                        if next_tok_full in commands_norm_map or next_tok_norm in commands_cfg:
                            break
                        # Stop if a sufficiently long pause occurs between words
                        try:
                            prev_end = last_context_end
                            if prev_end is not None and (fw['start'] - float(prev_end)) >= gap_terminate_s:
                                break
                        except Exception:
                            pass
                        forward_words.append(fw['word'])
                        last_context_end = fw.get('end', last_context_end)
                    if len(forward_words) >= 40:
                        break
                # Keep the command token visible in transcript by default; allow opt-out via config
                keep_cmd = bool(cfg.get('keep_command_token_in_transcript', True))
                try:
                    if isinstance(mutable_words[i].get('word'), str) and not keep_cmd:
                        mutable_words[i]['word'] = ''
                    # else: leave as-is so "intern" stays visible in transcript
                except Exception:
                    pass
                # Compute end-marker timing in seconds for precise audio replacement
                end_marker_start_s = None
                end_marker_end_s = None
                try:
                    if end_s != -1:
                        ws = mutable_words[end_s]
                        end_marker_start_s = float(ws.get('start', None) or ws.get('start_time', None) or ws.get('startTime', 0.0))
                        we = mutable_words[max(end_s, end_e - 1)]
                        end_marker_end_s = float(we.get('end', None) or we.get('end_time', None) or we.get('endTime', 0.0))
                except Exception:
                    end_marker_start_s = None
                    end_marker_end_s = None

                ai_commands.append({
                    'time': command_start_time,
                    'command_token': tok,
                    'mode': cfg.get('mode', 'generic'),
                    # Keep spoken command by default; allow opt-in muting via config
                    'remove_spoken_prompt': bool(cfg.get('remove_spoken_prompt', False)),
                    # Optional: completely disable TTS generation for this command
                    'disable_tts': bool(cfg.get('disable_tts', False)),
                    # Optional: ms of pad after context_end before inserting TTS
                    'insert_pad_ms': int(cfg.get('insert_pad_ms', 200)),
                    'local_context': ' '.join(forward_words),
                    'context_end': (end_marker_end_s if (end_marker_end_s is not None) else last_context_end),
                    'end_marker_start': end_marker_start_s,
                    'end_marker_end': end_marker_end_s,
                    'prompt': ' '.join(forward_words),
                })
                log.append(f"[AI_CMD_DETECT] token='{tok}' mode='{cfg.get('mode','generic')}' at={command_start_time:.3f}s ctx_words={len(forward_words)} ctx='{(' '.join(forward_words))[:120]}'")
                mutable_words[i]['_ai_cmd'] = True
                if end_s != -1 and RM_END:
                    for ww in mutable_words[end_s:end_e]:
                        if isinstance(ww, dict):
                            try:
                                ww['word'] = ''
                            except Exception:
                                pass
                i += 1
                continue
            elif cfg.get('action') == 'sfx':
                file_name = cfg.get('file')
                mutable_words[i]['_sfx_file'] = file_name
                # display {trigger} placeholder
                try:
                    # Use the original spoken token for placeholder readability
                    mutable_words[i]['word'] = f"{{{tok or tok_full}}}"
                except Exception:
                    mutable_words[i]['word'] = ''
                sfx_events.append({'time': mutable_words[i]['start'], 'file': file_name})
                log.append(f"[SFX] token='{tok}' file='{file_name}' at={mutable_words[i]['start']:.3f}s")
                i += 1
                continue

        # If we saw a likely command token but commands are disabled, surface that for diagnostics
        if insane_verbose and tok in {"intern", "flubber"} and tok not in (commands_cfg or {}):
            try:
                log.append(f"[AI_CMD_SEEN_BUT_DISABLED] token='{tok}' at={w.get('start', 0):.3f}s")
            except Exception:
                pass
        
        # advance to next word when no command branch consumed this token
        i += 1

    return ai_commands, sfx_events


## flubber handler moved to ai_flubber.py




__all__ = [
    "extract_ai_commands",
    "handle_flubber",
    "execute_intern_commands",
]
