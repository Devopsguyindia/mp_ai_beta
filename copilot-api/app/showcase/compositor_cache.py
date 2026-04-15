from __future__ import annotations

import os
from collections import OrderedDict


class CompositorPreviewCache:
    """
    In-memory LRU of composited PNG bytes keyed by render cache_key.
    Not suitable for multi-worker production; replace with Redis/S3 later.
    """

    def __init__(self, *, max_entries: int) -> None:
        self._max = max(1, max_entries)
        self._data: OrderedDict[str, bytes] = OrderedDict()

    def get(self, key: str) -> bytes | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: str, value: bytes) -> None:
        if key in self._data:
            del self._data[key]
        self._data[key] = value
        while len(self._data) > self._max:
            self._data.popitem(last=False)


_global_cache: CompositorPreviewCache | None = None


def get_compositor_cache() -> CompositorPreviewCache:
    global _global_cache
    if _global_cache is None:
        n = int(os.getenv("SHOWCASE_COMPOSITOR_CACHE_MAX_ENTRIES", "64"))
        _global_cache = CompositorPreviewCache(max_entries=max(1, n))
    return _global_cache


def reset_compositor_cache_for_tests() -> None:
    global _global_cache
    _global_cache = None
