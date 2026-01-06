from rest_framework import serializers

from .constants import LEAGUE_ID
from .models import Match, PlayerMatchStats


class PlayerMatchStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerMatchStats
        exclude = ["match"]  # Exclude the direct link to the match to avoid redundancy


class MatchSerializer(serializers.ModelSerializer):
    players = PlayerMatchStatsSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = "__all__"


# =============================================================================
# Request Serializers
# =============================================================================


class SyncLeagueRequestSerializer(serializers.Serializer):
    """Request serializer for league sync endpoint."""

    league_id = serializers.IntegerField(required=False, default=LEAGUE_ID)
    full_sync = serializers.BooleanField(required=False, default=False)


class FindMatchesByPlayersSerializer(serializers.Serializer):
    """Request serializer for finding matches by player steam IDs."""

    steam_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of Steam IDs to search for",
    )
    require_all = serializers.BooleanField(
        required=False,
        default=True,
        help_text="If True, all players must be in match. If False, any player.",
    )
    league_id = serializers.IntegerField(
        required=False, help_text="Optional filter to specific league"
    )


class RelinkUsersSerializer(serializers.Serializer):
    """Request serializer for relinking users to match stats."""

    match_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="If empty, relink all matches",
    )


class AutoLinkRequestSerializer(serializers.Serializer):
    """Request serializer for auto-linking tournament matches."""

    tournament_id = serializers.IntegerField(required=True)


class RetryFailedRequestSerializer(serializers.Serializer):
    """Request serializer for retrying failed matches."""

    league_id = serializers.IntegerField(required=False, default=LEAGUE_ID)


# =============================================================================
# Response Serializers
# =============================================================================


class SyncResultSerializer(serializers.Serializer):
    """Response serializer for sync results."""

    synced_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    new_last_match_id = serializers.IntegerField(allow_null=True)


class AutoLinkResultSerializer(serializers.Serializer):
    """Response serializer for auto-link results."""

    auto_linked_count = serializers.IntegerField()
    suggestions_created_count = serializers.IntegerField()


class SyncStatusSerializer(serializers.Serializer):
    """Response serializer for sync status."""

    league_id = serializers.IntegerField()
    last_sync_at = serializers.DateTimeField(allow_null=True)
    last_match_id = serializers.IntegerField(allow_null=True)
    failed_match_count = serializers.IntegerField()
    is_syncing = serializers.BooleanField()


class GameMatchSuggestionSerializer(serializers.Serializer):
    """Response serializer for match suggestions."""

    id = serializers.IntegerField()
    game_id = serializers.IntegerField()
    match_id = serializers.IntegerField(source="match.match_id")
    tournament_id = serializers.IntegerField()
    confidence_score = serializers.FloatField()
    player_overlap = serializers.IntegerField()
    auto_linked = serializers.BooleanField()
    created_at = serializers.DateTimeField()
