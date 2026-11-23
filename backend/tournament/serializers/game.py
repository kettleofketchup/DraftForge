from rest_framework import serializers

from app.models import Game, Team, Tournament
from app.serializers import TournamentUserSerializer
from tournament.serializers.team import TeamSerializerForTournament, TeamSerializerSlim


class GameSerializerForTournament(serializers.ModelSerializer):
    """Used inside TournamentSerializer which provides _users dict."""

    dire_team = TeamSerializerSlim(many=False, read_only=True)
    radiant_team = TeamSerializerSlim(many=False, read_only=True)
    winning_team = TeamSerializerSlim(many=False, read_only=True)
    herodraft_id = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj: Game) -> int | None:
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

    class Meta:
        model = Game

        fields = (
            "pk",
            "radiant_team",
            "dire_team",
            "gameid",
            "round",
            "winning_team",
            "herodraft_id",
        )


class GameSerializer(serializers.ModelSerializer):
    tournament_id = serializers.PrimaryKeyRelatedField(
        source="tournament",
        many=False,
        queryset=Tournament.objects.all(),
        write_only=True,
        required=False,
    )
    dire_team = TeamSerializerForTournament(many=False, read_only=True)
    radiant_team = TeamSerializerForTournament(many=False, read_only=True)
    radiant_team_id = serializers.PrimaryKeyRelatedField(
        source="radiant_team",
        many=False,
        queryset=Team.objects.all(),
        write_only=True,
        required=False,
    )
    dire_team_id = radiant_team_id = serializers.PrimaryKeyRelatedField(
        source="dire_team",
        many=False,
        queryset=Team.objects.all(),
        write_only=True,
        required=False,
    )

    winning_team = TeamSerializerForTournament(many=False, read_only=True)
    winning_team_id = serializers.PrimaryKeyRelatedField(
        source="winning_team",
        many=False,
        queryset=Team.objects.all(),
        write_only=True,
        required=False,
    )
    herodraft_id = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj: Game) -> int | None:
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

    class Meta:
        model = Game

        fields = (
            "pk",
            "tournament_id",
            "radiant_team",
            "radiant_team_id",
            "dire_team",
            "dire_team_id",
            "gameid",
            "round",
            "winning_team",
            "winning_team_id",
            "herodraft_id",
        )


class BracketGameSerializer(serializers.ModelSerializer):
    """Serializer for bracket view with full team details."""

    radiant_team = TeamSerializerForTournament(read_only=True)
    dire_team = TeamSerializerForTournament(read_only=True)
    winning_team = TeamSerializerForTournament(read_only=True)
    herodraft_id = serializers.SerializerMethodField()
    lobby_state = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj: Game) -> int | None:
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

    def get_lobby_state(self, obj: Game) -> str | None:
        """State of the game's latest dota_lobby lobby, or None. No password.

        get_bracket prefetches the lobbies into `latest_lobbies`; other
        callers serialize one game and query it.
        """
        lobbies = getattr(obj, "latest_lobbies", None)
        if lobbies is not None:
            return lobbies[0].state if lobbies else None
        return obj.lobbies.values_list("state", flat=True).first()

    class Meta:
        model = Game
        fields = (
            "pk",
            "round",
            "position",
            "bracket_type",
            "elimination_type",
            "radiant_team",
            "dire_team",
            "winning_team",
            "status",
            "next_game",
            "next_game_slot",
            "loser_next_game",
            "loser_next_game_slot",
            "swiss_record_wins",
            "swiss_record_losses",
            "gameid",
            "herodraft_id",
            "lobby_state",
        )


class BracketSaveSerializer(serializers.Serializer):
    """Serializer for saving bracket structure."""

    matches = serializers.ListField(
        child=serializers.DictField(), help_text="List of match objects to save"
    )


class BracketGenerateSerializer(serializers.Serializer):
    """Serializer for generating bracket."""

    seeding_method = serializers.ChoiceField(
        choices=["random", "mmr_total", "captain_mmr"], default="mmr_total"
    )


class LeagueMatchSerializer(serializers.ModelSerializer):
    """Serializer for matches in a league context with captain info."""

    radiant_captain = TournamentUserSerializer(
        source="radiant_team.captain", read_only=True, allow_null=True
    )
    dire_captain = TournamentUserSerializer(
        source="dire_team.captain", read_only=True, allow_null=True
    )
    radiant_team_name = serializers.CharField(
        source="radiant_team.name", read_only=True, allow_null=True
    )
    dire_team_name = serializers.CharField(
        source="dire_team.name", read_only=True, allow_null=True
    )
    tournament_name = serializers.CharField(
        source="tournament.name", read_only=True, allow_null=True
    )
    tournament_pk = serializers.IntegerField(
        source="tournament.pk", read_only=True, allow_null=True
    )
    date_played = serializers.DateTimeField(
        source="tournament.date_played", read_only=True, allow_null=True
    )

    class Meta:
        model = Game
        fields = [
            "pk",
            "tournament_pk",
            "tournament_name",
            "round",
            "date_played",
            "radiant_team",
            "dire_team",
            "radiant_team_name",
            "dire_team_name",
            "radiant_captain",
            "dire_captain",
            "winning_team",
            "gameid",
        ]
