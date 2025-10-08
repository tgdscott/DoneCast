import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, text
import json

# Use local database
engine = create_engine('sqlite:///database.db')

with engine.connect() as conn:
    print("=== CHECKING RECENT TEMPLATES ===\n")
    result = conn.execute(text(
        "SELECT id, name, background_music_rules_json, segments_json "
        "FROM templates "
        "ORDER BY created_at DESC "
        "LIMIT 3"
    ))
    
    for row in result:
        template_id, name, rules_json, segments_json = row
        print(f"Template: {name}")
        print(f"ID: {template_id}")
        
        # Check music rules
        if rules_json:
            try:
                rules = json.loads(rules_json)
                print(f"Music Rules: {len(rules)} rule(s)")
                for i, rule in enumerate(rules, 1):
                    print(f"  Rule {i}:")
                    print(f"    File: {rule.get('music_filename')}")
                    print(f"    Apply to: {rule.get('apply_to_segments')}")
                    print(f"    Volume: {rule.get('volume_db')} dB")
            except:
                print(f"Music Rules: ERROR parsing JSON")
        else:
            print(f"Music Rules: NONE (empty or null)")
        
        # Check segments
        if segments_json:
            try:
                segments = json.loads(segments_json)
                print(f"Segments: {len(segments)} segment(s)")
                for i, seg in enumerate(segments, 1):
                    seg_type = seg.get('segment_type', 'MISSING')
                    print(f"  Segment {i}: type='{seg_type}'")
            except:
                print(f"Segments: ERROR parsing JSON")
        else:
            print(f"Segments: NONE")
        
        print("---\n")
    
    print("\n=== CHECKING RECENT EPISODES ===\n")
    result = conn.execute(text(
        "SELECT id, title, template_id, status "
        "FROM episodes "
        "ORDER BY created_at DESC "
        "LIMIT 3"
    ))
    
    for row in result:
        episode_id, title, template_id, status = row
        print(f"Episode: {title}")
        print(f"ID: {episode_id}")
        print(f"Template ID: {template_id}")
        print(f"Status: {status}")
        print("---\n")
