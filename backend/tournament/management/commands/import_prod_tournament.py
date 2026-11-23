from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from app.management.prod_payload import (
    TeamLookup,
    UserRef,
    create_positions,
    index_users,
    parse_date_played,
    resolve_user,
    steam_account_id,
)
from app.models import CustomUser
from common.game import GameType
from draft.models import Draft, DraftOptions, DraftRound
from league.models import League
from org.mmr import OrgMmrError, bulk_set_org_mmrs, resolve_game_type, validate_org_mmr
from org.models import Organization, OrgUser
from telemetry.logging import get_logger
from tournament.models import Game, Team, Tournament

log = get_logger(__name__)

PROD_BASE_URL = "https://dota.kettle.sh/api"


class Command(BaseCommand):
    help = "Import tournament data from production API"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user_map: dict[str, CustomUser] = {}  # Map discordId -> local user
        self.prod_users: dict[str, dict[str, Any]] = {}
        self.new_user_mmrs: dict[int, int] = {}
        self.teams = TeamLookup()

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("tournament_id", type=int, help="Production tournament ID")
        parser.add_argument(
            "--include-draft", action="store_true", help="Include draft data"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=None,
            help=f"Production API base URL (default: {PROD_BASE_URL})",
        )
        parser.add_argument(
            "--league",
            type=int,
            default=None,
            help="Local league pk to attach the tournament to; its organization "
            "receives the imported users' MMR",
        )
        parser.add_argument(
            "--organization",
            type=int,
            default=None,
            help="Local organization pk that receives the imported users' MMR "
            "(defaults to the --league organization)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        tournament_id = options["tournament_id"]
        include_draft = options["include_draft"]
        dry_run = options.get("dry_run", False)
        base_url = options.get("url") or PROD_BASE_URL
        league, organization = self._resolve_target(
            options.get("league"), options.get("organization")
        )

        self.stdout.write(f"Fetching tournament {tournament_id} from production...")

        tournament_data = self.fetch_tournament(base_url, tournament_id)
        if not tournament_data:
            self.stderr.write(self.style.ERROR("Failed to fetch tournament data"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            self._show_dry_run_info(tournament_data)
            return

        if organization is None:
            self.stdout.write(
                self.style.WARNING(
                    "No --league/--organization given: imported MMR is skipped"
                )
            )

        with transaction.atomic():
            tournament = self.create_tournament(
                tournament_data,
                include_draft,
                league=league,
                organization=organization,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully imported tournament: {tournament.name} (pk={tournament.pk})"
                )
            )

    def _resolve_target(
        self, league_pk: int | None, organization_pk: int | None
    ) -> tuple[League | None, Organization | None]:
        league: League | None = None
        organization: Organization | None = None
        if league_pk is not None:
            league = League.objects.filter(pk=league_pk).first()
            if league is None:
                raise CommandError(f"League {league_pk} does not exist")
            organization = league.organization
        if organization_pk is not None:
            organization = Organization.objects.filter(pk=organization_pk).first()
            if organization is None:
                raise CommandError(f"Organization {organization_pk} does not exist")
        return league, organization

    def fetch_tournament(
        self, base_url: str, tournament_id: int
    ) -> dict[str, Any] | None:
        """Fetch tournament data from production API."""
        try:
            response = requests.get(
                f"{base_url}/tournaments/{tournament_id}/", timeout=60
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"API error: {e}"))
            return None

    def _show_dry_run_info(self, tournament_data: dict[str, Any]) -> None:
        """Show information about what would be imported."""
        self.prod_users = index_users(tournament_data)
        self.stdout.write(f"  Tournament: {tournament_data.get('name')}")
        self.stdout.write(f"  State: {tournament_data.get('state')}")
        self.stdout.write(f"  Type: {tournament_data.get('tournament_type')}")
        self.stdout.write(f"  Users: {len(tournament_data.get('users', []))}")
        self.stdout.write(f"  Teams: {len(tournament_data.get('teams', []))}")

        for team_data in tournament_data.get("teams", []):
            members = team_data.get("members", [])
            captain = self._user_data(team_data.get("captain"))
            captain_name = captain.get("username", "Unknown") if captain else "None"
            self.stdout.write(
                f"    Team: {team_data.get('name')} "
                f"(captain: {captain_name}, members: {len(members)})"
            )

        draft = tournament_data.get("draft")
        if draft:
            rounds = draft.get("draft_rounds", [])
            self.stdout.write(
                f"  Draft: {draft.get('draft_style')} ({len(rounds)} rounds)"
            )

    def _user_data(self, ref: UserRef) -> dict[str, Any] | None:
        return resolve_user(ref, self.prod_users)

    def get_or_create_user_by_discord(self, ref: UserRef) -> CustomUser | None:
        """Get or create user by Discord ID."""
        user_data = self._user_data(ref)
        if not user_data:
            return None

        discord_id = user_data.get("discordId")
        if not discord_id:
            return None

        if discord_id in self.user_map:
            return self.user_map[discord_id]

        user = CustomUser.objects.filter(discordId=discord_id).first()
        if user:
            self.user_map[discord_id] = user
            return user

        user = CustomUser.objects.create(
            username=user_data.get("username", f"user_{discord_id}"),
            discordId=discord_id,
            steam_account_id=steam_account_id(user_data),
            avatar=user_data.get("avatar"),
            nickname=user_data.get("nickname"),
            positions=create_positions(user_data),
        )

        mmr = user_data.get("mmr")
        if mmr:
            self.new_user_mmrs[user.pk] = mmr

        self.user_map[discord_id] = user
        self.stdout.write(f"  Created user: {user.username}")
        return user

    def _write_org_mmrs(
        self, organization: Organization | None, game_type: GameType
    ) -> None:
        """Org MMR for users this run created; existing users keep theirs."""
        pending, self.new_user_mmrs = self.new_user_mmrs, {}
        if organization is None:
            return
        values: dict[int, int | None] = {}
        for user_id, mmr in pending.items():
            try:
                validate_org_mmr(game_type, mmr)
            except OrgMmrError as exc:
                log.warning(
                    "prod_import_mmr_skipped",
                    system="app",
                    subsystem="prod_import",
                    user_id=user_id,
                    error=str(exc),
                )
                continue
            values[user_id] = mmr
        if not values:
            return
        for user_id in values:
            OrgUser.objects.get_or_create(user_id=user_id, organization=organization)
        bulk_set_org_mmrs(organization.pk, game_type, values)

    def create_tournament(
        self,
        data: dict[str, Any],
        include_draft: bool = False,
        *,
        league: League | None = None,
        organization: Organization | None = None,
    ) -> Tournament:
        """Create tournament and related objects."""
        self.prod_users = index_users(data)
        game_type = resolve_game_type(data.get("game_type"))

        users = []
        for ref in data.get("users", []):
            user = self.get_or_create_user_by_discord(ref)
            if user:
                users.append(user)
        # Before users.set(): its signal seeds LeagueUser MMR from the org row.
        self._write_org_mmrs(organization, game_type)

        # "Real-" prefix distinguishes imported tournaments from test data
        tournament = Tournament.objects.create(
            name=f"Real-{data['name']}",
            date_played=parse_date_played(data.get("date_played")),
            timezone=data.get("timezone", "US/Eastern"),
            state=data.get("state", "past"),
            tournament_type=data.get("tournament_type", "double_elimination"),
            game_type=game_type,
            league=league,
        )
        tournament.users.set(users)
        DraftOptions.ensure_for(tournament, timer_enabled=False)

        self.stdout.write(f"  Created tournament: {tournament.name}")

        for team_data in data.get("teams", []):
            self.teams.add(team_data, self._create_team(tournament, team_data))

        winning_team = self.teams.get(data.get("winning_team"))
        if winning_team:
            tournament.winning_team = winning_team
            tournament.save(update_fields=["winning_team"])

        if include_draft and data.get("draft"):
            self._create_draft(tournament, data["draft"])

        for game_data in data.get("games", []):
            self._create_game(tournament, game_data)

        self._write_org_mmrs(organization, game_type)
        return tournament

    def _create_team(self, tournament: Tournament, team_data: dict[str, Any]) -> Team:
        """Create a team from production API data."""
        team = Team.objects.create(
            tournament=tournament,
            name=team_data.get("name", "Unnamed Team"),
            captain=self.get_or_create_user_by_discord(team_data.get("captain")),
            deputy_captain=self.get_or_create_user_by_discord(
                team_data.get("deputy_captain")
            ),
            draft_order=team_data.get("draft_order", 0),
        )

        for field in ("members", "dropin_members", "left_members"):
            for ref in team_data.get(field, []):
                member = self.get_or_create_user_by_discord(ref)
                if member:
                    getattr(team, field).add(member)

        self.stdout.write(f"    Created team: {team.name}")
        return team

    def _create_draft(
        self, tournament: Tournament, draft_data: dict[str, Any]
    ) -> Draft:
        """Create draft and rounds."""
        draft = Draft.objects.create(
            tournament=tournament,
            draft_style=draft_data.get("draft_style", "snake"),
        )

        for round_data in draft_data.get("draft_rounds", []):
            captain = self.get_or_create_user_by_discord(round_data.get("captain"))
            choice = self.get_or_create_user_by_discord(round_data.get("choice"))

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

        self.stdout.write(
            f"    Created draft with {len(draft_data.get('draft_rounds', []))} rounds"
        )
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
