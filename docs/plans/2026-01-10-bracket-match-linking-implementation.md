# Bracket Match Linking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable manual linking of tournament bracket games to Steam matches via a modal UI with tiered suggestions based on player/captain overlap.

**Architecture:** Backend adds league configuration via YAML/Pydantic, enhances match suggestion API with captain-aware tiers, and adds link/unlink endpoints. Frontend adds a modal triggered from MatchStatsModal displaying tiered match suggestions with search.

**Tech Stack:** Django REST Framework, Pydantic Settings, React, TypeScript, Zustand, Shadcn UI, Cypress

---

## Task 1: Remove GameStat Model

**Files:**
- Modify: `backend/app/models.py:314-338`
- Create: `backend/app/migrations/XXXX_remove_gamestat.py` (auto-generated)

**Step 1: Delete GameStat class from models.py**

Remove lines 314-338 from `backend/app/models.py`:

```python
# DELETE THIS ENTIRE CLASS (lines 314-338):
class GameStat(models.Model):
    user = models.ForeignKey(...)
    # ... all of it
```

**Step 2: Create migration**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py makemigrations app --name remove_gamestat
```

Expected: Migration file created

**Step 3: Apply migration**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py migrate
```

Expected: Migration applied successfully

**Step 4: Run tests to verify no breakage**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py test app.tests -v 2
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "refactor: remove unused GameStat model"
```

---

## Task 2: Add League Configuration via YAML + Pydantic

**Files:**
- Create: `backend/config/__init__.py`
- Create: `backend/config/leagues.yaml`
- Create: `backend/config/settings.py`
- Modify: `backend/dtx/settings.py`

**Step 2.1: Create config directory and __init__.py**

```bash
mkdir -p backend/config
touch backend/config/__init__.py
```

**Step 2.2: Create leagues.yaml**

Create `backend/config/leagues.yaml`:

```yaml
leagues:
  - id: 17929
    name: "DTX"
    default: true
```

**Step 2.3: Create Pydantic settings loader**

Create `backend/config/settings.py`:

```python
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class LeagueConfig(BaseModel):
    id: int
    name: str
    default: bool = False


class AppConfig(BaseSettings):
    leagues: list[LeagueConfig] = []

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @property
    def default_league_id(self) -> int | None:
        for league in self.leagues:
            if league.default:
                return league.id
        return self.leagues[0].id if self.leagues else None

    @property
    def league_choices(self) -> list[tuple[int, str]]:
        return [(league.id, league.name) for league in self.leagues]


# Load configuration at module level
CONFIG_PATH = Path(__file__).parent / "leagues.yaml"
app_config = AppConfig.from_yaml(CONFIG_PATH)
```

**Step 2.4: Update Django settings**

Add to `backend/dtx/settings.py` (at the end of the file):

```python
# League configuration
from config.settings import app_config

LEAGUE_CHOICES = app_config.league_choices
DEFAULT_LEAGUE_ID = app_config.default_league_id
```

**Step 2.5: Verify config loads correctly**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend -c "from django.conf import settings; print(f'Leagues: {settings.LEAGUE_CHOICES}, Default: {settings.DEFAULT_LEAGUE_ID}')"
```

Expected: `Leagues: [(17929, 'DTX')], Default: 17929`

**Step 2.6: Commit**

```bash
git add backend/config/
git add backend/dtx/settings.py
git commit -m "feat: add league configuration via YAML + Pydantic"
```

---

## Task 3: Add league_id to Tournament Model

**Files:**
- Modify: `backend/app/models.py` (Tournament class)
- Create: `backend/app/migrations/XXXX_tournament_league_id.py`

**Step 3.1: Add league_id field to Tournament model**

In `backend/app/models.py`, find the Tournament class and add after the existing fields:

```python
from django.conf import settings

class Tournament(models.Model):
    # ... existing fields ...

    league_id = models.IntegerField(
        null=True,
        blank=True,
        default=settings.DEFAULT_LEAGUE_ID,
        help_text="Steam league ID for match linking",
    )
```

**Step 3.2: Create and apply migration**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py makemigrations app --name tournament_league_id
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py migrate
```

**Step 3.3: Run tests**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py test app.tests -v 2
```

Expected: All tests pass

**Step 3.4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add league_id field to Tournament model"
```

---

## Task 4: Add SuggestionTier to GameMatchSuggestion

**Files:**
- Modify: `backend/steam/models.py`
- Create: `backend/steam/migrations/XXXX_gamematchsuggestion_tier.py`

**Step 4.1: Add SuggestionTier choices and field**

In `backend/steam/models.py`, add before the GameMatchSuggestion class:

```python
class SuggestionTier(models.TextChoices):
    ALL_PLAYERS = "all_players", "All Players Match"
    CAPTAINS_PLUS = "captains_plus", "Both Captains + Some Players"
    CAPTAINS_ONLY = "captains_only", "Both Captains Only"
    PARTIAL = "partial", "Partial Player Overlap"
```

Then add the field to GameMatchSuggestion:

```python
class GameMatchSuggestion(models.Model):
    # ... existing fields ...

    suggestion_tier = models.CharField(
        max_length=20,
        choices=SuggestionTier.choices,
        default=SuggestionTier.PARTIAL,
    )
```

**Step 4.2: Create and apply migration**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py makemigrations steam --name gamematchsuggestion_tier
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py migrate
```

**Step 4.3: Commit**

```bash
git add backend/steam/models.py backend/steam/migrations/
git commit -m "feat: add suggestion_tier field to GameMatchSuggestion"
```

---

## Task 5: Create Match Suggestions Service

**Files:**
- Create: `backend/steam/services/__init__.py`
- Create: `backend/steam/services/match_suggestions.py`
- Create: `backend/steam/tests/test_match_suggestions.py`

**Step 5.1: Create services directory**

```bash
mkdir -p backend/steam/services
touch backend/steam/services/__init__.py
```

**Step 5.2: Write failing test for tier calculation**

Create `backend/steam/tests/test_match_suggestions.py`:

