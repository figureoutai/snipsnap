import asyncio

class UniqueAsyncQueue(asyncio.Queue):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._items = set()
        self._lock = asyncio.Lock()

    async def put(self, item):
        async with self._lock:
            if item not in self._items:
                await super().put(item)
                self._items.add(item)

    async def get(self):
        item = await super().get()
        async with self._lock:
            self._items.remove(item)
        return item
    
    def put_nowait(self, item):
        if item not in self._items:
            self._items.add(item)
            super().put_nowait(item)
