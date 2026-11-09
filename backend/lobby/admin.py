from django.contrib import admin
from django.http import HttpRequest

from lobby.models import GameLobby, GameLobbyEvent


@admin.register(GameLobby)
class GameLobbyAdmin(admin.ModelAdmin):
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
    readonly_fields = ("ended", "created_at", "updated_at")


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