```python
from django.test import TestCase

from app.models import CustomUser, Team, Tournament, Game
from steam.models import Match, PlayerMatchStats, SuggestionTier
from steam.services.match_suggestions import calculate_suggestion_tier


class CalculateSuggestionTierTest(TestCase):
    def setUp(self):
        # Create tournament
        self.tournament = Tournament.objects.create(name="Test Tournament")

        # Create users with steam IDs
        self.users = []
        for i in range(10):
            user = CustomUser.objects.create(
                username=f"player{i}",
                discordId=str(100000000000000000 + i),
                steamid=76561197960265728 + i,
            )
            self.users.append(user)

        # Create two teams
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
            captain=self.users[0],
        )
        self.team1.members.set(self.users[0:5])

        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
            captain=self.users[5],
        )
        self.team2.members.set(self.users[5:10])

        # Create a game
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        # Create a match
        self.match = Match.objects.create(
            match_id=9000000001,
            radiant_win=True,
            duration=2400,
            start_time=1704567890,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )

    def test_all_players_tier(self):
        """When all 10 players match, tier is ALL_PLAYERS."""
        # Add all 10 players to match
        for i, user in enumerate(self.users):
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=i,
                hero_id=1,
                kills=0, deaths=0, assists=0,
                gold_per_min=0, xp_per_min=0,
                last_hits=0, denies=0,
                hero_damage=0, tower_damage=0, hero_healing=0,
            )

        tier = calculate_suggestion_tier(self.match, self.team1, self.team2)
        self.assertEqual(tier, SuggestionTier.ALL_PLAYERS)

    def test_captains_plus_tier(self):
        """When both captains + some players match, tier is CAPTAINS_PLUS."""
        # Add both captains + 2 more players (4 total)
        for user in [self.users[0], self.users[5], self.users[1], self.users[6]]:
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=0,
                hero_id=1,
                kills=0, deaths=0, assists=0,
                gold_per_min=0, xp_per_min=0,
                last_hits=0, denies=0,
                hero_damage=0, tower_damage=0, hero_healing=0,
            )

        tier = calculate_suggestion_tier(self.match, self.team1, self.team2)
        self.assertEqual(tier, SuggestionTier.CAPTAINS_PLUS)

    def test_captains_only_tier(self):
        """When only both captains match, tier is CAPTAINS_ONLY."""
        # Add only both captains
        for user in [self.users[0], self.users[5]]:
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=0,
                hero_id=1,
                kills=0, deaths=0, assists=0,
                gold_per_min=0, xp_per_min=0,
                last_hits=0, denies=0,
                hero_damage=0, tower_damage=0, hero_healing=0,
            )

        tier = calculate_suggestion_tier(self.match, self.team1, self.team2)
        self.assertEqual(tier, SuggestionTier.CAPTAINS_ONLY)

    def test_partial_tier(self):
        """When captains don't both match, tier is PARTIAL."""
        # Add only one captain + some other players
        for user in [self.users[0], self.users[1], self.users[2]]:
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=0,
                hero_id=1,
                kills=0, deaths=0, assists=0,
                gold_per_min=0, xp_per_min=0,
                last_hits=0, denies=0,
                hero_damage=0, tower_damage=0, hero_healing=0,
            )

        tier = calculate_suggestion_tier(self.match, self.team1, self.team2)
        self.assertEqual(tier, SuggestionTier.PARTIAL)
```

**Step 5.3: Run test to verify it fails**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py test steam.tests.test_match_suggestions -v 2
```

Expected: FAIL with "cannot import name 'calculate_suggestion_tier'"

**Step 5.4: Implement match suggestions service**

Create `backend/steam/services/match_suggestions.py`:

```python
from django.db.models import Q

from app.models import Game, Team
from steam.models import Match, PlayerMatchStats, SuggestionTier


def get_team_steam_ids(team: Team) -> set[int]:
    """Get all steam IDs for a team's members."""
    return set(
        team.members.exclude(steamid__isnull=True)
        .exclude(steamid=0)
        .values_list("steamid", flat=True)
    )


def calculate_suggestion_tier(
    match: Match, radiant_team: Team, dire_team: Team
) -> SuggestionTier:
    """
    Calculate the suggestion tier based on player overlap.

    Tiers:
    - ALL_PLAYERS: All 10 players match
    - CAPTAINS_PLUS: Both captains + some other players match
    - CAPTAINS_ONLY: Only both captains match
    - PARTIAL: Some players match but not both captains
    """
    radiant_steam_ids = get_team_steam_ids(radiant_team)
    dire_steam_ids = get_team_steam_ids(dire_team)
    all_team_steam_ids = radiant_steam_ids | dire_steam_ids

    match_steam_ids = set(
        PlayerMatchStats.objects.filter(match=match).values_list("steam_id", flat=True)
    )

    overlap = all_team_steam_ids & match_steam_ids

    # Check if both captains are present
    radiant_captain_id = (
        radiant_team.captain.steamid
        if radiant_team.captain and radiant_team.captain.steamid
        else None
    )
    dire_captain_id = (
        dire_team.captain.steamid
        if dire_team.captain and dire_team.captain.steamid
        else None
    )

    both_captains_present = (
        radiant_captain_id in match_steam_ids and dire_captain_id in match_steam_ids
    )

    if len(overlap) >= 10:
        return SuggestionTier.ALL_PLAYERS
    elif both_captains_present and len(overlap) > 2:
        return SuggestionTier.CAPTAINS_PLUS
    elif both_captains_present:
        return SuggestionTier.CAPTAINS_ONLY
    else:
        return SuggestionTier.PARTIAL


