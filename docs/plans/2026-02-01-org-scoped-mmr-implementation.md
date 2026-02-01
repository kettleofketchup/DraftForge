# Organization-Scoped MMR Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move MMR from global user field to organization-scoped membership, with frontend support for editing org-scoped MMR.

**Architecture:** Create `org` and `league` Django apps with OrgUser and LeagueUser models. OrgUser holds the source-of-truth MMR per organization. LeagueUser snapshots MMR when joining a league. Frontend edit modals accept organizationId to scope MMR edits.

**Tech Stack:** Django, Django REST Framework, React, TypeScript, Zod, react-hook-form

---

## Phase 1: Backend - Create New Apps and Models

### Task 1: Create org Django app

**Files:**
- Create: `backend/org/__init__.py`
- Create: `backend/org/apps.py`
- Create: `backend/org/models.py`
- Create: `backend/org/admin.py`
- Create: `backend/org/serializers.py`
- Modify: `backend/app/settings.py` (add to INSTALLED_APPS)

**Step 1: Create app directory structure**

```bash
mkdir -p backend/org
touch backend/org/__init__.py
```

**Step 2: Create apps.py**

```python
# backend/org/apps.py
from django.apps import AppConfig


class OrgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "org"
```

**Step 3: Create models.py with OrgUser**

```python
# backend/org/models.py
from django.db import models
from django.utils import timezone


class OrgUser(models.Model):
    """User's membership and MMR within an organization."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="org_memberships",
        db_index=True,
    )
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="members",
        db_index=True,
    )
    mmr = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    # MMR verification (moved from CustomUser)
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    @property
    def needs_mmr_verification(self) -> bool:
        """Check if user needs to verify their MMR (>30 days since last verification)."""
        if not self.has_active_dota_mmr:
            return False
        if self.dota_mmr_last_verified is None:
            return True
        days_since = (timezone.now() - self.dota_mmr_last_verified).days
        return days_since > 30

    class Meta:
        unique_together = ["user", "organization"]
        verbose_name = "Organization User"
        verbose_name_plural = "Organization Users"

    def __str__(self):
        return f"{self.user.username} @ {self.organization.name} (MMR: {self.mmr})"
```

**Step 4: Create admin.py**

```python
# backend/org/admin.py
from django.contrib import admin
from .models import OrgUser


@admin.register(OrgUser)
class OrgUserAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "mmr", "joined_at", "has_active_dota_mmr"]
    list_filter = ["organization", "has_active_dota_mmr"]
    search_fields = ["user__username", "user__nickname", "organization__name"]
    raw_id_fields = ["user", "organization"]
```

**Step 5: Add to INSTALLED_APPS**

Modify `backend/app/settings.py`:
```python
INSTALLED_APPS = [
    # ... existing apps
    "org",
]
```

**Step 6: Create initial migration**

```bash
just py::manage makemigrations org
```

**Step 7: Commit**

```bash
git add backend/org backend/app/settings.py
git commit -m "feat(org): create org app with OrgUser model"
```

---

### Task 2: Create league Django app

**Files:**
- Create: `backend/league/__init__.py`
- Create: `backend/league/apps.py`
- Create: `backend/league/models.py`
- Create: `backend/league/admin.py`
- Create: `backend/league/serializers.py`
- Modify: `backend/app/settings.py` (add to INSTALLED_APPS)

**Step 1: Create app directory structure**

```bash
mkdir -p backend/league
touch backend/league/__init__.py
```

**Step 2: Create apps.py**

```python
# backend/league/apps.py
from django.apps import AppConfig


class LeaguePlayerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "league"
```

**Step 3: Create models.py with LeagueUser**

```python
# backend/league/models.py
from django.db import models


class LeagueUser(models.Model):
    """User's membership in a league, tied to their org membership."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True,
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True,
    )
    league = models.ForeignKey(
        "app.League",
        on_delete=models.CASCADE,
        related_name="members",
    )
    mmr = models.IntegerField(default=0, db_index=True)  # Snapshot from org_user.mmr
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "league"]
        verbose_name = "League User"
        verbose_name_plural = "League Users"

    def __str__(self):
        return f"{self.user.username} in {self.league.name} (MMR: {self.mmr})"
```

**Step 4: Create admin.py**

```python
# backend/league/admin.py
from django.contrib import admin
from .models import LeagueUser


@admin.register(LeagueUser)
class LeagueUserAdmin(admin.ModelAdmin):
    list_display = ["user", "league", "mmr", "org_user", "joined_at"]
    list_filter = ["league"]
    search_fields = ["user__username", "user__nickname", "league__name"]
    raw_id_fields = ["user", "org_user", "league"]
```

**Step 5: Add to INSTALLED_APPS**

