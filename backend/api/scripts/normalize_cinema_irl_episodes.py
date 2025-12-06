"""One-off script to normalize Cinema IRL episode titles and numbering.

Preferred usage (from repo root, venv activated):

    python backend/api/scripts/normalize_cinema_irl_episodes.py --dry-run
    python backend/api/scripts/normalize_cinema_irl_episodes.py --commit

This will:
- Target only episodes for the Cinema IRL podcast
- For titles like "Episode 12 - The Strangers Chapter 1", set:
    - episode_number = 12 (if missing)
    - season_number = 1 if n < 92 else 2
    - title = "E12 - The Strangers Chapter 1"
- For titles already starting with "E<number> - ...", leave title unchanged
    but still backfill season_number/episode_number if missing.
"""

import os
import sys
import argparse
import re
from typing import Tuple

from sqlmodel import Session, select

from api.core.database import engine
from api.models.episode import Episode
from api.models.podcast_models import Podcast


CURRENT_FILE = os.path.abspath(__file__)
BACKEND_DIR = os.path.dirname(os.path.dirname(CURRENT_FILE))  # .../backend
REPO_ROOT = os.path.dirname(BACKEND_DIR)

for path in (BACKEND_DIR, REPO_ROOT):
        if path not in sys.path:
                sys.path.insert(0, path)


CINEMA_IRL_TITLE = "Cinema IRL"


EPISODE_PREFIX_RE = re.compile(r"^Episode\s+(\d+)\s*-\s*(.+)$", re.IGNORECASE)
E_PREFIX_RE = re.compile(r"^E(\d+)\s*-\s*(.+)$")


def season_for_episode_number(n: int) -> int:
    """Return season number for a given absolute episode number.

    Per user: Season 2 started with Episode 92, so:
    - 1–91   => season 1
    - 92+    => season 2
    """
    if n >= 92:
        return 2
    return 1


def extract_number_and_rest_from_title(title: str) -> Tuple[int | None, str | None, str]:
    """Attempt to extract the numeric episode index and remainder of title.

    Returns (number, rest, mode) where mode is one of:
    - "episode_prefix"  (from "Episode N - ...")
    - "e_prefix"        (from "E<N> - ...")
    - "none"            (no match)
    """
    m = EPISODE_PREFIX_RE.match(title.strip())
    if m:
        num = int(m.group(1))
        rest = m.group(2).strip()
        return num, rest, "episode_prefix"

    m = E_PREFIX_RE.match(title.strip())
    if m:
        num = int(m.group(1))
        rest = m.group(2).strip()
        return num, rest, "e_prefix"

    return None, None, "none"


def normalize_episode(ep: Episode, dry_run: bool = True) -> bool:
    """Normalize a single episode.

    Returns True if any changes would be made.
    """
    original_title = ep.title or ""
    number, rest, mode = extract_number_and_rest_from_title(original_title)

    changed = False

    if number is not None:
        # Backfill episode_number if missing
        if ep.episode_number is None:
            ep.episode_number = number
            changed = True

        # Backfill season_number if missing
        if ep.season_number is None:
            ep.season_number = season_for_episode_number(number)
            changed = True

        # Only rewrite title if it was in "Episode N - ..." format
        if mode == "episode_prefix" and rest is not None:
            new_title = f"E{number} - {rest}"
            if new_title != original_title:
                ep.title = new_title
                changed = True

    # If no number parsed but numbering fields are missing, we do nothing

    if changed:
        print(f"[CHANGE]{' (dry-run)' if dry_run else ''} {ep.id} :: '{original_title}' -> '{ep.title}' | S={ep.season_number} E={ep.episode_number}")

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Cinema IRL episode titles and numbering")
    parser.add_argument("--commit", action="store_true", help="Apply changes to the database (otherwise dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run even if --commit is provided")
    args = parser.parse_args()

    dry_run = not args.commit or args.dry_run

    with Session(engine) as session:
        # Find the Cinema IRL podcast(s)
        podcasts = session.exec(
            select(Podcast).where(Podcast.title == CINEMA_IRL_TITLE)
        ).all()

        if not podcasts:
            print(f"No podcast found with title '{CINEMA_IRL_TITLE}'.")
            return

        if len(podcasts) > 1:
            print(f"WARNING: Found {len(podcasts)} podcasts titled '{CINEMA_IRL_TITLE}'. Updating all of them.")

        podcast_ids = [p.id for p in podcasts]

        episodes = session.exec(
            select(Episode).where(Episode.podcast_id.in_(podcast_ids))
        ).all()

        print(f"Found {len(episodes)} episodes for Cinema IRL.")

        total_changed = 0

        for ep in episodes:
            if normalize_episode(ep, dry_run=dry_run):
                total_changed += 1

        print(f"Total episodes with changes: {total_changed}")

        if not dry_run and total_changed > 0:
            session.commit()
            print("Changes committed.")
        else:
            print("Dry-run mode; no changes committed.")


if __name__ == "__main__":
    main()