def get_match_suggestions_for_game(game: Game, search: str | None = None) -> list[dict]:
    """
    Get match suggestions for a bracket game with tiered ordering.

    Returns matches from the tournament's league that aren't already linked,
    ordered by tier (best matches first).
    """
    if not game.radiant_team or not game.dire_team:
        return []

    tournament = game.tournament
    league_id = tournament.league_id

    if not league_id:
        return []

    # Get matches from this league that aren't linked to any game
    linked_match_ids = Game.objects.filter(
        gameid__isnull=False
    ).values_list("gameid", flat=True)

    matches_query = Match.objects.filter(league_id=league_id).exclude(
        match_id__in=linked_match_ids
    )

    # Apply search filter
    if search:
        # Try to parse as match ID
        try:
            match_id = int(search)
            matches_query = matches_query.filter(match_id__icontains=str(match_id))
        except ValueError:
            # Search by captain name - get captain steam IDs matching the search
            from app.models import CustomUser
            matching_users = CustomUser.objects.filter(
                Q(username__icontains=search) | Q(global_name__icontains=search)
            ).exclude(steamid__isnull=True).exclude(steamid=0)

            matching_steam_ids = list(matching_users.values_list("steamid", flat=True))

            if matching_steam_ids:
                # Find matches containing these players
                match_ids_with_player = PlayerMatchStats.objects.filter(
                    steam_id__in=matching_steam_ids
                ).values_list("match_id", flat=True)
                matches_query = matches_query.filter(match_id__in=match_ids_with_player)
            else:
                return []

    matches = list(matches_query.prefetch_related("players__user")[:50])

    # Calculate tier for each match and build response
    suggestions = []
    for match in matches:
        tier = calculate_suggestion_tier(match, game.radiant_team, game.dire_team)

        # Get captain info from match
        radiant_captain_info = _get_captain_match_info(
            match, game.radiant_team.captain
        )
        dire_captain_info = _get_captain_match_info(
            match, game.dire_team.captain
        )

        suggestions.append({
            "match_id": match.match_id,
            "start_time": match.start_time,
            "duration": match.duration,
            "radiant_win": match.radiant_win,
            "tier": tier,
            "tier_display": tier.label,
            "player_overlap": _count_player_overlap(
                match, game.radiant_team, game.dire_team
            ),
            "radiant_captain": radiant_captain_info,
            "dire_captain": dire_captain_info,
        })

    # Sort by tier priority
    tier_order = {
        SuggestionTier.ALL_PLAYERS: 0,
        SuggestionTier.CAPTAINS_PLUS: 1,
        SuggestionTier.CAPTAINS_ONLY: 2,
        SuggestionTier.PARTIAL: 3,
    }
    suggestions.sort(key=lambda s: (tier_order[s["tier"]], -s["start_time"]))

    return suggestions


def _get_captain_match_info(match: Match, captain) -> dict | None:
    """Get captain's info from match stats if they played."""
    if not captain or not captain.steamid:
        return None

    try:
        stats = PlayerMatchStats.objects.get(
            match=match, steam_id=captain.steamid
        )
        return {
            "steam_id": captain.steamid,
            "username": captain.username,
            "avatar": captain.avatarUrl if hasattr(captain, "avatarUrl") else None,
            "hero_id": stats.hero_id,
        }
    except PlayerMatchStats.DoesNotExist:
        return None


def _count_player_overlap(match: Match, team1: Team, team2: Team) -> int:
    """Count how many team players are in the match."""
    team_steam_ids = get_team_steam_ids(team1) | get_team_steam_ids(team2)
    match_steam_ids = set(
        PlayerMatchStats.objects.filter(match=match).values_list("steam_id", flat=True)
    )
    return len(team_steam_ids & match_steam_ids)
```

**Step 5.5: Run tests**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py test steam.tests.test_match_suggestions -v 2
```

Expected: All tests pass

**Step 5.6: Commit**

```bash
git add backend/steam/services/ backend/steam/tests/
git commit -m "feat: add match suggestions service with tier calculation"
```

---

## Task 6: Add API Endpoints for Match Linking

**Files:**
- Modify: `backend/steam/functions/api.py`
- Modify: `backend/steam/urls.py`
- Modify: `backend/steam/serializers.py`

**Step 6.1: Add serializers for new endpoints**

Add to `backend/steam/serializers.py`:

```python
class MatchSuggestionDetailSerializer(serializers.Serializer):
    match_id = serializers.IntegerField()
    start_time = serializers.IntegerField()
    duration = serializers.IntegerField()
    radiant_win = serializers.BooleanField()
    tier = serializers.CharField()
    tier_display = serializers.CharField()
    player_overlap = serializers.IntegerField()
    radiant_captain = serializers.DictField(allow_null=True)
    dire_captain = serializers.DictField(allow_null=True)


class MatchSuggestionsResponseSerializer(serializers.Serializer):
    suggestions = MatchSuggestionDetailSerializer(many=True)
    linked_match_id = serializers.IntegerField(allow_null=True)


class LinkMatchRequestSerializer(serializers.Serializer):
    match_id = serializers.IntegerField()
```

**Step 6.2: Add API views**

Add to `backend/steam/functions/api.py`:

```python
from steam.services.match_suggestions import get_match_suggestions_for_game


@api_view(["GET"])
@permission_classes([AllowAny])
def get_game_match_suggestions(request, game_id):
    """
    Get match suggestions for a bracket game with captain-aware tiers.

    Query params:
    - search: Filter by match ID or captain name
    """
    from app.models import Game

    try:
        game = Game.objects.select_related(
            "tournament",
            "radiant_team__captain",
            "dire_team__captain",
        ).prefetch_related(
            "radiant_team__members",
            "dire_team__members",
        ).get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {"error": "Game not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    search = request.query_params.get("search", None)
    suggestions = get_match_suggestions_for_game(game, search=search)

    return Response({
        "suggestions": suggestions,
        "linked_match_id": game.gameid,
    })


@api_view(["POST"])
@permission_classes([IsAdminUser])
def link_game_match(request, game_id):
    """Link a bracket game to a Steam match."""
    from app.models import Game
    from steam.serializers import LinkMatchRequestSerializer

    serializer = LinkMatchRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    match_id = serializer.validated_data["match_id"]

    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {"error": "Game not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Verify match exists
    if not Match.objects.filter(match_id=match_id).exists():
        return Response(
            {"error": "Match not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    game.gameid = match_id
    game.save()

    return Response({"status": "linked", "match_id": match_id})


@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def unlink_game_match(request, game_id):
    """Unlink a bracket game from its Steam match."""
    from app.models import Game

    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {"error": "Game not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    game.gameid = None
    game.save()

    return Response({"status": "unlinked"})
```

