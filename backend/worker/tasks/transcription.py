import os
import shutil
import logging
from pathlib import Path

from worker.tasks import celery_app
from api.core.paths import WS_ROOT as PROJECT_ROOT
from api.services import transcription as trans


@celery_app.task(name="transcribe_media_file")
def transcribe_media_file(filename: str) -> dict:
	"""Background transcription immediately after upload.

	Writes two files under transcripts/ (new naming only by default):
	  - {stem}.original.json (snapshot, never modified by this task if exists)
	  - {stem}.json (working copy for downstream processing; created if missing)
	Optional legacy mirrors {stem}.original.words.json and {stem}.words.json can be enabled via
	TRANSCRIPTS_LEGACY_MIRROR=1 for backward compatibility.
	"""
	try:
		tr_dir = PROJECT_ROOT / 'transcripts'
		tr_dir.mkdir(parents=True, exist_ok=True)

		# Flags
		_force = (os.getenv("TRANSCRIPTION_FORCE", "").strip().lower() in {"1","true","yes","on"})
		mirror_legacy = (os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower() in {"1","true","yes","on"})

		# Transcribe using shared service (filename relative to media_uploads)
		words = trans.get_word_timestamps(filename)
		stem = Path(filename).stem
		import json as _json

		# Canonical outputs
		orig_new = tr_dir / f"{stem}.original.json"
		work_new = tr_dir / f"{stem}.json"
		# Legacy mirrors
		orig_legacy = tr_dir / f"{stem}.original.words.json"
		work_legacy = tr_dir / f"{stem}.words.json"

		# Write original snapshot and working copy
		if _force or (not orig_new.exists() and not orig_legacy.exists()):
			with open(orig_new, 'w', encoding='utf-8') as fh:
				_json.dump(words, fh, ensure_ascii=False)
		if _force or (not work_new.exists() and not work_legacy.exists()):
			with open(work_new, 'w', encoding='utf-8') as fh:
				_json.dump(words, fh, ensure_ascii=False)

		# Optional bridge/mirror to legacy names
		if mirror_legacy:
			try:
				if orig_legacy.exists() and not orig_new.exists():
					shutil.copyfile(orig_legacy, orig_new)
				if orig_new.exists() and not orig_legacy.exists():
					shutil.copyfile(orig_new, orig_legacy)
				if work_legacy.exists() and not work_new.exists():
					shutil.copyfile(work_legacy, work_new)
				if work_new.exists() and not work_legacy.exists():
					shutil.copyfile(work_new, work_legacy)
			except Exception:
				logging.warning("[transcribe] Failed to mirror transcript files to legacy/new names", exc_info=True)

		if _force:
			logging.info(
				f"[transcribe] FORCED fresh transcripts for {filename} -> {orig_new.name}, {work_new.name}" +
				(f", mirrored -> {orig_legacy.name}, {work_legacy.name}" if mirror_legacy else "")
			)
		else:
			logging.info(
				f"[transcribe] cached transcripts for {filename} -> {orig_new.name}, {work_new.name}" +
				(f", mirrored -> {orig_legacy.name}, {work_legacy.name}" if mirror_legacy else "")
			)

		return {"ok": True, "filename": filename, "original": orig_new.name, "working": work_new.name}
	except Exception as ex:
		logging.warning("[transcribe] failed for %s: %s", filename, ex, exc_info=True)
		# Dev fallback: synthetic words
		try:
			if os.getenv("TRANSCRIPTION_FAKE", "").strip().lower() in {"1","true","yes","on"}:
				from pydub import AudioSegment as _AS
				src = PROJECT_ROOT / 'media_uploads' / filename
				audio = _AS.from_file(src) if src.is_file() else _AS.silent(duration=10000)
				dur_s = max(1.0, len(audio) / 1000.0)
				words = []
				t = 0.0
				idx = 0
				while t < dur_s:
					w = "flubber" if (idx % 10 == 5) else f"w{idx}"
					words.append({"word": w, "start": round(t,3), "end": round(t+0.3,3), "speaker": None})
					t += 0.5
					idx += 1
				tr_dir = PROJECT_ROOT / 'transcripts'
				tr_dir.mkdir(parents=True, exist_ok=True)
				import json as _json
				stem = Path(filename).stem
				orig_new = tr_dir / f"{stem}.original.json"
				work_new = tr_dir / f"{stem}.json"
				orig_legacy = tr_dir / f"{stem}.original.words.json"
				work_legacy = tr_dir / f"{stem}.words.json"
				mirror_legacy = (os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower() in {"1","true","yes","on"})
				if not orig_new.exists() and not orig_legacy.exists():
					with open(orig_new, 'w', encoding='utf-8') as fh:
						_json.dump(words, fh, ensure_ascii=False)
				if not work_new.exists() and not work_legacy.exists():
					with open(work_new, 'w', encoding='utf-8') as fh:
						_json.dump(words, fh, ensure_ascii=False)
				if mirror_legacy:
					try:
						if orig_new.exists() and not orig_legacy.exists():
							shutil.copyfile(orig_new, orig_legacy)
						if work_new.exists() and not work_legacy.exists():
							shutil.copyfile(work_new, work_legacy)
					except Exception:
						pass
				logging.info(
					f"[transcribe] DEV FAKE wrote {orig_new.name}, {work_new.name}" +
					(f", mirrored -> {orig_legacy.name}, {work_legacy.name}" if mirror_legacy else "")
				)
				return {"ok": True, "filename": filename, "original": orig_new.name, "working": work_new.name, "fake": True}
		except Exception as ex2:
			logging.warning("[transcribe] dev-fake fallback failed: %s", ex2, exc_info=True)
		return {"ok": False, "filename": filename, "error": str(ex)}

