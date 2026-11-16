"""A cancelled request must not freeze daphne's event loop (asgiref < 3.13).

Django wraps each request in ThreadSensitiveContext. When daphne kills a slow
request whose sync thread later hops back to the loop (async_to_sync from sync
middleware or on_commit group_send), asgiref 3.11's __aexit__ joined that
thread on the loop itself and deadlocked the whole process.
"""

import subprocess
import sys
import textwrap

from django.test import SimpleTestCase

SCENARIO = textwrap.dedent(
    """
    import asyncio
    import time

    from asgiref.sync import ThreadSensitiveContext, async_to_sync, sync_to_async


    async def inner() -> str:
        return "ok"


    def slow_request() -> str:
        time.sleep(0.5)
        return async_to_sync(inner)()


    async def request() -> None:
        async with ThreadSensitiveContext():
            await sync_to_async(slow_request, thread_sensitive=True)()


    async def main() -> None:
        task = asyncio.create_task(request())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.wait_for(asyncio.sleep(0), timeout=2)
        print("loop alive")


    asyncio.run(main())
    """
)


class AsgiCancelDeadlockTest(SimpleTestCase):
    def test_cancelled_request_does_not_block_event_loop(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, "-c", SCENARIO],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            self.fail("event loop deadlocked joining a cancelled request's thread")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("loop alive", result.stdout)
