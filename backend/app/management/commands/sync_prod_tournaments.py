import logging
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import CustomUser, Draft, DraftRound, Game, Team, Tournament

logger = logging.getLogger(__name__)

PROD_API_URL = "https://dota.kettle.sh/api/tournaments/"


class Command(BaseCommand):
    help = "Sync tournaments from production (dota.kettle.sh) to local database"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_map = {}  # Map prod user pk -> local user

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
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

        # Build user map from discordId for matching
        self._build_user_map()

        with transaction.atomic():
            # Delete all existing tournaments and related data
            existing_count = Tournament.objects.count()
            self.stdout.write(f"Deleting {existing_count} existing tournaments...")

            # Delete in order to respect foreign key constraints
            DraftRound.objects.all().delete()
            Draft.objects.all().delete()
            Game.objects.all().delete()
            Team.objects.all().delete()
            Tournament.objects.all().delete()

            # Create tournaments from production data
            created_count = 0
            for tournament_data in prod_tournaments:
                try:
                    self._create_tournament(tournament_data)
                    created_count += 1
                    self.stdout.write(f"  Synced: {tournament_data.get('name')}")
                except Exception as e:
                    logger.warning(
                        f"Failed to create tournament {tournament_data.get('name')}: {e}"
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

    def _build_user_map(self):
        """Build a map of production user identifiers to local users."""
        for user in CustomUser.objects.all():
            if user.discordId:
                self.user_map[f"discord:{user.discordId}"] = user
            if user.steamid:
                self.user_map[f"steam:{user.steamid}"] = user
            if user.username:
                self.user_map[f"username:{user.username}"] = user

    def _find_local_user(self, user_data: dict) -> CustomUser | None:
        """Find local user matching production user data."""
        if not user_data:
            return None

        # Try discordId first
        discord_id = user_data.get("discordId")
        if discord_id:
            user = self.user_map.get(f"discord:{discord_id}")
            if user:
                return user

        # Try steamid
        steamid = user_data.get("steamid")
        if steamid:
            user = self.user_map.get(f"steam:{steamid}")
            if user:
                return user

        # Try username as fallback
        username = user_data.get("username")
        if username:
            user = self.user_map.get(f"username:{username}")
            if user:
                return user

        return None

    def _create_tournament(self, tournament_data: dict) -> Tournament:
        """Create a tournament from production API data."""
        # Parse date
        date_str = tournament_data.get("date_played")
        if date_str:
            date_played = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            date_played = datetime.now().date()

        # Create tournament
        tournament = Tournament.objects.create(
            name=tournament_data.get("name", "Unnamed Tournament"),
            date_played=date_played,
            state=tournament_data.get("state", "future"),
            tournament_type=tournament_data.get(
                "tournament_type", "double_elimination"
            ),
        )

        # Add users to tournament
        users_data = tournament_data.get("users", [])
        for user_data in users_data:
            local_user = self._find_local_user(user_data)
            if local_user:
                tournament.users.add(local_user)

        # Create teams
        team_map = {}  # Map prod team pk -> local team
        teams_data = tournament_data.get("teams", [])
        for team_data in teams_data:
            team = self._create_team(tournament, team_data)
            if team:
                team_map[team_data.get("pk")] = team

        # Set winning team if exists
        winning_team_pk = tournament_data.get("winning_team")
        if winning_team_pk and winning_team_pk in team_map:
            tournament.winning_team = team_map[winning_team_pk]
            tournament.save()

        # Create draft if exists
        draft_data = tournament_data.get("draft")
        if draft_data:
            self._create_draft(tournament, draft_data, team_map)

        # Create games
        games_data = tournament_data.get("games", [])
        for game_data in games_data:
            self._create_game(tournament, game_data, team_map)

        return tournament

    def _create_team(self, tournament: Tournament, team_data: dict) -> Team | None:
        """Create a team from production API data."""
        captain_data = team_data.get("captain")
        captain = self._find_local_user(captain_data) if captain_data else None

        team = Team.objects.create(
            tournament=tournament,
            name=team_data.get("name", "Unnamed Team"),
            captain=captain,
            draft_order=team_data.get("draft_order", 0),
        )

        # Add members
        for member_data in team_data.get("members", []):
            member = self._find_local_user(member_data)
            if member:
                team.members.add(member)

        # Add dropin members
        for member_data in team_data.get("dropin_members", []):
            member = self._find_local_user(member_data)
            if member:
                team.dropin_members.add(member)

        # Add left members
        for member_data in team_data.get("left_members", []):
            member = self._find_local_user(member_data)
            if member:
                team.left_members.add(member)

        return team

    def _create_draft(
        self, tournament: Tournament, draft_data: dict, team_map: dict
    ) -> Draft | None:
        """Create a draft from production API data."""
        draft = Draft.objects.create(
            tournament=tournament,
            draft_style=draft_data.get("draft_style", "snake"),
        )

        # Create draft rounds
        for round_data in draft_data.get("draft_rounds", []):
            captain_data = round_data.get("captain")
            captain = self._find_local_user(captain_data) if captain_data else None

            choice_data = round_data.get("choice")
            choice = self._find_local_user(choice_data) if choice_data else None

            if captain:
                DraftRound.objects.create(
                    draft=draft,
                    captain=captain,
                    choice=choice,
                    pick_number=round_data.get("pick_number", 1),
                    pick_phase=round_data.get("pick_phase", 1),
                )

        return draft

    def _create_game(
        self, tournament: Tournament, game_data: dict, team_map: dict
    ) -> Game | None:
        """Create a game from production API data."""
        radiant_data = game_data.get("radiant_team")
        dire_data = game_data.get("dire_team")
        winning_data = game_data.get("winning_team")

        radiant_team = None
        dire_team = None
        winning_team = None

        # Find teams by matching name since we don't have pk mapping
        if radiant_data:
            radiant_team = Team.objects.filter(
                tournament=tournament, name=radiant_data.get("name")
            ).first()
        if dire_data:
            dire_team = Team.objects.filter(
                tournament=tournament, name=dire_data.get("name")
            ).first()
        if winning_data:
            winning_team = Team.objects.filter(
                tournament=tournament, name=winning_data.get("name")
            ).first()

        game = Game.objects.create(
            tournament=tournament,
            round=game_data.get("round", 1),
            gameid=game_data.get("gameid"),
            radiant_team=radiant_team,
            dire_team=dire_team,
            winning_team=winning_team,
        )

        return game
