import json
import os
from typing import Any, Dict, List, Tuple, Optional

import requests


class SpreakerClient:
    """
    Minimal, stable client used by our API for:
      - listing shows for the authenticated user
      - uploading an episode (kept as-is, but not changed in this patch)
    """

    BASE_URL = "https://api.spreaker.com/v2"

    def _get_paginated(self, path: str, params: Optional[Dict[str, Any]] = None, items_key: str = "items") -> Tuple[bool, Any]:
        """
        Helper to fetch all pages for endpoints that return a next_url and accumulate results.
        Returns (ok, {items: [...], ...other keys...})
        """
        try:
            url = f"{self.BASE_URL}{path}"
            all_items = []
            extra = {}
            while url:
                r = self.session.get(url, params=params if url.endswith(path) else None, timeout=30)
                if r.status_code // 100 != 2:
                    # Try to parse error from response wrapper
                    try:
                        data = r.json()
                        err = data.get("response", {}).get("error") or data.get("error") or r.text
                        return False, err
                    except Exception:
                        return False, r.text
                data = r.json()
                resp = data.get("response", data)
                items = resp.get(items_key, [])
                if isinstance(items, list):
                    all_items.extend(items)
                # Copy extra keys from first page
                if not extra:
                    for k, v in resp.items():
                        if k != items_key:
                            extra[k] = v
                next_url = resp.get("next_url")
                url = next_url if next_url else None
                params = None  # Only send params on first request
            return True, {items_key: all_items, **extra}
        except Exception as e:
            return False, str(e)

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.session = requests.Session()
        # Ensure API understands we want JSON
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        try:
            r = self.session.get(f"{self.BASE_URL}{path}", params=params, timeout=30)
            if r.status_code // 100 != 2:
                return False, f"GET {path} -> {r.status_code}: {r.text}"
            data = r.json()
            return True, data.get("response", data)
        except Exception as e:
            return False, str(e)

    def _post(self, path: str, data: Dict[str, Any], files: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        try:
            r = self.session.post(f"{self.BASE_URL}{path}", data=data, files=files, timeout=120)
            if r.status_code // 100 != 2:
                return False, f"POST {path} -> {r.status_code}: {r.text}"
            data = r.json()
            return True, data.get("response", data)
        except Exception as e:
            return False, str(e)

    def _put(self, path: str, data: Dict[str, Any], files: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        """Fallback PUT helper (some Spreaker endpoints may expect PUT semantics)."""
        try:
            r = self.session.put(f"{self.BASE_URL}{path}", data=data, files=files, timeout=120)
            if r.status_code // 100 != 2:
                return False, f"PUT {path} -> {r.status_code}: {r.text}"
            data = r.json()
            return True, data.get("response", data)
        except Exception as e:
            return False, str(e)

    def update_show_image(self, show_id: str, image_file_path: str) -> Tuple[bool, Any]:
        if not os.path.isfile(image_file_path):
            return False, f"image file not found: {image_file_path}"
        # Choose MIME type based on extension; default to image/png
        ext = os.path.splitext(image_file_path)[1].lower()
        mime = "image/png"
        if ext in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif ext in {".webp"}:
            mime = "image/webp"
        files = {
            "image_file": (os.path.basename(image_file_path), open(image_file_path, "rb"), mime),
        }
        ok, resp = self._post(f"/shows/{show_id}", data={}, files=files)
        for f in files.values():
            try:
                f[1].close()
            except Exception:
                pass
        return ok, resp

    def update_show_metadata(self, show_id: str, *, title: Optional[str] = None, description: Optional[str] = None,
                              language: Optional[str] = None, author_name: Optional[str] = None,
                              owner_name: Optional[str] = None, email: Optional[str] = None,
                              copyright_line: Optional[str] = None, category_id: Optional[int] = None,
                              category_2_id: Optional[int] = None, category_3_id: Optional[int] = None,
                              episode_sorting: Optional[str] = None, website_url: Optional[str] = None,
                              twitter_name: Optional[str] = None, show_type: Optional[str] = None) -> Tuple[bool, Any]:
        """Update show textual metadata on Spreaker.
        Only sends fields that are provided (non-None).
        Spreaker field mapping assumptions (may need adjustment if API differs):
          - title
          - description
          - language (2-letter or IETF code as accepted by Spreaker)
          - author (maps from author_name)
          - owner (maps from owner_name)
          - email
          - copyright
          - type (Episodic/Serial) -> ensure correct casing
        """
        data: Dict[str, Any] = {}
        if title is not None: data["title"] = title
        if description is not None: data["description"] = description
        if language is not None: data["language"] = language
        if author_name is not None: data["author_name"] = author_name
        if owner_name is not None: data["owner_name"] = owner_name
        if email is not None: data["email"] = email
        if copyright_line is not None: data["copyright"] = copyright_line
        if category_id is not None: data["category_id"] = category_id
        if category_2_id is not None: data["category_2_id"] = category_2_id
        if category_3_id is not None: data["category_3_id"] = category_3_id
        if episode_sorting is not None: data["episode_sorting"] = episode_sorting
        if website_url is not None: data["website_url"] = website_url
        if twitter_name is not None: data["twitter_name"] = twitter_name
        if show_type is not None:
            st = show_type.lower()
            if st in ("episodic","serial"):
                # Use lowercase if API expects raw, adjust if capitalized required
                data["type"] = st
        if not data:
            return True, {"skipped": "no fields to update"}
        ok, resp = self._post(f"/shows/{show_id}", data=data, files=None)
        return ok, resp

    def get_episode(self, episode_id: str) -> Tuple[bool, Any]:
        return self._get(f"/episodes/{episode_id}")

    def get_show(self, show_id: str) -> Tuple[bool, Any]:
        """Fetch a show's details (including RSS url if provided by Spreaker).
        Returns (ok, response_dict_or_error)."""
        return self._get(f"/shows/{show_id}")

    def get_all_episodes_for_show(self, show_id: str) -> Tuple[bool, Any]:
        """
        Fetches all episodes for a given show, handling pagination.
        """
        return self._get_paginated(f"/shows/{show_id}/episodes", params={"limit": 100}, items_key="items")

    def create_show(self, *, title: str, description: str = "", language: str = "en") -> Tuple[bool, Any]:
        """Create a new show on Spreaker.

        Spreaker API expects at minimum a title; description & language optional.
        Returns (ok, {"show_id": str, ...raw show object fields...}) on success OR (False, error_message).
        """
        data = {
            "title": title,
        }
        if description:
            data["description"] = description
        if language:
            data["language"] = language
        ok, resp = self._post("/shows", data=data, files=None)
        if not ok:
            return False, resp
        show = resp.get("show") or resp
        show_id = show.get("show_id") if isinstance(show, dict) else None
        if not show_id:
            return False, f"Unexpected create_show response: {resp}"
        out = {"show_id": show_id, **show}
        return True, out

    # ------------ Public API ------------

    def get_shows(self) -> Tuple[bool, Any]:
        """
        Returns (ok, shows_or_error)
        Each item has at least: show_id, title; on failure returns error text.
        """
        ok, me = self._get("/me")
        if not ok:
            return False, f"/me error: {me}"
        user = me.get("user")
        if not user or "user_id" not in user:
            return False, "No user_id in /me response"

        user_id = user["user_id"]
        ok, shows_resp = self._get(f"/users/{user_id}/shows", params={"limit": 100})
        if not ok:
            return False, f"/users/{user_id}/shows error: {shows_resp}"

        items = shows_resp.get("items", [])
        # Normalize: ensure show_id is present and title exists
        cleaned = []
        for it in items:
            if "show_id" in it and "title" in it:
                cleaned.append(it)
        return True, cleaned

    # ------------ Analytics helpers (totals endpoints) ------------

    def get_me(self) -> Tuple[bool, Any]:
        """Return the authenticated user object with user_id."""
        return self._get("/me")

    def get_user_id(self) -> Optional[str]:
        ok, me = self.get_me()
        if not ok:
            return None
        try:
            return str((me or {}).get("user", {}).get("user_id"))
        except Exception:
            return None

    def get_user_shows_plays_totals(self, user_id: str, params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        """GET /v2/users/{USER-ID}/shows/statistics/plays/totals
        Returns provider-shaped JSON; caller must normalize.
        Optional params may include date window (from/to) if supported.
        """
        return self._get(f"/users/{user_id}/shows/statistics/plays/totals", params=params)

    def get_show_episodes_plays_totals(self, show_id: str, params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        """GET /v2/shows/{SHOW-ID}/episodes/statistics/plays/totals
        Returns per-episode totals for a show; follows pagination if present.
        """
        return self._get_paginated(f"/shows/{show_id}/episodes/statistics/plays/totals", params=params, items_key="items")

    def upload_episode(
        self,
        show_id: str,
        title: str,
        file_path: str,
        description: Optional[str] = None,
        publish_state: Optional[str] = None,   # 'unpublished'|'public'|'limited'
        auto_published_at: Optional[str] = None,
        image_file: Optional[str] = None,
        tags: Optional[str] = None,
        explicit: Optional[bool] = None,
        transcript_url: Optional[str] = None,
        season_number: Optional[int] = None,
        episode_number: Optional[int] = None,
    ) -> Tuple[bool, Any]:
        """Upload an episode to Spreaker with robust fallbacks.

        Tries multiple field variants for visibility and scheduling since Spreaker’s
        documentation and behavior can vary by account or API version.
        Returns (ok, {episode_id}) or (False, diagnostics).
        """
        if not os.path.isfile(file_path):
            return False, f"media file not found: {file_path}"

        # Build static fields
        base_data: Dict[str, Any] = {"title": title}
        if description:
            base_data["description"] = description
        if tags:
            base_data["tags"] = tags
        if explicit is not None:
            base_data["explicit"] = "true" if explicit else "false"
        if transcript_url:
            base_data["transcript_url"] = transcript_url
        if season_number is not None:
            try:
                base_data["season_number"] = int(season_number)
            except (TypeError, ValueError):
                pass
        if episode_number is not None:
            try:
                base_data["episode_number"] = int(episode_number)
            except (TypeError, ValueError):
                pass

        # Visibility variants
        vis_from_state = "PUBLIC"
        if str(publish_state).lower() in {"unpublished", "private"}:
            vis_from_state = "PRIVATE"
        elif str(publish_state).lower() in {"limited"}:
            vis_from_state = "LIMITED"
        visibility_variants: List[Dict[str, Any]] = [
            {"visibility": vis_from_state},
            # Some tenants still accept publish_state instead of visibility
            {"publish_state": publish_state or ("unpublished" if vis_from_state == "PRIVATE" else "public")},
            # Lowercase visibility fallback
            {"visibility": vis_from_state.lower()},
        ]

        # Scheduling variants
        schedule_variants: List[Dict[str, Any]] = []
        if auto_published_at:
            schedule_variants = [
                {"auto_published_at": auto_published_at},
                {"publish_at": auto_published_at},
            ]
        else:
            schedule_variants = [{}]

        # Prepare files with dynamic image MIME and reusable audio handle
        attempts: List[Dict[str, Any]] = []
        audio_fh = open(file_path, "rb")
        try:
            file_tuples_base: Dict[str, Any] = {
                "media_file": (os.path.basename(file_path), audio_fh, "audio/mpeg"),
            }
            if image_file and os.path.isfile(image_file):
                ext = os.path.splitext(image_file)[1].lower()
                mime = "image/png" if ext not in {".jpg", ".jpeg", ".webp"} else ("image/jpeg" if ext in {".jpg", ".jpeg"} else "image/webp")
                img_fh = open(image_file, "rb")
                file_tuples_base["image_file"] = (os.path.basename(image_file), img_fh, mime)

            success_resp: Optional[Dict[str, Any]] = None
            ok_overall = False
            for vis in visibility_variants:
                for sched in schedule_variants:
                    # rewind audio file
                    try:
                        audio_fh.seek(0)
                    except Exception:
                        pass
                    files = dict(file_tuples_base)
                    # if image handle present, rewind
                    if "image_file" in files:
                        try:
                            files["image_file"][1].seek(0)
                        except Exception:
                            pass
                    data = {**base_data, **vis, **sched}
                    ok_try, resp_try = self._post(f"/shows/{show_id}/episodes", data=data, files=files)
                    rec: Dict[str, Any] = {"ok": ok_try, "data_keys": list(data.keys()), "resp_type": type(resp_try).__name__}
                    if not ok_try and isinstance(resp_try, str):
                        rec["error"] = resp_try[:400]
                    attempts.append(rec)
                    if ok_try:
                        # Expect resp like {"episode": {...}}
                        ep = resp_try.get("episode") if isinstance(resp_try, dict) else None
                        if ep and ep.get("episode_id"):
                            success_resp = {"episode_id": ep.get("episode_id")}
                            ok_overall = True
                            break
                if ok_overall:
                    break
        finally:
            try:
                audio_fh.close()
            except Exception:
                pass
            # Close image handle if opened
            try:
                if 'file_tuples_base' in locals() and isinstance(file_tuples_base.get('image_file'), tuple):
                    file_tuples_base['image_file'][1].close()
            except Exception:
                pass

        if not ok_overall or not success_resp:
            return False, {"attempts": attempts}
        return True, success_resp

    def update_episode(
        self,
        episode_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        publish_state: Optional[str] = None,
        tags: Optional[str] = None,
        explicit: Optional[bool] = None,
        image_file: Optional[str] = None,
        transcript_url: Optional[str] = None,
        debug_try_all: bool = False,
        force_all_fields: bool = False,
        season_number: Optional[int] = None,
        episode_number: Optional[int] = None,
    ) -> Tuple[bool, Any]:
        """Update existing episode metadata on Spreaker.

        Spreaker API (pattern inferred from show update) appears to accept POST /episodes/{id} with form fields.
        Only sends fields that are provided. publish_state maps to visibility like in upload.
        """
        data: Dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if tags is not None:
            data["tags"] = tags
        if explicit is not None:
            data["explicit"] = explicit
        if publish_state is not None:
            if publish_state == "unpublished":
                data["visibility"] = "PRIVATE"
            elif publish_state == "limited":
                data["visibility"] = "LIMITED"
            else:
                data["visibility"] = "PUBLIC"
        if transcript_url is not None:
            data["transcript_url"] = transcript_url
        if season_number is not None:
            try:
                data["season_number"] = int(season_number)
            except (TypeError, ValueError):
                pass
        if episode_number is not None:
            try:
                data["episode_number"] = int(episode_number)
            except (TypeError, ValueError):
                pass
        files = None
        fh = None
        if image_file and os.path.isfile(image_file):
            ext = os.path.splitext(image_file)[1].lower()
            mime = "image/png" if ext not in {".jpg", ".jpeg", ".webp"} else ("image/jpeg" if ext in {".jpg", ".jpeg"} else "image/webp")
            fh = open(image_file, "rb")
            files = {"image_file": (os.path.basename(image_file), fh, mime)}
        # Env override for always-on debug attempt mode
        if not debug_try_all and os.getenv("SPREAKER_DEBUG_ALL") == "1":
            debug_try_all = True
        # Endpoint/method discovery: Spreaker docs for updating episodes aren't public; attempt a sequence.
        attempts: List[Dict[str, Any]] = []
        endpoint_variants = [
            ("POST", f"/episodes/{episode_id}"),
            ("PUT", f"/episodes/{episode_id}"),
            ("POST", f"/episodes/{episode_id}/update"),
            ("POST", f"/episode/{episode_id}"),  # singular fallback
            ("PUT", f"/episodes/{episode_id}/update"),
        ]

        def perform(method: str, path: str):
            if method == "POST":
                return self._post(path, data=data, files=files)
            return self._put(path, data=data, files=files)

        # Pre-change snapshot (for verification) only if we intend to modify textual fields.
        verify_fields = {k: v for k, v in {"title": title, "description": description}.items() if v is not None}
        if force_all_fields and not verify_fields:
            # still allow verification on title/description if forcing but they weren't passed explicitly
            ok_pre_force, snap_force = self.get_episode(str(episode_id))
            if ok_pre_force and isinstance(snap_force, dict):
                epf = snap_force.get("episode") or snap_force
                # nothing to compare; skip verification
                verify_fields = {}
        pre_snapshot = None
        if verify_fields:
            ok_pre, snap = self.get_episode(str(episode_id))
            if ok_pre and isinstance(snap, dict):
                pre_snapshot = snap.get("episode") or snap

        success_resp = None
        success = False
        first_success_index: Optional[int] = None
        for idx, (method, path) in enumerate(endpoint_variants):
            # Ensure file handle rewound for each attempt if present
            if fh and not fh.closed:
                try:
                    fh.seek(0)
                except Exception:
                    pass
            ok_try, resp_try = perform(method, path)
            attempt_rec: Dict[str, Any] = {"method": method, "path": path, "ok": ok_try, "resp_type": type(resp_try).__name__}
            if not ok_try:
                # include truncated error text for diagnostics
                if isinstance(resp_try, str):
                    attempt_rec["error"] = resp_try[:300]
                attempts.append(attempt_rec)
                continue
            # success path
            if first_success_index is None:
                first_success_index = idx
                success_resp = resp_try
            # verification only done for first success to keep request count bounded
            verified = False
            if verify_fields:
                ok_after, after = self.get_episode(str(episode_id))
                if ok_after and isinstance(after, dict):
                    ep_after = after.get("episode") or after
                    verified = True
                    for f, desired in verify_fields.items():
                        if ep_after.get(f) != desired:
                            verified = False
                            break
            else:
                verified = True  # nothing to verify
            attempt_rec["verified"] = verified
            attempts.append(attempt_rec)
            if verified and not debug_try_all:
                success = True
                break
            # if debug_try_all, continue gathering attempts across remaining variants
        if first_success_index is not None and not success:
            # treat first success as overall success even if later variants failed or verification failed (debug mode)
            success = True
        if not success:
            # Provide aggregated attempt data for diagnostics
            diag = {"attempts": attempts, "pre_snapshot": bool(pre_snapshot)}
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
            return False, diag

        if fh:
            try:
                fh.close()
            except Exception:
                pass
        # Attach attempt trace to success for transparency
        if isinstance(success_resp, dict):
            success_resp = {**success_resp, "_attempts": attempts, "_attempt_strategy": "all" if debug_try_all else "first_success"}
        return True, success_resp

    def update_episode_image(self, episode_id: str, image_file: str, debug_try_all: bool = False) -> Tuple[bool, Any]:
        """Attempt dedicated image update endpoints for episodes (heuristic)."""
        if not os.path.isfile(image_file):
            return False, f"image file not found: {image_file}"
        attempts: List[Dict[str, Any]] = []
        fh = open(image_file, 'rb')
        files_tpl = (os.path.basename(image_file), fh, 'image/png')
        variant_paths = [
            ("POST", f"/episodes/{episode_id}") ,  # already tried in main path, but include for correlation
            ("PUT", f"/episodes/{episode_id}"),
            ("POST", f"/episodes/{episode_id}/image"),
            ("PUT", f"/episodes/{episode_id}/image"),
            ("POST", f"/episodes/{episode_id}/cover"),
            ("PUT", f"/episodes/{episode_id}/cover"),
        ]
        success = False
        success_resp: Any = None
        for idx, (method, path) in enumerate(variant_paths):
            try:
                fh.seek(0)
            except Exception:
                pass
            files = {"image_file": files_tpl}
            if method == 'POST':
                ok_try, resp_try = self._post(path, data={}, files=files)
            else:
                ok_try, resp_try = self._put(path, data={}, files=files)
            rec = {"method": method, "path": path, "ok": ok_try, "resp_type": type(resp_try).__name__}
            if not ok_try and isinstance(resp_try, str):
                rec['error'] = resp_try[:300]
            attempts.append(rec)
            if ok_try and not debug_try_all:
                success = True
                success_resp = resp_try
                break
            if ok_try:
                success = True
                success_resp = resp_try
        try:
            fh.close()
        except Exception:
            pass
        if not success:
            return False, {"attempts": attempts}
        if isinstance(success_resp, dict):
            success_resp = {**success_resp, "_image_attempts": attempts}
        else:
            success_resp = {"raw": success_resp, "_image_attempts": attempts}
        return True, success_resp
