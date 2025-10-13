#!/usr/bin/env python3
"""
Migrate audio files from Spreaker to GCS.

Usage:
  # Dry run (first 5 episodes)
  python migrate_spreaker.py --podcast cinema-irl --user-id b6d5f77e-699e-444b-a31a-e1b4cb15feb4 --limit 5
  
  # Live migration (first 10 episodes)
  python migrate_spreaker.py --podcast cinema-irl --user-id b6d5f77e-699e-444b-a31a-e1b4cb15feb4 --limit 10 --live
  
  # Full migration with failures skipped
  python migrate_spreaker.py --podcast cinema-irl --user-id b6d5f77e-699e-444b-a31a-e1b4cb15feb4 --live --skip-failures
"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

import subprocess
import argparse
import time
import requests
from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode, Podcast


def get_audio_url(spreaker_id):
    """Get audio download URL from Spreaker API."""
    try:
        url = f"https://api.spreaker.com/v2/episodes/{spreaker_id}"
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data['response']['episode'].get('download_url')
    except:
        pass
    return None


def download(url, path):
    """Download file to local path."""
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def upload(local, gcs):
    """Upload to GCS using gcloud."""
    try:
        result = subprocess.run(
            f'gcloud storage cp "{local}" "{gcs}"',
            shell=True, capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False


def main():
    p = argparse.ArgumentParser(description='Migrate from Spreaker to GCS')
    p.add_argument('--podcast', required=True)
    p.add_argument('--user-id', required=True)
    p.add_argument('--bucket', default='ppp-media-us-west1')
    p.add_argument('--limit', type=int)
    p.add_argument('--skip-failures', action='store_true')
    p.add_argument('--live', action='store_true')
    p.add_argument('--yes', action='store_true', help='Skip confirmation prompt')
    args = p.parse_args()
    
    temp = Path('./temp_migration')
    temp.mkdir(exist_ok=True)
    
    print(f"\n{'='*80}")
    print("SPREAKER MIGRATION")
    print(f"{'='*80}")
    print(f"Podcast: {args.podcast}")
    print(f"Mode: {'LIVE' if args.live else 'DRY RUN'}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print(f"{'='*80}\n")
    
    if args.live and not args.yes:
        confirm = input("Type 'yes' to continue: ")
        if confirm != 'yes':
            return
    
    with Session(engine) as session:
        podcast = session.exec(
            select(Podcast).where(Podcast.slug == args.podcast)
        ).first()
        
        if not podcast:
            print(f"Podcast not found: {args.podcast}")
            return
        
        episodes = list(session.exec(
            select(Episode).where(
                Episode.podcast_id == podcast.id,
                Episode.spreaker_episode_id.isnot(None),
                Episode.gcs_audio_path.is_(None)
            ).order_by(Episode.episode_number.desc().nulls_last())
        ).all())
        
        if args.limit:
            episodes = episodes[:args.limit]
        
        print(f"Episodes to migrate: {len(episodes)}\n")
        
        if not args.live:
            for i, ep in enumerate(episodes[:5], 1):
                print(f"  {i}. Ep {ep.episode_number}: {ep.title}")
            if len(episodes) > 5:
                print(f"  ... and {len(episodes)-5} more")
            print(f"\nAdd --live to perform migration")
            return
    
    success = fail = 0
    start = time.time()
    
    for i, ep in enumerate(episodes, 1):
        print(f"\n[{i}/{len(episodes)}] Ep {ep.episode_number}: {ep.title[:50]}")
        print(f"  Spreaker ID: {ep.spreaker_episode_id}")
        
        url = get_audio_url(ep.spreaker_episode_id)
        if not url:
            print("  Failed to get URL")
            fail += 1
            if not args.skip_failures:
                break
            continue
        
        fname = ep.final_audio_path or f"ep{ep.episode_number}.mp3"
        local = temp / f"{ep.id}_{fname}"
        
        print(f"  Downloading...")
        if not download(url, local):
            print("  Download failed")
            fail += 1
            if not args.skip_failures:
                break
            continue
        
        size = local.stat().st_size
        print(f"  Downloaded: {size/1024/1024:.1f} MB")
        
        gcs = f"gs://{args.bucket}/podcasts/{podcast.slug}/episodes/{ep.id}/audio/{fname}"
        print(f"  Uploading...")
        if not upload(local, gcs):
            print("  Upload failed")
            fail += 1
            if not args.skip_failures:
                break
            continue
        
        with Session(engine) as session:
            db_ep = session.get(Episode, ep.id)
            if db_ep:
                db_ep.gcs_audio_path = gcs
                db_ep.audio_file_size = size
                session.add(db_ep)
                session.commit()
        
        local.unlink()
        success += 1
        
        elapsed = time.time() - start
        remaining = (len(episodes) - i) * (elapsed / i)
        print(f"  ✓ Complete ({success} done, {fail} failed)")
        print(f"  Time: {elapsed/60:.1f}m elapsed, {remaining/60:.1f}m remaining")
    
    print(f"\n{'='*80}")
    print(f"DONE: {success} success, {fail} failed")
    print(f"Time: {(time.time()-start)/60:.1f} minutes")
    print(f"{'='*80}\n")
    
    if success > 0:
        print("Verify: python backend/check_episode_urls.py --podcast cinema-irl")


if __name__ == '__main__':
    main()
