# Cache Invalidation Strategies

When and how to invalidate Redis cache in the DTX backend.

## Invalidation Functions

```python
from cacheops import invalidate_all, invalidate_model, invalidate_obj
```

### invalidate_obj(instance)

Invalidates cache for a specific model instance.

```python
# After updating a tournament
tournament.name = "New Name"
tournament.save()
invalidate_obj(tournament)
```

### invalidate_model(Model)

Invalidates ALL cached data for a model.

```python
# After bulk operations
Team.objects.filter(tournament=tournament).update(current_points=0)
invalidate_model(Team)
```

### invalidate_all()

Nuclear option - clears entire cache.

```python
# On app startup (see apps.py)
from cacheops import invalidate_all
invalidate_all()
```

## Transaction-Safe Invalidation (Preferred)

When writes happen inside `transaction.atomic()`, signal handlers, or `@transaction.atomic` decorators,
cacheops `invalidate_obj()` may fire before data is committed — causing stale cache reads.

Use the `invalidate_after_commit` utility from `app/cache_utils.py`:

```python
from app.cache_utils import invalidate_after_commit

# Inside a transaction — invalidation deferred until commit
with transaction.atomic():
    user.nickname = "New"
    user.save()
    org_user.mmr = 5000
    org_user.save()
    invalidate_after_commit(
        *user.tournaments.all(),
        org_user,
        org_user.organization,
    )

# Inside a signal handler — signals run INSIDE the triggering transaction
@receiver(post_save, sender=Match)
def match_post_save(sender, instance, **kwargs):
    for game in instance.games.all():
        invalidate_after_commit(game, game.tournament)

# With @transaction.atomic decorator
@transaction.atomic
def save_bracket(request, tournament_id):
    # ... create/update games ...
    invalidate_after_commit(tournament, *saved_games)
```

### Rule of Thumb

If you ever have:
- `transaction.atomic()` blocks
- `on_commit` hooks
- Bulk `.update()` / `.bulk_create()`
- Writes in signal handlers

...use `invalidate_after_commit()` instead of direct `invalidate_obj()`.

Direct `invalidate_obj()` is only safe OUTSIDE any transaction context (e.g., after M2M `.add()`/`.remove()` which auto-commit).

## Override save() Pattern

For models with related data that must stay consistent:

```python
class DraftRound(models.Model):
    draft = models.ForeignKey(Draft, on_delete=models.CASCADE)
    choice = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        from cacheops import invalidate_model, invalidate_obj

        # Invalidate specific related instances
        invalidate_obj(self.draft.tournament)
        invalidate_obj(self.draft)

        # Invalidate entire models affected by draft picks
        invalidate_model(Tournament)
        invalidate_model(Draft)
        invalidate_model(Team)
```

## Signal-Based Invalidation (Alternative)

**WARNING**: Signal handlers run INSIDE the triggering transaction. Always use `invalidate_after_commit`:

```python
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from app.cache_utils import invalidate_after_commit

@receiver(post_save, sender=DraftRound)
def invalidate_draft_cache(sender, instance, **kwargs):
    invalidate_after_commit(instance.draft)

@receiver(post_delete, sender=Team)
def invalidate_team_cache(sender, instance, **kwargs):
    if instance.tournament:
        invalidate_after_commit(instance.tournament)
```

## Function-Level Invalidation

After operations that modify multiple models:

```python
def pick_player_for_round(draft_round, player):
    """Pick a player in the draft."""
    draft_round.choice = player
    draft_round.save()

    # Add player to team
    team = get_team_for_captain(draft_round.captain)
    team.members.add(player)

    # Explicit invalidation after complex operation
    from cacheops import invalidate_model
    invalidate_model(Tournament)
    invalidate_model(Draft)
    invalidate_model(Team)

    return draft_round
```

## Invalidation Decision Matrix

| Operation | Invalidate |
|-----------|------------|
| Create Tournament | `invalidate_model(Tournament)` |
| Update Tournament | `invalidate_obj(tournament)` |
| Delete Tournament | Automatic (cacheops handles) |
| Add Team to Tournament | `invalidate_obj(tournament)`, `invalidate_model(Team)` |
| Draft Pick | `invalidate_model(Tournament, Draft, Team)` |
| Game Result | `invalidate_obj(game.tournament)`, `invalidate_model(Game, Team)` |
| User Profile Update | `invalidate_obj(user)` |
| Bulk Update | `invalidate_model(AffectedModel)` |

## Cascading Invalidation

When models have deep relationships:

```python
def invalidate_tournament_cascade(tournament):
    """Invalidate tournament and all related caches."""
    from cacheops import invalidate_obj, invalidate_model

    # Primary object
    invalidate_obj(tournament)

    # Related objects
    for team in tournament.teams.all():
        invalidate_obj(team)

    if hasattr(tournament, 'draft'):
        invalidate_obj(tournament.draft)
        for round in tournament.draft.rounds.all():
            invalidate_obj(round)

    # Or just invalidate entire models (simpler, less targeted)
    invalidate_model(Team)
    invalidate_model(Draft)
    invalidate_model(DraftRound)
    invalidate_model(Game)
```

## Avoiding Over-Invalidation

### Bad: Invalidate everything always

```python
def update_tournament(tournament, data):
    tournament.name = data['name']
    tournament.save()
    # Overkill - invalidates unrelated data
    invalidate_all()
```

### Good: Targeted invalidation

```python
def update_tournament(tournament, data):
    tournament.name = data['name']
    tournament.save()
    # Only invalidate what changed
    invalidate_obj(tournament)
```

### Good: Let cacheops handle it

```python
def update_tournament(tournament, data):
    tournament.name = data['name']
    tournament.save()
    # Cacheops auto-invalidates because we're using @cached_as(Tournament, ...)
    # No manual invalidation needed for simple saves
```

## When Manual Invalidation is Required

1. **Bulk operations**: `Model.objects.filter().update()` bypasses save()
2. **Raw SQL**: Direct database modifications
3. **Related model changes**: M2M add/remove, FK updates
4. **Complex transactions**: Multiple models changed atomically
5. **External data sync**: Data imported from external sources

## Startup Invalidation

Ensure fresh cache on deploy:

```python
# app/apps.py
class AppConfig(AppConfig):
    def ready(self):
        if os.environ.get("DISABLE_CACHE", "false").lower() != "true":
            try:
                from cacheops import invalidate_all
                invalidate_all()
            except Exception:
                pass  # Redis not available
```
