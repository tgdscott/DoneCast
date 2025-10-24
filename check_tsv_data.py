import csv
from pathlib import Path

p = Path('cinema-irl-episode-downloads.tsv')
data = list(csv.DictReader(open(p, 'r', encoding='utf-8'), delimiter='\t'))

print(f'Total rows: {len(data)}')

total_7d = sum(int(r['downloads_7_day']) if r.get('downloads_7_day') else 0 for r in data)
total_30d = sum(int(r['downloads_30_day']) if r.get('downloads_30_day') else 0 for r in data)

print(f'7d total: {total_7d}')
print(f'30d total: {total_30d}')

print('\nRows where 7d > 30d:')
weird = [r for r in data if (int(r.get('downloads_7_day', 0) or 0) > int(r.get('downloads_30_day', 0) or 0)) and int(r.get('downloads_7_day', 0) or 0) > 0]
print(f'Count: {len(weird)}')
for r in weird[:10]:
    print(f"  {r['episode_title']}: 7d={r['downloads_7_day']}, 30d={r['downloads_30_day']}")

print('\n\nSnapshot date:')
print(f"  As of: {data[0].get('downloads_asof', 'N/A')}")
