import sys
sys.path.insert(0, 'backend')

from api.services.op3_historical_data import get_historical_data

# Force reload
import importlib
import api.services.op3_historical_data
importlib.reload(api.services.op3_historical_data)

h = api.services.op3_historical_data.get_historical_data()

print('Download totals (after data fix):')
print(f'  7d: {h.get_total_downloads(7)}')
print(f'  30d: {h.get_total_downloads(30)}')
print(f'  All-time: {h.get_total_downloads()}')

print('\nTop 3 episodes (all-time):')
top3 = h.get_top_episodes(limit=3, days=None)
for i, ep in enumerate(top3, 1):
    print(f"  {i}. {ep['episode_title']}: {ep['downloads']} downloads")

print('\n3 Most recent episodes:')
all_eps = h.get_all_episodes()
recent = sorted(all_eps, key=lambda x: x['pub_date'], reverse=True)[:3]
for ep in recent:
    print(f"  {ep['episode_title']} ({ep['pub_date']}): {ep['downloads_all']} all-time, {ep['downloads_30d']} 30d")