Modify `backend/app/settings.py`:
```python
INSTALLED_APPS = [
    # ... existing apps
    "org",
    "league",
]
```

**Step 6: Create initial migration**

```bash
just py::manage makemigrations league
```

**Step 7: Commit**

```bash
git add backend/league backend/app/settings.py
git commit -m "feat(league): create league app with LeagueUser model"
```

---

## Phase 2: Data Migrations

### Task 3: Migrate all users to OrgUser

**Files:**
- Create: `backend/org/migrations/0002_populate_org_users.py`

**Step 1: Create data migration**

```bash
just py::manage makemigrations org --empty --name populate_org_users
```

**Step 2: Write migration code**

```python
# backend/org/migrations/0002_populate_org_users.py
from django.db import migrations


def migrate_users_to_org(apps, schema_editor):
    """Create OrgUser for ALL users with Organization pk=1."""
    CustomUser = apps.get_model("app", "CustomUser")
    OrgUser = apps.get_model("org", "OrgUser")
    Organization = apps.get_model("app", "Organization")

    try:
        org = Organization.objects.get(pk=1)
    except Organization.DoesNotExist:
        # No organization with pk=1, skip migration
        return

    for user in CustomUser.objects.all():
        OrgUser.objects.get_or_create(
            user=user,
            organization=org,
            defaults={
                "mmr": user.mmr or 0,
                "has_active_dota_mmr": getattr(user, "has_active_dota_mmr", False),
                "dota_mmr_last_verified": getattr(user, "dota_mmr_last_verified", None),
            },
        )


def reverse_migration(apps, schema_editor):
    """Delete all OrgUser records."""
    OrgUser = apps.get_model("org", "OrgUser")
    OrgUser.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("org", "0001_initial"),
        ("app", "0077_add_discord_server_id_to_organization"),
    ]

    operations = [
        migrations.RunPython(migrate_users_to_org, reverse_migration),
    ]
```

**Step 3: Run migration**

```bash
just db::migrate::all
```

**Step 4: Verify migration**

```bash
just py::manage shell -c "from org.models import OrgUser; print(f'OrgUser count: {OrgUser.objects.count()}')"
```

**Step 5: Commit**

```bash
git add backend/org/migrations/
git commit -m "feat(org): migrate all users to OrgUser (org pk=1)"
```

---

### Task 4: Migrate tournament users to LeagueUser

**Files:**
- Create: `backend/league/migrations/0002_populate_league_users.py`

**Step 1: Create data migration**

```bash
just py::manage makemigrations league --empty --name populate_league_users
```

**Step 2: Write migration code**

```python
# backend/league/migrations/0002_populate_league_users.py
from django.db import migrations


def migrate_tournament_users_to_league_users(apps, schema_editor):
    """Create LeagueUser for all existing tournament users."""
    Tournament = apps.get_model("app", "Tournament")
    OrgUser = apps.get_model("org", "OrgUser")
    LeagueUser = apps.get_model("league", "LeagueUser")

    for tournament in Tournament.objects.select_related("league").prefetch_related("users"):
        league = tournament.league
        if not league:
            continue

        # Get first organization from league
        org = league.organizations.first()
        if not org:
            continue

        for user in tournament.users.all():
            try:
                org_user = OrgUser.objects.get(user=user, organization=org)
            except OrgUser.DoesNotExist:
                # Create OrgUser if missing
                org_user = OrgUser.objects.create(
                    user=user,
                    organization=org,
                    mmr=user.mmr or 0,
                )

            LeagueUser.objects.get_or_create(
                user=user,
                league=league,
                defaults={
                    "org_user": org_user,
                    "mmr": org_user.mmr,
                },
            )


def reverse_migration(apps, schema_editor):
    """Delete all LeagueUser records."""
    LeagueUser = apps.get_model("league", "LeagueUser")
    LeagueUser.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0001_initial"),
        ("org", "0002_populate_org_users"),
        ("app", "0077_add_discord_server_id_to_organization"),
    ]

    operations = [
        migrations.RunPython(migrate_tournament_users_to_league_users, reverse_migration),
    ]
```

**Step 3: Run migration**

```bash
just db::migrate::all
```

**Step 4: Verify migration**

```bash
just py::manage shell -c "from league.models import LeagueUser; print(f'LeagueUser count: {LeagueUser.objects.count()}')"
```

**Step 5: Commit**

```bash
git add backend/league/migrations/
git commit -m "feat(league): migrate tournament users to LeagueUser"
```

---