**Step 6.3: Add URL routes**

Add to `backend/steam/urls.py`:

```python
from .functions.api import (
    # ... existing imports ...
    get_game_match_suggestions,
    link_game_match,
    unlink_game_match,
)

# Add to urlpatterns:
    path(
        "games/<int:game_id>/match-suggestions/",
        get_game_match_suggestions,
        name="game_match_suggestions",
    ),
    path(
        "games/<int:game_id>/link-match/",
        link_game_match,
        name="link_game_match",
    ),
    path(
        "games/<int:game_id>/unlink-match/",
        unlink_game_match,
        name="unlink_game_match",
    ),
```

**Step 6.4: Run tests**

Run:
```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py test app.tests steam.tests -v 2
```

Expected: All tests pass

**Step 6.5: Commit**

```bash
git add backend/steam/
git commit -m "feat: add API endpoints for match suggestions and linking"
```

---

## Task 7: Create LinkSteamMatchModal Component

**Files:**
- Create: `frontend/app/components/bracket/modals/LinkSteamMatchModal.tsx`
- Create: `frontend/app/components/bracket/modals/SteamMatchCard.tsx`

**Step 7.1: Create SteamMatchCard component**

Create `frontend/app/components/bracket/modals/SteamMatchCard.tsx`:

```typescript
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Button } from '~/components/ui/button';
import { User } from 'lucide-react';
import { cn } from '~/lib/utils';

interface CaptainInfo {
  steam_id: number;
  username: string | null;
  avatar: string | null;
  hero_id: number;
}

interface MatchSuggestion {
  match_id: number;
  start_time: number;
  duration: number;
  radiant_win: boolean;
  tier: string;
  tier_display: string;
  player_overlap: number;
  radiant_captain: CaptainInfo | null;
  dire_captain: CaptainInfo | null;
}

interface SteamMatchCardProps {
  match: MatchSuggestion;
  onLink: (matchId: number) => void;
  onViewDetails: (matchId: number) => void;
  isCurrentlyLinked: boolean;
}

const HERO_ICON_URL = 'https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/';

function getHeroIconUrl(heroId: number): string {
  // This would need a hero ID to name mapping
  // For now, use a placeholder approach
  return `${HERO_ICON_URL}default.png`;
}

function CaptainDisplay({ captain }: { captain: CaptainInfo | null }) {
  if (!captain) {
    return (
      <div className="flex flex-col items-center">
        <Avatar className="h-10 w-10">
          <AvatarFallback>
            <User className="h-5 w-5" />
          </AvatarFallback>
        </Avatar>
        <span className="text-xs text-muted-foreground mt-1">Unknown</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center">
      <Avatar className="h-10 w-10">
        <AvatarImage src={captain.avatar || undefined} />
        <AvatarFallback>
          <User className="h-5 w-5" />
        </AvatarFallback>
      </Avatar>
      <span className="text-xs text-foreground mt-1 max-w-[80px] truncate">
        {captain.username || captain.steam_id}
      </span>
      <div className="w-6 h-6 mt-1 bg-muted rounded" title={`Hero ID: ${captain.hero_id}`} />
    </div>
  );
}

export function SteamMatchCard({
  match,
  onLink,
  onViewDetails,
  isCurrentlyLinked,
}: SteamMatchCardProps) {
  const date = new Date(match.start_time * 1000);
  const formattedDate = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const formattedTime = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
  const durationMinutes = Math.floor(match.duration / 60);

  return (
    <div
      className={cn(
        'border rounded-lg p-4',
        isCurrentlyLinked && 'ring-2 ring-primary'
      )}
      data-testid="match-card"
    >
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <p className="font-medium">Match #{match.match_id}</p>
          <p className="text-xs text-muted-foreground">
            {formattedDate} &bull; {formattedTime} &bull; {durationMinutes}m
          </p>
        </div>
        <span className="text-xs text-muted-foreground">
          {match.player_overlap} players
        </span>
      </div>

      {/* Captains */}
      <div className="flex items-center justify-center gap-6 py-3">
        <CaptainDisplay captain={match.radiant_captain} />
        <span className="text-lg font-bold text-muted-foreground">VS</span>
        <CaptainDisplay captain={match.dire_captain} />
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-3">
        <Button
          variant="outline"
          size="sm"
          className="flex-1"
          onClick={() => onViewDetails(match.match_id)}
          data-testid="view-details-btn"
        >
          View Details
        </Button>
        <Button
          size="sm"
          className="flex-1"
          onClick={() => onLink(match.match_id)}
          disabled={isCurrentlyLinked}
          data-testid="link-btn"
        >
          {isCurrentlyLinked ? 'Linked' : 'Link'}
        </Button>
      </div>
    </div>
  );
}
```

**Step 7.2: Create LinkSteamMatchModal component**

Create `frontend/app/components/bracket/modals/LinkSteamMatchModal.tsx`:

