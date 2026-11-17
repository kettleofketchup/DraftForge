"""On-demand diagnostics for a live backend process."""

import faulthandler
import io
import signal
import sys


def install_thread_dump_handler() -> bool:
    """Dump every thread's Python stack to stderr on SIGUSR1.

    faulthandler's handler runs in C, so it still fires when the event loop
    or the GIL holder is stuck. Daphne/Twisted only claim SIGINT, SIGTERM,
    SIGBREAK and SIGCHLD. Operator procedure: docs/architecture/docker.md.
    """
    sigusr1 = getattr(signal, "SIGUSR1", None)
    if sigusr1 is None:
        return False
    try:
        faulthandler.register(sigusr1, file=sys.stderr, all_threads=True, chain=False)
    except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
        # stderr without a real fd (captured by a test runner, closed)
        return False
    return True