### Task 5: Remove MMR fields from CustomUser

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/migrations/XXXX_remove_user_mmr_fields.py`

**Step 1: Remove fields from CustomUser model**

In `backend/app/models.py`, remove from `CustomUser` class:
- `mmr = models.IntegerField(null=True, blank=True)`
- `league_mmr = models.IntegerField(null=True, blank=True)`
- `has_active_dota_mmr = models.BooleanField(default=False)`
- `dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)`
- `needs_mmr_verification` property

**Step 2: Create migration**

```bash
just py::manage makemigrations app --name remove_user_mmr_fields
```

**Step 3: Run migration**

```bash
just db::migrate::all
```

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat(app): remove mmr fields from CustomUser"
```

---

## Phase 3: Backend Serializers and Views

### Task 6: Create OrgUser serializer

**Files:**
- Modify: `backend/org/serializers.py`

**Step 1: Create OrgUserSerializer**

```python
# backend/org/serializers.py
from rest_framework import serializers
from .models import OrgUser
from app.serializers import PositionsSerializer


class OrgUserSerializer(serializers.ModelSerializer):
    """Returns user data with org-scoped MMR. Same schema as TournamentUserSerializer."""

    id = serializers.IntegerField(read_only=True)  # OrgUser's pk (for PATCH requests)
    pk = serializers.IntegerField(source="user.pk", read_only=True)  # User's pk
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    discordId = serializers.CharField(source="user.discordId", read_only=True)
    positions = PositionsSerializer(source="user.positions", read_only=True)
    steamid = serializers.IntegerField(source="user.steamid", read_only=True)
    steam_account_id = serializers.IntegerField(source="user.steam_account_id", read_only=True)
    avatarUrl = serializers.CharField(source="user.avatarUrl", read_only=True)
    mmr = serializers.IntegerField(read_only=True)  # From OrgUser.mmr

    class Meta:
        model = OrgUser
        fields = (
            "id",
            "pk",
            "username",
            "nickname",
            "avatar",
            "discordId",
            "positions",
            "steamid",
            "steam_account_id",
            "avatarUrl",
            "mmr",
        )


class OrgUserWriteSerializer(serializers.ModelSerializer):
    """Serializer for updating OrgUser MMR."""

    class Meta:
        model = OrgUser
        fields = ("mmr", "has_active_dota_mmr", "dota_mmr_last_verified")
```

**Step 2: Commit**

```bash
git add backend/org/serializers.py
git commit -m "feat(org): add OrgUserSerializer"
```

---

### Task 7: Update tournament serializers to use OrgUser

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Update TournamentSerializerBase**

Find `TournamentSerializerBase` in `backend/app/serializers.py` and update:

```python
class TournamentSerializerBase(serializers.ModelSerializer):
    users = serializers.SerializerMethodField()
    captains = serializers.SerializerMethodField()
    tournament_type = serializers.CharField(read_only=False)

    def get_users(self, tournament):
        """Return users with org-scoped MMR."""
        from org.models import OrgUser
        from org.serializers import OrgUserSerializer

        league = tournament.league
        if not league:
            return TournamentUserSerializer(tournament.users.all(), many=True).data

        org = league.organizations.first()
        if not org:
            return TournamentUserSerializer(tournament.users.all(), many=True).data

        org_users = OrgUser.objects.filter(
            user__in=tournament.users.all(),
            organization=org,
        ).select_related("user", "user__positions")

        return OrgUserSerializer(org_users, many=True).data

    def get_captains(self, tournament):
        """Return captains with org-scoped MMR."""
        from org.models import OrgUser
        from org.serializers import OrgUserSerializer

        league = tournament.league
        if not league:
            return TournamentUserSerializer(tournament.captains.all(), many=True).data

        org = league.organizations.first()
        if not org:
            return TournamentUserSerializer(tournament.captains.all(), many=True).data

        org_users = OrgUser.objects.filter(
            user__in=tournament.captains.all(),
            organization=org,
        ).select_related("user", "user__positions")

        return OrgUserSerializer(org_users, many=True).data

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "captains",
            "tournament_type",
        )
```

**Step 2: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat(app): update tournament serializers to use OrgUser MMR"
```

---

### Task 8: Create OrgUser API endpoints

**Files:**
- Create: `backend/org/views.py`
- Create: `backend/org/urls.py`
- Modify: `backend/app/urls.py`

**Step 1: Create views.py**

```python
# backend/org/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from app.permissions import IsStaff
from app.models import Organization
from .models import OrgUser
from .serializers import OrgUserSerializer, OrgUserWriteSerializer


