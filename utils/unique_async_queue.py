import asyncio
import weakref
from threading import RLock

class UniqueAsyncQueue(asyncio.Queue):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._items = weakref.WeakSet()   # weak references avoid leaks
        self._lock = RLock()              # thread-safe lock

    def put_nowait(self, item):
        with self._lock:
            if item not in self._items:
                self._items.add(item)
                super().put_nowait(item)

    async def put(self, item):
        # coroutine-safe version
        async with asyncio.Lock():
            if item not in self._items:
                await super().put(item)
                self._items.add(item)

    async def get(self):
        item = await super().get()
        with self._lock:
            self._items.discard(item)
        return item