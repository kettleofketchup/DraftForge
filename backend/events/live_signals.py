"""Domain notification for event writes that bypass Django's model signals."""

from django.dispatch import Signal

# Send alongside the database write, before its transaction commits. Receivers
# may mark durable work pending, but must not publish a task or call Discord.
event_data_changed = Signal()
