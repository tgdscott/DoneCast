from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import AudioSegment, match_target_dbfs
from difflib import SequenceMatcher


def execute_intern_commands(
    cmds: List[Dict[str, Any]],
    cleaned_audio: AudioSegment,
    main_content_audio: AudioSegment,
    tts_provider: str,
    elevenlabs_api_key: Optional[str],
    ai_enhancer,
    log: List[str],
    *,
    insane_verbose: bool = False,
    mutable_words: Optional[List[Dict[str, Any]]] = None,
    fast_mode: bool = False,
) -> AudioSegment:
    """Execute Intern commands (audio or shownotes), preserving spoken prompt.
    This code was extracted from commands.py to isolate Intern behavior.
    """
    out = cleaned_audio
    import re as _re

    def _norm(s: str) -> str:
        return _re.sub(r"\W+", "", (s or "").lower())

    def _build_flexible_tail_regex(prompt: str):
        words = _re.findall(r"\w+", (prompt or "").lower())
        if not words:
            return None
        core = r"(?:\W+|_)+".join(_re.escape(w) for w in words)
        pat = rf"(?:\W+|_)*{core}(?:\W+|_)*\Z"
        try:
            return _re.compile(pat, flags=_re.DOTALL)
        except Exception:
            return None

    def _strip_prompt_prefix_suffix(answer: str, prompts: List[str], log_list: list):
        a = (answer or "")
        if not prompts:
            return a

        def _strip_prefix(a_in: str, p_in: str) -> str:
            if not p_in or not _norm(a_in).startswith(_norm(p_in)):
                return a_in
            words = _re.findall(r"\w+", (p_in or "").lower())
            if not words:
                return a_in
            core = r"(?:\W+|_)+".join(_re.escape(w) for w in words[1:])
            pref = rf"^\s*(?:\W+|_)*{_re.escape(words[0])}" + (rf"(?:{core})" if core else "")
            m = _re.search(pref, a_in, flags=_re.IGNORECASE | _re.DOTALL)
            if m:
                a2 = a_in[m.end() :].lstrip(" .,:;\n\t—–-")
                if a2:
                    try:
                        log_list.append("[INTERN_ANSWER_ECHO_STRIPPED] removed_prompt_prefix(flex)")
                    except Exception:
                        pass
                    return a2
            return a_in

        for p in prompts:
            a2 = _strip_prefix(a, p)
            if a2 != a:
                a = a2
                break

        def _strip_suffix(a_in: str, p_in: str) -> str:
            if not p_in or not _norm(a_in).endswith(_norm(p_in)):
                return a_in
            tail_re = _build_flexible_tail_regex(p_in)
            m = tail_re.search(a_in.lower()) if tail_re else None
            if m:
                a2 = a_in[: m.start()].rstrip(" .,:;\n\t—–-")
                if a2:
                    try:
                        log_list.append("[INTERN_ANSWER_ECHO_STRIPPED] removed_prompt_suffix(flex)")
                    except Exception:
                        pass
                    return a2
            n = len(_norm(p_in))
            if n >= 6:
                i, j = len(a_in) - 1, n
                while i >= 0 and j > 0:
                    if a_in[i].isalnum():
                        j -= 1
                    i -= 1
                a2 = a_in[: max(0, i + 1)].rstrip(" .,:;\n\t—–-")
                if a2:
                    try:
                        log_list.append("[INTERN_ANSWER_ECHO_STRIPPED] removed_prompt_suffix(fallback)")
                    except Exception:
                        pass
                    return a2
            return a_in

        for p in prompts:
            a2 = _strip_suffix(a, p)
            if a2 != a:
                return a2
        return a

    def _dedupe_tail(answer: str, log_list: list) -> str:
        """Remove duplicated trailing sentence/phrase like '... summary. summary.' or repeated n-grams.
        Conservative: only trim when high-confidence duplicate is found.
        """
        if not answer:
            return answer
        text = answer.strip()
        # Sentence-based check
        parts = _re.split(r"(?<=[\.!?…])\s+", text)
        if len(parts) >= 2:
            last = parts[-1].strip()
            prev = parts[-2].strip()
            if last and prev and _norm(last) == _norm(prev):
                try:
                    log_list.append("[INTERN_TAIL_DEDUP] removed duplicate last sentence")
                except Exception:
                    pass
                return " ".join(parts[:-1]).strip()
        # N-gram tail check (8-20 words) with flexible removal preserving spacing
        words = _re.findall(r"\w+", text)
        n = len(words)
        for k in (18, 16, 14, 12, 10, 8):
            if n >= 2 * k:
                tail1 = words[-k:]
                tail2 = words[-2 * k : -k]
                if _norm(" ".join(tail1)) == _norm(" ".join(tail2)):
                    # Build a flexible regex for the last k-word sequence and drop one occurrence at the end
                    core = r"(?:\W+|_)+".join(_re.escape(w) for w in tail1)
                    pat = _re.compile(rf"(.*?)(?:\W+|_)*{core}(?:\W+|_)*\Z", flags=_re.DOTALL | _re.IGNORECASE)
                    m = pat.match(text)
                    if m:
                        try:
                            log_list.append(f"[INTERN_TAIL_DEDUP] removed repeated tail k={k}")
                        except Exception:
                            pass
                        return m.group(1).rstrip(" .,:;\n\t—–-")
        return text

    def _strip_promptish_tail(answer: str, prompts: List[str], log_list: list) -> str:
        """Fuzzy-strip a trailing phrase that closely matches the prompt, allowing minor spelling/punctuation differences.
        Triggers only if the best-match window is near the end and similarity is high.
        """
        if not answer or not prompts:
            return answer
        a_text = answer
        a_low = a_text.lower()
        a_norm = _norm(a_text)
        best_cut = None
        for p in prompts:
            p_norm = _norm(p)
            if not p_norm or len(p_norm) < 6:
                continue
            # examine the last ~220 chars to keep it fast and target end echo
            tail_start = max(0, len(a_low) - 220)
            tail = a_low[tail_start:]
            # window sizes around prompt length (+/- 40%)
            L = len(p_norm)
            win_lengths = sorted(set([max(4, int(L * r)) for r in (0.6, 0.8, 1.0, 1.2, 1.4)]))
            for wlen in win_lengths:
                if wlen > len(tail):
                    continue
                # slide window within tail
                for i in range(0, len(tail) - wlen + 1, 2):
                    window = tail[i : i + wlen]
                    sim = SequenceMatcher(None, _norm(window), p_norm).ratio()
                    if sim >= 0.86:
                        # Global start index of this window
                        global_i = tail_start + i
                        # Consider only if it's within the last ~140 chars
                        if global_i >= len(a_low) - 140:
                            best_cut = min(best_cut, global_i) if best_cut is not None else global_i
        if best_cut is not None:
            try:
                log_list.append("[INTERN_TAIL_FUZZY_STRIP] removed prompt-like tail")
            except Exception:
                pass
            # Trim back to best_cut (on original text) and strip trailing punctuation
            return a_text[:best_cut].rstrip(" .,:;\n\t—–-")
        return answer

    for cmd in cmds:
        if cmd.get("command_token") != "intern":
            continue
        prompt_text = (cmd.get("local_context") or "").strip()
        if not prompt_text:
            cmd["skipped"] = "empty_prompt"
            log.append("[INTERN_SKIP] empty prompt_text; no action taken")
            continue
        log.append(f"[INTERN_PROMPT] '{prompt_text[:200]}'")
        
        # If user has explicitly set mode (from override review), respect it - don't let LLM override
        explicit_mode = cmd.get("mode")
        if explicit_mode:
            action = "add_to_shownotes" if explicit_mode == "shownote" else "generate_audio"
            log.append(f"[INTERN_EXPLICIT_MODE] mode={explicit_mode} -> action={action}")
        else:
            # No explicit mode - let LLM interpret the command
            try:
                if fast_mode:
                    interpreted = {"action": "generate_audio"}
                    try:
                        log.append("[INTERN_FAST_MODE] enabled; skipping LLM interpret")
                    except Exception:
                        pass
                else:
                    interpreted = ai_enhancer.interpret_intern_command(prompt_text) if prompt_text else {"action": "generate_audio"}
            except Exception as e:
                interpreted = {"action": "generate_audio"}
                log.append(f"[INTERN_INTERPRET_FALLBACK] {e}")
            default_action = "add_to_shownotes" if (cmd.get("mode") == "shownote") else "generate_audio"
            action = (interpreted or {}).get("action") or default_action
        # Get the clean topic from the interpretation, but fall back to the
        # original prompt if the interpretation failed for some reason.
        query_text = (interpreted or {}).get("topic") or prompt_text
        try:
            cmd["interpreted_topic"] = (interpreted or {}).get("topic")
        except Exception:
            pass
        log.append(f"[INTERN_QUERY] action='{action}' topic='{query_text[:200]}'")
        if action == "add_to_shownotes":
            try:
                note = ai_enhancer.get_answer_for_topic(
                    query_text,
                    context=(cmd.get("local_context") or ""),
                    mode="shownote",
                )
                if note:
                    cmd["note"] = note.strip()
                    log.append(f"[INTERN_NOTE] added len={len(cmd['note'])}")
            except Exception as e:
                cmd["shownote_error"] = str(e)
                log.append(f"[INTERN_NOTE_ERROR] {e}")
        else:
            try:
                # Check if user provided an override answer first
                override_answer = (cmd.get("override_answer") or "").strip()
                if override_answer:
                    answer = override_answer
                    log.append(f"[INTERN_OVERRIDE_ANSWER] using user-edited text len={len(answer)}")
                elif fast_mode:
                    answer = "The intern is out to lunch."
                    try:
                        log.append("[INTERN_FAST_MODE] using placeholder answer")
                    except Exception:
                        pass
                else:
                    answer = ai_enhancer.get_answer_for_topic(
                        query_text,
                        context=(cmd.get("local_context") or ""),
                        mode="audio",
                    )
                try:
                    spoken_prompt = (cmd.get("local_context") or "").strip()
                    prompts = [spoken_prompt, (query_text or "").strip()]
                    seen = set()
                    prompts = [p for p in prompts if p and not (p in seen or seen.add(p))]
                    answer = _strip_prompt_prefix_suffix(answer, prompts, log)
                    # Also remove duplicated or prompt-like tail phrases to avoid end-echo in TTS
                    answer = _dedupe_tail(answer, log)
                    answer = _strip_promptish_tail(answer, prompts, log)
                except Exception:
                    pass
                try:
                    if mutable_words is not None and (answer or "").strip():
                        ctx_end = float(cmd.get("context_end", cmd.get("time", 0)) or 0.0)
                        insert_idx = len(mutable_words)
                        for _idx, _w in enumerate(mutable_words):
                            try:
                                if float((_w or {}).get("start", 1e12)) >= ctx_end:
                                    insert_idx = _idx
                                    break
                            except Exception:
                                continue
                        tokens = [t for t in (answer or "").split() if t]
                        if tokens:
                            base_t = float(ctx_end)
                            synthetic_entries = [
                                {
                                    "word": t,
                                    "speaker": "AI",
                                    "start": base_t + (k * 0.30),
                                    "end": base_t + (k * 0.30) + 0.25,
                                }
                                for k, t in enumerate(tokens)
                            ]
                            mutable_words[insert_idx:insert_idx] = synthetic_entries
                            log.append(f"[INTERN_TRANSCRIPT_INSERT] words={len(tokens)} at_index={insert_idx}")
                except Exception:
                    pass
                if insane_verbose:
                    log.append(f"[INTERN_ANSWER_TEXT] '{(answer or '')[:200]}'")
                log.append(f"[INTERN_ANSWER] len={len(answer or '')}")
            except Exception as e:
                log.append(f"[INTERN_ANSWER_ERROR] {e}; using fallback reply")
                answer = "The intern is out to lunch."
            try:
                # Check if user provided pre-generated audio URL
                override_audio_url = (cmd.get("override_audio_url") or "").strip()
                if override_audio_url:
                    # Download the pre-generated audio from the URL
                    try:
                        import requests
                        import io
                        log.append(f"[INTERN_OVERRIDE_AUDIO] downloading from {override_audio_url[:100]}")
                        response = requests.get(override_audio_url, timeout=30)
                        response.raise_for_status()
                        audio_bytes = io.BytesIO(response.content)
                        speech = AudioSegment.from_file(audio_bytes)
                        log.append(f"[INTERN_OVERRIDE_AUDIO] loaded {len(speech)}ms from URL")
                    except Exception as e:
                        log.append(f"[INTERN_OVERRIDE_AUDIO_ERROR] {e}; will generate fresh TTS")
                        speech = ai_enhancer.generate_speech_from_text(
                            answer, provider=tts_provider, api_key=elevenlabs_api_key
                        )
                elif fast_mode:
                    # Insert a short placeholder clip (silence) to avoid network calls in fast mode
                    speech = AudioSegment.silent(duration=600)
                    try:
                        log.append("[INTERN_FAST_MODE] inserted 600ms placeholder audio")
                    except Exception:
                        pass
                elif bool(cmd.get("disable_tts")):
                    cmd["audio_generated"] = False
                    log.append("[INTERN_TTS_DISABLED] skipping TTS generation for this command")
                    speech = None
                else:
                    speech = ai_enhancer.generate_speech_from_text(
                        answer, provider=tts_provider, api_key=elevenlabs_api_key
                    )
                if speech is None:
                    log.append("[INTERN_NO_AUDIO_INSERTED]")
                    continue
                if not speech:
                    raise ValueError("TTS returned empty audio")
                # normalize loudness and lightly fade out to avoid perceived tails
                speech = match_target_dbfs(speech).fade_out(80)
                orig_len = len(main_content_audio)
                cleaned_len = len(out)
                ratio = cleaned_len / orig_len if orig_len else 1.0
                prompt_start_ms = int(float(cmd.get("time", 0)) * 1000 * ratio)
                prompt_end_ms = int(float(cmd.get("context_end", cmd.get("time", 0))) * 1000 * ratio)
                prompt_start_ms = max(0, min(prompt_start_ms, len(out)))
                prompt_end_ms = max(prompt_start_ms, min(prompt_end_ms, len(out)))
                # Prefer explicit end-marker timing if present (e.g., 'stop'/'stop intern'), else use a tiny pad
                end_marker_start = cmd.get("end_marker_start")
                end_marker_end = cmd.get("end_marker_end")
                insertion_ms = prompt_end_ms
                if isinstance(end_marker_start, (int, float)) and isinstance(end_marker_end, (int, float)) and end_marker_end >= end_marker_start:
                    ems = int(float(end_marker_start) * 1000 * ratio)
                    eme = int(float(end_marker_end) * 1000 * ratio)
                    ems = max(0, min(ems, len(out)))
                    eme = max(ems, min(eme, len(out)))
                    if eme > ems:
                        out = AudioSegment(out[:ems]) + AudioSegment(out[eme:])
                        insertion_ms = ems
                        log.append(f"[INTERN_END_MARKER_CUT] cut_ms=[{ems},{eme}] insert_at={insertion_ms}")
                else:
                    insert_pad_ms = max(0, int(cmd.get("insert_pad_ms", 120)))
                    insertion_ms = min(prompt_end_ms + insert_pad_ms, len(out))
                log.append(
                    f"[INTERN_TIMING_ANCHORED] insertion_ms={insertion_ms} window=[{prompt_start_ms},{prompt_end_ms}]"
                )
                try:
                    if cmd.get("remove_spoken_prompt"):
                        if prompt_end_ms > prompt_start_ms:
                            # Replace the spoken prompt region with pure silence of the same duration
                            silence_len = int(max(0, prompt_end_ms - prompt_start_ms))
                            silence = AudioSegment.silent(duration=silence_len)
                            out = out[:prompt_start_ms] + silence + out[prompt_end_ms:]
                            log.append(f"[INTERN_PROMPT_MUTED] from_ms={prompt_start_ms} to_ms={prompt_end_ms}")
                except Exception:
                    pass
                out = out[:insertion_ms] + speech + out[insertion_ms:]
                cmd["audio_inserted_at_ms"] = insertion_ms
                cmd["audio_generated"] = True
                log.append(f"[INTERN_AUDIO] at_ms={insertion_ms} duration_ms={len(speech)}")
            except Exception as e:
                cmd["intern_audio_error"] = str(e)
                log.append(f"[INTERN_AUDIO_ERROR] {e}; attempting fallback clip")
                # Best-effort fallback: speak a short default line so users hear something predictable
                try:
                    if fast_mode:
                        fb_speech = AudioSegment.silent(duration=500)
                    elif not bool(cmd.get("disable_tts")):
                        fb_text = "The intern is out to lunch."
                        fb_speech = ai_enhancer.generate_speech_from_text(
                            fb_text, provider=tts_provider, api_key=elevenlabs_api_key
                        )
                    else:
                        fb_speech = None
                        if fb_speech:
                            fb_speech = match_target_dbfs(fb_speech).fade_out(80)
                            orig_len = len(main_content_audio)
                            cleaned_len = len(out)
                            ratio = cleaned_len / orig_len if orig_len else 1.0
                            prompt_start_ms = int(float(cmd.get("time", 0)) * 1000 * ratio)
                            prompt_end_ms = int(float(cmd.get("context_end", cmd.get("time", 0))) * 1000 * ratio)
                            prompt_start_ms = max(0, min(prompt_start_ms, len(out)))
                            prompt_end_ms = max(prompt_start_ms, min(prompt_end_ms, len(out)))
                            end_marker_start = cmd.get("end_marker_start")
                            end_marker_end = cmd.get("end_marker_end")
                            insertion_ms = prompt_end_ms
                            if isinstance(end_marker_start, (int, float)) and isinstance(end_marker_end, (int, float)) and end_marker_end >= end_marker_start:
                                ems = int(float(end_marker_start) * 1000 * ratio)
                                eme = int(float(end_marker_end) * 1000 * ratio)
                                ems = max(0, min(ems, len(out)))
                                eme = max(ems, min(eme, len(out)))
                                if eme > ems:
                                    out = AudioSegment(out[:ems]) + AudioSegment(out[eme:])
                                    insertion_ms = ems
                                    log.append(f"[INTERN_END_MARKER_CUT] cut_ms=[{ems},{eme}] insert_at={insertion_ms}")
                            else:
                                insertion_ms = min(prompt_end_ms + max(0, int(cmd.get("insert_pad_ms", 120))), len(out))
                            out = out[:insertion_ms] + fb_speech + out[insertion_ms:]
                            cmd["audio_inserted_at_ms"] = insertion_ms
                            cmd["audio_generated"] = True
                            log.append(f"[INTERN_AUDIO_FALLBACK] inserted fallback at_ms={insertion_ms} duration_ms={len(fb_speech)}")
                except Exception as e2:
                    log.append(f"[INTERN_AUDIO_FALLBACK_ERROR] {e2}")
    return out


__all__ = ["execute_intern_commands"]