```typescript
import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Input } from '~/components/ui/input';
import { Button } from '~/components/ui/button';
import { Search, Unlink } from 'lucide-react';
import { api } from '~/components/api/axios';
import { SteamMatchCard } from './SteamMatchCard';
import { DotaMatchStatsModal } from './DotaMatchStatsModal';
import type { BracketMatch } from '../types';
import { cn } from '~/lib/utils';

interface MatchSuggestion {
  match_id: number;
  start_time: number;
  duration: number;
  radiant_win: boolean;
  tier: string;
  tier_display: string;
  player_overlap: number;
  radiant_captain: {
    steam_id: number;
    username: string | null;
    avatar: string | null;
    hero_id: number;
  } | null;
  dire_captain: {
    steam_id: number;
    username: string | null;
    avatar: string | null;
    hero_id: number;
  } | null;
}

interface LinkSteamMatchModalProps {
  isOpen: boolean;
  onClose: () => void;
  game: BracketMatch;
  onLinkUpdated: () => void;
}

const TIER_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  all_players: {
    bg: 'bg-green-500/20',
    border: 'border-green-500',
    text: 'text-green-400',
  },
  captains_plus: {
    bg: 'bg-blue-500/20',
    border: 'border-blue-500',
    text: 'text-blue-400',
  },
  captains_only: {
    bg: 'bg-yellow-500/20',
    border: 'border-yellow-500',
    text: 'text-yellow-400',
  },
  partial: {
    bg: 'bg-gray-500/20',
    border: 'border-gray-500',
    text: 'text-gray-400',
  },
};

export function LinkSteamMatchModal({
  isOpen,
  onClose,
  game,
  onLinkUpdated,
}: LinkSteamMatchModalProps) {
  const [search, setSearch] = useState('');
  const [suggestions, setSuggestions] = useState<MatchSuggestion[]>([]);
  const [linkedMatchId, setLinkedMatchId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [detailsMatchId, setDetailsMatchId] = useState<number | null>(null);

  // Fetch suggestions when modal opens or search changes
  useEffect(() => {
    if (!isOpen || !game.gameId) return;

    const fetchSuggestions = async () => {
      setIsLoading(true);
      try {
        const params = search ? `?search=${encodeURIComponent(search)}` : '';
        const response = await api.get(
          `/steam/games/${game.gameId}/match-suggestions/${params}`
        );
        setSuggestions(response.data.suggestions);
        setLinkedMatchId(response.data.linked_match_id);
      } catch (error) {
        console.error('Failed to fetch suggestions:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const debounce = setTimeout(fetchSuggestions, 300);
    return () => clearTimeout(debounce);
  }, [isOpen, game.gameId, search]);

  const handleLink = async (matchId: number) => {
    if (!game.gameId) return;

    try {
      await api.post(`/steam/games/${game.gameId}/link-match/`, {
        match_id: matchId,
      });
      setLinkedMatchId(matchId);
      onLinkUpdated();
      onClose();
    } catch (error) {
      console.error('Failed to link match:', error);
    }
  };

  const handleUnlink = async () => {
    if (!game.gameId) return;

    try {
      await api.delete(`/steam/games/${game.gameId}/link-match/`);
      setLinkedMatchId(null);
      onLinkUpdated();
    } catch (error) {
      console.error('Failed to unlink match:', error);
    }
  };

  // Group suggestions by tier
  const groupedSuggestions = suggestions.reduce(
    (acc, suggestion) => {
      const tier = suggestion.tier;
      if (!acc[tier]) acc[tier] = [];
      acc[tier].push(suggestion);
      return acc;
    },
    {} as Record<string, MatchSuggestion[]>
  );

  const tierOrder = ['all_players', 'captains_plus', 'captains_only', 'partial'];

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent
          className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
          data-testid="link-steam-match-modal"
        >
          <DialogHeader>
            <DialogTitle>Link Steam Match</DialogTitle>
          </DialogHeader>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by Match ID or Captain name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
              data-testid="match-search-input"
            />
          </div>

          {/* Currently linked */}
          {linkedMatchId && (
            <div
              className="flex items-center justify-between p-3 bg-muted rounded-lg"
              data-testid="currently-linked"
            >
              <span className="text-sm">
                Currently Linked: <strong>Match #{linkedMatchId}</strong>
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleUnlink}
                data-testid="unlink-btn"
              >
                <Unlink className="h-4 w-4 mr-1" />
                Unlink
              </Button>
            </div>
          )}

          {/* Suggestions */}
          <div className="flex-1 overflow-y-auto space-y-4">
            {isLoading ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading suggestions...
              </div>
            ) : suggestions.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No matches found
              </div>
            ) : (
              tierOrder.map((tier) => {
                const tierSuggestions = groupedSuggestions[tier];
                if (!tierSuggestions?.length) return null;

                const styles = TIER_STYLES[tier];
                const tierLabel =
                  tierSuggestions[0]?.tier_display || tier.replace('_', ' ');

                return (
                  <div key={tier} data-testid={`tier-${tier}`}>
                    <div
                      className={cn(
                        'px-3 py-1.5 rounded-t-lg border-b',
                        styles.bg,
                        styles.border,
                        styles.text
                      )}
                    >
                      <span className="text-sm font-medium">{tierLabel}</span>
                    </div>
                    <div className="space-y-2 p-2 border border-t-0 rounded-b-lg">
                      {tierSuggestions.map((suggestion) => (
                        <SteamMatchCard
                          key={suggestion.match_id}
                          match={suggestion}
                          onLink={handleLink}
                          onViewDetails={setDetailsMatchId}
                          isCurrentlyLinked={
                            linkedMatchId === suggestion.match_id
                          }
                        />
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Details modal */}
      <DotaMatchStatsModal
        open={detailsMatchId !== null}
        onClose={() => setDetailsMatchId(null)}
        matchId={detailsMatchId}
      />
    </>
  );
}
```

**Step 7.3: Commit**

```bash
git add frontend/app/components/bracket/modals/
git commit -m "feat: add LinkSteamMatchModal and SteamMatchCard components"
```

---

## Task 8: Integrate LinkSteamMatchModal with MatchStatsModal

**Files:**
- Modify: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

**Step 8.1: Add link button and modal integration**

Update `frontend/app/components/bracket/modals/MatchStatsModal.tsx`:

