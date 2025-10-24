"""
OP3 Historical Data Parser

Parses TSV exports from public OP3 to provide historical fallback data
during transition to self-hosted instance.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to the TSV file (relative to project root)
# __file__ = .../backend/api/services/op3_historical_data.py
# parent.parent.parent.parent = project root
TSV_PATH = Path(__file__).parent.parent.parent.parent / "cinema-irl-episode-downloads.tsv"


class OP3HistoricalData:
    """Parses and provides access to historical OP3 data from TSV export."""
    
    def __init__(self, tsv_path: Optional[Path] = None):
        self.tsv_path = tsv_path or TSV_PATH
        self._data: Dict[str, Dict] = {}
        self._loaded = False
    
    def _load_data(self):
        """Load TSV data into memory cache."""
        if self._loaded:
            return
        
        if not self.tsv_path.exists():
            logger.warning(f"Historical TSV not found at {self.tsv_path}")
            self._loaded = True
            return
        
        try:
            with open(self.tsv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    episode_title = row.get('episode_title', '').strip()
                    if episode_title:
                        # Parse download counts (may be empty strings)
                        downloads_3d = int(row['downloads_3_day']) if row.get('downloads_3_day') else 0
                        downloads_7d = int(row['downloads_7_day']) if row.get('downloads_7_day') else 0
                        downloads_30d = int(row['downloads_30_day']) if row.get('downloads_30_day') else 0
                        downloads_all = int(row['downloads_all_time']) if row.get('downloads_all_time') else 0
                        
                        # Fix bad data: 30d must be >= 7d (use 7d if 30d is missing/zero)
                        if downloads_30d < downloads_7d:
                            downloads_30d = downloads_7d
                        
                        # Fix bad data: all-time must be >= 30d
                        if downloads_all < downloads_30d:
                            downloads_all = downloads_30d
                        
                        self._data[episode_title] = {
                            'pub_date': row.get('episode_pub_date', ''),
                            'downloads_3d': downloads_3d,
                            'downloads_7d': downloads_7d,
                            'downloads_30d': downloads_30d,
                            'downloads_all': downloads_all,
                            'as_of': row.get('downloads_asof', '')
                        }
            
            logger.info(f"Loaded {len(self._data)} historical episode records from TSV")
            self._loaded = True
        
        except Exception as e:
            logger.error(f"Failed to load historical TSV: {e}", exc_info=True)
            self._loaded = True
    
    def get_episode_downloads(self, episode_title: str) -> Optional[Dict]:
        """
        Get historical download stats for an episode by title.
        
        Returns dict with keys: downloads_3d, downloads_7d, downloads_30d, downloads_all, pub_date, as_of
        """
        if not self._loaded:
            self._load_data()
        
        return self._data.get(episode_title)
    
    def get_all_episodes(self) -> List[Dict]:
        """Get all historical episode data as a list."""
        if not self._loaded:
            self._load_data()
        
        return [
            {'episode_title': title, **stats}
            for title, stats in self._data.items()
        ]
    
    def get_total_downloads(self, days: Optional[int] = None) -> int:
        """
        Get total downloads across all episodes.
        
        Args:
            days: If specified, return downloads for that period (3, 7, 30, or None for all-time)
        """
        if not self._loaded:
            self._load_data()
        
        if days == 3:
            key = 'downloads_3d'
        elif days == 7:
            key = 'downloads_7d'
        elif days == 30:
            key = 'downloads_30d'
        else:
            key = 'downloads_all'
        
        return sum(stats.get(key, 0) for stats in self._data.values())
    
    def get_top_episodes(self, limit: int = 5, days: Optional[int] = None) -> List[Dict]:
        """
        Get top episodes by download count.
        
        Args:
            limit: Maximum number of episodes to return
            days: If specified, sort by downloads for that period (7, 30, or None for all-time)
        
        Returns:
            List of dicts with episode_title and download count
        """
        if not self._loaded:
            self._load_data()
        
        if days == 7:
            key = 'downloads_7d'
        elif days == 30:
            key = 'downloads_30d'
        else:
            key = 'downloads_all'
        
        # Sort by download count for the specified period
        episodes = [
            {
                'episode_title': title,
                'downloads': stats.get(key, 0),
                'pub_date': stats.get('pub_date', '')
            }
            for title, stats in self._data.items()
        ]
        
        # Sort by downloads (descending) then by pub_date (descending for recency)
        episodes.sort(key=lambda x: (x['downloads'], x['pub_date']), reverse=True)
        
        return episodes[:limit]


# Singleton instance
_historical_data = OP3HistoricalData()


def get_historical_data() -> OP3HistoricalData:
    """Get the singleton historical data instance."""
    return _historical_data
