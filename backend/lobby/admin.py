from django.contrib import admin
from django.http import HttpRequest

from lobby.models import GameLobby, GameLobbyEvent


@admin.register(GameLobby)
class GameLobbyAdmin(admin.ModelAdmin):
    """Mostly read-only: the lobby's lifecycle belongs to dota_lobby."""

    list_display = (
        "external_ref",
        "lobby_id",
        "game",
        "state",
        "trigger",
        "bot",
        "match_id",
        "last_error_code",
        "created_at",
    )
    list_filter = ("state", "ended", "trigger")
    search_fields = ("external_ref", "lobby_id", "gc_lobby_id", "bot")
    raw_id_fields = (
        "game",
        "requested_by",
        "radiant_team",
        "dire_team",
        "provisional_winner_team",
    )
    # Lifecycle fields mirror dota_lobby and only its events and the reconcile
    # task may change them. Editing `state` here would also recompute `ended`
    # behind the form's back and could break lobby_one_active_per_game.
    readonly_fields = (
        "external_ref",
        "lobby_id",
        "state",
        "state_reason",
        "ended",
        "last_seq",
        "created_at",
        "updated_at",
        "accepted_at",
        "ended_at",
        "password_key_id",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Lobbies are created through dota_lobby, never by hand.
        return False


@admin.register(GameLobbyEvent)
class GameLobbyEventAdmin(admin.ModelAdmin):
    """Read-only: events are what dota_lobby sent, kept for auditing."""

    list_display = ("event_id", "lobby", "seq", "type", "source", "occurred_at")
    list_filter = ("type", "source")
    search_fields = ("event_id", "lobby__lobby_id", "lobby__external_ref")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: GameLobbyEvent | None = None
    ) -> bool:
        return False
