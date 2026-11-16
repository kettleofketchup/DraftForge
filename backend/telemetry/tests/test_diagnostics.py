"""SIGUSR1 must dump every thread's stack from a process that loaded backend.asgi."""

import os
import selectors
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CHILD = textwrap.dedent(
    """
    import sys
    import threading

    import backend.asgi  # noqa: F401

    parked = threading.Event()


    def parked_worker() -> None:
        parked.wait()


    threading.Thread(target=parked_worker, daemon=True).start()
    print("ready", flush=True)
    sys.stdin.readline()
    parked.set()
    print("exited cleanly", flush=True)
    """
)


def _read_until(
    proc: subprocess.Popen[bytes], stream: str, marker: bytes, timeout: float
) -> bytes:
    assert proc.stdout is not None and proc.stderr is not None
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
    sel.register(proc.stderr, selectors.EVENT_READ, "stderr")
    buffers: dict[str, bytes] = {"stdout": b"", "stderr": b""}
    deadline = time.monotonic() + timeout
    while marker not in buffers[stream]:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or proc.poll() is not None:
            break
        for key, _ in sel.select(remaining):
            chunk = os.read(key.fileobj.fileno(), 65536)  # type: ignore[union-attr]
            buffers[key.data] += chunk
    sel.close()
    return buffers[stream]


class ThreadDumpSignalTest(SimpleTestCase):
    def test_sigusr1_dumps_all_threads_to_stderr(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", CHILD],
            cwd=Path(settings.BASE_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            startup = _read_until(proc, "stdout", b"ready\n", timeout=60)
            self.assertIn(b"ready\n", startup, startup.decode(errors="replace"))

            proc.send_signal(signal.SIGUSR1)
            dump = _read_until(proc, "stderr", b"parked_worker", timeout=10)
            self.assertIn(b"parked_worker", dump, dump.decode(errors="replace"))

            stdout, stderr = proc.communicate(b"\n", timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

        self.assertEqual(proc.returncode, 0, stderr.decode(errors="replace"))
        self.assertIn(b"exited cleanly", stdout)
