"""dota_lobby lobby states, plus the two DraftForge adds before a lobby exists."""

# dota_lobby's states (docs/api/index.md on the service side).
PENDING = "pending"
CREATING = "creating"
WAITING = "waiting"
READY = "ready"
LAUNCHING = "launching"
IN_GAME = "in_game"
POST_GAME = "post_game"
FINISHED = "finished"
FAILED = "failed"
CLOSING = "closing"
CLOSED = "closed"
TIMED_OUT = "timed_out"

# DraftForge-only: the create request is prepared but dota_lobby has not
# accepted it yet, or dota_lobby rejected it before a lobby existed.
REQUESTED = "requested"
ERROR = "error"

# States dota_lobby never leaves.
SERVICE_TERMINAL_STATES = frozenset({FINISHED, FAILED, CLOSED, TIMED_OUT})
# Rows in these states no longer count as a game's active lobby.
ENDED_STATES = SERVICE_TERMINAL_STATES | {ERROR}
