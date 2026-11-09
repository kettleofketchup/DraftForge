from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from lobby import services
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

    actions = ("create_new_lobby", "close_lobbies")

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Lobbies are created through dota_lobby, never by hand.
        return False

    @admin.action(description="Create a new lobby for these games (retry)")
    def create_new_lobby(self, request: HttpRequest, queryset: QuerySet) -> None:
        games = {row.game_id: row.game for row in queryset.select_related("game")}
        for game in games.values():
            eligibility = services.queue_create(game, user_id=request.user.pk)
            if eligibility.ok:
                self.message_user(request, f"Lobby requested for game {game.pk}.")
            else:
                self.message_user(
                    request,
                    f"Game {game.pk}: {eligibility.code} {eligibility.details or ''}",
                    level=messages.WARNING,
                )

    @admin.action(description="Close these lobbies (before the match starts)")
    def close_lobbies(self, request: HttpRequest, queryset: QuerySet) -> None:
        closed = skipped = 0
        for row in queryset.filter(ended=False):
            if services.close_lobby(row, "closed_by_staff"):
                closed += 1
            else:
                skipped += 1
        self.message_user(
            request, f"Closed {closed} lobbies; {skipped} already in a match."
        )


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
