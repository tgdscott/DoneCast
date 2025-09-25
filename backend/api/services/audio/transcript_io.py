from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


def write_working_json(
    words: List[Dict[str, Any]],
    sanitized_output_filename: str,
    transcripts_dir: Path,
    log: List[str],
) -> Path:
    """Write JSON to {transcripts_dir}/{sanitized_output_filename}.json with UTF-8, indent=2."""
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    path = transcripts_dir / f"{sanitized_output_filename}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(words, fh, ensure_ascii=False, indent=2)
    log.append(f"[TRANSCRIPTS] wrote working transcript JSON {path.name} entries={len(words)}")
    return path


def write_nopunct_sidecar(
    words: List[Dict[str, Any]],
    sanitized_output_filename: str,
    transcripts_dir: Path,
    log: List[str],
) -> Path:
    """Write a punctuation-stripped sidecar JSON (.nopunct.json) always.

    For each item, strip punctuation from 'word' keeping apostrophes, collapse whitespace,
    and keep all other fields unchanged. Writes UTF-8, indent=2.
    """
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    path = transcripts_dir / f"{sanitized_output_filename}.nopunct.json"
    cleaned_items: List[Dict[str, Any]] = []
    for item in (words or []):
        if not isinstance(item, dict):
            continue
        cleaned = re.sub(r"[^\w\s']", "", str(item.get("word", "")))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        new_item = dict(item)
        new_item["word"] = cleaned
        cleaned_items.append(new_item)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cleaned_items, fh, ensure_ascii=False, indent=2)
    log.append(f"[TRANSCRIPTS] wrote punctuation-sanitized JSON {path.name} entries={len(words)}")
    return path


def load_transcript_json(path: Path) -> List[Dict[str, Any]]:
    """Load a transcript JSON list from the given path.

    If JSON is not a list, return []. Exceptions bubble up to caller.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []
