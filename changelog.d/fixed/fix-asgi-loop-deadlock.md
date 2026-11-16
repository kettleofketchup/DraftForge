- Fixed the backend freezing until restarted when a slow request was cancelled
  (client disconnect, then daphne's application close timeout): asgiref 3.11 joined
  the request's still-running thread on the event loop, deadlocking every HTTP and
  WebSocket connection. asgiref is now pinned to >=3.13.0, which joins off the loop.
