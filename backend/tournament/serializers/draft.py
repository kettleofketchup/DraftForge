from rest_framework import serializers

from app.serializers import UserPkField
from draft.models import Draft, DraftOptions, DraftRound
from tournament.models import Tournament
from tournament.serializers.team import TeamSerializerForTournament, TeamSerializerSlim
from tournament.serializers.users import serialize_user_with_mmr


def users_remaining_pks(draft: Draft) -> list[int]:
    """``Draft.users_remaining`` pks, taking the exclusions from prefetched rounds/teams."""
    tournament = draft.tournament
    draft_cache = getattr(draft, "_prefetched_objects_cache", {})
    tournament_cache = getattr(tournament, "_prefetched_objects_cache", {})
    if "draft_rounds" not in draft_cache or "teams" not in tournament_cache:
        return [u.pk for u in draft.users_remaining]
    if not tournament.users.exists():
        return []
    teams = tournament.teams.all()
    excluded = (
        {r.choice_id for r in draft.draft_rounds.all() if r.choice_id}
        | {t.captain_id for t in teams if t.captain_id}
        | {m.pk for t in teams for m in t.members.all()}
        | {m.pk for t in teams for m in t.dropin_members.all()}
        | {m.pk for t in teams for m in t.left_members.all()}
    )
    remaining = (
        tournament.users.nocache()
        .exclude(id__in=excluded)
        .exclude(id__in=tournament.draft_locked_user_ids())
        .distinct()
    )
    return [u.pk for u in remaining]


def _shared_draft_options(
    serializer: serializers.BaseSerializer, tournament: Tournament
) -> DraftOptions:
    """``get_draft_options()`` once per tournament for a whole serializer tree.

    Reuses the ``draft_options`` prefetched by tournament_state_queryset (marked
    with ``loaded_uncached``); a fresh context only takes one loaded uncached.
    Any other cached relation may predate a write and is re-read.
    """
    context = serializer.root.context
    memo = context.setdefault("_draft_options", {})
    if tournament.pk not in memo:
        fresh = context.get("fresh", False)
        options = _prefetched_draft_options(tournament)
        loaded_uncached = getattr(options, "loaded_uncached", None)
        if loaded_uncached is None or (fresh and not loaded_uncached):
            options = tournament.get_draft_options(fresh=fresh)
        memo[tournament.pk] = options
    return memo[tournament.pk]


def _prefetched_draft_options(tournament: Tournament) -> DraftOptions | None:
    if not Tournament.draft_options.is_cached(tournament):
        return None
    try:
        return tournament.draft_options
    except DraftOptions.DoesNotExist:
        return None


class DraftRoundForDraftSerializer(serializers.ModelSerializer):
    captain = serializers.SerializerMethodField()
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()

    choice = serializers.SerializerMethodField()
    team = TeamSerializerForTournament(many=False, read_only=True)

    def get_captain(self, draft_round: DraftRound) -> dict | None:
        return serialize_user_with_mmr(
            draft_round.captain, draft_round.draft.tournament
        )

    def get_choice(self, draft_round: DraftRound) -> dict | None:
        return serialize_user_with_mmr(draft_round.choice, draft_round.draft.tournament)

    class Meta:
        model = DraftRound
        fields = (
            "pk",
            "captain",
            "pick_phase",
            "pick_number",
            "choice",
            "team",
            "started_at",
            "completed_at",
            "timed_out_at",
            "grace_time_ms",
            "pick_duration_ms",
            "reserve_used_ms",
            "skip_count",
        )


class DraftRoundSerializerSlim(DraftRoundForDraftSerializer):
    """Slim variant — user fields as pks."""

    captain = UserPkField()
    choice = UserPkField()
    team = TeamSerializerSlim(many=False, read_only=True)


class TournamentSerializerForWebSocket(serializers.ModelSerializer):
    """
    Minimal tournament serializer for WebSocket broadcasts.
    Includes teams with PK-only members for real-time state updates.
    Full user data provided via _users dict.
    """

    teams = TeamSerializerSlim(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "teams",
        )


class DraftOptionsSerializer(serializers.ModelSerializer):
    grace_time_ms = serializers.IntegerField(min_value=1000, required=False)
    reserve_time_ms = serializers.IntegerField(min_value=0, required=False)
    hero_grace_time_ms = serializers.IntegerField(min_value=1000, required=False)
    hero_reserve_time_ms = serializers.IntegerField(min_value=0, required=False)

    class Meta:
        model = DraftOptions
        fields = (
            "timer_enabled",
            "grace_time_ms",
            "reserve_time_ms",
            "timeout_action",
            "hero_timer_enabled",
            "hero_grace_time_ms",
            "hero_reserve_time_ms",
        )
        read_only_fields = ("timeout_action",)


class DraftSerializerForTournament(serializers.ModelSerializer):
    """
    Serializer for draft data used in WebSocket broadcasts.
    Includes tournament.teams for real-time team updates.
    Full user data provided via _users dict.
    """

    draft_rounds = DraftRoundSerializerSlim(
        many=True,
        read_only=True,
    )
    users_remaining = serializers.SerializerMethodField()
    # Include tournament with teams for WebSocket broadcasts
    # This allows clients to update team state without additional API calls
    tournament = TournamentSerializerForWebSocket(read_only=True)
    state = serializers.CharField(read_only=True)
    clock_armed = serializers.SerializerMethodField()
    paused_at = serializers.DateTimeField(read_only=True)
    resuming_until = serializers.DateTimeField(read_only=True)
    is_manual_pause = serializers.BooleanField(read_only=True)
    draft_options = serializers.SerializerMethodField()

    def get_users_remaining(self, draft: Draft) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return users_remaining_pks(draft)

    def get_clock_armed(self, draft: Draft) -> bool:
        return draft.is_clock_armed(
            lambda: _shared_draft_options(self, draft.tournament)
        )

    def get_draft_options(self, draft: Draft) -> dict:
        return DraftOptionsSerializer(
            _shared_draft_options(self, draft.tournament)
        ).data

    class Meta:
        model = Draft
        fields = (
            "pk",
            "draft_rounds",
            "users_remaining",
            "latest_round",
            "draft_style",
            "tournament",
            "state",
            "clock_armed",
            "paused_at",
            "resuming_until",
            "is_manual_pause",
            "draft_options",
        )


class DraftSerializerSlim(DraftSerializerForTournament):
    """Slim variant — user fields as PKs, uses slim nested serializers."""

    draft_rounds = DraftRoundSerializerSlim(many=True, read_only=True)
    users_remaining = serializers.SerializerMethodField()

    def get_users_remaining(self, draft: Draft) -> list[int]:
        return users_remaining_pks(draft)
