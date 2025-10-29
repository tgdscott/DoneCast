from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from pydub import AudioSegment

from api.core.paths import TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR

from .formatting import fmt_ts

TRANSCRIPTS_DIR = _TRANSCRIPTS_DIR

_PUNCT_RE = re.compile(r"[^\w\s']+", flags=re.UNICODE)


def build_phrases(words_list: List[Dict[str, Any]], gap_s: float = 0.8) -> List[Dict[str, Any]]:
    phrases: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    prev_end: Optional[float] = None
    prev_speaker: Optional[str] = None
    for w in (words_list or []):
        if not isinstance(w, dict):
            continue
        txt = str((w.get("word") or "")).strip()
        if txt == "":
            continue
        st = float(w.get("start") or 0.0)
        en = float(w.get("end") or st)
        spk = (w.get("speaker") or "") or "Speaker"
        gap = (st - float(prev_end)) if (prev_end is not None) else 0.0
        if cur is None or spk != prev_speaker or (gap_s and gap >= gap_s):
            if cur is not None:
                phrases.append(cur)
            cur = {
                "speaker": spk,
                "start": st,
                "end": en,
                "text": txt,
            }
        else:
            cur["end"] = en
            cur["text"] = (cur["text"] + " " + txt).strip()
        prev_end = en
        prev_speaker = spk
    if cur is not None:
        phrases.append(cur)
    return phrases


def write_phrase_txt(path: Path, phrases: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    for p in phrases:
        lines.append(
            f"[{fmt_ts(p.get('start', 0.0))} - {fmt_ts(p.get('end', 0.0))}] "
            f"{p.get('speaker', 'Speaker')}: {p.get('text', '').strip()}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))


def offset_phrases(
    phrases: List[Dict[str, Any]], offset_s: float, *, speaker_override: Optional[str] = None
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in phrases:
        out.append(
            {
                "speaker": speaker_override or p.get("speaker") or "Speaker",
                "start": float(p.get("start", 0.0)) + float(offset_s or 0.0),
                "end": float(p.get("end", 0.0)) + float(offset_s or 0.0),
                "text": p.get("text", ""),
            }
        )
    return out


def write_nopunct_sidecar(words_json_path: Path, out_basename: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(words_json_path, "r", encoding="utf-8") as f:
        words = json.load(f)

    def _strip_punct(token: str) -> str:
        return _PUNCT_RE.sub("", token)

    out_words: List[Dict[str, Any]] = []
    for w in words:
        w2 = dict(w)
        if "word" in w2 and isinstance(w2["word"], str):
            w2["word"] = _strip_punct(w2["word"])
        out_words.append(w2)

    out_path = dest_dir / f"{out_basename}.nopunct.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_words, f, ensure_ascii=False)
    return out_path


def write_final_transcripts_and_cleanup(
    sanitized_output_filename: str,
    mutable_words: List[Dict[str, Any]],
    placements: List[Tuple[dict, AudioSegment, int, int]],
    template: Any,
    main_content_filename: str,
    log: List[str],
) -> None:
    try:
        working_json = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.json"
        with open(working_json, "w", encoding="utf-8") as fh:
            json.dump(mutable_words, fh)
        log.append(
            f"[TRANSCRIPTS] updated working JSON {working_json.name} entries={len(mutable_words)}"
        )
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] update working JSON: {e}")

    try:
        final_txt = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.final.txt"
        final_phrases = build_phrases(mutable_words)
        write_phrase_txt(final_txt, final_phrases)
        log.append(
            f"[TRANSCRIPTS] wrote final (content) {final_txt.name} phrases={len(final_phrases)}"
        )
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] write final content transcript: {e}")

    try:
        published_txt = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.txt"
        pub_phrases: List[Dict[str, Any]] = []
        if placements:
            content_phr = build_phrases(mutable_words)
            content_added = False
            for seg, _seg_audio, st_ms, en_ms in placements:
                seg_type = str((seg.get("segment_type") or "content")).lower()
                if seg_type == "content" and not content_added:
                    pub_phrases.extend(offset_phrases(content_phr, st_ms / 1000.0))
                    content_added = True
                elif seg_type != "content":
                    label = (
                        seg.get("name")
                        or seg.get("title")
                        or (seg.get("source") or {}).get("label")
                        or (seg.get("source") or {}).get("filename")
                        or seg_type.title()
                    )
                    pub_phrases.append(
                        {
                            "speaker": "Narrator",
                            "start": st_ms / 1000.0,
                            "end": en_ms / 1000.0,
                            "text": f"[{label}]",
                        }
                    )
        else:
            pub_phrases = build_phrases(mutable_words)
        write_phrase_txt(published_txt, pub_phrases)
        log.append(
            f"[TRANSCRIPTS] wrote published transcript {published_txt.name} phrases={len(pub_phrases)}"
        )
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] write published transcript: {e}")

    try:
        content_stem = Path(main_content_filename).stem
        cleaned_stem = f"cleaned_{content_stem}"
        precut_stem = f"precut_{content_stem}"
        keep_base = f"{sanitized_output_filename}.json"
        legacy_patterns = [
            f"*{content_stem}.words.json",
            f"*{content_stem}.original.words.json",
            f"{sanitized_output_filename}.words.json",
            f"{sanitized_output_filename}.original.words.json",
            f"{cleaned_stem}.words.json",
            f"{cleaned_stem}.original.words.json",
            f"{precut_stem}.words.json",
            f"{precut_stem}.original.words.json",
        ]
        for pat in legacy_patterns:
            for p in TRANSCRIPTS_DIR.glob(pat):
                if p.name == keep_base or p.suffix.lower() == ".txt":
                    continue
                try:
                    p.unlink()
                    log.append(f"[TRANSCRIPTS_CLEAN] removed {p.name}")
                except Exception as _e:
                    log.append(
                        f"[TRANSCRIPTS_CLEAN_WARN] could not remove {p.name}: {type(_e).__name__}: {_e}"
                    )
        helper_targets = [
            TRANSCRIPTS_DIR / f"{sanitized_output_filename}.nopunct.json",
            TRANSCRIPTS_DIR / f"{sanitized_output_filename}.original.json",
            TRANSCRIPTS_DIR / f"{content_stem}.original.json",
            TRANSCRIPTS_DIR / f"{cleaned_stem}.original.json",
            TRANSCRIPTS_DIR / f"{precut_stem}.original.json",
        ]
        for p in helper_targets:
            try:
                if p.exists():
                    p.unlink()
                    log.append(f"[TRANSCRIPTS_CLEAN] removed {p.name}")
            except Exception as _e:
                log.append(
                    f"[TRANSCRIPTS_CLEAN_WARN] could not remove {getattr(p, 'name', p)}: {type(_e).__name__}: {_e}"
                )
    except Exception as e:
        log.append(f"[TRANSCRIPTS_CLEAN_ERROR] {e}")


__all__ = [
    "build_phrases",
    "write_phrase_txt",
    "offset_phrases",
    "write_nopunct_sidecar",
    "write_final_transcripts_and_cleanup",
]