```typescript
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { BarChart3, Link2 } from 'lucide-react';
import { useUserStore } from '~/store/userStore';
import { useBracketStore } from '~/store/bracketStore';
import { DotaMatchStatsModal } from './DotaMatchStatsModal';
import { LinkSteamMatchModal } from './LinkSteamMatchModal';
import type { BracketMatch } from '../types';
import { cn } from '~/lib/utils';

interface MatchStatsModalProps {
  match: BracketMatch | null;
  isOpen: boolean;
  onClose: () => void;
}

export function MatchStatsModal({ match, isOpen, onClose }: MatchStatsModalProps) {
  const isStaff = useUserStore((state) => state.isStaff());
  const { setMatchWinner, advanceWinner, fetchBracket } = useBracketStore();
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);

  if (!match) return null;

  const isGameComplete = match.status === 'completed';
  const hasMatchId = !!match.steamMatchId;

  const handleSetWinner = (winner: 'radiant' | 'dire') => {
    setMatchWinner(match.id, winner);
    advanceWinner(match.id);
  };

  const handleLinkUpdated = () => {
    // Refresh bracket data to reflect the new link
    if (match.gameId) {
      // Get tournament ID from the URL or store
      const tournamentId = window.location.pathname.match(/\/tournaments\/(\d+)/)?.[1];
      if (tournamentId) {
        fetchBracket(parseInt(tournamentId, 10));
      }
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="match-stats-modal">
        <DialogHeader>
          <DialogTitle>Match Details</DialogTitle>
          <DialogDescription>
            {match.bracketType === 'grand_finals'
              ? 'Grand Finals'
              : `${match.bracketType === 'winners' ? 'Winners' : 'Losers'} Round ${match.round}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Teams display */}
          <div className="grid grid-cols-3 gap-4 items-center py-4">
            {/* Radiant team */}
            <TeamCard
              team={match.radiantTeam}
              score={match.radiantScore}
              isWinner={match.winner === 'radiant'}
              label="Radiant"
            />

            {/* VS divider */}
            <div className="text-center">
              <span className="text-2xl font-bold text-muted-foreground">VS</span>
              {match.status === 'completed' && (
                <Badge className="block mt-2" variant="outline">
                  Final
                </Badge>
              )}
              {match.status === 'live' && (
                <Badge className="block mt-2 bg-red-500">LIVE</Badge>
              )}
            </div>

            {/* Dire team */}
            <TeamCard
              team={match.direTeam}
              score={match.direScore}
              isWinner={match.winner === 'dire'}
              label="Dire"
            />
          </div>

          {/* Staff controls */}
          {isStaff && match.status !== 'completed' && match.radiantTeam && match.direTeam && (
            <div className="border-t pt-4">
              <p className="text-sm text-muted-foreground mb-2">Set Winner:</p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => handleSetWinner('radiant')}
                >
                  {match.radiantTeam.name} Wins
                </Button>
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => handleSetWinner('dire')}
                >
                  {match.direTeam.name} Wins
                </Button>
              </div>
            </div>
          )}

          {/* Steam match linking and stats */}
          <div className="border-t pt-4">
            <div className="flex items-center justify-between gap-2">
              {/* Link button - always visible for staff */}
              {isStaff && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowLinkModal(true)}
                  data-testid="link-steam-match-btn"
                >
                  <Link2 className="w-4 h-4 mr-1" />
                  {hasMatchId
                    ? `Linked: Match #${match.steamMatchId}`
                    : 'Link Steam Match'}
                </Button>
              )}

              {/* View stats button - only when linked and completed */}
              {hasMatchId && isGameComplete && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowStatsModal(true)}
                >
                  <BarChart3 className="w-4 h-4 mr-1" />
                  View Stats
                </Button>
              )}

              {/* Show match ID for non-staff when linked */}
              {!isStaff && hasMatchId && (
                <p className="text-sm text-muted-foreground">
                  Steam Match ID: {match.steamMatchId}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Detailed Match Stats Modal */}
        <DotaMatchStatsModal
          open={showStatsModal}
          onClose={() => setShowStatsModal(false)}
          matchId={match.steamMatchId}
        />

        {/* Link Steam Match Modal */}
        <LinkSteamMatchModal
          isOpen={showLinkModal}
          onClose={() => setShowLinkModal(false)}
          game={match}
          onLinkUpdated={handleLinkUpdated}
        />
      </DialogContent>
    </Dialog>
  );
}

interface TeamCardProps {
  team?: { name: string; captain?: { avatarUrl?: string } };
  score?: number;
  isWinner: boolean;
  label: string;
}

