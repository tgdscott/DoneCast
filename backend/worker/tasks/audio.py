import os
import shutil
import logging
from pathlib import Path
from typing import Optional
from sqlmodel import select

from worker.tasks import celery_app
from api.core.paths import WS_ROOT as PROJECT_ROOT
from api.core.paths import APP_ROOT as APP_ROOT_DIR
from api.core.database import get_session
from api.core import crud
from api.core.config import settings
from api.services import audio_processor
from api.services.audio.common import sanitize_filename
from api.services import transcription as trans
from api.services import ai_enhancer
from pydub import AudioSegment
from api.services import clean_engine
from api.services.clean_engine.features import apply_flubber_cuts
from api.models.podcast import MediaItem, MediaCategory, Episode
from uuid import UUID
from api.models.notification import Notification
from api.core.paths import MEDIA_DIR
from api.services.billing import usage as usage_svc
from math import ceil
from celery import current_task


# Directory to persist large assembly logs
ASSEMBLY_LOG_DIR = PROJECT_ROOT / "assembly_logs"
ASSEMBLY_LOG_DIR.mkdir(exist_ok=True)


@celery_app.task(name="create_podcast_episode")
def create_podcast_episode(
	episode_id: str,
	template_id: str,
	main_content_filename: str,
	output_filename: str,
	tts_values: dict,
	episode_details: dict,
	user_id: str,
	podcast_id: str,
	intents: dict | None = None,
	*,
	skip_charge: bool = False,
):
	"""
	Assemble final audio from template + content. Set episode.status=processed and store final_audio_path.
	"""
	logging.info(f"[assemble] CWD = {os.getcwd()}")
	session = next(get_session())
	try:
		# Helper: resolve existing media file across common dev/prod locations
		from pathlib import Path as _Path
		def _resolve_media_file(name: str) -> Optional[Path]:
			try:
				p = _Path(str(name))
				if p.is_absolute() and p.exists():
					return p
			except Exception:
				pass
			try:
				base = _Path(str(name)).name
			except Exception:
				base = str(name)
			candidates = [
				PROJECT_ROOT / 'media_uploads' / base,            # WS_ROOT/media_uploads
				APP_ROOT_DIR / 'media_uploads' / base,            # backend/media_uploads
				APP_ROOT_DIR.parent / 'media_uploads' / base,     # repo_root/media_uploads
				MEDIA_DIR / base,                                 # configured MEDIA_DIR (e.g., local_media)
			]
			for c in candidates:
				try:
					if c.exists():
						return c
				except Exception:
					continue
			return None
		# --- Charge processing minutes at job start (idempotent by task id) ---
		if not skip_charge:
			try:
				from uuid import UUID as _UUID
				uid = _UUID(user_id)
				eid = _UUID(episode_id)
				# Resolve source path
				from pathlib import Path as _Path
				src_name = _Path(str(main_content_filename)).name
				src_path = MEDIA_DIR / src_name
				seconds = 0.0
				if src_path.is_file():
					# Try ffprobe first
					try:
						import subprocess, json as _json
						cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(src_path)]
						proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
						if proc.returncode == 0:
							data = _json.loads(proc.stdout or '{}')
							dur = float(data.get('format', {}).get('duration', 0))
							if dur and dur > 0:
								seconds = float(dur)
					except Exception:
						pass
					if seconds <= 0:
						try:
							from pydub import AudioSegment as _AS
							seg = _AS.from_file(src_path)
							seconds = len(seg) / 1000.0
						except Exception:
							seconds = 0.0
				minutes = max(1, int(ceil(seconds / 60.0))) if seconds > 0 else 1
				corr = None
				try:
					corr = str(current_task.request.id)
				except Exception:
					corr = None
				res = usage_svc.post_debit(
					session=session,
					user_id=uid,
					minutes=minutes,
					episode_id=eid,
					reason="PROCESS_AUDIO",
					correlation_id=corr,
					notes="charge at job start",
				)
				if res is not None:
					logging.info("usage.debit posted", extra={"user_id":str(uid),"episode_id":str(eid),"minutes":minutes,"correlation_id":corr})
			except Exception:
				logging.warning("[assemble] failed posting usage debit at start", exc_info=True)

		# Fetch template and episode
		template = crud.get_template_by_id(session, UUID(template_id))
		if not template:
			logging.warning("[assemble] stale job: template %s not found; dropping task", template_id)
			# Persist a minimal assembly log for visibility
			try:
				log_path = ASSEMBLY_LOG_DIR / f"{episode_id}.log"
				with open(log_path, "w", encoding="utf-8") as fh:
					fh.write(f"[assemble] template not found: {template_id}\n")
			except Exception:
				pass
			return {"dropped": True, "reason": "template not found", "template_id": template_id}
		episode = crud.get_episode_by_id(session, UUID(episode_id))
		if not episode:
			logging.warning("[assemble] stale job: episode %s not found; dropping task", episode_id)
			try:
				log_path = ASSEMBLY_LOG_DIR / f"{episode_id}.log"
				with open(log_path, "w", encoding="utf-8") as fh:
					fh.write(f"[assemble] episode not found: {episode_id}\n")
			except Exception:
				pass
			return {"dropped": True, "reason": "episode not found", "episode_id": episode_id}

		# Idempotency guard
		if getattr(episode, 'status', None) == 'processed' and getattr(episode, 'final_audio_path', None):
			logging.info(f"[assemble] duplicate task for already processed episode {episode_id}; skipping reassembly")
			return {"message": "Episode already processed (idempotent skip)", "episode_id": episode.id}

		cover_image_path = (episode_details or {}).get("cover_image_path")
		logging.info(f"[assemble] start: output={output_filename}, template={template_id}, user={user_id}")
		if cover_image_path:
			logging.info(f"[assemble] cover_image_path from FE: {cover_image_path}")

		# User cleanup settings
		user_obj = crud.get_user_by_id(session, UUID(user_id)) if hasattr(crud, 'get_user_by_id') else None
		cleanup_settings = {}
		if user_obj and getattr(user_obj, 'audio_cleanup_settings_json', None):
			import json as _json
			try:
				cleanup_settings = _json.loads(user_obj.audio_cleanup_settings_json or '{}')
			except Exception:
				cleanup_settings = {}

		# Preferred TTS provider
		preferred_tts_provider = None
		try:
			preferred_tts_provider = (cleanup_settings.get('ttsProvider') or '').strip().lower() if isinstance(cleanup_settings, dict) else None
		except Exception:
			preferred_tts_provider = None
		if preferred_tts_provider not in {'elevenlabs','google'}:
			# Prefer ElevenLabs if either a per-user key OR a platform env key exists
			has_user_key = bool(getattr(user_obj, 'elevenlabs_api_key', None))
			has_env_key = bool(getattr(settings, 'ELEVENLABS_API_KEY', None))
			preferred_tts_provider = 'elevenlabs' if (has_user_key or has_env_key) else 'google'

		# Resolve transcript JSON...
		base_stems = []
		try:
			base_stems.append(Path(main_content_filename).stem)
		except Exception:
			pass
		try:
			wn = getattr(episode, 'working_audio_name', None)
			if isinstance(wn, str) and wn:
				base_stems.append(Path(wn).stem)
		except Exception:
			pass
		try:
			if output_filename:
				base_stems.append(Path(output_filename).stem)
		except Exception:
			pass
		base_stems = [s for s in dict.fromkeys([s for s in base_stems if s])]
		search_dirs = [PROJECT_ROOT / 'transcripts']
		try:
			ws_root = PROJECT_ROOT.parent
			if ws_root and (ws_root / 'transcripts').exists():
				search_dirs.append(ws_root / 'transcripts')
		except Exception:
			pass
		words_json_path = None
		for d in search_dirs:
			for stem in base_stems:
				# prefer new
				cand_new = d / f"{stem}.json"
				cand_legacy = d / f"{stem}.words.json"
				if cand_new.is_file():
					words_json_path = cand_new
					break
				if cand_legacy.is_file():
					words_json_path = cand_legacy
					break
			if words_json_path:
				break
		try:
			logging.info(f"[assemble] resolved words_json_path={str(words_json_path) if words_json_path else 'None'} stems={base_stems} search={list(map(str, search_dirs))}")
		except Exception:
			pass

		base_audio_name = getattr(episode, 'working_audio_name', None) or main_content_filename
		# Resolve the actual file path for the base audio (dev may store under backend/media_uploads or media_uploads root)
		source_audio_path = _resolve_media_file(base_audio_name) or (PROJECT_ROOT / 'media_uploads' / Path(str(base_audio_name)).name)
		try:
			logging.info(f"[assemble] resolved base audio path={str(source_audio_path)}")
		except Exception:
			pass

		# Snapshot original transcript (*.original.json preferred)
		try:
			if words_json_path and Path(words_json_path).is_file():
				tr_dir = PROJECT_ROOT / 'transcripts'
				tr_dir.mkdir(parents=True, exist_ok=True)
				try:
					_pref_raw = Path(output_filename).stem if output_filename else None
				except Exception:
					_pref_raw = None
				if not _pref_raw:
					try:
						_pref_raw = Path(base_audio_name).stem
					except Exception:
						_pref_raw = Path(words_json_path).stem
				# Sanitize to ensure Windows-safe filenames (e.g., remove '?')
				preferred_stem = sanitize_filename(str(_pref_raw)) if _pref_raw else None
				orig_new = tr_dir / f"{preferred_stem}.original.json"
				orig_legacy = tr_dir / f"{preferred_stem}.original.words.json"
				# Only create snapshot if neither exists
				if (not orig_new.exists()) and (not orig_legacy.exists()):
					try:
						shutil.copyfile(words_json_path, orig_new)
					except Exception:
						logging.warning("[assemble] Failed to snapshot original transcript", exc_info=True)
				try:
					import json as _json
					meta = _json.loads(getattr(episode, 'meta_json', '{}') or '{}') if getattr(episode, 'meta_json', None) else {}
					ts = meta.get('transcripts') or {}
					ts['original'] = (orig_new.name if orig_new.exists() else (orig_legacy.name if orig_legacy.exists() else None))
					meta['transcripts'] = ts
					episode.meta_json = _json.dumps(meta)
					session.add(episode)
					session.commit()
				except Exception:
					session.rollback()
		except Exception:
			logging.warning("[assemble] Failed original transcript snapshot block", exc_info=True)

		# Load user-provided flubber cuts from meta
		cuts_ms = None
		try:
			import json as _json
			stored_meta = _json.loads(getattr(episode, 'meta_json', '{}') or '{}')
			if isinstance(stored_meta.get('flubber_cuts_ms'), list):
				cuts_ms = [(int(s), int(e)) for s,e in stored_meta['flubber_cuts_ms'] if isinstance(s, int) and isinstance(e, int) and e > s]
		except Exception:
			cuts_ms = None

		# If no transcript found, generate minimal transcript JSON (*.json + legacy mirror)
		if not words_json_path:
			try:
				_pref_raw2 = None
				try:
					_pref_raw2 = Path(output_filename).stem if output_filename else None
				except Exception:
					_pref_raw2 = None
				if not _pref_raw2:
					try:
						_pref_raw2 = Path(base_audio_name).stem
					except Exception:
						_pref_raw2 = None
				target_dir = PROJECT_ROOT / 'transcripts'
				target_dir.mkdir(parents=True, exist_ok=True)
				_fn = str(base_audio_name)
				words_list = trans.get_word_timestamps(_fn)
				out_stem = sanitize_filename(f"{_pref_raw2 or Path(str(_fn)).stem}")
				out_path = target_dir / f"{out_stem}.json"
				import json as _json
				with open(out_path, 'w', encoding='utf-8') as fh:
					_json.dump(words_list, fh)
				# legacy mirror (optional)
				if os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower() in {"1","true","yes","on"}:
					try:
						legacy = target_dir / f"{out_stem}.words.json"
						if not legacy.exists():
							shutil.copyfile(out_path, legacy)
					except Exception:
						pass
				words_json_path = out_path
				logging.info(f"[assemble] generated words_json via transcription: {out_path}")
			except Exception as e_gen:
				logging.warning(f"[assemble] failed to generate words_json: {e_gen}; will skip clean_engine and continue to mixer-only")

		# Build engine settings
		us = clean_engine.UserSettings(
			flubber_keyword=str((cleanup_settings or {}).get('flubberKeyword', 'flubber') or 'flubber'),
			intern_keyword=str((cleanup_settings or {}).get('internKeyword', 'intern') or 'intern'),
			filler_words=(cleanup_settings or {}).get('fillerWords', ["um","uh","like","you know","sort of","kind of"]),
			aggressive_fillers=(cleanup_settings or {}).get('aggressiveFillersList', []),
			filler_phrases=(cleanup_settings or {}).get('fillerPhrases', []),
			strict_filler_removal=bool((cleanup_settings or {}).get('strictFillerRemoval', True)),
		)
		ss = clean_engine.SilenceSettings(
			detect_threshold_dbfs=int((cleanup_settings or {}).get('silenceThreshDb', -40)),
			min_silence_ms=int(float((cleanup_settings or {}).get('maxPauseSeconds', 1.5)) * 1000),
			target_silence_ms=int(float((cleanup_settings or {}).get('targetPauseSeconds', 0.5)) * 1000),
			edge_keep_ratio=float((cleanup_settings or {}).get('pauseEdgeKeepRatio', 0.5)),
			max_removal_pct=float((cleanup_settings or {}).get('maxPauseRemovalPct', 0.9)),
		)
		ins = clean_engine.InternSettings(
			min_break_s=float((cleanup_settings or {}).get('internMinBreak', 2.0)),
			max_break_s=float((cleanup_settings or {}).get('internMaxBreak', 3.0)),
			scan_window_s=float((cleanup_settings or {}).get('internScanWindow', 12.0)),
		)
		_beep_file_raw = (cleanup_settings or {}).get('censorBeepFile')
		try:
			if _beep_file_raw is not None and not isinstance(_beep_file_raw, (str, Path)):
				_beep_file_raw = str(_beep_file_raw)
		except Exception:
			_beep_file_raw = None
		censor_cfg = clean_engine.CensorSettings(
			enabled=bool((cleanup_settings or {}).get('censorEnabled', False)),
			words=list((cleanup_settings or {}).get('censorWords', ["fuck", "shit"])) if isinstance((cleanup_settings or {}).get('censorWords', None), list) else ["fuck", "shit"],
			fuzzy=bool((cleanup_settings or {}).get('censorFuzzy', True)),
			match_threshold=float((cleanup_settings or {}).get('censorMatchThreshold', 0.8)),
			beep_ms=int((cleanup_settings or {}).get('censorBeepMs', 250)),
			beep_freq_hz=int((cleanup_settings or {}).get('censorBeepFreq', 1000)),
			beep_gain_db=float((cleanup_settings or {}).get('censorBeepGainDb', 0.0)),
			beep_file=(Path(_beep_file_raw) if isinstance(_beep_file_raw, (str, Path)) and str(_beep_file_raw).strip() else None),
		)
		try:
			bf = getattr(censor_cfg, 'beep_file', None)
			if isinstance(bf, (str, Path)):
				bf_path = Path(str(bf))
				if not bf_path.is_absolute() and not bf_path.exists():
					cand1 = (PROJECT_ROOT / 'media_uploads' / bf_path.name)
					cand2 = (PROJECT_ROOT / bf_path)
					if cand1.exists():
						censor_cfg.beep_file = cand1
					elif cand2.exists():
						censor_cfg.beep_file = cand2
		except Exception:
			pass

		# Build SFX trigger map
		sfx_map = {}
		try:
			q = select(MediaItem).where(MediaItem.user_id == episode.user_id)
			items = session.exec(q).all()
			for it in items:
				key = (it.trigger_keyword or '').strip().lower()
				if key:
					sfx_map[key] = PROJECT_ROOT / 'media_uploads' / it.filename
		except Exception:
			sfx_map = {}

		# Lightweight synth for Intern VO
		def _synth(text: str) -> AudioSegment:
			try:
				return ai_enhancer.generate_speech_from_text(
					text,
					voice_id=str((tts_values or {}).get("intern_voice_id") or ""),
					api_key=getattr(user_obj, 'elevenlabs_api_key', None),
					provider=preferred_tts_provider,
				)
			except Exception:
				return AudioSegment.silent(duration=800)

		# Intents
		intents = intents or {}
		flubber_intent = str((intents.get('flubber') if isinstance(intents, dict) else '') or '').lower()
		intern_intent = str((intents.get('intern') if isinstance(intents, dict) else '') or '').lower()
		sfx_intent = str((intents.get('sfx') if isinstance(intents, dict) else '') or '').lower()
		censor_intent = str((intents.get('censor') if isinstance(intents, dict) else '') or '').lower()
		logging.info(f"[assemble] intents: flubber={flubber_intent or 'unset'} intern={intern_intent or 'unset'} sfx={sfx_intent or 'unset'} censor={censor_intent or 'unset'}")
		if flubber_intent == 'no':
			cuts_ms = None
		if intern_intent == 'no':
			try:
				ins = clean_engine.InternSettings(min_break_s=ins.min_break_s, max_break_s=ins.max_break_s, scan_window_s=0.0)
			except Exception:
				pass
		if sfx_intent == 'no':
			sfx_map = None
		try:
			if censor_intent == 'no':
				setattr(censor_cfg, 'enabled', False)
			elif censor_intent == 'yes':
				setattr(censor_cfg, 'enabled', True)
		except Exception:
			pass

		# Run clean engine if transcript exists; else precut
		engine_result = None
		cleaned_path = None
		if words_json_path and Path(words_json_path).is_file():
			try:
				_stem = Path(base_audio_name).stem
				_out_stem = _stem if _stem.startswith('cleaned_') else f"cleaned_{_stem}"
				_engine_out = f"{_out_stem}.mp3"
			except Exception:
				_engine_out = f"cleaned_{Path(base_audio_name).stem}.mp3"
			engine_result = clean_engine.run_all(
				audio_path=source_audio_path,
				words_json_path=words_json_path,
				work_dir=PROJECT_ROOT,
				user_settings=us,
				silence_cfg=ss,
				intern_cfg=ins,
				censor_cfg=censor_cfg,
				sfx_map=sfx_map if sfx_map else None,
				synth=_synth,
				flubber_cuts_ms=cuts_ms,
				output_name=_engine_out,
				disable_intern_insertion=True,
			)
			cleaned_path = engine_result.get('final_path')
			try:
				edits = (((engine_result or {}).get('summary', {}) or {}).get('edits', {}) or {})
				spans = edits.get('censor_spans_ms', [])
				mode = edits.get('censor_mode', {})
				logging.info(f"[assemble] engine censor_enabled={bool(getattr(censor_cfg,'enabled', False))} spans={len(spans)} mode={mode} final={cleaned_path}")
			except Exception:
				pass
		else:
			try:
				logging.warning(
					f"[assemble] words.json not found for stems={base_stems} in {', '.join(str(d) for d in search_dirs)}; skipping clean_engine."
				)
				if cuts_ms and isinstance(cuts_ms, list) and len(cuts_ms) > 0:
					src_path = (_resolve_media_file(base_audio_name) or (PROJECT_ROOT / 'media_uploads' / Path(str(base_audio_name)).name)).resolve()
					if src_path.is_file():
						audio = AudioSegment.from_file(src_path)
						precut = apply_flubber_cuts(audio, cuts_ms)
						out_dir = (PROJECT_ROOT / 'cleaned_audio')
						out_dir.mkdir(parents=True, exist_ok=True)
						precut_name = f"precut_{Path(base_audio_name).stem}.mp3"
						precut_path = out_dir / precut_name
						precut.export(precut_path, format='mp3')
						# Mirror the precut audio into canonical MEDIA_DIR so downstream orchestrator can load it
						dest = MEDIA_DIR / precut_path.name
						try:
							shutil.copyfile(precut_path, dest)
						except Exception:
							logging.warning("[assemble] Failed to copy precut audio to MEDIA_DIR; mixer may not find it", exc_info=True)
						try:
							episode.working_audio_name = dest.name if dest.exists() else precut_path.name
							session.add(episode)
							session.commit()
						except Exception:
							session.rollback()
						base_audio_name = (episode.working_audio_name or precut_path.name)
						logging.info(f"[assemble] applied {len(cuts_ms)} flubber cuts without words.json; working_audio_name={episode.working_audio_name}")
					else:
						logging.warning(f"[assemble] base audio not found for precut: {src_path}")
			except Exception:
				logging.warning("[assemble] precut stage failed; proceeding with original audio (no flubber cuts)", exc_info=True)

		# Persist pointers to final transcript
		try:
			_final_words = None
			if engine_result:
				try:
					_final_words = (
						(engine_result or {}).get('summary', {})
						.get('edits', {})
						.get('words_json')
					)
				except Exception:
					_final_words = None
			if not _final_words and (episode.working_audio_name or '').startswith('precut_'):
				try:
					_fn = str(episode.working_audio_name or '')
					if _fn:
						words_list2 = trans.get_word_timestamps(_fn)
						tr_dir2 = PROJECT_ROOT / 'transcripts'
						tr_dir2.mkdir(parents=True, exist_ok=True)
						out2 = tr_dir2 / f"{Path(_fn).stem}.json"
						import json as _json
						with open(out2, 'w', encoding='utf-8') as fh:
							_json.dump(words_list2, fh)
						# legacy mirror
						try:
							legacy2 = tr_dir2 / f"{Path(_fn).stem}.words.json"
							if not legacy2.exists():
								shutil.copyfile(out2, legacy2)
						except Exception:
							pass
						_final_words = str(out2)
						logging.info(f"[assemble] generated final transcript for precut audio: {out2}")
				except Exception:
					logging.warning("[assemble] Failed to generate final transcript for precut audio", exc_info=True)
			if _final_words:
				try:
					import json as _json
					meta = _json.loads(getattr(episode, 'meta_json', '{}') or '{}') if getattr(episode, 'meta_json', None) else {}
					ts = meta.get('transcripts') or {}
					ts['final'] = os.path.basename(_final_words)
					meta['transcripts'] = ts
					episode.meta_json = _json.dumps(meta)
					session.add(episode)
					session.commit()
				except Exception:
					session.rollback()
		except Exception:
			logging.warning("[assemble] Failed final transcript persist block", exc_info=True)

		# Choose words for mixer-only phase:
		try:
			_engine_words = (
				(engine_result or {}).get('summary', {})
				.get('edits', {})
				.get('words_json')
			) if engine_result else None
			words_json_for_mixer = None
			candidate_stems = []
			try:
				_out_stem_raw = Path(output_filename).stem
				candidate_stems.append(_out_stem_raw)
				candidate_stems.append(sanitize_filename(_out_stem_raw))
			except Exception:
				pass
			try:
				candidate_stems.append(Path(base_audio_name).stem)
			except Exception:
				pass
			try:
				candidate_stems.append(sanitize_filename(Path(base_audio_name).stem))
			except Exception:
				pass
			candidate_stems = [s for s in dict.fromkeys([s for s in candidate_stems if s])]
			for d in search_dirs:
				for s in candidate_stems:
					cand = d / f"{s}.original.json"
					if cand.is_file():
						words_json_for_mixer = cand
						break
				if words_json_for_mixer:
					break
			if not words_json_for_mixer:
				if _engine_words and Path(_engine_words).is_file():
					words_json_for_mixer = Path(_engine_words)
				else:
					words_json_for_mixer = Path(words_json_path) if words_json_path else None
			words_json_path = words_json_for_mixer
			logging.info("[assemble] mixer words selected: %s", str(words_json_path) if words_json_path else 'None')
		except Exception:
			pass

		# Mirror cleaned audio into MEDIA_DIR (canonical source for orchestrator)
		if cleaned_path:
			try:
				src = Path(cleaned_path)
				dest = MEDIA_DIR / src.name
				dest.parent.mkdir(parents=True, exist_ok=True)
				try:
					shutil.copyfile(src, dest)
					logging.info(f"[assemble] Copied cleaned audio to MEDIA_DIR: {dest}")
				except Exception:
					logging.warning("[assemble] Failed to copy cleaned audio to MEDIA_DIR; mixer may not find it", exc_info=True)
				episode.working_audio_name = dest.name
				session.add(episode)
				session.commit()
			except Exception:
				session.rollback()

		# Ensure the base audio exists under MEDIA_DIR for orchestrator lookup (copy if necessary)
		try:
			if source_audio_path and source_audio_path.exists():
				target = MEDIA_DIR / source_audio_path.name
				if not target.exists():
					shutil.copyfile(source_audio_path, target)
					logging.info(f"[assemble] mirrored base audio into MEDIA_DIR: {target}")
		except Exception:
			logging.warning("[assemble] Failed to mirror base audio into MEDIA_DIR", exc_info=True)

		# Phase 2: mixer-only
		try:
			import json as _json
			_raw_settings = getattr(user_obj, 'audio_cleanup_settings_json', None)
			_parsed_settings = _json.loads(_raw_settings) if _raw_settings else {}
		except Exception:
			_parsed_settings = {}
		_user_commands = (_parsed_settings or {}).get('commands') or {}
		try:
			_defaults_cmds = {
				"flubber": {"action": "rollback_restart", "trigger_keyword": "flubber"},
				"intern": {
					"action": "ai_command",
					"trigger_keyword": str(((_parsed_settings or {}).get('internKeyword') or 'intern') or 'intern'),
					"end_markers": ["stop", "stop intern"],
					"remove_end_marker": True,
					"keep_command_token_in_transcript": True,
				},
			}
			if isinstance(_user_commands, dict):
				_user_commands = {**_defaults_cmds, **_user_commands}
			else:
				_user_commands = _defaults_cmds
		except Exception:
			pass
		_user_filler_words = (_parsed_settings or {}).get('fillerWords') or []
		mixer_only_opts = {
			"removeFillers": False,
			"removePauses": False,
			"fillerWords": _user_filler_words if isinstance(_user_filler_words, list) else [],
			"commands": _user_commands if isinstance(_user_commands, dict) else {},
		}
		try:
			logging.info(f"[assemble] mix-only commands keys={list((mixer_only_opts.get('commands') or {}).keys())}")
		except Exception:
			pass
		stream_log_path = str(ASSEMBLY_LOG_DIR / f"{episode.id}.log")
		final_path, log, ai_note_additions = audio_processor.process_and_assemble_episode(
			template=template,
			main_content_filename=episode.working_audio_name or main_content_filename,
			output_filename=output_filename,
			cleanup_options={**mixer_only_opts, "internIntent": intern_intent, "flubberIntent": flubber_intent},
			tts_overrides=tts_values or {},
			cover_image_path=cover_image_path,
			elevenlabs_api_key=getattr(user_obj, 'elevenlabs_api_key', None),
			tts_provider=preferred_tts_provider,
			mix_only=True,
			words_json_path=str(words_json_path) if words_json_path else None,
			log_path=stream_log_path,
		)
		logging.info("[assemble] processor invoked: mix_only=True words_json=%s", str(words_json_path) if words_json_path else 'None')

		# Mark episode processed
		try:
			from api.models.podcast import EpisodeStatus as _EpStatus
			episode.status = _EpStatus.processed  # type: ignore[attr-defined]
		except Exception:
			episode.status = "processed"  # type: ignore[assignment]

		if ai_note_additions:
			existing = episode.show_notes or ""
			combined = existing + ("\n\n" if existing else "") + "\n\n".join(ai_note_additions)
			episode.show_notes = combined
			logging.info(f"[assemble] Added {len(ai_note_additions)} AI shownote additions")

		episode.final_audio_path = os.path.basename(str(final_path))
		if cover_image_path and not getattr(episode, "cover_path", None):
			episode.cover_path = Path(cover_image_path).name

		session.add(episode)
		session.commit()
		logging.info(f"[assemble] done. final={final_path}")

		try:
			note = Notification(user_id=episode.user_id, type="assembly", title="Episode assembled", body=f"{episode.title}")
			session.add(note)
			session.commit()
		except Exception:
			logging.warning("[assemble] Failed to create notification", exc_info=True)

		try:
			if isinstance(log, list):
				max_entries = 800
				max_len = 4000
				trimmed_for_disk = []
				for entry in log[:max_entries]:
					if isinstance(entry, str) and len(entry) > max_len:
						trimmed_for_disk.append(entry[:max_len] + "...(truncated)")
					else:
						trimmed_for_disk.append(entry)
				log_path = ASSEMBLY_LOG_DIR / f"{episode.id}.log"
				with open(log_path, "w", encoding="utf-8") as fh:
					for line in trimmed_for_disk:
						try:
							fh.write(line.replace("\n", " ") + "\n")
						except Exception:
							pass
		except Exception:
			logging.warning("[assemble] Failed to persist assembly log", exc_info=True)

		try:
			main_fn = os.path.basename(str(main_content_filename))
			q = select(MediaItem).where(MediaItem.filename == main_fn, MediaItem.user_id == episode.user_id)
			media_item = session.exec(q).first()
			if media_item and media_item.category == MediaCategory.main_content:
				media_path = Path('media_uploads') / media_item.filename
				if media_path.is_file():
					try:
						media_path.unlink()
					except Exception:
						logging.warning(f"[cleanup] Unable to unlink file {media_path}")
				session.delete(media_item)
				session.commit()
				logging.info(f"[cleanup] Removed main content source {media_item.filename} after assembly")
		except Exception:
			logging.warning("[cleanup] Failed to remove main content media item", exc_info=True)

		return {"message": "Episode assembled successfully!", "episode_id": episode.id}
	except Exception as e:
		logging.exception(f"Error during episode assembly for {output_filename}: {e}")
		try:
			episode = crud.get_episode_by_id(session, UUID(episode_id))
			if episode:
				try:
					from api.models.podcast import EpisodeStatus as _EpStatus
					episode.status = _EpStatus.error  # type: ignore[attr-defined]
				except Exception:
					episode.status = "error"  # type: ignore[assignment]
				session.add(episode)
				session.commit()
		except Exception:
			pass
		raise
	finally:
		session.close()

