"""Discord bot's HTTP wrappers around the internal signup API.

The lower-level transport helpers (``_post``, auth handling, generic GETs)
live in ``app.internal_client`` because 30+ other worker/Celery call sites
share them. This package only owns the bot-side signup-flow wrappers.
"""
