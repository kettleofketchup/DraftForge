"""Redis channel layer whose receive locks never cross event loops (#588)."""

import asyncio
import weakref
from typing import Any

from channels_redis.core import ChannelLock, RedisChannelLayer


class CancelSafeChannelLock(ChannelLock):
    """ChannelLock that undoes its wait count when a waiting acquire is cancelled.

    channels_redis 4.3.0 leaves the count raised, so the lock is never dropped
    and stays bound to the loop it waited on.
    """

    async def acquire(self, channel: str) -> bool:
        self.wait_counts[channel] += 1
        try:
            return await self.locks[channel].acquire()
        except BaseException:
            self.wait_counts[channel] -= 1
            if self.wait_counts[channel] < 1:
                del self.locks[channel]
                del self.wait_counts[channel]
            raise


class PerLoopChannelLock:
    """One ChannelLock per running loop; the layer itself is cached process-wide."""

    def __init__(self) -> None:
        self._by_loop: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, CancelSafeChannelLock
        ] = weakref.WeakKeyDictionary()

    def _current(self) -> CancelSafeChannelLock:
        loop = asyncio.get_running_loop()
        locks = self._by_loop.get(loop)
        if locks is None:
            locks = self._by_loop[loop] = CancelSafeChannelLock()
        return locks

    async def acquire(self, channel: str) -> bool:
        return await self._current().acquire(channel)

    def locked(self, channel: str) -> bool:
        return self._current().locked(channel)

    def release(self, channel: str) -> None:
        self._current().release(channel)


class LoopSafeRedisChannelLayer(RedisChannelLayer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.receive_clean_locks = PerLoopChannelLock()
