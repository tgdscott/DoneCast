#!/usr/bin/env python3
"""
Query helper: fetch Episode 222 and related MediaItem rows.
Usage:
  # activate your venv first
  python scripts\episode_222_report.py --db-url "$env:DATABASE_URL"

The script will print a compact JSON report to stdout.
It reads DB connection from environment variable DATABASE_URL if not provided.
"""
import os
import sys
import json
import argparse

try:
    import psycopg
except Exception:
    print("Missing dependency: psycopg. Install with: pip install psycopg[binary]")
    sys.exit(1)

QUERY_EPISODE_BY_NUMBER = """
SELECT id, title, episode_number, podcast_id, working_audio_name, meta_json, created_at, processed_at
FROM episode
WHERE episode_number = 222
LIMIT 1;
"""

QUERY_MEDIA_BY_EPISODE = """
SELECT id, filename, friendly_name, category, used_in_episode_id, transcript_ready, transcription_error, created_at, expires_at
FROM mediaitem
WHERE used_in_episode_id = %s
ORDER BY created_at DESC;
"""

QUERY_MEDIA_BY_FILENAME_PATTERNS = """
SELECT id, filename, friendly_name, category, used_in_episode_id, transcript_ready, transcription_error, created_at, expires_at
FROM mediaitem
WHERE filename ILIKE ANY (ARRAY[%s]) OR friendly_name ILIKE ANY (ARRAY[%s])
ORDER BY created_at DESC
LIMIT 50;
"""

def run(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db-url', help='Postgres DSN (overrides DATABASE_URL env var)')
    parser.add_argument('--patterns', nargs='*', default=['%cinema%','%222%'], help='Filename/friendly_name patterns to search')
    args = parser.parse_args()

    dsn = args.db_url or os.getenv('DATABASE_URL')
    if not dsn:
        print('No DATABASE_URL provided. Set env var or use --db-url.')
        sys.exit(2)

    try:
        conn = psycopg.connect(dsn)
    except Exception as e:
        print('Failed to connect to DB:', e)
        sys.exit(3)

    try:
        ep = run(conn, QUERY_EPISODE_BY_NUMBER)
        episode = ep[0] if ep else None
        report = {'episode_query': QUERY_EPISODE_BY_NUMBER.strip(), 'episode': episode, 'media_by_episode': [], 'media_by_patterns': []}
        if episode:
            media = run(conn, QUERY_MEDIA_BY_EPISODE, (episode['id'],))
            report['media_by_episode'] = media
        # patterns search
        patterns = args.patterns
        # psycopg expects lists encoded properly; we'll pass as tuple of arrays
        media_pat = run(conn, QUERY_MEDIA_BY_FILENAME_PATTERNS, (patterns, patterns))
        report['media_by_patterns'] = media_pat

        print(json.dumps(report, default=str, indent=2))
    finally:
        conn.close()

if __name__ == '__main__':
    main()
