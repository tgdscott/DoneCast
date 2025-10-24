import sys
sys.path.insert(0, 'backend')

from api.services.op3_historical_data import get_historical_data

h = get_historical_data()
episodes = h.get_all_episodes()

print(f'Total episodes: {len(episodes)}')
print(f'\nTotal 7d: {sum(ep["downloads_7d"] for ep in episodes)}')
print(f'Total 30d: {sum(ep["downloads_30d"] for ep in episodes)}')
print(f'Total all-time: {sum(ep["downloads_all"] for ep in episodes)}')

print('\n7d method:', h.get_total_downloads(7))
print('30d method:', h.get_total_downloads(30))
print('All-time method:', h.get_total_downloads())

print('\n\nTop 5 all-time episodes:')
top_episodes = sorted(episodes, key=lambda x: x['downloads_all'], reverse=True)[:5]
for ep in top_episodes:
    print(f"  {ep['episode_title']}: {ep['downloads_all']} downloads")

print('\n\n3 Most recent episodes:')
recent_episodes = sorted(episodes, key=lambda x: x['pub_date'], reverse=True)[:3]
for ep in recent_episodes:
    print(f"  {ep['episode_title']} ({ep['pub_date']}): {ep['downloads_all']} downloads")
