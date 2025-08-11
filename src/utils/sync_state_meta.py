import json
import os
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

"""
Persistent file-based state tracking in source environment that maps to custom resources.
This state tracks the last sync time for each environment.
The state is stored as JSON on /tmp/phase_sync_cache.json path and survives pod restarts.
"""

class SyncStateCache:
    """
    Persistent file-based cache to track the last sync time for each environment.
    Cache key format: "{namespace}:{cr_name}:{cr_uid}"
    """
    
    def __init__(self, cache_file_path: str = "/tmp/phase_sync_cache.json"):
        self.cache_file_path = cache_file_path
        self._ensure_cache_file_exists()
    
    def _ensure_cache_file_exists(self):
        """Ensure the cache file exists and is properly initialized."""
        if not os.path.exists(self.cache_file_path):
            try:
                os.makedirs(os.path.dirname(self.cache_file_path), exist_ok=True)
                self._write_cache({})
                logger.info(f"Created new sync cache file: {self.cache_file_path}")
            except Exception as e:
                logger.error(f"Failed to create cache file {self.cache_file_path}: {e}")
                raise
    
    def _read_cache(self) -> Dict[str, str]:
        """Read cache data from disk."""
        try:
            with open(self.cache_file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Cache file corrupted or missing, reinitializing: {e}")
            self._write_cache({})
            return {}
        except Exception as e:
            logger.error(f"Failed to read cache file: {e}")
            return {}
    
    def _write_cache(self, data: Dict[str, str]):
        """Write cache data to disk."""
        try:
            with open(self.cache_file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write cache file: {e}")
            raise
    
    def get_cache_key(self, namespace: str, cr_name: str, cr_uid: str) -> str:
        """Generate a unique cache key using namespace, CR name, and UID."""
        return f"{namespace}:{cr_name}:{cr_uid}"
    
    def get_last_sync(self, namespace: str, cr_name: str, cr_uid: str) -> Optional[datetime]:
        """Get the last sync timestamp for an environment."""
        key = self.get_cache_key(namespace, cr_name, cr_uid)
        cache_data = self._read_cache()
        timestamp_str = cache_data.get(key)
        if timestamp_str:
            try:
                return datetime.fromisoformat(timestamp_str)
            except ValueError as e:
                logger.warning(f"Invalid timestamp in cache for {key}: {timestamp_str}, error: {e}")
                return None
        return None
    
    def update_sync_time(self, namespace: str, cr_name: str, timestamp: datetime, cr_uid: str):
        """Update the sync timestamp for an environment."""
        key = self.get_cache_key(namespace, cr_name, cr_uid)
        cache_data = self._read_cache()
        
        cache_data[key] = timestamp.isoformat()
        self._write_cache(cache_data)
        logger.debug(f"Updated sync time for {key}: {timestamp}")
    
    def needs_sync(self, namespace: str, cr_name: str, current_timestamp: datetime, cr_uid: str) -> bool:
        """
        Check if an environment needs to be synced based on timestamp comparison.
        Returns True if:
        - No previous sync record exists
        - Current timestamp is newer than last sync
        - CR was deleted and recreated (different UID)
        """
        last_sync = self.get_last_sync(namespace, cr_name, cr_uid)
        
        if last_sync is None:
            logger.info(f"No sync record found for {namespace}:{cr_name}:{cr_uid}, full sync needed")
            return True
        
        needs_sync = current_timestamp > last_sync
        if needs_sync:
            logger.info(f"Environment has been updated ({current_timestamp} > {last_sync})")
        else:
            logger.debug(f"Environment is up to date")
        
        return needs_sync
    
    def clear(self):
        """Clear all cached sync states."""
        self._write_cache({})
        logger.info("Sync state cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """Get statistics about the cache."""
        cache_data = self._read_cache()
        return {
            "total_entries": len(cache_data),
            "cache_file_path": self.cache_file_path,
            "file_exists": os.path.exists(self.cache_file_path)
        }


# Global cache instance
sync_cache = SyncStateCache()
