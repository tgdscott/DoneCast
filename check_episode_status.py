#!/usr/bin/env python3

import sys
import os
sys.path.append('backend')
os.chdir('backend')

from api.core.database import engine
from sqlalchemy import text
from sqlmodel import Session

def check_episode_status():
    
    episode_id = '62f66e9c-f04f-4550-8cdb-01fa0f2b1c9b'
    
    with Session(engine) as session:
        result = session.execute(text('''
            SELECT 
                id, 
                title, 
                status, 
                final_audio_path, 
                gcs_audio_path,
                created_at,
                processed_at,
                working_audio_name
            FROM episode 
            WHERE id = :episode_id
        '''), {'episode_id': episode_id}).fetchone()
        
        if result:
            print('=== Episode Status ===')
            print(f'ID: {result[0]}')
            print(f'Title: {result[1]}')
            print(f'Status: {result[2]}')
            print(f'Final Audio Path: {result[3]}')
            print(f'GCS Audio Path: {result[4]}')
            print(f'Created At: {result[5]}')
            print(f'Processed At: {result[6]}')
            print(f'Working Audio Name: {result[7]}')
        else:
            print('Episode not found')
            
        # Also check for any recent episodes that might be stuck in processing
        print('\n=== Recent Processing Episodes ===')
        recent_result = session.execute(text('''
            SELECT 
                id, 
                title, 
                status, 
                created_at
            FROM episode 
            WHERE status = 'processing'
            ORDER BY created_at DESC 
            LIMIT 5
        ''')).fetchall()
        
        if recent_result:
            for ep in recent_result:
                print(f'{ep[0]}: {ep[1]} - {ep[2]} - {ep[3]}')
        else:
            print('No episodes currently in processing state')

if __name__ == '__main__':
    check_episode_status()