class OrgUserViewSet(viewsets.ModelViewSet):
    """ViewSet for OrgUser management."""

    serializer_class = OrgUserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = OrgUser.objects.select_related("user", "user__positions", "organization")
        org_id = self.request.query_params.get("organization")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        return queryset

    def get_permissions(self):
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsStaff()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return OrgUserWriteSerializer
        return OrgUserSerializer

    @action(detail=False, methods=["get"])
    def by_user_and_org(self, request):
        """Get OrgUser by user_id and organization_id."""
        user_id = request.query_params.get("user_id")
        org_id = request.query_params.get("organization_id")

        if not user_id or not org_id:
            return Response(
                {"error": "user_id and organization_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org_user = get_object_or_404(
            OrgUser.objects.select_related("user", "user__positions"),
            user_id=user_id,
            organization_id=org_id,
        )
        return Response(OrgUserSerializer(org_user).data)

    @action(detail=False, methods=["post"])
    def get_or_create(self, request):
        """Get or create OrgUser for user in organization."""
        user_id = request.data.get("user_id")
        org_id = request.data.get("organization_id")

        if not user_id or not org_id:
            return Response(
                {"error": "user_id and organization_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = get_object_or_404(Organization, pk=org_id)
        org_user, created = OrgUser.objects.get_or_create(
            user_id=user_id,
            organization=org,
            defaults={"mmr": 0},
        )

        return Response(
            OrgUserSerializer(org_user).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
```

**Step 2: Create urls.py**

```python
# backend/org/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrgUserViewSet

router = DefaultRouter()
router.register(r"org-users", OrgUserViewSet, basename="org-user")

urlpatterns = [
    path("", include(router.urls)),
]
```

**Step 3: Add to main urls.py**

In `backend/app/urls.py`, add:
```python
urlpatterns = [
    # ... existing patterns
    path("api/", include("org.urls")),
]
```

**Step 4: Commit**

```bash
git add backend/org/views.py backend/org/urls.py backend/app/urls.py
git commit -m "feat(org): add OrgUser API endpoints"
```

---

### Task 8.1: Update shuffle_draft.py to use OrgUser MMR

**Files:**
- Modify: `backend/app/functions/shuffle_draft.py`

**Step 1: Update get_team_total_mmr function**

```python
# backend/app/functions/shuffle_draft.py
def get_team_total_mmr(team, org=None):
    """Calculate total MMR for a team using org-scoped MMR."""
    from org.models import OrgUser

    if not org:
        # Fallback to 0 if no org context
        return 0

    # Get captain's MMR
    try:
        captain_org_user = OrgUser.objects.get(user=team.captain, organization=org)
        total = captain_org_user.mmr
    except OrgUser.DoesNotExist:
        total = 0

    # Get members' MMR
    member_ids = team.members.exclude(id=team.captain_id).values_list('id', flat=True)
    member_mmrs = OrgUser.objects.filter(
        user_id__in=member_ids,
        organization=org
    ).values_list('mmr', flat=True)

    total += sum(member_mmrs)
    return total
```

**Step 2: Commit**

```bash
git add backend/app/functions/shuffle_draft.py
git commit -m "feat(app): update shuffle_draft to use OrgUser MMR"
```

---

### Task 8.2: Update TeamSerializer.get_total_mmr

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Update get_total_mmr method**

Find `TeamSerializer` and update `get_total_mmr`:

```python
class TeamSerializer(serializers.ModelSerializer):
    # ... existing fields

    def get_total_mmr(self, team):
        """Calculate total MMR using org-scoped MMR."""
        from org.models import OrgUser

        # Get org from tournament's league
        tournament = team.tournament
        league = tournament.league if tournament else None
        org = league.organizations.first() if league else None

        if not org:
            return 0

        # Get all team member IDs (captain + members)
        member_ids = [team.captain_id] + list(
            team.members.exclude(id=team.captain_id).values_list('id', flat=True)
        )

        # Sum MMR from OrgUser
        total = OrgUser.objects.filter(
            user_id__in=member_ids,
            organization=org
        ).aggregate(total=models.Sum('mmr'))['total'] or 0

        return total
```

**Step 2: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat(app): update TeamSerializer to use OrgUser MMR"
```

---

### Task 8.3: Update match_finalization.py

**Files:**
- Modify: `backend/app/services/match_finalization.py`

**Step 1: Update LeagueRating creation to use OrgUser MMR**

Find where `LeagueRating` is created and update `base_mmr` source:

```python
# When creating LeagueRating for a player
from org.models import OrgUser

def get_or_create_league_rating(player, league):
    """Get or create LeagueRating with base_mmr from OrgUser."""
    org = league.organizations.first()

    # Get base MMR from OrgUser
    base_mmr = 0
    if org:
        try:
            org_user = OrgUser.objects.get(user=player, organization=org)
            base_mmr = org_user.mmr
        except OrgUser.DoesNotExist:
            pass

    rating, created = LeagueRating.objects.get_or_create(
        league=league,
        player=player,
        defaults={'base_mmr': base_mmr}
    )
    return rating
```

**Step 2: Commit**

```bash
git add backend/app/services/match_finalization.py
git commit -m "feat(app): update match_finalization to use OrgUser MMR"
```

---

### Task 8.4: Update mmr_calculation.py

**Files:**
- Modify: `backend/steam/functions/mmr_calculation.py`

**Step 1: Update to work with OrgUser instead of CustomUser.mmr**

This file manages `league_mmr` which is being removed. Update to work with `LeagueUser.mmr`:

```python
# backend/steam/functions/mmr_calculation.py
from org.models import OrgUser
from league.models import LeagueUser

def update_user_league_mmr(user, league, new_mmr):
    """Update user's MMR in a league context."""
    org = league.organizations.first()
    if not org:
        return

    # Get or create OrgUser
    org_user, _ = OrgUser.objects.get_or_create(
        user=user,
        organization=org,
        defaults={'mmr': 0}
    )

    # Get or create LeagueUser
    league_user, _ = LeagueUser.objects.get_or_create(
        user=user,
        org_user=org_user,
        league=league,
        defaults={'mmr': org_user.mmr}
    )

    # Update league-specific MMR
    league_user.mmr = new_mmr
    league_user.save()
```

**Step 2: Commit**

```bash
git add backend/steam/functions/mmr_calculation.py
git commit -m "feat(steam): update mmr_calculation to use OrgUser/LeagueUser"
```

---

### Task 8.5: Update TournamentUserSerializer to include league_mmr

**Files:**
- Modify: `backend/org/serializers.py`

**Step 1: Update OrgUserSerializer to include league_mmr**

```python
# backend/org/serializers.py
class OrgUserSerializer(serializers.ModelSerializer):
    """Returns user data with org-scoped MMR and league MMR."""

    id = serializers.IntegerField(read_only=True)  # OrgUser's pk
    pk = serializers.IntegerField(source="user.pk", read_only=True)  # User's pk
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    discordId = serializers.CharField(source="user.discordId", read_only=True)
    positions = PositionsSerializer(source="user.positions", read_only=True)
    steamid = serializers.IntegerField(source="user.steamid", read_only=True)
    steam_account_id = serializers.IntegerField(source="user.steam_account_id", read_only=True)
    avatarUrl = serializers.CharField(source="user.avatarUrl", read_only=True)
    mmr = serializers.IntegerField(read_only=True)  # From OrgUser.mmr
    league_mmr = serializers.SerializerMethodField()  # From LeagueUser.mmr

    def get_league_mmr(self, org_user):
        """Get league MMR if league context is provided."""
        league_id = self.context.get('league_id')
        if not league_id:
            return None

        from league.models import LeagueUser
        try:
            league_user = LeagueUser.objects.get(
                org_user=org_user,
                league_id=league_id
            )
            return league_user.mmr
        except LeagueUser.DoesNotExist:
            return None

    class Meta:
        model = OrgUser
        fields = (
            "id",
            "pk",
            "username",
            "nickname",
            "avatar",
            "discordId",
            "positions",
            "steamid",
            "steam_account_id",
            "avatarUrl",
            "mmr",
            "league_mmr",
        )
```

**Step 2: Update TournamentSerializerBase to pass league context**

```python
def get_users(self, tournament):
    """Return users with org-scoped MMR and league MMR."""
    from org.models import OrgUser
    from org.serializers import OrgUserSerializer

    league = tournament.league
    if not league:
        return TournamentUserSerializer(tournament.users.all(), many=True).data

    org = league.organizations.first()
    if not org:
        return TournamentUserSerializer(tournament.users.all(), many=True).data

    org_users = OrgUser.objects.filter(
        user__in=tournament.users.all(),
        organization=org,
    ).select_related("user", "user__positions")

    # Pass league_id in context for league_mmr lookup
    return OrgUserSerializer(
        org_users,
        many=True,
        context={'league_id': league.id}
    ).data
```

**Step 3: Commit**

```bash
git add backend/org/serializers.py backend/app/serializers.py
git commit -m "feat(org): add league_mmr to OrgUserSerializer"
```

---

## Phase 4: Frontend Updates

### Task 9: Add OrgUser TypeScript types and API

**Files:**
- Create: `frontend/app/components/org/types.ts`
- Create: `frontend/app/components/org/api.ts`
- Modify: `frontend/app/components/user/schemas.ts`

**Step 1: Create org types**

```typescript
// frontend/app/components/org/types.ts
import { z } from "zod";
import { PositionSchema } from "../user/schemas";

export const OrgUserSchema = z.object({
  id: z.number(),  // OrgUser pk (for PATCH requests)
  pk: z.number(),  // User pk
  username: z.string(),
  nickname: z.string().nullable().optional(),
  avatar: z.string().nullable().optional(),
  discordId: z.string().nullable().optional(),
  positions: PositionSchema.optional(),
  steamid: z.number().nullable().optional(),
  steam_account_id: z.number().nullable().optional(),
  avatarUrl: z.string().nullable().optional(),
  mmr: z.number(),  // Org-scoped MMR
  league_mmr: z.number().nullable().optional(),  // League-scoped MMR
});

export type OrgUserType = z.infer<typeof OrgUserSchema>;

export interface OrgUserUpdatePayload {
  mmr?: number;
  has_active_dota_mmr?: boolean;
}
```

**Step 2: Create org API functions**

```typescript
// frontend/app/components/org/api.ts
import { OrgUserType, OrgUserUpdatePayload } from "./types";

const API_BASE = "/api/org-users";

export async function getOrgUser(userId: number, organizationId: number): Promise<OrgUserType> {
  const response = await fetch(
    `${API_BASE}/by_user_and_org/?user_id=${userId}&organization_id=${organizationId}`
  );
  if (!response.ok) throw new Error("Failed to fetch org user");
  return response.json();
}

export async function updateOrgUser(
  orgUserId: number,
  data: OrgUserUpdatePayload
): Promise<OrgUserType> {
  const response = await fetch(`${API_BASE}/${orgUserId}/`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error("Failed to update org user");
  return response.json();
}

export async function getOrCreateOrgUser(
  userId: number,
  organizationId: number
): Promise<OrgUserType> {
  const response = await fetch(`${API_BASE}/get_or_create/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, organization_id: organizationId }),
  });
  if (!response.ok) throw new Error("Failed to get or create org user");
  return response.json();
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/org/
git commit -m "feat(frontend): add OrgUser types and API"
```

---

### Task 10: Update UserEditModal to accept organizationId

**Files:**
- Modify: `frontend/app/components/user/userCard/editModal.tsx`
- Modify: `frontend/app/components/user/userCard/editForm.tsx`

**Step 1: Update editModal.tsx**

Update `UserEditModal` and `UserEditModalDialog` to accept `organizationId` prop:

```typescript
// frontend/app/components/user/userCard/editModal.tsx
import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { Pencil } from "lucide-react";
import { UserEditForm } from "./editForm";
import { UserType } from "../types";
import { getOrgUser, updateOrgUser } from "../../org/api";
import { OrgUserType } from "../../org/types";

