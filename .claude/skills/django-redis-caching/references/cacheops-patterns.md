# Cacheops Patterns

Django-cacheops decorator patterns for the DTX backend.

## @cached_as Decorator

Caches function results, invalidates when monitored models change.

### List Endpoint Pattern

```python
from cacheops import cached_as
from rest_framework.response import Response

class TournamentViewSet(viewsets.ModelViewSet):
    def list(self, request, *args, **kwargs):
        # Include full path for query param variations
        cache_key = f"tournament_list:{request.get_full_path()}"

        @cached_as(
            Tournament, Team, Draft, Game, DraftRound, CustomUser,
            extra=cache_key,
            timeout=60 * 10  # 10 minutes for active data
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        return Response(get_data())
```

### Detail Endpoint Pattern

```python
def retrieve(self, request, *args, **kwargs):
    pk = kwargs["pk"]
    cache_key = f"tournament_detail:{pk}"

    @cached_as(
        Tournament.objects.filter(pk=pk),  # Specific queryset
        keep_fresh=True,  # Update cache on model change
        extra=cache_key,
        timeout=60 * 60
    )
    def get_data():
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return serializer.data

    return Response(get_data())
```

### Function Caching

```python
from cacheops import cached_as

def get_draft_simulations(draft, request):
    cache_key = f"draft_mmrs:{draft.pk}:{request.get_full_path()}"

    @cached_as(
        Draft, CustomUser, Tournament, Team,
        extra=cache_key,
        timeout=60 * 15  # 15 minutes
    )
    def get_data(request):
        return DraftSerializerMMRs(draft).data

    return get_data(request)
```

## @cached Decorator

Low-level caching without model monitoring.

```python
from cacheops import cached

@cached(timeout=15)
def get_discord_members(request):
    """Short cache for external API calls."""
    return fetch_discord_api()
```

## Cache Key Best Practices

### Include Discriminators

```python
# Bad - no variation for different queries
cache_key = "tournaments"

# Good - includes query params
cache_key = f"tournaments:{request.get_full_path()}"

# Good - includes pk for detail views
cache_key = f"tournament:{pk}"

# Good - includes user context if needed
cache_key = f"user_tournaments:{request.user.pk}"
```

### Namespace Keys

```python
# Prefix with model/feature name
cache_key = f"tournament_list:{path}"
cache_key = f"draft_detail:{pk}"
cache_key = f"team_members:{team_pk}"
```

## Model Monitoring

### Single Model

```python
@cached_as(Tournament, timeout=60 * 60)
def get_tournaments():
    return list(Tournament.objects.all())
```

### Multiple Models

```python
@cached_as(Tournament, Team, Game, timeout=60 * 60)
def get_tournament_with_teams(pk):
    return Tournament.objects.prefetch_related('teams', 'games').get(pk=pk)
```

### Specific Queryset

```python
# Only invalidate when THIS tournament changes
@cached_as(Tournament.objects.filter(pk=pk), keep_fresh=True)
def get_single_tournament(pk):
    return Tournament.objects.get(pk=pk)
```

## keep_fresh Parameter

```python
# keep_fresh=True: Update cache immediately when model changes
@cached_as(Model, keep_fresh=True)
def get_data():
    pass

# keep_fresh=False (default): Invalidate cache, recompute on next request
@cached_as(Model, keep_fresh=False)
def get_data():
    pass
```

Use `keep_fresh=True` for:
- Detail endpoints (single object)
- Frequently accessed data
- Data that must be immediately consistent

Use `keep_fresh=False` for:
- List endpoints (many objects)
- Expensive computations
- Data where slight staleness is acceptable

## Avoiding Cache Stampede

For expensive computations, use locking:

```python
from cacheops import cached_as

@cached_as(Model, timeout=60 * 60)
def expensive_computation():
    # If many requests hit uncached endpoint simultaneously,
    # only one will compute, others wait
    return heavy_calculation()
```

## Debugging

```python
# Check if caching is enabled
from django.conf import settings
print(settings.CACHEOPS)

# Bypass cache for testing
DISABLE_CACHE=true python manage.py runserver

# View cache stats (if redis-cli available)
# redis-cli INFO stats
```
