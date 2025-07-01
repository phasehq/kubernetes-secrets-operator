import os
import json
import time
from typing import Dict, Optional

from utils.const import TOKEN_CACHE_DIR

def get_cache_file_path(service_account_id: str) -> str:
    return os.path.join(TOKEN_CACHE_DIR, f"{service_account_id}.json")

def get_cached_token(service_account_id: str) -> Optional[Dict]:
    cache_file = get_cache_file_path(service_account_id)
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cache = json.load(f)
            if time.time() < cache.get('expiry', 0):
                return cache
    return None

def update_cached_token(service_account_id: str, token_data: Dict):
    os.makedirs(TOKEN_CACHE_DIR, exist_ok=True)
    cache_file = get_cache_file_path(service_account_id)
    with open(cache_file, 'w') as f:
        json.dump(token_data, f)
