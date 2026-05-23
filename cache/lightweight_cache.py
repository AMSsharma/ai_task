import time
from typing import Any, Optional, Dict


class LightweightCache:
    """
    A simple in-memory TTL (Time-To-Live) cache for storing temporary data.
    Entries automatically expire after the specified TTL duration.
    """

    def __init__(self):
        self.store: Dict[str, dict] = {}

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache if it exists and hasn't expired.
        
        Args:
            key: The cache key
            
        Returns:
            The cached value if found and not expired, None otherwise
        """
        if key not in self.store:
            return None

        entry = self.store[key]
        
        # Check if the entry has expired
        if entry["expires_at"] < time.time():
            del self.store[key]
            return None

        return entry["value"]

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """
        Store a value in the cache with a TTL.
        
        Args:
            key: The cache key
            value: The value to cache (should be JSON-serializable)
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self.store[key] = {
            "value": value,
            "expires_at": time.time() + ttl
        }

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self.store.clear()

    def cleanup_expired(self) -> None:
        """Remove all expired entries from the cache."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.store.items()
            if entry["expires_at"] < current_time
        ]
        for key in expired_keys:
            del self.store[key]


# Global cache instance
cache = LightweightCache()
