import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, text
import json

# Use local database
engine = create_engine('sqlite:///database.db')

with engine.connect() as conn:
    print("=== CHECKING TEMPLATES ===\n")
    result = conn.execute(text(
        "SELECT id, name, background_music_rules_json "
        "FROM templates "
        "ORDER BY created_at DESC "
        "LIMIT 3"
    ))
    
    for row in result:
        template_id, name, rules_json = row
        print(f"Template: {name}")
        print(f"ID: {template_id}")
        
        if rules_json:
            try:
                rules = json.loads(rules_json)
                print(f"Music Rules ({len(rules)} rules):")
                for i, rule in enumerate(rules, 1):
                    print(f"  Rule {i}:")
                    print(f"    File: {rule.get('music_filename')}")
                    print(f"    Apply to: {rule.get('apply_to_segments')}")
                    print(f"    Volume: {rule.get('volume_db')} dB")
                    print(f"    Offsets: start={rule.get('start_offset_s')}s, end={rule.get('end_offset_s')}s")
                    print(f"    Fades: in={rule.get('fade_in_s')}s, out={rule.get('fade_out_s')}s")
            except Exception as e:
                print(f"  Error parsing rules: {e}")
        else:
            print("  No music rules")
        
        print("---\n")

    print("\n=== CHECKING EPISODES ===\n")
    result2 = conn.execute(text(
        "SELECT e.id, e.title, e.template_id, t.name as template_name "
        "FROM episodes e "
        "LEFT JOIN templates t ON e.template_id = t.id "
        "ORDER BY e.created_at DESC "
        "LIMIT 5"
    ))
    
    for row in result2:
        episode_id, title, template_id, template_name = row
        print(f"Episode: {title}")
        print(f"  Template: {template_name} (ID: {template_id})")
        print("---\n")
