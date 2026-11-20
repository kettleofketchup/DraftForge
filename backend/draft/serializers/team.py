"""Team draft REST serializers."""

from rest_framework import serializers

from app.models import CustomUser, Draft, DraftEvent, DraftRound, Tournament
from app.serializers import (
    DraftRoundSerializerSlim,
    TeamSerializerForTournament,
    TeamSerializerSlim,
    TournamentUserSerializer,
    UserPkField,
    _serialize_user_with_mmr,
)


class DraftPredictMMRSerializer(serializers.Serializer):
    pk = serializers.IntegerField(required=True)


class TournamentSerializerDraft(serializers.ModelSerializer):
    teams = TeamSerializerSlim(many=True, read_only=True)
    users = serializers.SerializerMethodField()

    tournament_type = serializers.CharField(read_only=False)
    captains = UserPkField(many=True, read_only=True)

    def get_users(self, tournament: Tournament) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in tournament.users.all()]

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "teams",
            "captains",
            "tournament_type",
        )


class DraftSerializer(serializers.ModelSerializer):
    tournament = TournamentSerializerDraft(
        many=False,
        read_only=True,
    )
    users_remaining = serializers.SerializerMethodField()

    draft_rounds = DraftRoundSerializerSlim(
        many=True,
        read_only=True,
    )

    def get_users_remaining(self, draft: Draft) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in draft.users_remaining]

    class Meta:
        model = Draft
        fields = (
            "pk",
            "tournament",
            "draft_rounds",
            "draft_style",
            "users_remaining",
            "latest_round",
        )


class DraftSerializerMMRs(serializers.ModelSerializer):
    class Meta:
        model = Draft
        fields = (
            "pk",
            "snake_first_pick_mmr",
            "snake_last_pick_mmr",
            "normal_first_pick_mmr",
            "normal_last_pick_mmr",
        )


class DraftRoundSerializer(serializers.ModelSerializer):
    draft = serializers.PrimaryKeyRelatedField(
        many=False,
        queryset=Draft.objects.all(),
        write_only=True,
        required=False,
    )
    captain = serializers.SerializerMethodField()
    captain_id = serializers.PrimaryKeyRelatedField(
        source="captain",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()
    team = TeamSerializerForTournament(many=False, read_only=True)

    choice = serializers.SerializerMethodField()
    choice_id = serializers.PrimaryKeyRelatedField(
        source="choice",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )

    def get_captain(self, draft_round: DraftRound) -> dict | None:
        return _serialize_user_with_mmr(
            draft_round.captain, draft_round.draft.tournament
        )

    def get_choice(self, draft_round: DraftRound) -> dict | None:
        return _serialize_user_with_mmr(
            draft_round.choice, draft_round.draft.tournament
        )

    class Meta:
        model = DraftRound
        fields = (
            "pk",
            "draft",
            "captain",
            "captain_id",
            "pick_phase",
            "pick_number",
            "choice",
            "choice_id",
            "team",
        )


class DraftEventSerializer(serializers.ModelSerializer):
    actor = TournamentUserSerializer(read_only=True)

    class Meta:
        model = DraftEvent
        fields = (
            "pk",
            "event_type",
            "payload",
            "actor",
            "created_at",
        )
