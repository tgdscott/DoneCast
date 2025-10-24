import csv
from pathlib import Path

data = list(csv.DictReader(open('cinema-irl-episode-downloads.tsv', 'r', encoding='utf-8'), delimiter='\t'))

print(f'TSV snapshot date: {data[0]["downloads_asof"]}')
print(f'Total episodes in TSV: {len(data)}')
print(f'Total all-time downloads in TSV: {sum(int(r.get("downloads_all_time", 0) or 0) for r in data)}')

# Check October 2025 episodes specifically
october_eps = [r for r in data if '2025-10' in r.get('episode_pub_date', '')]
print(f'\nOctober 2025 episodes: {len(october_eps)}')
print(f'October downloads (sum of all-time for Oct episodes): {sum(int(r.get("downloads_all_time", 0) or 0) for r in october_eps)}')

print('\nSample October episodes:')
for ep in october_eps[:5]:
    print(f"  {ep['episode_title']}: {ep.get('downloads_all_time', 0)} downloads")
