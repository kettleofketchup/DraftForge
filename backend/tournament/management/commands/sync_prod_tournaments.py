from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from app.management.prod_payload import steam_account_id
from app.models import CustomUser, Game, Team, Tournament
from common.game import GameType
from draft.models import Draft, DraftOptions, DraftRound
from telemetry.logging import get_logger
from tournament.management.prod_payload import (
    TeamLookup,
    UserRef,
    index_users,
    parse_date_played,
    resolve_user,
)

log = get_logger(__name__)

PROD_API_URL = "https://dota.kettle.sh/api/tournaments/"


class Command(BaseCommand):
    help = "Sync tournaments from production (dota.kettle.sh) to local database"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user_map: dict[str, CustomUser] = {}
        self.prod_users: dict[str, dict[str, Any]] = {}
        self.teams = TeamLookup()

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without making changes",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=PROD_API_URL,
            help=f"Production API URL (default: {PROD_API_URL})",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options.get("dry_run", False)
        api_url = options.get("url", PROD_API_URL)

        self.stdout.write(f"Fetching tournaments from {api_url}...")

        try:
            response = requests.get(api_url, timeout=60)
            response.raise_for_status()
            prod_tournaments = response.json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch tournaments: {e}"))
            raise

        self.stdout.write(f"Found {len(prod_tournaments)} tournaments in production")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            for t in prod_tournaments:
                teams = t.get("teams", [])
                self.stdout.write(f"  Would sync: {t.get('name')} ({len(teams)} teams)")
            return

        # The list endpoint has no _users dict; the detail endpoint does.
        prod_tournaments = [self._with_users(api_url, t) for t in prod_tournaments]

        self._build_user_map()

        with transaction.atomic():
            existing_count = Tournament.objects.count()
            self.stdout.write(f"Deleting {existing_count} existing tournaments...")

            DraftRound.objects.all().delete()
            Draft.objects.all().delete()
            Game.objects.all().delete()
            Team.objects.all().delete()
            Tournament.objects.all().delete()

            created_count = 0
            for tournament_data in prod_tournaments:
                try:
                    with transaction.atomic():
                        self._create_tournament(tournament_data)
                    created_count += 1
                    self.stdout.write(f"  Synced: {tournament_data.get('name')}")
                except Exception as e:
                    log.warning(
                        "prod_tournament_sync_skipped",
                        system="app",
                        subsystem="prod_import",
                        tournament_name=tournament_data.get("name"),
                        error=str(e),
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped tournament {tournament_data.get('name')}: {e}"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully synced {created_count} tournaments from production!"
                )
            )

    def _with_users(self, api_url: str, data: dict[str, Any]) -> dict[str, Any]:
        pk = data.get("pk")
        if "_users" in data or not isinstance(pk, int):
            return data
        try:
            response = requests.get(f"{api_url.rstrip('/')}/{pk}/", timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.stdout.write(
                self.style.WARNING(f"Failed to fetch tournament {pk} detail: {e}")
            )
            return data

    def _build_user_map(self) -> None:
        """Build a map of production user identifiers to local users."""
        for user in CustomUser.objects.all():
            if user.discordId:
                self.user_map[f"discord:{user.discordId}"] = user
            if user.steam_account_id:
                self.user_map[f"steam:{user.steam_account_id}"] = user
            if user.username:
                self.user_map[f"username:{user.username}"] = user

    def _find_local_user(self, ref: UserRef) -> CustomUser | None:
        """Find local user matching production user data."""
        user_data = resolve_user(ref, self.prod_users)
        if not user_data:
            return None
        keys = (
            f"discord:{user_data.get('discordId')}",
            f"steam:{steam_account_id(user_data)}",
            f"username:{user_data.get('username')}",
        )
        for key in keys:
            user = self.user_map.get(key)
            if user:
                return user
        return None

    def _create_tournament(self, tournament_data: dict[str, Any]) -> Tournament:
        """Create a tournament from production API data."""
        self.prod_users = index_users(tournament_data)
        self.teams = TeamLookup()

        game_type = tournament_data.get("game_type")
        tournament = Tournament.objects.create(
            name=tournament_data.get("name", "Unnamed Tournament"),
            date_played=parse_date_played(tournament_data.get("date_played")),
            timezone=tournament_data.get("timezone", "UTC"),
            state=tournament_data.get("state", "future"),
            tournament_type=tournament_data.get(
                "tournament_type", "double_elimination"
            ),
            game_type=(game_type if game_type in GameType.values else GameType.DOTA2),
        )
        DraftOptions.ensure_for(tournament, timer_enabled=False)

        users = [self._find_local_user(ref) for ref in tournament_data.get("users", [])]
        tournament.users.add(*[user for user in users if user])

        for team_data in tournament_data.get("teams", []):
            self.teams.add(team_data, self._create_team(tournament, team_data))

        winning_team = self.teams.get(tournament_data.get("winning_team"))
        if winning_team:
            tournament.winning_team = winning_team
            tournament.save(update_fields=["winning_team"])

        draft_data = tournament_data.get("draft")
        if draft_data:
            self._create_draft(tournament, draft_data)

        for game_data in tournament_data.get("games", []):
            self._create_game(tournament, game_data)

        return tournament

    def _create_team(self, tournament: Tournament, team_data: dict[str, Any]) -> Team:
        """Create a team from production API data."""
        team = Team.objects.create(
            tournament=tournament,
            name=team_data.get("name", "Unnamed Team"),
            captain=self._find_local_user(team_data.get("captain")),
            deputy_captain=self._find_local_user(team_data.get("deputy_captain")),
            draft_order=team_data.get("draft_order", 0),
        )

        for field in ("members", "dropin_members", "left_members"):
            for ref in team_data.get(field, []):
                member = self._find_local_user(ref)
                if member:
                    getattr(team, field).add(member)

        return team

    def _create_draft(
        self, tournament: Tournament, draft_data: dict[str, Any]
    ) -> Draft:
        """Create a draft from production API data."""
        draft = Draft.objects.create(
            tournament=tournament,
            draft_style=draft_data.get("draft_style", "snake"),
        )

        for round_data in draft_data.get("draft_rounds", []):
            captain = self._find_local_user(round_data.get("captain"))
            choice = self._find_local_user(round_data.get("choice"))

            if captain:
                DraftRound.objects.create(
                    draft=draft,
                    captain=captain,
                    choice=choice,
                    pick_number=round_data.get("pick_number", 1),
                    pick_phase=round_data.get("pick_phase", 1),
                )

        draft.state = draft.derive_legacy_state()
        draft.save(update_fields=["state"])
        return draft

    def _create_game(self, tournament: Tournament, game_data: dict[str, Any]) -> Game:
        """Create a game from production API data."""
        return Game.objects.create(
            tournament=tournament,
            round=game_data.get("round", 1),
            gameid=game_data.get("gameid"),
            radiant_team=self.teams.get(game_data.get("radiant_team")),
            dire_team=self.teams.get(game_data.get("dire_team")),
            winning_team=self.teams.get(game_data.get("winning_team")),
        )