function TeamCard({ team, score, isWinner, label }: TeamCardProps) {
  if (!team) {
    return (
      <div className="text-center p-4 rounded-lg bg-muted/50">
        <div className="h-12 w-12 rounded-full bg-muted mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">TBD</p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'text-center p-4 rounded-lg',
        isWinner ? 'bg-green-500/10 ring-2 ring-green-500' : 'bg-muted/50'
      )}
    >
      <Avatar className="h-12 w-12 mx-auto mb-2">
        <AvatarImage src={team.captain?.avatarUrl} />
        <AvatarFallback>{team.name.substring(0, 2).toUpperCase()}</AvatarFallback>
      </Avatar>
      <p className={cn('font-medium', isWinner && 'text-green-500')}>{team.name}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
      {score !== undefined && (
        <p className={cn('text-2xl font-bold mt-1', isWinner && 'text-green-500')}>
          {score}
        </p>
      )}
      {isWinner && <span className="text-green-500">Winner</span>}
    </div>
  );
}
```

**Step 8.2: Commit**

```bash
git add frontend/app/components/bracket/modals/MatchStatsModal.tsx
git commit -m "feat: integrate LinkSteamMatchModal with MatchStatsModal"
```

---

## Task 9: Add Test Data Population Function

**Files:**
- Modify: `backend/tests/populate.py`

**Step 9.1: Add populate_bracket_linking_scenario function**

Add to `backend/tests/populate.py`:

```python
def populate_bracket_linking_scenario(force=False):
    """
    Creates a tournament with bracket and unlinked Steam matches
    for testing the match linking modal.

    Scenario:
    - Tournament "Link Test Tournament" with 4 teams
    - Bracket generated (6 games, all pending/unlinked)
    - 6 Steam matches in league 17929:
      - 2 matches: all 10 players match (tier: all_players)
      - 2 matches: both captains + 4 players (tier: captains_plus)
      - 2 matches: both captains only (tier: captains_only)
    """
    from app.models import Game, Tournament
    from steam.models import Match, PlayerMatchStats

    print("Populating bracket linking test scenario...")

    tournament_name = "Link Test Tournament"

    # Check if already exists
    if Tournament.objects.filter(name=tournament_name).exists():
        if not force:
            print(f"Tournament '{tournament_name}' already exists. Use force=True to recreate.")
            return
        # Delete existing
        Tournament.objects.filter(name=tournament_name).delete()
        Match.objects.filter(match_id__gte=9100000001, match_id__lt=9100000010).delete()

    # Ensure we have enough users with steam IDs
    users_with_steam = list(
        CustomUser.objects.filter(steamid__isnull=False)
        .exclude(steamid=0)
        .order_by("pk")[:20]
    )

    if len(users_with_steam) < 20:
        print(f"Need 20 users with Steam IDs, found {len(users_with_steam)}. Run populate_users first.")
        return

    # Create tournament
    tournament = Tournament.objects.create(
        name=tournament_name,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league_id=17929,
    )

    # Create 4 teams of 5 players each
    teams = []
    team_names = ["Link Alpha", "Link Beta", "Link Gamma", "Link Delta"]
    for i, name in enumerate(team_names):
        team_members = users_with_steam[i * 5 : (i + 1) * 5]
        team = Team.objects.create(
            tournament=tournament,
            name=name,
            captain=team_members[0],
            draft_order=i + 1,
        )
        team.members.set(team_members)
        teams.append(team)

    # Create bracket games (all pending, no teams assigned except first round)
    games = []
    bracket_structure = [
        {"round": 1, "bracket_type": "winners", "position": 0, "radiant": teams[0], "dire": teams[1]},
        {"round": 1, "bracket_type": "winners", "position": 1, "radiant": teams[2], "dire": teams[3]},
        {"round": 1, "bracket_type": "losers", "position": 0, "radiant": None, "dire": None},
        {"round": 2, "bracket_type": "winners", "position": 0, "radiant": None, "dire": None},
        {"round": 2, "bracket_type": "losers", "position": 0, "radiant": None, "dire": None},
        {"round": 1, "bracket_type": "grand_finals", "position": 0, "radiant": None, "dire": None},
    ]

    for info in bracket_structure:
        game = Game.objects.create(
            tournament=tournament,
            round=info["round"],
            bracket_type=info["bracket_type"],
            position=info["position"],
            elimination_type="double",
            radiant_team=info["radiant"],
            dire_team=info["dire"],
            status="pending",
        )
        games.append(game)

    # Set up bracket links
    games[0].next_game = games[3]
    games[0].next_game_slot = "radiant"
    games[0].loser_next_game = games[2]
    games[0].loser_next_game_slot = "radiant"
    games[0].save()

    games[1].next_game = games[3]
    games[1].next_game_slot = "dire"
    games[1].loser_next_game = games[2]
    games[1].loser_next_game_slot = "dire"
    games[1].save()

    games[2].next_game = games[4]
    games[2].next_game_slot = "radiant"
    games[2].save()

    games[3].next_game = games[5]
    games[3].next_game_slot = "radiant"
    games[3].loser_next_game = games[4]
    games[3].loser_next_game_slot = "dire"
    games[3].save()

    games[4].next_game = games[5]
    games[4].next_game_slot = "dire"
    games[4].save()

    # Create Steam matches with different tiers
    # Get team 1 and 2 players (first bracket game)
    team1_players = list(teams[0].members.all())
    team2_players = list(teams[1].members.all())
    all_players = team1_players + team2_players

    match_base_id = 9100000001
    base_time = int(date.today().strftime("%s"))

    # Tier 1: All players match (2 matches)
    for i in range(2):
        match = Match.objects.create(
            match_id=match_base_id + i,
            radiant_win=(i == 0),
            duration=2400 + i * 100,
            start_time=base_time - (i * 3600),
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        # Add all 10 players
        for j, user in enumerate(all_players):
            PlayerMatchStats.objects.create(
                match=match,
                steam_id=user.steamid,
                user=user,
                player_slot=j,
                hero_id=1 + j,
                kills=5, deaths=3, assists=10,
                gold_per_min=500, xp_per_min=600,
                last_hits=200, denies=20,
                hero_damage=15000, tower_damage=2000, hero_healing=0,
            )

    # Tier 2: Both captains + some players (2 matches)
    for i in range(2):
        match = Match.objects.create(
            match_id=match_base_id + 2 + i,
            radiant_win=(i == 0),
            duration=2500 + i * 100,
            start_time=base_time - ((2 + i) * 3600),
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        # Add both captains + 2 more from each team (6 total)
        players_to_add = [
            team1_players[0],  # captain 1
            team2_players[0],  # captain 2
            team1_players[1],
            team1_players[2],
            team2_players[1],
            team2_players[2],
        ]
        for j, user in enumerate(players_to_add):
            PlayerMatchStats.objects.create(
                match=match,
                steam_id=user.steamid,
                user=user,
                player_slot=j,
                hero_id=10 + j,
                kills=4, deaths=4, assists=8,
                gold_per_min=450, xp_per_min=550,
                last_hits=180, denies=15,
                hero_damage=12000, tower_damage=1500, hero_healing=0,
            )

    # Tier 3: Both captains only (2 matches)
    for i in range(2):
        match = Match.objects.create(
            match_id=match_base_id + 4 + i,
            radiant_win=(i == 0),
            duration=2600 + i * 100,
            start_time=base_time - ((4 + i) * 3600),
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        # Add only both captains
        for j, user in enumerate([team1_players[0], team2_players[0]]):
            PlayerMatchStats.objects.create(
                match=match,
                steam_id=user.steamid,
                user=user,
                player_slot=j,
                hero_id=20 + j,
                kills=8, deaths=2, assists=12,
                gold_per_min=550, xp_per_min=650,
                last_hits=250, denies=25,
                hero_damage=20000, tower_damage=3000, hero_healing=0,
            )

    print(f"Created tournament '{tournament_name}' with {len(games)} games and 6 test matches")


# Update populate_all to include new function
def populate_all(force=False):
    """Run all population functions."""
    populate_users(force)
    populate_tournaments(force)
    populate_steam_matches(force)
    populate_bracket_linking_scenario(force)
```

**Step 9.2: Commit**

```bash
git add backend/tests/populate.py
git commit -m "feat: add populate_bracket_linking_scenario for test data"
```

---

## Task 10: Add Cypress E2E Tests

**Files:**
- Create: `frontend/tests/cypress/e2e/bracket-match-linking.cy.ts`

**Step 10.1: Create Cypress test file**

Create `frontend/tests/cypress/e2e/bracket-match-linking.cy.ts`:

```typescript
describe('Bracket Match Linking', () => {
  beforeEach(() => {
    // Login as staff user
    cy.visit('/');
    cy.get('[data-testid="login-button"]').click();
    // Assuming there's a test login flow
    cy.visit('/tournaments');
  });

  describe('Full Flow: Bracket to Linked Match', () => {
    beforeEach(() => {
      // Navigate to the Link Test Tournament bracket
      cy.contains('Link Test Tournament').click();
      cy.get('[data-testid="bracket-tab"]').click();
    });

    it('should open match modal and link a steam match', () => {
      // Click on first winners bracket game
      cy.get('[data-testid="match-node-w-1-0"]').click();

      // MatchStatsModal opens
      cy.get('[data-testid="match-stats-modal"]').should('be.visible');

      // Click link button
      cy.get('[data-testid="link-steam-match-btn"]').click();

      // LinkSteamMatchModal opens
      cy.get('[data-testid="link-steam-match-modal"]').should('be.visible');

      // Verify tier sections exist
      cy.get('[data-testid="tier-all_players"]').should('exist');

      // Select first "All Players Match" suggestion
      cy.get('[data-testid="tier-all_players"]')
        .find('[data-testid="match-card"]')
        .first()
        .find('[data-testid="link-btn"]')
        .click();

      // Modal closes, verify link persisted
      cy.get('[data-testid="link-steam-match-modal"]').should('not.exist');
      cy.get('[data-testid="link-steam-match-btn"]').should('contain', 'Linked: Match #');
    });
  });

  describe('Modal Functionality', () => {
    beforeEach(() => {
      cy.contains('Link Test Tournament').click();
      cy.get('[data-testid="bracket-tab"]').click();
      cy.get('[data-testid="match-node-w-1-0"]').click();
      cy.get('[data-testid="link-steam-match-btn"]').click();
    });

    it('should filter matches by search term', () => {
      // Search by match ID
      cy.get('[data-testid="match-search-input"]').type('9100000');
      cy.get('[data-testid="match-card"]').should('have.length.greaterThan', 0);

      // Clear and search by captain name
      cy.get('[data-testid="match-search-input"]').clear();
      // Use a username from the test data
      cy.get('[data-testid="match-search-input"]').type('phantom');
      cy.get('[data-testid="match-card"]').should('have.length.greaterThan', 0);
    });

    it('should show view details button', () => {
      cy.get('[data-testid="match-card"]')
        .first()
        .find('[data-testid="view-details-btn"]')
        .should('exist');
    });

    it('should unlink an already linked match', () => {
      // First link a match
      cy.get('[data-testid="tier-all_players"]')
        .find('[data-testid="link-btn"]')
        .first()
        .click();

      // Reopen modal
      cy.get('[data-testid="match-node-w-1-0"]').click();
      cy.get('[data-testid="link-steam-match-btn"]').click();

      // Verify "Currently Linked" section shows
      cy.get('[data-testid="currently-linked"]').should('be.visible');

      // Click unlink
      cy.get('[data-testid="unlink-btn"]').click();

      // Close and reopen to verify unlinked
      cy.get('[data-testid="link-steam-match-modal"]').within(() => {
        cy.get('[data-testid="currently-linked"]').should('not.exist');
      });
    });

    it('should allow linking to a different match', () => {
      // Link first match
      cy.get('[data-testid="match-card"]')
        .first()
        .find('[data-testid="link-btn"]')
        .click();

      // Reopen and link different match
      cy.get('[data-testid="match-node-w-1-0"]').click();
      cy.get('[data-testid="link-steam-match-btn"]').click();

      // Link the second match in the list
      cy.get('[data-testid="match-card"]')
        .eq(1)
        .find('[data-testid="link-btn"]')
        .click();

      // Should close modal
      cy.get('[data-testid="link-steam-match-modal"]').should('not.exist');
    });
  });
});
```

**Step 10.2: Commit**

```bash
git add frontend/tests/cypress/e2e/
git commit -m "test: add Cypress E2E tests for bracket match linking"
```

---

## Task 11: Final Integration Testing

**Step 11.1: Run all backend tests**

```bash
docker compose --project-directory . -f docker/docker-compose.test.yaml run --rm --entrypoint "python" backend backend/manage.py test app.tests steam.tests -v 2
```

Expected: All tests pass

**Step 11.2: Populate test data**

```bash
source .venv/bin/activate
inv db.populate.all
```

**Step 11.3: Start test environment**

```bash
inv test.up
```

**Step 11.4: Run Cypress tests**

```bash
inv test.headless
```

Or interactively:
```bash
inv test.open
```

**Step 11.5: Final commit**

```bash
git add -A
git commit -m "feat: complete bracket match linking implementation"
```

---

## Summary

This plan implements:

1. **Backend cleanup**: Remove unused GameStat model
2. **Configuration**: YAML-based league configuration with Pydantic
3. **Data model**: Tournament.league_id, GameMatchSuggestion.suggestion_tier
4. **Services**: Tier calculation logic with captain awareness
5. **API**: Match suggestions endpoint with search, link/unlink endpoints
6. **Frontend**: LinkSteamMatchModal with tiered suggestions, SteamMatchCard
7. **Integration**: MatchStatsModal link button
8. **Test data**: populate_bracket_linking_scenario
9. **E2E tests**: Cypress tests for full linking flow
