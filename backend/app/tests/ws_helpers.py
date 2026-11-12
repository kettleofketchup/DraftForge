"""Frame-reading helpers for team-draft consumer tests (1 Hz pings are always in flight).

`receive_output(timeout=...)` cancels the application on timeout, so these
helpers time out on the output queue directly and leave the socket running.
"""

import asyncio
import json
import time
from typing import Any

from channels.testing import WebsocketCommunicator


async def _next_output(comm: WebsocketCommunicator, timeout: float) -> dict[str, Any]:
    if comm.future.done():
        comm.future.result()
    return await asyncio.wait_for(comm.output_queue.get(), timeout=max(timeout, 0.001))


async def _next_json(comm: WebsocketCommunicator, timeout: float) -> dict[str, Any]:
    output = await _next_output(comm, timeout)
    assert output["type"] == "websocket.send", output
    return json.loads(output["text"])


async def read_until_type(
    comm: WebsocketCommunicator, wanted: str, timeout: float = 5
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        try:
            frame = await _next_json(comm, deadline - time.monotonic())
        except asyncio.TimeoutError:
            raise AssertionError(f"timed out waiting for frame type {wanted!r}") from None
        if frame.get("type") == wanted:
            return frame


async def next_non_ping_output(
    comm: WebsocketCommunicator, timeout: float = 5
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        output = await _next_output(comm, deadline - time.monotonic())
        if output.get("type") == "websocket.send" and output.get("text"):
            if json.loads(output["text"]).get("type") == "ping":
                continue
        return output


async def assert_no_frame_except_ping(
    comm: WebsocketCommunicator, timeout: float = 0.5
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            frame = await _next_json(comm, deadline - time.monotonic())
        except asyncio.TimeoutError:
            return
        if frame.get("type") != "ping":
            raise AssertionError(f"unexpected frame {frame['type']}")
