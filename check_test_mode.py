#!/usr/bin/env python3
"""Check production test_mode setting."""
import os
import sys

# Set production database connection
os.environ['DATABASE_URL'] = 'postgresql://podcast:wSB6nBYVqRfRKfbwFGrT@/podcast?host=/cloudsql/podcast612:us-west1:podcast-prod'

try:
    from sqlmodel import Session, create_engine, select
    from backend.api.models.settings import AppSetting
    import json
    
    engine = create_engine(os.environ['DATABASE_URL'])
    
    with Session(engine) as session:
        admin_setting = session.get(AppSetting, 'admin_settings')
        
        if admin_setting:
            print(f"Found admin_settings:")
            print(f"  key: {admin_setting.key}")
            print(f"  value_json: {admin_setting.value_json}")
            
            settings = json.loads(admin_setting.value_json or '{}')
            test_mode = settings.get('test_mode')
            
            print(f"\n  test_mode: {test_mode}")
            print(f"  test_mode (bool): {bool(test_mode)}")
            
            if test_mode:
                print("\n⚠️  TEST MODE IS ENABLED IN PRODUCTION!")
                print("   This prefixes all episode filenames with 'test'")
                print("   To disable: UPDATE appsetting SET value_json = '{\"test_mode\": false}' WHERE key = 'admin_settings';")
        else:
            print("No admin_settings record found (test_mode defaults to False)")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
