# DTX Model Cache Dependencies

Model relationships and their cache invalidation requirements.

## Entity Relationship Diagram

```
CustomUser
├── positions → PositionsModel
├── captain_of → Team (reverse)
├── member_of → Team.members (M2M reverse)
├── tournaments → Tournament.users (M2M reverse)
└── draft_picks → DraftRound.choice (reverse)

Tournament
├── users → CustomUser (M2M)
├── winning_team → Team (OneToOne)
├── teams → Team (reverse FK)
├── draft → Draft (OneToOne reverse)
└── games → Game (reverse FK)

Team
├── tournament → Tournament (FK)
├── captain → CustomUser (FK)
├── members → CustomUser (M2M)
├── dropin_members → CustomUser (M2M)
├── left_members → CustomUser (M2M)
└── games → Game (reverse FK)

Draft
├── tournament → Tournament (OneToOne)
└── rounds → DraftRound (reverse FK)

DraftRound
├── draft → Draft (FK)
├── captain → CustomUser (FK)
└── choice → CustomUser (FK)

Game
├── tournament → Tournament (FK)
├── radiant_team → Team (FK)
├── dire_team → Team (FK)
├── winning_team → Team (FK)
└── stats → GameStat (reverse FK)
```

## Cache Dependency Chains

### Tournament Changes

When Tournament is modified, these caches may be stale:
- Tournament list views
- Tournament detail views
- Team list (tournament-filtered)
- Draft views
- Game views

```python
def on_tournament_change(tournament):
    invalidate_obj(tournament)
    # Views using @cached_as(Tournament, ...) auto-invalidate
```

### Team Changes

When Team is modified:
- Team list/detail views
- Tournament views (includes teams)
- Draft views (teams are draft result)
- Game views (teams play games)

```python
def on_team_change(team):
    invalidate_obj(team)
    if team.tournament:
        invalidate_obj(team.tournament)
```

### Draft/DraftRound Changes

Most complex - affects multiple models:
- Draft views
- Tournament views
- Team views (members change)
- User views (user's team assignment)

```python
def on_draft_round_change(draft_round):
    invalidate_obj(draft_round)
    invalidate_obj(draft_round.draft)
    invalidate_obj(draft_round.draft.tournament)
    invalidate_model(Team)  # Team membership changes
```

### Game Changes

When Game results are recorded:
- Game views
- Tournament views (standings)
- Team views (points/record)

```python
def on_game_change(game):
    invalidate_obj(game)
    invalidate_obj(game.tournament)
    invalidate_obj(game.radiant_team)
    invalidate_obj(game.dire_team)
```

### User Changes

When CustomUser is modified:
- User views
- Team views (if member)
- Draft views (if drafted)

```python
def on_user_change(user):
    invalidate_obj(user)
    # Invalidate teams user belongs to
    for team in user.team_members.all():
        invalidate_obj(team)
```

## View → Model Dependencies

Reference for `@cached_as` decorator dependencies:

### TournamentViewSet

```python
@cached_as(
    Tournament,
    Team,
    Draft,
    Game,
    DraftRound,
    CustomUser,
    extra=cache_key,
    timeout=60 * 10
)
```

### TeamViewSet

```python
@cached_as(
    Team,
    Tournament,
    CustomUser,
    extra=cache_key,
    timeout=60 * 60
)
```

### DraftViewSet

```python
@cached_as(
    Draft,
    Tournament,
    Team,
    DraftRound,
    CustomUser,
    extra=cache_key,
    timeout=60 * 60
)
```

### DraftRoundViewSet

```python
@cached_as(
    DraftRound,
    Draft,
    Tournament,
    Team,
    CustomUser,
    extra=cache_key,
    timeout=60 * 10
)
```

### GameViewSet

```python
@cached_as(
    Game,
    Tournament,
    Team,
    extra=cache_key,
    timeout=60 * 10
)
```

### UserViewSet

```python
@cached_as(
    CustomUser,
    PositionsModel,
    extra=cache_key,
    timeout=60 * 60
)
```

## M2M Relationship Caching

M2M changes don't trigger model save(), need explicit handling:

```python
# Adding user to tournament
tournament.users.add(user)
invalidate_obj(tournament)
invalidate_obj(user)

# Adding member to team
team.members.add(user)
invalidate_obj(team)
invalidate_obj(user)
if team.tournament:
    invalidate_obj(team.tournament)
```

## Uncached Models

These models are NOT in CACHEOPS config:
- `PositionsModel` - Always fetched with User
- `GameStat` - Detailed stats, usually aggregated
- `steam.Match` - External data
- `steam.PlayerMatchStats` - External data
- `bracket.TournamentBracket` - Bracket display
- `bracket.BracketSlot` - Bracket slots

Consider adding to CACHEOPS if performance issues arise:

```python
# In settings.py CACHEOPS
"app.positionsmodel": {"ops": "all", "timeout": 60 * 60},
"bracket.tournamentbracket": {"ops": "all", "timeout": 60 * 15},
```
