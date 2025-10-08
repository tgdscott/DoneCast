#!/usr/bin/env python3
"""Check templates for background music configuration"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from sqlmodel import Session, create_engine, select
from api.models.podcast import PodcastTemplate, Episode
import json

# Connect to local dev database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.db")
engine = create_engine(DATABASE_URL, echo=False)

def check_templates():
    """Check all templates for music configuration"""
    with Session(engine) as session:
        templates = session.exec(select(PodcastTemplate)).all()
        
        print(f"\n{'='*80}")
        print(f"Found {len(templates)} templates")
        print(f"{'='*80}\n")
        
        for template in templates:
            print(f"Template: {template.name} (ID: {template.id})")
            print(f"  User ID: {template.user_id}")
            print(f"  Podcast ID: {template.podcast_id}")
            print(f"  Active: {template.is_active}")
            
            # Parse segments
            try:
                segments = json.loads(template.segments_json)
                print(f"  Segments: {len(segments)}")
                for i, seg in enumerate(segments):
                    seg_type = seg.get('segment_type', 'unknown')
                    print(f"    [{i}] type='{seg_type}'")
            except Exception as e:
                print(f"  ⚠️  Error parsing segments: {e}")
            
            # Parse music rules
            try:
                music_rules = json.loads(template.background_music_rules_json)
                print(f"  Background Music Rules: {len(music_rules)}")
                
                if len(music_rules) == 0:
                    print(f"    ⚠️  NO MUSIC RULES CONFIGURED")
                else:
                    for i, rule in enumerate(music_rules):
                        print(f"    [{i}] file='{rule.get('music_filename', 'N/A')}'")
                        print(f"        apply_to={rule.get('apply_to_segments', [])}")
                        print(f"        volume_db={rule.get('volume_db', 'N/A')}")
                        print(f"        fade_in_s={rule.get('fade_in_s', 'N/A')}")
                        print(f"        fade_out_s={rule.get('fade_out_s', 'N/A')}")
            except Exception as e:
                print(f"  ⚠️  Error parsing music rules: {e}")
            
            print()

def check_recent_episodes():
    """Check recent episodes for template usage"""
    with Session(engine) as session:
        episodes = session.exec(
            select(Episode)
            .order_by(Episode.created_at.desc())
            .limit(5)
        ).all()
        
        print(f"\n{'='*80}")
        print(f"Last 5 Episodes")
        print(f"{'='*80}\n")
        
        for episode in episodes:
            print(f"Episode: {episode.title or 'Untitled'} (ID: {episode.id})")
            print(f"  Status: {episode.status}")
            print(f"  Template ID: {episode.template_id}")
            print(f"  Created: {episode.created_at}")
            
            if episode.template_id:
                template = session.get(PodcastTemplate, episode.template_id)
                if template:
                    try:
                        music_rules = json.loads(template.background_music_rules_json)
                        print(f"  Template Music Rules: {len(music_rules)}")
                        if len(music_rules) > 0:
                            print(f"    ✅ Music configured")
                        else:
                            print(f"    ⚠️  NO MUSIC RULES")
                    except Exception as e:
                        print(f"    ⚠️  Error: {e}")
            print()

if __name__ == "__main__":
    print("\n🔍 TEMPLATE MUSIC DIAGNOSTIC TOOL")
    check_templates()
    check_recent_episodes()
    
    print("\n" + "="*80)
    print("NEXT STEPS:")
    print("="*80)
    print("""
If templates show NO MUSIC RULES:
  → Music settings are not being saved from the frontend
  → Check browser console for errors when saving template
  → Check network tab to verify music rules are in the PUT request

If templates HAVE music rules but episodes don't play music:
  → Check Cloud Run logs for [MUSIC_RULE_*] messages
  → Look for [MUSIC_RULE_NO_MATCH] or [MUSIC_RULE_SKIP]
  → Verify segment_type matches apply_to_segments
    """)
