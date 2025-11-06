from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import AudioSegment, match_target_dbfs
from difflib import SequenceMatcher


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
    """Execute Intern commands (audio only), preserving spoken prompt.
    This code was extracted from commands.py to isolate Intern behavior.
    """
    log.append(f"[INTERN_EXEC] 🎬 STARTING EXECUTION cmds_count={len(cmds)} audio_duration={len(cleaned_audio)/1000:.2f}s")
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
        log.append(f"[INTERN_START] cmd_id={cmd.get('command_id')} time={cmd.get('time')} has_override_answer={bool(cmd.get('override_answer'))} has_override_audio={bool(cmd.get('override_audio_url'))}")
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
            answer_text = ""
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

                answer_text = (answer or "").strip()
                if not answer_text:
                    answer_text = "The intern is out to lunch."

                try:
                    spoken_prompt = (cmd.get("local_context") or "").strip()
                    prompts = [spoken_prompt, (query_text or "").strip()]
                    seen = set()
                    prompts = [p for p in prompts if p and not (p in seen or seen.add(p))]
                    answer_text = _strip_prompt_prefix_suffix(answer_text, prompts, log)
                    # Also remove duplicated or prompt-like tail phrases to avoid end-echo in TTS
                    answer_text = _dedupe_tail(answer_text, log)
                    answer_text = _strip_promptish_tail(answer_text, prompts, log)
                except Exception:
                    pass
                try:
                    if mutable_words is not None and (answer_text or "").strip():
                        ctx_end = _safe_float(cmd.get("context_end"))
                        if ctx_end is None:
                            ctx_end = _safe_float(cmd.get("time"))
                        if ctx_end is None:
                            ctx_end = 0.0
                        insert_idx = len(mutable_words)
                        for _idx, _w in enumerate(mutable_words):
                            try:
                                if float((_w or {}).get("start", 1e12)) >= ctx_end:
                                    insert_idx = _idx
                                    break
                            except Exception:
                                continue
                        tokens = [t for t in (answer_text or "").split() if t]
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
                    log.append(f"[INTERN_ANSWER_TEXT] '{(answer_text or '')[:200]}'")
                log.append(f"[INTERN_ANSWER] len={len(answer_text or '')}")
                cmd["final_answer_text"] = answer_text
            except Exception as e:
                log.append(f"[INTERN_ANSWER_ERROR] {e}; using fallback reply")
                answer_text = "The intern is out to lunch."
                cmd["final_answer_text"] = answer_text
            try:
                # Check if user provided pre-generated audio URL
                override_audio_url = (cmd.get("override_audio_url") or "").strip()
                log.append(f"[INTERN_AUDIO_SOURCE] override_url={'YES' if override_audio_url else 'NO'} fast_mode={fast_mode} disable_tts={bool(cmd.get('disable_tts'))}")
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
                        voice_id = cmd.get("voice_id")
                        speech = ai_enhancer.generate_speech_from_text(
                            answer_text, voice_id=voice_id, provider=tts_provider, api_key=elevenlabs_api_key
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
                    voice_id = cmd.get("voice_id")
                    log.append(f"[INTERN_TTS_GENERATE] voice_id={voice_id} text_len={len(answer_text)} provider={tts_provider}")
                    try:
                        speech = ai_enhancer.generate_speech_from_text(
                            answer_text, voice_id=voice_id, provider=tts_provider, api_key=elevenlabs_api_key
                        )
                        if speech:
                            log.append(f"[INTERN_TTS_SUCCESS] generated {len(speech)}ms audio")
                        else:
                            log.append(f"[INTERN_TTS_WARNING] TTS returned empty/None audio")
                    except Exception as tts_err:
                        log.append(f"[INTERN_TTS_FAILED] {type(tts_err).__name__}: {tts_err}")
                        speech = None
                if speech is None:
                    log.append(f"[INTERN_NO_AUDIO_INSERTED] cmd_id={cmd.get('command_id')} - speech generation failed")
                    cmd["audio_generated"] = False
                    cmd["skip_reason"] = "speech_generation_failed"
                    continue
                if not speech:
                    log.append(f"[INTERN_EMPTY_AUDIO] cmd_id={cmd.get('command_id')} - speech is empty")
                    cmd["audio_generated"] = False
                    cmd["skip_reason"] = "speech_empty"
                    continue
                # normalize loudness and lightly fade out to avoid perceived tails
                speech = match_target_dbfs(speech).fade_out(80)
                orig_len = len(main_content_audio)
                cleaned_len = len(out)
                ratio = cleaned_len / orig_len if orig_len else 1.0

                start_s = _safe_float(cmd.get("time"))
                if start_s is None:
                    start_s = 0.0
                context_end_s = _safe_float(cmd.get("context_end"))
                if context_end_s is None:
                    context_end_s = start_s
                insertion_s = _safe_float(cmd.get("insertion_s"))
                if insertion_s is None:
                    insertion_s = _safe_float(cmd.get("end_marker_end"))
                if insertion_s is None:
                    insertion_s = context_end_s

                prompt_start_ms = int(start_s * 1000 * ratio)
                prompt_end_ms = int(context_end_s * 1000 * ratio)
                prompt_start_ms = max(0, min(prompt_start_ms, len(out)))
                prompt_end_ms = max(prompt_start_ms, min(prompt_end_ms, len(out)))

                insertion_ms = int(insertion_s * 1000 * ratio)
                insertion_ms = max(0, min(insertion_ms, len(out)))
                log.append(f"[INTERN_INSERT_ONLY] insert_at={insertion_ms}ms (s={insertion_s:.3f})")
                if insertion_ms < prompt_end_ms:
                    log.append(
                        f"[INTERN_INSERT_ADJUST] insertion before context_end; forcing at context_end {prompt_end_ms}"
                    )
                    insertion_ms = prompt_end_ms
                    insertion_s = (prompt_end_ms / 1000.0) / ratio if ratio else (prompt_end_ms / 1000.0)
                cmd["resolved_insertion_ms"] = insertion_ms
                cmd["resolved_insertion_s"] = insertion_s
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
                
                # Add silence buffers around AI response for clean insertion
                silence_before_ms = int(max(0, cmd.get("add_silence_before_ms", 0)))
                silence_after_ms = int(max(0, cmd.get("add_silence_after_ms", 0)))
                
                if silence_before_ms > 0:
                    silence_before = AudioSegment.silent(duration=silence_before_ms)
                    log.append(f"[INTERN_BUFFER] adding {silence_before_ms}ms silence BEFORE response")
                else:
                    silence_before = AudioSegment.silent(duration=0)
                
                if silence_after_ms > 0:
                    silence_after = AudioSegment.silent(duration=silence_after_ms)
                    log.append(f"[INTERN_BUFFER] adding {silence_after_ms}ms silence AFTER response")
                else:
                    silence_after = AudioSegment.silent(duration=0)
                
                # Insert: silence_before + speech + silence_after at the marked position
                out = out[:insertion_ms] + silence_before + speech + silence_after + out[insertion_ms:]
                cmd["audio_inserted_at_ms"] = insertion_ms
                cmd["audio_generated"] = True
                log.append(f"[INTERN_AUDIO] at_ms={insertion_ms} duration_ms={len(speech)} total_with_buffers={len(silence_before) + len(speech) + len(silence_after)}")
            except Exception as e:
                cmd["intern_audio_error"] = str(e)
                log.append(f"[INTERN_AUDIO_ERROR] {e}; attempting fallback clip")
                # Best-effort fallback: speak a short default line so users hear something predictable
                try:
                    if fast_mode:
                        fb_speech = AudioSegment.silent(duration=500)
                    elif not bool(cmd.get("disable_tts")):
                        fb_text = "The intern is out to lunch."
                        voice_id = cmd.get("voice_id")
                        fb_speech = ai_enhancer.generate_speech_from_text(
                            fb_text, voice_id=voice_id, provider=tts_provider, api_key=elevenlabs_api_key
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
    
    # Summary logging
    inserted_count = sum(1 for cmd in cmds if cmd.get("audio_generated"))
    skipped_count = len(cmds) - inserted_count
    log.append(f"[INTERN_SUMMARY] total_commands={len(cmds)} inserted={inserted_count} skipped={skipped_count}")
    if skipped_count > 0:
        skip_reasons = [cmd.get("skip_reason", "unknown") for cmd in cmds if not cmd.get("audio_generated")]
        log.append(f"[INTERN_SKIPPED_REASONS] {skip_reasons}")
    
    return out


__all__ = ["execute_intern_commands"]