interface UserEditModalProps {
  user: UserType;
  organizationId: number;
  onSave?: (updatedUser: UserType) => void;
}

export function UserEditModal({ user, organizationId, onSave }: UserEditModalProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button variant="ghost" size="icon" onClick={() => setOpen(true)}>
        <Pencil className="h-4 w-4" />
      </Button>
      <UserEditModalDialog
        user={user}
        organizationId={organizationId}
        open={open}
        onOpenChange={setOpen}
        onSave={onSave}
      />
    </>
  );
}

interface UserEditModalDialogProps {
  user: UserType;
  organizationId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (updatedUser: UserType) => void;
}

export function UserEditModalDialog({
  user,
  organizationId,
  open,
  onOpenChange,
  onSave,
}: UserEditModalDialogProps) {
  const [orgUser, setOrgUser] = useState<OrgUserType | null>(null);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    nickname: user.nickname || "",
    mmr: 0,
    steamid: user.steamid || null,
    positions: user.positions,
  });

  useEffect(() => {
    if (open && organizationId) {
      setLoading(true);
      getOrgUser(user.pk!, organizationId)
        .then((data) => {
          setOrgUser(data);
          setFormData((prev) => ({ ...prev, mmr: data.mmr }));
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [open, user.pk, organizationId]);

  const handleSave = async () => {
    if (!orgUser) return;

    try {
      // Update OrgUser MMR
      await updateOrgUser(orgUser.pk, { mmr: formData.mmr });

      // Update user profile (nickname, positions, etc.)
      // ... existing user update logic

      onSave?.({ ...user, mmr: formData.mmr });
      onOpenChange(false);
    } catch (error) {
      console.error("Failed to save:", error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit User: {user.nickname || user.username}</DialogTitle>
        </DialogHeader>
        {loading ? (
          <div>Loading...</div>
        ) : (
          <UserEditForm
            formData={formData}
            setFormData={setFormData}
            onSave={handleSave}
            onCancel={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/user/userCard/editModal.tsx
git commit -m "feat(frontend): update UserEditModal to use organizationId"
```

---

### Task 11: Update UserCard to pass organizationId

**Files:**
- Modify: `frontend/app/components/user/userCard.tsx`

**Step 1: Update UserCard props and edit modal usage**

Add `organizationId` prop to `UserCard`:

```typescript
interface UserCardProps {
  user: UserType;
  organizationId?: number;
  deleteButtonType?: "tournament" | "team" | "none";
  onDelete?: () => void;
  // ... other existing props
}

export function UserCard({
  user,
  organizationId,
  deleteButtonType = "none",
  onDelete,
  // ... other props
}: UserCardProps) {
  // ... existing code

  // Update edit modal usage
  {isStaff && organizationId && (
    <UserEditModal
      user={user}
      organizationId={organizationId}
      onSave={handleUserUpdate}
    />
  )}

  // ... rest of component
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/user/userCard.tsx
git commit -m "feat(frontend): update UserCard to pass organizationId to edit modal"
```

---

### Task 12: Update Tournament PlayersTab to pass organizationId

**Files:**
- Modify: `frontend/app/pages/tournament/tabs/PlayersTab.tsx`

**Step 1: Get organizationId from tournament's league**

```typescript
// In PlayersTab.tsx
import { useTournament } from "~/hooks/useTournament";

export function PlayersTab() {
  const { tournament } = useTournament();

  // Get organization from tournament's league
  const organizationId = tournament?.league?.organizations?.[0]?.pk;

  return (
    <div>
      {tournament?.users?.map((user) => (
        <UserCard
          key={user.pk}
          user={user}
          organizationId={organizationId}
          deleteButtonType="tournament"
          onDelete={() => handleRemoveUser(user.pk)}
        />
      ))}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/pages/tournament/tabs/PlayersTab.tsx
git commit -m "feat(frontend): pass organizationId to UserCard in PlayersTab"
```

---

### Task 13: Update EditProfileModal for own profile

**Files:**
- Modify: `frontend/app/pages/user/EditProfileModal.tsx`

**Step 1: Update to show org-scoped MMR (read-only for own profile)**

The user's own profile modal should show their MMR from their default organization but remain disabled (admin-only editable).

```typescript
// In EditProfileModal.tsx
import { useEffect, useState } from "react";
import { getOrgUser } from "~/components/org/api";

export function EditProfileModal({ user, defaultOrganizationId }) {
  const [orgMmr, setOrgMmr] = useState<number | null>(null);

  useEffect(() => {
    if (defaultOrganizationId && user.pk) {
      getOrgUser(user.pk, defaultOrganizationId)
        .then((data) => setOrgMmr(data.mmr))
        .catch(() => setOrgMmr(null));
    }
  }, [user.pk, defaultOrganizationId]);

  return (
    // ... existing modal structure
    <Input
      type="number"
      value={orgMmr ?? 0}
      disabled
      label="Organization MMR"
      helperText="Contact an admin to update your MMR"
    />
    // ...
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/pages/user/EditProfileModal.tsx
git commit -m "feat(frontend): show org-scoped MMR in EditProfileModal"
```

---

### Task 14: Update UserProfilePage to show org MMR

**Files:**
- Modify: `frontend/app/pages/user/UserProfilePage.tsx`

**Step 1: Fetch and display org-scoped MMR**

```typescript
// In UserProfilePage.tsx
import { useEffect, useState } from "react";
import { getOrgUser } from "~/components/org/api";

export function UserProfilePage() {
  const { user } = useUser();
  const [orgMmr, setOrgMmr] = useState<number | null>(null);

  useEffect(() => {
    if (user?.default_organization && user.pk) {
      getOrgUser(user.pk, user.default_organization)
        .then((data) => setOrgMmr(data.mmr))
        .catch(() => setOrgMmr(null));
    }
  }, [user]);

  return (
    // ... existing structure
    <div>
      <span>Organization MMR:</span>
      <span>{orgMmr ?? "Not set"}</span>
    </div>
    // ...
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/pages/user/UserProfilePage.tsx
git commit -m "feat(frontend): display org-scoped MMR on UserProfilePage"
```

---

## Phase 5: Update Draft Logic

### Task 15: Update draft simulation to use OrgUser MMR

**Files:**
- Modify: `backend/app/models.py` (ShuffleDraftSettings._simulate_draft)

**Step 1: Update _simulate_draft method**

Find `_simulate_draft` in `ShuffleDraftSettings` and update to fetch MMR from OrgUser:

```python
def _simulate_draft(self, draft_style: str) -> dict:
    """Simulate draft picks and return team rosters with MMRs."""
    from org.models import OrgUser

    teams = list(self.tournament.teams.order_by("draft_order"))
    if not teams:
        return {}

    # Get organization from tournament's league
    league = self.tournament.league
    org = league.organizations.first() if league else None

    # Get available players with org-scoped MMR
    if org:
        org_users = {
            ou.user_id: ou.mmr
            for ou in OrgUser.objects.filter(
                user__in=self.tournament.users.exclude(
                    teams_as_captain__tournament=self.tournament
                ),
                organization=org,
            )
        }
        available_players = [
            (user_id, org_users.get(user_id, 0))
            for user_id in self.tournament.users.exclude(
                teams_as_captain__tournament=self.tournament
            ).values_list("id", flat=True)
        ]
        available_players.sort(key=lambda x: -x[1])  # Sort by MMR desc
    else:
        # Fallback: no org, use 0 MMR
        available_players = [
            (user_id, 0)
            for user_id in self.tournament.users.exclude(
                teams_as_captain__tournament=self.tournament
            ).values_list("id", flat=True)
        ]

    # ... rest of simulation logic (unchanged)
```

**Step 2: Update other MMR references in draft logic**

Search for other `user.mmr` or `captain.mmr` references and update similarly.

**Step 3: Commit**

```bash
git add backend/app/models.py
git commit -m "feat(app): update draft simulation to use OrgUser MMR"
```

---

## Phase 6: Testing

### Task 16: Write backend tests for OrgUser

**Files:**
- Create: `backend/org/tests.py`

**Step 1: Create test file**

```python
# backend/org/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from app.models import Organization
from .models import OrgUser

User = get_user_model()


class OrgUserModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.org = Organization.objects.create(name="Test Org")

    def test_create_org_user(self):
        org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.org,
            mmr=5000,
        )
        self.assertEqual(org_user.mmr, 5000)
        self.assertEqual(org_user.user, self.user)
        self.assertEqual(org_user.organization, self.org)

    def test_unique_constraint(self):
        OrgUser.objects.create(user=self.user, organization=self.org, mmr=5000)
        with self.assertRaises(Exception):
            OrgUser.objects.create(user=self.user, organization=self.org, mmr=6000)

    def test_needs_mmr_verification_false_when_inactive(self):
        org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.org,
            has_active_dota_mmr=False,
        )
        self.assertFalse(org_user.needs_mmr_verification)

    def test_needs_mmr_verification_true_when_never_verified(self):
        org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.org,
            has_active_dota_mmr=True,
            dota_mmr_last_verified=None,
        )
        self.assertTrue(org_user.needs_mmr_verification)
```

**Step 2: Run tests**

```bash
just py::test backend/org/tests.py -v
```

**Step 3: Commit**

```bash
git add backend/org/tests.py
git commit -m "test(org): add OrgUser model tests"
```

---

### Task 17: Write backend tests for LeagueUser

**Files:**
- Create: `backend/league/tests.py`

**Step 1: Create test file**

```python
# backend/league/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from app.models import Organization, League
from org.models import OrgUser
from .models import LeagueUser

User = get_user_model()


class LeagueUserModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(name="Test League", steam_league_id=12345)
        self.league.organizations.add(self.org)
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.org,
            mmr=5000,
        )

    def test_create_league_user(self):
        league_user = LeagueUser.objects.create(
            user=self.user,
            org_user=self.org_user,
            league=self.league,
            mmr=self.org_user.mmr,
        )
        self.assertEqual(league_user.mmr, 5000)
        self.assertEqual(league_user.org_user, self.org_user)

    def test_unique_constraint(self):
        LeagueUser.objects.create(
            user=self.user,
            org_user=self.org_user,
            league=self.league,
            mmr=5000,
        )
        with self.assertRaises(Exception):
            LeagueUser.objects.create(
                user=self.user,
                org_user=self.org_user,
                league=self.league,
                mmr=6000,
            )
```

**Step 2: Run tests**

```bash
just py::test backend/league/tests.py -v
```

**Step 3: Commit**

```bash
git add backend/league/tests.py
git commit -m "test(league): add LeagueUser model tests"
```

---

## Final Checklist

- [ ] OrgUser model created with indexes
- [ ] LeagueUser model created with indexes
- [ ] Migration moves all existing users to OrgUser (org pk=1)
- [ ] Migration creates LeagueUser for all existing tournament users
- [ ] CustomUser.mmr and related fields removed
- [ ] OrgUserSerializer returns same schema as TournamentUserSerializer
- [ ] Tournament serializers return MMR from OrgUser
- [ ] OrgUser API endpoints created
- [ ] Frontend OrgUser types and API created
- [ ] UserEditModal accepts organizationId
- [ ] UserCard passes organizationId to edit modal
- [ ] PlayersTab passes organizationId from tournament's league
- [ ] EditProfileModal shows org-scoped MMR (read-only)
- [ ] UserProfilePage displays org-scoped MMR
- [ ] Draft simulation uses OrgUser MMR
- [ ] Backend tests for OrgUser
- [ ] Backend tests for LeagueUser
