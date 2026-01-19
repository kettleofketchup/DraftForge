import logging
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import (
    CustomUser,
    Draft,
    DraftRound,
    Game,
    PositionsModel,
    Team,
    Tournament,
)

logger = logging.getLogger(__name__)

PROD_BASE_URL = "https://dota.kettle.sh/api"


class Command(BaseCommand):
    help = "Import tournament data from production API"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_map = {}  # Map discordId -> local user

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        tournament_id = options["tournament_id"]
        include_draft = options["include_draft"]
        dry_run = options.get("dry_run", False)
        base_url = options.get("url") or self.PROD_BASE_URL

        self.stdout.write(f"Fetching tournament {tournament_id} from production...")

        # Fetch tournament data
        tournament_data = self.fetch_tournament(base_url, tournament_id)
        if not tournament_data:
            self.stderr.write(self.style.ERROR("Failed to fetch tournament data"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            self._show_dry_run_info(tournament_data)
            return

        with transaction.atomic():
            # Create local tournament
            tournament = self.create_tournament(tournament_data, include_draft)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully imported tournament: {tournament.name} (pk={tournament.pk})"
                )
            )

    def fetch_tournament(self, base_url, tournament_id):
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

    def _show_dry_run_info(self, tournament_data):
        """Show information about what would be imported."""
        self.stdout.write(f"  Tournament: {tournament_data.get('name')}")
        self.stdout.write(f"  State: {tournament_data.get('state')}")
        self.stdout.write(f"  Type: {tournament_data.get('tournament_type')}")
        self.stdout.write(f"  Users: {len(tournament_data.get('users', []))}")
        self.stdout.write(f"  Teams: {len(tournament_data.get('teams', []))}")

        for team_data in tournament_data.get("teams", []):
            members = team_data.get("members", [])
            captain = team_data.get("captain", {})
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

    def get_or_create_user_by_discord(self, user_data):
        """Get or create user by Discord ID."""
        if not user_data:
            return None

        discord_id = user_data.get("discordId")
        if not discord_id:
            return None

        # Check cache first
        if discord_id in self.user_map:
            return self.user_map[discord_id]

        # Try to find existing user
        user = CustomUser.objects.filter(discordId=discord_id).first()
        if user:
            self.user_map[discord_id] = user
            return user

        # Create positions
        positions_data = user_data.get("positions")
        if positions_data:
            positions = PositionsModel.objects.create(
                carry=positions_data.get("carry", 0),
                mid=positions_data.get("mid", 0),
                offlane=positions_data.get("offlane", 0),
                soft_support=positions_data.get("soft_support", 0),
                hard_support=positions_data.get("hard_support", 0),
            )
        else:
            positions = PositionsModel.objects.create()

        # Create user
        user = CustomUser.objects.create(
            username=user_data.get("username", f"user_{discord_id}"),
            discordId=discord_id,
            steamid=user_data.get("steamid"),
            mmr=user_data.get("mmr"),
            avatar=user_data.get("avatar"),
            nickname=user_data.get("nickname"),
            positions=positions,
        )

        self.user_map[discord_id] = user
        self.stdout.write(f"  Created user: {user.username}")
        return user

    def create_tournament(self, data, include_draft=False):
        """Create tournament and related objects."""
        # Add users to map and collect for tournament
        users = []
        for user_data in data.get("users", []):
            user = self.get_or_create_user_by_discord(user_data)
            if user:
                users.append(user)

        # Parse date
        date_str = data.get("date_played")
        if date_str:
            date_played = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            date_played = datetime.now().date()

        # Create tournament with "Real-" prefix to distinguish from test data
        tournament = Tournament.objects.create(
            name=f"Real-{data['name']}",
            date_played=date_played,
            timezone=data.get("timezone", "US/Eastern"),
            state=data.get("state", "past"),
            tournament_type=data.get("tournament_type", "double_elimination"),
        )
        tournament.users.set(users)

        self.stdout.write(f"  Created tournament: {tournament.name}")

        # Create teams
        team_map = {}  # Map prod team name -> local team
        for team_data in data.get("teams", []):
            team = self._create_team(tournament, team_data)
            if team:
                team_map[team_data.get("name")] = team

        # Set winning team if exists
        winning_team_data = data.get("winning_team")
        if winning_team_data:
            winning_team_name = winning_team_data.get("name")
            if winning_team_name and winning_team_name in team_map:
                tournament.winning_team = team_map[winning_team_name]
                tournament.save()

        # Create draft if requested and exists
        if include_draft and data.get("draft"):
            self._create_draft(tournament, data["draft"])

        # Create games
        for game_data in data.get("games", []):
            self._create_game(tournament, game_data, team_map)

        return tournament

    def _create_team(self, tournament, team_data):
        """Create a team from production API data."""
        captain = self.get_or_create_user_by_discord(team_data.get("captain"))

        team = Team.objects.create(
            tournament=tournament,
            name=team_data.get("name", "Unnamed Team"),
            captain=captain,
            draft_order=team_data.get("draft_order", 0),
        )

        # Add members
        for member_data in team_data.get("members", []):
            member = self.get_or_create_user_by_discord(member_data)
            if member:
                team.members.add(member)

        # Add dropin members
        for member_data in team_data.get("dropin_members", []):
            member = self.get_or_create_user_by_discord(member_data)
            if member:
                team.dropin_members.add(member)

        # Add left members
        for member_data in team_data.get("left_members", []):
            member = self.get_or_create_user_by_discord(member_data)
            if member:
                team.left_members.add(member)

        self.stdout.write(f"    Created team: {team.name}")
        return team

    def _create_draft(self, tournament, draft_data):
        """Create draft and rounds."""
        draft = Draft.objects.create(
            tournament=tournament,
            draft_style=draft_data.get("draft_style", "snake"),
        )

        # Create draft rounds
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

        self.stdout.write(
            f"    Created draft with {len(draft_data.get('draft_rounds', []))} rounds"
        )
        return draft

    def _create_game(self, tournament, game_data, team_map):
        """Create a game from production API data."""
        radiant_data = game_data.get("radiant_team")
        dire_data = game_data.get("dire_team")
        winning_data = game_data.get("winning_team")

        radiant_team = None
        dire_team = None
        winning_team = None

        # Find teams by name
        if radiant_data:
            radiant_team = team_map.get(radiant_data.get("name"))
        if dire_data:
            dire_team = team_map.get(dire_data.get("name"))
        if winning_data:
            winning_team = team_map.get(winning_data.get("name"))

        game = Game.objects.create(
            tournament=tournament,
            round=game_data.get("round", 1),
            gameid=game_data.get("gameid"),
            radiant_team=radiant_team,
            dire_team=dire_team,
            winning_team=winning_team,
        )

        return game
