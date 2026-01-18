# Organizations & Leagues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Organization and League models with hierarchical permissions, create browsing pages, modernize tournament forms with Zod, and enable steam ID editing on profile.

**Architecture:** New Organization → League → Tournament hierarchy with inherited admin/staff permissions. Frontend uses Zod + React Hook Form for all new forms. Components follow existing patterns with co-located hooks/forms directories.

**Tech Stack:** Django REST Framework, django-cacheops, nh3 (markdown sanitization), React, TypeScript, Zod, React Hook Form, shadcn/ui, Zustand

---

## Prerequisites

### Task 0.1: Install Missing shadcn/ui Components

**Files:**
- Create: `frontend/app/components/ui/textarea.tsx`
- Create: `frontend/app/components/ui/collapsible.tsx`

**Step 1: Add Textarea component**

```bash
cd /home/kettle/git_repos/website/frontend
npx shadcn@latest add textarea
```

If that fails, create manually:

```typescript
// frontend/app/components/ui/textarea.tsx
import * as React from "react"
import { cn } from "~/lib/utils"

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Textarea.displayName = "Textarea"

export { Textarea }
```

**Step 2: Add Collapsible component**

```bash
npx shadcn@latest add collapsible
```

**Step 3: Commit**

```bash
git add frontend/app/components/ui/
git commit -m "chore: add textarea and collapsible shadcn components"
```

---

## Phase 1: Backend Models & Migrations

### Task 1.1: Install nh3 for Markdown Sanitization

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add nh3 dependency**

```bash
cd /home/kettle/git_repos/website
source .venv/bin/activate
poetry add nh3
```

**Step 2: Verify installation**

Run: `poetry show nh3`
Expected: Package info displayed

**Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: add nh3 for markdown sanitization"
```

---

### Task 1.2: Create Organization Model

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/migrations/XXXX_add_organization.py` (auto-generated)

**Step 1: Add import at top of models.py (after `import requests`)**

```python
import nh3
```

**Step 2: Add Organization model after the `CustomUser` class (around line 200)**

```python
class Organization(models.Model):
    """Organization that owns leagues and tournaments."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="", max_length=10000)
    logo = models.URLField(blank=True, default="")
    rules_template = models.TextField(blank=True, default="", max_length=50000)
    admins = models.ManyToManyField(
        "CustomUser",
        related_name="admin_organizations",
        blank=True,
    )
    staff = models.ManyToManyField(
        "CustomUser",
        related_name="staff_organizations",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.name
```

**Note:** Markdown sanitization moved to serializer to avoid double-sanitization on re-save.

**Step 3: Create migration**

Run: `cd /home/kettle/git_repos/website && source .venv/bin/activate && python backend/manage.py makemigrations app --name add_organization`
Expected: Migration file created

**Step 4: Apply migration**

Run: `DISABLE_CACHE=true inv db.migrate.all`
Expected: Applied successfully

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add Organization model"
```

---

### Task 1.3: Create League Model

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/migrations/XXXX_add_league.py` (auto-generated)

**Step 1: Add League model after Organization**

```python
class League(models.Model):
    """League that belongs to an organization, 1:1 with Steam league."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="leagues",
    )
    steam_league_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="", max_length=10000)
    rules = models.TextField(blank=True, default="", max_length=50000)
    prize_pool = models.CharField(max_length=100, blank=True, default="")
    admins = models.ManyToManyField(
        "CustomUser",
        related_name="admin_leagues",
        blank=True,
    )
    staff = models.ManyToManyField(
        "CustomUser",
        related_name="staff_leagues",
        blank=True,
    )
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "League"
        verbose_name_plural = "Leagues"

    def __str__(self):
        return f"{self.name} ({self.steam_league_id})"
```

**Step 2: Create migration**

Run: `python backend/manage.py makemigrations app --name add_league`
Expected: Migration file created

**Step 3: Apply migration**

Run: `DISABLE_CACHE=true inv db.migrate.all`
Expected: Applied successfully

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add League model"
```

---

### Task 1.4: Add Organization default_league and User default_organization

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/migrations/XXXX_add_defaults.py` (auto-generated)

**Step 1: Add default_league to Organization**

Add field to Organization model:

```python
default_league = models.ForeignKey(
    "League",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="default_for_organization",
)
```

**Step 2: Add default_organization to CustomUser**

Add field to CustomUser model (after guildNickname):

```python
default_organization = models.ForeignKey(
    "Organization",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="default_for_users",
)
```

**Step 3: Create migration**

Run: `python backend/manage.py makemigrations app --name add_default_org_league`
Expected: Migration file created

**Step 4: Apply migration**

Run: `DISABLE_CACHE=true inv db.migrate.all`
Expected: Applied successfully

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add default_organization to User and default_league to Organization"
```

---

### Task 1.5: Add League FK to Tournament

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/migrations/XXXX_tournament_league_fk.py` (auto-generated)

**Step 1: Add league FK to Tournament model**

Find the Tournament model and add after `league_id`:

```python
league = models.ForeignKey(
    "League",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="tournaments",
)
```

**Step 2: Create migration**

Run: `python backend/manage.py makemigrations app --name tournament_league_fk`
Expected: Migration file created

**Step 3: Apply migration**

Run: `DISABLE_CACHE=true inv db.migrate.all`
Expected: Applied successfully

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add league FK to Tournament"
```

---

### Task 1.6: Data Migration for Existing Tournaments

**Files:**
- Create: `backend/app/migrations/XXXX_migrate_tournament_leagues.py`

**Step 1: Create data migration file**

```python
# backend/app/migrations/XXXX_migrate_tournament_leagues.py
"""Data migration to link existing tournaments to leagues."""

from django.db import migrations


def migrate_tournaments_to_leagues(apps, schema_editor):
    """
    1. Create default "DTX" Organization
    2. Create League objects for each unique steam league_id
    3. Link existing tournaments to the new League FK
    """
    Organization = apps.get_model("app", "Organization")
    League = apps.get_model("app", "League")
    Tournament = apps.get_model("app", "Tournament")

    # Step 1: Create default organization
    org, _ = Organization.objects.get_or_create(
        name="DTX",
        defaults={"description": "DTX Dota 2 Organization"}
    )

    # Step 2: Get unique league_ids from existing tournaments
    unique_league_ids = (
        Tournament.objects
        .exclude(league_id__isnull=True)
        .values_list("league_id", flat=True)
        .distinct()
    )

    # Step 3: Create League for each unique steam league_id
    league_mapping = {}
    for steam_league_id in unique_league_ids:
        league, _ = League.objects.get_or_create(
            steam_league_id=steam_league_id,
            defaults={
                "organization": org,
                "name": f"League {steam_league_id}",
            }
        )
        league_mapping[steam_league_id] = league

    # Step 4: Link tournaments to leagues
    for tournament in Tournament.objects.exclude(league_id__isnull=True):
        if tournament.league_id in league_mapping:
            tournament.league = league_mapping[tournament.league_id]
            tournament.save(update_fields=["league"])


def reverse_migration(apps, schema_editor):
    """Reverse: Clear league FK on tournaments (preserves org/league objects)."""
    Tournament = apps.get_model("app", "Tournament")
    Tournament.objects.update(league=None)


class Migration(migrations.Migration):
    dependencies = [
        ("app", "XXXX_tournament_league_fk"),  # Replace with actual migration name
    ]

    operations = [
        migrations.RunPython(
            migrate_tournaments_to_leagues,
            reverse_code=reverse_migration,
        ),
    ]
```

**Step 2: Update dependency to match actual migration name**

Edit the file and replace `XXXX_tournament_league_fk` with the actual migration file name from Task 1.5.

**Step 3: Apply migration with cache disabled**

Run: `DISABLE_CACHE=true inv db.migrate.all`
Expected: All tournaments with league_id linked to League objects

**Step 4: Verify migration**

Run: `inv dev.run --service backend --cmd "python manage.py shell -c \"from app.models import Tournament, League; print(f'Leagues: {League.objects.count()}, Linked Tournaments: {Tournament.objects.exclude(league__isnull=True).count()}')\""`

**Step 5: Commit**

```bash
git add backend/app/migrations/
git commit -m "feat: data migration to link existing tournaments to leagues"
```

---

## Phase 2: Backend Serializers

### Task 2.1: Create Organization Serializer

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add imports**

```python
import nh3

from .models import (
    CustomUser,
    Draft,
    DraftRound,
    Game,
    Joke,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
```

**Step 2: Add OrganizationSerializer (after TournamentsSerializer)**

```python
class OrganizationSerializer(serializers.ModelSerializer):
    admins = TournamentUserSerializer(many=True, read_only=True)
    staff = TournamentUserSerializer(many=True, read_only=True)
    admin_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="admins",
        required=False,
    )
    staff_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="staff",
        required=False,
    )
    # Use annotated fields from ViewSet queryset (avoids N+1)
    league_count = serializers.IntegerField(read_only=True)
    tournament_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "pk",
            "name",
            "description",
            "logo",
            "rules_template",
            "admins",
            "staff",
            "admin_ids",
            "staff_ids",
            "default_league",
            "league_count",
            "tournament_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("pk", "created_at", "updated_at", "league_count", "tournament_count")

    def validate_description(self, value):
        """Sanitize markdown to prevent XSS."""
        if value:
            return nh3.clean(value)
        return value

    def validate_rules_template(self, value):
        """Sanitize markdown to prevent XSS."""
        if value:
            return nh3.clean(value)
        return value


class OrganizationsSerializer(serializers.ModelSerializer):
    """Lightweight serializer for organization list view."""

    league_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = ("pk", "name", "logo", "league_count", "created_at")
        read_only_fields = ("pk", "league_count", "created_at")
```

**Step 3: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat: add Organization serializers with nh3 sanitization"
```

---

### Task 2.2: Create League Serializer

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add LeagueSerializer after OrganizationsSerializer**

```python
class LeagueSerializer(serializers.ModelSerializer):
    admins = TournamentUserSerializer(many=True, read_only=True)
    staff = TournamentUserSerializer(many=True, read_only=True)
    admin_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="admins",
        required=False,
    )
    staff_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="staff",
        required=False,
    )
    tournament_count = serializers.IntegerField(read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = League
        fields = (
            "pk",
            "organization",
            "organization_name",
            "steam_league_id",
            "name",
            "description",
            "rules",
            "prize_pool",
            "admins",
            "staff",
            "admin_ids",
            "staff_ids",
            "tournament_count",
            "last_synced",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("pk", "created_at", "updated_at", "tournament_count", "organization_name")

    def validate_description(self, value):
        if value:
            return nh3.clean(value)
        return value

    def validate_rules(self, value):
        if value:
            return nh3.clean(value)
        return value


class LeaguesSerializer(serializers.ModelSerializer):
    """Lightweight serializer for league list view."""

    tournament_count = serializers.IntegerField(read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = League
        fields = (
            "pk",
            "organization",
            "organization_name",
            "steam_league_id",
            "name",
            "tournament_count",
        )
        read_only_fields = ("pk", "tournament_count", "organization_name")
```

**Step 2: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat: add League serializers"
```

---

### Task 2.3: Update TournamentSerializer for League

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add league field to TournamentSerializer**

Find `TournamentSerializer` and add to fields:

```python
league = LeaguesSerializer(read_only=True)
league_id_write = serializers.PrimaryKeyRelatedField(
    queryset=League.objects.all(),
    write_only=True,
    source="league",
    required=False,
    allow_null=True,
)
```

Add `"league"` and `"league_id_write"` to the `fields` tuple.

**Step 2: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat: add league to TournamentSerializer"
```

---

### Task 2.4: Update UserSerializer for default_organization

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add default_organization to UserSerializer**

Find `UserSerializer` and add:

```python
default_organization = serializers.PrimaryKeyRelatedField(
    queryset=Organization.objects.all(),
    required=False,
    allow_null=True,
)
```

Add `"default_organization"` to the `fields` tuple.

**Step 2: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat: add default_organization to UserSerializer"
```

---

## Phase 3: Backend Views & Permissions

### Task 3.1: Create Permission Helpers

**Files:**
- Create: `backend/app/permissions_org.py`

**Step 1: Create permission helpers file**

```python
"""Organization and League permission helpers."""

from rest_framework import permissions


def has_org_admin_access(user, organization):
    """Check if user is org admin or superuser."""
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or organization.admins.filter(pk=user.pk).exists()
    )


def has_org_staff_access(user, organization):
    """Check if user has staff access to org (admin or staff)."""
    if not user.is_authenticated:
        return False
    return (
        has_org_admin_access(user, organization)
        or organization.staff.filter(pk=user.pk).exists()
    )


def has_league_admin_access(user, league):
    """Check if user is league admin, org admin, or superuser."""
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or league.organization.admins.filter(pk=user.pk).exists()
        or league.admins.filter(pk=user.pk).exists()
    )


def has_league_staff_access(user, league):
    """Check if user has staff access to league."""
    if not user.is_authenticated:
        return False
    return (
        has_league_admin_access(user, league)
        or league.organization.staff.filter(pk=user.pk).exists()
        or league.staff.filter(pk=user.pk).exists()
    )


class IsOrgAdmin(permissions.BasePermission):
    """Permission check for organization admin access."""

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return has_org_admin_access(request.user, obj)


class IsLeagueAdmin(permissions.BasePermission):
    """Permission check for league admin access."""

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return has_league_admin_access(request.user, obj)
```

**Step 2: Commit**

```bash
git add backend/app/permissions_org.py
git commit -m "feat: add organization and league permission helpers"
```

---

### Task 3.2: Create Organization ViewSet

**Files:**
- Modify: `backend/app/views_main.py`

**Step 1: Add imports**

```python
from django.db.models import Count

from .models import CustomUser, Draft, DraftRound, Game, League, Organization, Team, Tournament
from .permissions_org import has_org_admin_access, has_league_admin_access, IsOrgAdmin, IsLeagueAdmin
from .serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    LeagueSerializer,
    LeaguesSerializer,
    OrganizationSerializer,
    OrganizationsSerializer,
    TeamSerializer,
    TournamentSerializer,
    TournamentsSerializer,
    UserSerializer,
)
```

**Step 2: Add OrganizationView after existing ViewSets**

```python
class OrganizationView(viewsets.ModelViewSet):
    """Organization CRUD endpoints."""

    queryset = Organization.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return OrganizationsSerializer
        return OrganizationSerializer

    def get_queryset(self):
        """Annotate counts to avoid N+1 queries."""
        return Organization.objects.annotate(
            league_count=Count("leagues", distinct=True),
            tournament_count=Count("leagues__tournaments", distinct=True),
        ).order_by("name")

    def get_permissions(self):
        if self.action in ["create", "destroy"]:
            self.permission_classes = [IsAdminUser]
        elif self.action in ["update", "partial_update"]:
            self.permission_classes = [IsOrgAdmin]
        else:
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        cache_key = f"organization_list:{request.get_full_path()}"

        @cached_as(Organization, League, Tournament, extra=cache_key, timeout=60 * 10)
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"organization_detail:{pk}"

        @cached_as(Organization, League, Tournament, extra=cache_key, timeout=60 * 10)
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)
```

**Step 3: Commit**

```bash
git add backend/app/views_main.py
git commit -m "feat: add Organization ViewSet with annotated queries"
```

---

### Task 3.3: Create League ViewSet

**Files:**
- Modify: `backend/app/views_main.py`

**Step 1: Add LeagueView after OrganizationView**

```python
class LeagueView(viewsets.ModelViewSet):
    """League CRUD endpoints with org filtering."""

    queryset = League.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return LeaguesSerializer
        return LeagueSerializer

    def get_queryset(self):
        """Optimize with select_related and annotations."""
        queryset = League.objects.select_related("organization").annotate(
            tournament_count=Count("tournaments", distinct=True),
        ).order_by("name")

        org_id = self.request.query_params.get("organization")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        return queryset

    def get_permissions(self):
        if self.action == "create":
            self.permission_classes = [IsAuthenticated]
        elif self.action in ["update", "partial_update", "destroy"]:
            self.permission_classes = [IsLeagueAdmin]
        else:
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        org_id = request.data.get("organization")
        if org_id:
            try:
                org = Organization.objects.get(pk=org_id)
                if not has_org_admin_access(request.user, org):
                    return Response(
                        {"error": "Must be organization admin to create league"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Organization.DoesNotExist:
                return Response(
                    {"error": "Organization not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        cache_key = f"league_list:{request.get_full_path()}"

        @cached_as(League, Tournament, Organization, extra=cache_key, timeout=60 * 10)
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"league_detail:{pk}"

        @cached_as(League, Tournament, Organization, extra=cache_key, timeout=60 * 10)
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)
```

**Step 2: Commit**

```bash
git add backend/app/views_main.py
git commit -m "feat: add League ViewSet with optimized queries"
```

---

### Task 3.4: Add URL Routes

**Files:**
- Modify: `backend/app/urls.py`

**Step 1: Add routes to router**

Find the router registration section and add:

```python
router.register(r"organizations", views_main.OrganizationView, basename="organization")
router.register(r"leagues", views_main.LeagueView, basename="league")
```

**Step 2: Commit**

```bash
git add backend/app/urls.py
git commit -m "feat: add organization and league URL routes"
```

---

### Task 3.5: Add Tournament Filtering

**Files:**
- Modify: `backend/app/views_main.py`

**Step 1: Update TournamentView list method**

Find `TournamentView` and update the `list` method to include filter params in cache key. Also add a `get_queryset` method:

```python
def get_queryset(self):
    queryset = Tournament.objects.all().order_by("-date_played")
    org_id = self.request.query_params.get("organization")
    league_id = self.request.query_params.get("league")
    if org_id:
        queryset = queryset.filter(league__organization_id=org_id)
    if league_id:
        queryset = queryset.filter(league_id=league_id)
    return queryset
```

**Note:** The existing `list` method already uses `request.get_full_path()` in cache_key which includes query params.

**Step 2: Commit**

```bash
git add backend/app/views_main.py
git commit -m "feat: add organization and league filtering to tournaments"
```

---

## Phase 4: Backend Tests

### Task 4.1: Create Organization Tests

**Files:**
- Create: `backend/app/tests/test_organization.py`

**Step 1: Create test file**

```python
"""Tests for Organization API endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, Organization


class OrganizationAPITest(TestCase):
    """Test organization API endpoints."""

    def setUp(self):
        """Create test users and organization."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.org_admin = CustomUser.objects.create_user(
            username="orgadmin",
            password="test123",
        )
        self.superuser = CustomUser.objects.create_superuser(
            username="superuser",
            password="test123",
        )
        self.org = Organization.objects.create(
            name="Test Org",
            description="Test Description",
        )
        self.org.admins.add(self.org_admin)
        self.client = APIClient()

    def test_list_organizations_public(self):
        """GET /api/organizations/ is public."""
        response = self.client.get("/api/organizations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_organization_public(self):
        """GET /api/organizations/{id}/ is public."""
        response = self.client.get(f"/api/organizations/{self.org.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Org")

    def test_create_organization_requires_superuser(self):
        """POST /api/organizations/ requires superuser."""
        # Org admin (not superuser) should be denied
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(
            "/api/organizations/",
            {"name": "New Org"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Superuser should succeed
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {"name": "New Org"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_organization_requires_org_admin(self):
        """PATCH /api/organizations/{id}/ requires org admin."""
        # Regular user denied
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/",
            {"name": "Updated Name"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Org admin allowed
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/",
            {"name": "Updated Name"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_markdown_sanitization_script(self):
        """Organization sanitizes script tags."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "XSS Test",
                "description": "<script>alert('xss')</script>Safe text",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("<script>", response.data["description"])
        self.assertIn("Safe text", response.data["description"])

    def test_markdown_sanitization_event_handlers(self):
        """Organization sanitizes event handlers."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "XSS Test 2",
                "description": '<img src="x" onerror="alert(1)">Safe',
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("onerror", response.data["description"])

    def test_markdown_sanitization_javascript_url(self):
        """Organization sanitizes javascript: URLs."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "XSS Test 3",
                "description": '<a href="javascript:alert(1)">Click</a>',
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("javascript:", response.data["description"])
```

**Step 2: Run test to verify**

Run: `inv test.run --cmd 'python manage.py test app.tests.test_organization -v 2'`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/app/tests/test_organization.py
git commit -m "test: add Organization API tests with XSS coverage"
```

---

### Task 4.2: Create League Tests

**Files:**
- Create: `backend/app/tests/test_league.py`

**Step 1: Create test file**

```python
"""Tests for League API endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization


class LeagueAPITest(TestCase):
    """Test league API endpoints."""

    def setUp(self):
        """Create test data."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.org_admin = CustomUser.objects.create_user(
            username="orgadmin",
            password="test123",
        )
        self.league_admin = CustomUser.objects.create_user(
            username="leagueadmin",
            password="test123",
        )
        self.org = Organization.objects.create(name="Test Org")
        self.org.admins.add(self.org_admin)
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name="Test League",
        )
        self.league.admins.add(self.league_admin)
        self.client = APIClient()

    def test_list_leagues_public(self):
        """GET /api/leagues/ is public."""
        response = self.client.get("/api/leagues/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_leagues_by_org(self):
        """GET /api/leagues/?organization={id} filters correctly."""
        other_org = Organization.objects.create(name="Other Org")
        League.objects.create(
            organization=other_org,
            steam_league_id=99999,
            name="Other League",
        )
        response = self.client.get(f"/api/leagues/?organization={self.org.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Test League")

    def test_create_league_requires_org_admin(self):
        """POST /api/leagues/ requires org admin."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/leagues/",
            {
                "organization": self.org.pk,
                "steam_league_id": 54321,
                "name": "New League",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(
            "/api/leagues/",
            {
                "organization": self.org.pk,
                "steam_league_id": 54321,
                "name": "New League",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_league_org_admin_access(self):
        """PATCH allows org admin to update league."""
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"name": "Updated by Org Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_league_league_admin_access(self):
        """PATCH allows league admin to update league."""
        self.client.force_authenticate(user=self.league_admin)
        response = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"name": "Updated by League Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_league_denied_regular_user(self):
        """PATCH denied for regular users."""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"name": "Should Fail"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_org_admin_inherits_league_access(self):
        """Org admin can update any league in their org."""
        new_league = League.objects.create(
            organization=self.org,
            steam_league_id=11111,
            name="Another League",
        )
        # new_league has no admins, but org_admin should still have access
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.patch(
            f"/api/leagues/{new_league.pk}/",
            {"name": "Updated via Org Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
```

**Step 2: Run test to verify**

Run: `inv test.run --cmd 'python manage.py test app.tests.test_league -v 2'`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/app/tests/test_league.py
git commit -m "test: add League API tests"
```

---

## Phase 5: Frontend Types & Schemas

### Task 5.1: Create Organization Types and Schema

**Files:**
- Create: `frontend/app/components/organization/schemas.ts`
- Create: `frontend/app/components/organization/index.ts`

**Step 1: Create directory**

```bash
mkdir -p frontend/app/components/organization/hooks
mkdir -p frontend/app/components/organization/forms
```

**Step 2: Create schemas.ts (single source of truth for types)**

```typescript
import { z } from 'zod';
import type { UserType } from '~/components/user/types';

export const OrganizationSchema = z.object({
  pk: z.number().optional(),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional().default(''),
  logo: z.union([z.string().url(), z.literal('')]).optional().default(''),
  rules_template: z.string().optional().default(''),
  admin_ids: z.array(z.number()).optional(),
  staff_ids: z.array(z.number()).optional(),
  default_league: z.number().nullable().optional(),
  league_count: z.number().optional(),
  tournament_count: z.number().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export const CreateOrganizationSchema = OrganizationSchema.pick({
  name: true,
  description: true,
  logo: true,
  rules_template: true,
});

// Inferred types from Zod schemas
export type OrganizationType = z.infer<typeof OrganizationSchema> & {
  admins?: UserType[];
  staff?: UserType[];
};
export type CreateOrganizationInput = z.infer<typeof CreateOrganizationSchema>;
export type OrganizationsType = OrganizationType[];
```

**Step 3: Create index.ts**

```typescript
export { OrganizationSchema, CreateOrganizationSchema } from './schemas';
export type { OrganizationType, OrganizationsType, CreateOrganizationInput } from './schemas';
```

**Step 4: Commit**

```bash
git add frontend/app/components/organization/
git commit -m "feat: add Organization types and schemas"
```

---

### Task 5.2: Create League Types and Schema

**Files:**
- Create: `frontend/app/components/league/schemas.ts`
- Create: `frontend/app/components/league/index.ts`

**Step 1: Create directory**

```bash
mkdir -p frontend/app/components/league/hooks
mkdir -p frontend/app/components/league/forms
```

**Step 2: Create schemas.ts**

```typescript
import { z } from 'zod';
import type { UserType } from '~/components/user/types';

export const LeagueSchema = z.object({
  pk: z.number().optional(),
  organization: z.number(),
  organization_name: z.string().optional(),
  steam_league_id: z.number().min(1, 'Steam League ID is required'),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional().default(''),
  rules: z.string().optional().default(''),
  prize_pool: z.string().optional().default(''),
  admin_ids: z.array(z.number()).optional(),
  staff_ids: z.array(z.number()).optional(),
  tournament_count: z.number().optional(),
  last_synced: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export const CreateLeagueSchema = LeagueSchema.pick({
  organization: true,
  steam_league_id: true,
  name: true,
  description: true,
  rules: true,
});

export type LeagueType = z.infer<typeof LeagueSchema> & {
  admins?: UserType[];
  staff?: UserType[];
};
export type CreateLeagueInput = z.infer<typeof CreateLeagueSchema>;
export type LeaguesType = LeagueType[];
```

**Step 3: Create index.ts**

```typescript
export { LeagueSchema, CreateLeagueSchema } from './schemas';
export type { LeagueType, LeaguesType, CreateLeagueInput } from './schemas';
```

**Step 4: Commit**

```bash
git add frontend/app/components/league/
git commit -m "feat: add League types and schemas"
```

---

## Phase 6: Frontend API Layer

### Task 6.1: Add Organization API Functions

**Files:**
- Modify: `frontend/app/components/api/api.tsx`

**Step 1: Add imports**

```typescript
import type { OrganizationType, OrganizationsType } from '~/components/organization/schemas';
import type { LeagueType, LeaguesType } from '~/components/league/schemas';
```

**Step 2: Add organization API functions**

```typescript
// Organization API
export async function getOrganizations(): Promise<OrganizationsType> {
  const response = await axios.get<OrganizationsType>('/organizations/');
  return response.data;
}

export async function fetchOrganization(pk: number): Promise<OrganizationType> {
  const response = await axios.get<OrganizationType>(`/organizations/${pk}/`);
  return response.data;
}

export async function createOrganization(
  data: Partial<OrganizationType>,
): Promise<OrganizationType> {
  const response = await axios.post<OrganizationType>('/organizations/', data);
  return response.data;
}

export async function updateOrganization(
  pk: number,
  data: Partial<OrganizationType>,
): Promise<OrganizationType> {
  const response = await axios.patch<OrganizationType>(
    `/organizations/${pk}/`,
    data,
  );
  return response.data;
}

export async function deleteOrganization(pk: number): Promise<void> {
  await axios.delete(`/organizations/${pk}/`);
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/api/api.tsx
git commit -m "feat: add Organization API functions"
```

---

### Task 6.2: Add League API Functions

**Files:**
- Modify: `frontend/app/components/api/api.tsx`

**Step 1: Add league API functions**

```typescript
// League API
export async function getLeagues(organizationId?: number): Promise<LeaguesType> {
  const params = organizationId ? `?organization=${organizationId}` : '';
  const response = await axios.get<LeaguesType>(`/leagues/${params}`);
  return response.data;
}

export async function fetchLeague(pk: number): Promise<LeagueType> {
  const response = await axios.get<LeagueType>(`/leagues/${pk}/`);
  return response.data;
}

export async function createLeague(
  data: Partial<LeagueType>,
): Promise<LeagueType> {
  const response = await axios.post<LeagueType>('/leagues/', data);
  return response.data;
}

export async function updateLeague(
  pk: number,
  data: Partial<LeagueType>,
): Promise<LeagueType> {
  const response = await axios.patch<LeagueType>(`/leagues/${pk}/`, data);
  return response.data;
}

export async function deleteLeague(pk: number): Promise<void> {
  await axios.delete(`/leagues/${pk}/`);
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/api/api.tsx
git commit -m "feat: add League API functions"
```

---

### Task 6.3: Update Tournament API for Filtering

**Files:**
- Modify: `frontend/app/components/api/api.tsx`

**Step 1: Update getTournaments to accept filters**

Replace existing `getTournaments`:

```typescript
export async function getTournaments(filters?: {
  organizationId?: number;
  leagueId?: number;
}): Promise<TournamentsType> {
  const params = new URLSearchParams();
  if (filters?.organizationId) {
    params.append('organization', filters.organizationId.toString());
  }
  if (filters?.leagueId) {
    params.append('league', filters.leagueId.toString());
  }
  const queryString = params.toString() ? `?${params.toString()}` : '';
  const response = await axios.get<TournamentsType>(`/tournaments/${queryString}`);
  return response.data as TournamentsType;
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/api/api.tsx
git commit -m "feat: add tournament filtering by org and league"
```

---

## Phase 7: Frontend Zustand Store

### Task 7.1: Add Organization State to Store

**Files:**
- Modify: `frontend/app/store/userStore.ts`

**Step 1: Add imports**

```typescript
import {
  fetchCurrentUser,
  fetchDraft,
  fetchOrganization,
  fetchTournament,
  fetchUsers,
  get_dtx_members,
  getGames,
  getLeagues,
  getOrganizations,
  getTeams,
  getTournaments,
  getTournamentsBasic,
} from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
```

**Step 2: Add to interface**

Add to `UserState` interface:

```typescript
// Organizations
organizations: OrganizationType[];
organization: OrganizationType | null;
setOrganizations: (orgs: OrganizationType[]) => void;
setOrganization: (org: OrganizationType | null) => void;
getOrganizations: () => Promise<void>;
getOrganization: (pk: number) => Promise<void>;

// Leagues
leagues: LeagueType[];
league: LeagueType | null;
setLeagues: (leagues: LeagueType[]) => void;
setLeague: (league: LeagueType | null) => void;
getLeagues: (orgId?: number) => Promise<void>;
```

**Step 3: Add implementations**

Add in the store implementation:

```typescript
// Organizations
organizations: [] as OrganizationType[],
organization: null,
setOrganizations: (orgs) => set({ organizations: orgs }),
setOrganization: (org) => set({ organization: org }),
getOrganizations: async () => {
  try {
    const response = await getOrganizations();
    set({ organizations: response });
    log.debug('Organizations fetched successfully:', response);
  } catch (error) {
    log.error('Error fetching organizations:', error);
  }
},
getOrganization: async (pk: number) => {
  try {
    const response = await fetchOrganization(pk);
    set({ organization: response });
    log.debug('Organization fetched successfully:', response);
  } catch (error) {
    log.error('Error fetching organization:', error);
    set({ organization: null });
  }
},

// Leagues
leagues: [] as LeagueType[],
league: null,
setLeagues: (leagues) => set({ leagues }),
setLeague: (league) => set({ league }),
getLeagues: async (orgId?: number) => {
  try {
    const response = await getLeagues(orgId);
    set({ leagues: response });
    log.debug('Leagues fetched successfully:', response);
  } catch (error) {
    log.error('Error fetching leagues:', error);
  }
},
```

**Step 4: DO NOT add to partialize**

Keep the partialize function unchanged - do NOT persist organizations/leagues to avoid stale data:

```typescript
partialize: (state) => ({
  currentUser: state.currentUser,
  users: state.users,
}),
```

**Step 5: Commit**

```bash
git add frontend/app/store/userStore.ts
git commit -m "feat: add organization and league state to Zustand store"
```

---

## Phase 8: Frontend Organization Components

### Task 8.1: Create Organization Hooks

**Files:**
- Create: `frontend/app/components/organization/hooks/useOrganizations.ts`
- Create: `frontend/app/components/organization/hooks/useOrganization.ts`

**Step 1: Create useOrganizations.ts**

```typescript
import { useCallback, useEffect } from 'react';
import { useUserStore } from '~/store/userStore';

export function useOrganizations() {
  const organizations = useUserStore((state) => state.organizations);
  const getOrganizations = useUserStore((state) => state.getOrganizations);

  const refetch = useCallback(() => {
    getOrganizations();
  }, [getOrganizations]);

  useEffect(() => {
    if (organizations.length === 0) {
      refetch();
    }
  }, [organizations.length, refetch]);

  return {
    organizations,
    isLoading: organizations.length === 0,
    refetch,
  };
}
```

**Step 2: Create useOrganization.ts**

```typescript
import { useCallback, useEffect } from 'react';
import { useUserStore } from '~/store/userStore';

export function useOrganization(pk: number | undefined) {
  const organization = useUserStore((state) => state.organization);
  const getOrganization = useUserStore((state) => state.getOrganization);

  const refetch = useCallback(() => {
    if (pk) {
      getOrganization(pk);
    }
  }, [pk, getOrganization]);

  useEffect(() => {
    if (pk && (!organization || organization.pk !== pk)) {
      refetch();
    }
  }, [pk, organization, refetch]);

  return {
    organization: organization?.pk === pk ? organization : null,
    isLoading: !organization || organization.pk !== pk,
    refetch,
  };
}
```

**Step 3: Export from index.ts**

Update `frontend/app/components/organization/index.ts`:

```typescript
export { OrganizationSchema, CreateOrganizationSchema } from './schemas';
export type { OrganizationType, OrganizationsType, CreateOrganizationInput } from './schemas';
export { useOrganizations } from './hooks/useOrganizations';
export { useOrganization } from './hooks/useOrganization';
```

**Step 4: Commit**

```bash
git add frontend/app/components/organization/
git commit -m "feat: add Organization hooks with proper dependencies"
```

---

### Task 8.2: Create OrganizationCard Component

**Files:**
- Create: `frontend/app/components/organization/OrganizationCard.tsx`

**Step 1: Create component**

```typescript
import { Building2 } from 'lucide-react';
import { Link } from 'react-router';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { OrganizationType } from './schemas';

interface OrganizationCardProps {
  organization: OrganizationType;
}

export function OrganizationCard({ organization }: OrganizationCardProps) {
  return (
    <Link to={`/organizations/${organization.pk}`}>
      <Card className="hover:bg-accent transition-colors cursor-pointer">
        <CardHeader className="flex flex-row items-center gap-4">
          {organization.logo ? (
            <img
              src={organization.logo}
              alt={organization.name}
              className="w-12 h-12 rounded-lg object-cover"
            />
          ) : (
            <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center">
              <Building2 className="w-6 h-6 text-muted-foreground" />
            </div>
          )}
          <div>
            <CardTitle className="text-lg">{organization.name}</CardTitle>
            <CardDescription>
              {organization.league_count} league
              {organization.league_count !== 1 ? 's' : ''}
            </CardDescription>
          </div>
        </CardHeader>
        {organization.description && (
          <CardContent>
            <p className="text-sm text-muted-foreground line-clamp-2">
              {organization.description}
            </p>
          </CardContent>
        )}
      </Card>
    </Link>
  );
}
```

**Step 2: Export from index.ts**

Add to `frontend/app/components/organization/index.ts`:

```typescript
export { OrganizationCard } from './OrganizationCard';
```

**Step 3: Commit**

```bash
git add frontend/app/components/organization/
git commit -m "feat: add OrganizationCard component"
```

---

### Task 8.3: Create OrganizationPopover Component

**Files:**
- Create: `frontend/app/components/organization/OrganizationPopover.tsx`

**Step 1: Create component**

```typescript
import { Building2, ChevronRight } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import type { OrganizationType } from './schemas';

interface OrganizationPopoverProps {
  organization: OrganizationType;
  children: React.ReactNode;
}

export function OrganizationPopover({
  organization,
  children,
}: OrganizationPopoverProps) {
  const [open, setOpen] = useState(false);

  const handleMouseEnter = useCallback(() => setOpen(true), []);
  const handleMouseLeave = useCallback(() => setOpen(false), []);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        asChild
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        role="button"
        tabIndex={0}
        aria-expanded={open}
      >
        {children}
      </PopoverTrigger>
      <PopoverContent
        className="w-80"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            {organization.logo ? (
              <img
                src={organization.logo}
                alt={organization.name}
                className="w-10 h-10 rounded-lg object-cover"
              />
            ) : (
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                <Building2 className="w-5 h-5 text-muted-foreground" />
              </div>
            )}
            <div>
              <h4 className="font-semibold">{organization.name}</h4>
              <p className="text-sm text-muted-foreground">
                {organization.league_count} leagues &middot;{' '}
                {organization.tournament_count} tournaments
              </p>
            </div>
          </div>

          {organization.description && (
            <p className="text-sm text-muted-foreground line-clamp-3">
              {organization.description}
            </p>
          )}

          <Link
            to={`/organizations/${organization.pk}`}
            className="flex items-center justify-between text-sm text-primary hover:underline"
          >
            View Organization
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
```

**Step 2: Export from index.ts**

Add to exports:

```typescript
export { OrganizationPopover } from './OrganizationPopover';
```

**Step 3: Commit**

```bash
git add frontend/app/components/organization/
git commit -m "feat: add OrganizationPopover component with accessibility"
```

---

### Task 8.4: Create CreateOrganizationModal

**Files:**
- Create: `frontend/app/components/organization/forms/CreateOrganizationModal.tsx`

**Step 1: Create component using existing FormField pattern**

```typescript
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { createOrganization } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import { useUserStore } from '~/store/userStore';
import { CreateOrganizationSchema, type CreateOrganizationInput } from '../schemas';

interface CreateOrganizationModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateOrganizationModal({
  open,
  onOpenChange,
}: CreateOrganizationModalProps) {
  const getOrganizations = useUserStore((state) => state.getOrganizations);

  const form = useForm<CreateOrganizationInput>({
    resolver: zodResolver(CreateOrganizationSchema),
    defaultValues: {
      name: '',
      description: '',
      logo: '',
      rules_template: '',
    },
  });

  async function onSubmit(data: CreateOrganizationInput) {
    toast.promise(createOrganization(data), {
      loading: 'Creating organization...',
      success: () => {
        getOrganizations();
        onOpenChange(false);
        form.reset();
        return 'Organization created successfully';
      },
      error: 'Failed to create organization',
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Organization</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Organization name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Organization description"
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="logo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Logo URL</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="https://example.com/logo.png"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Create</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Export from index.ts**

Add:

```typescript
export { CreateOrganizationModal } from './forms/CreateOrganizationModal';
```

**Step 3: Commit**

```bash
git add frontend/app/components/organization/
git commit -m "feat: add CreateOrganizationModal with FormField pattern"
```

---

## Phase 9: Frontend League Components

### Task 9.1: Create League Hooks

**Files:**
- Create: `frontend/app/components/league/hooks/useLeagues.ts`
- Create: `frontend/app/components/league/hooks/useLeague.ts`

**Step 1: Create useLeagues.ts**

```typescript
import { useCallback, useEffect } from 'react';
import { useUserStore } from '~/store/userStore';

export function useLeagues(organizationId?: number) {
  const leagues = useUserStore((state) => state.leagues);
  const getLeagues = useUserStore((state) => state.getLeagues);

  const refetch = useCallback(() => {
    getLeagues(organizationId);
  }, [getLeagues, organizationId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Filter to ensure we only show leagues for the current org
  const filteredLeagues = organizationId
    ? leagues.filter((l) => l.organization === organizationId)
    : leagues;

  return {
    leagues: filteredLeagues,
    isLoading: leagues.length === 0,
    refetch,
  };
}
```

**Step 2: Create useLeague.ts**

```typescript
import { useCallback, useEffect, useState } from 'react';
import { fetchLeague } from '~/components/api/api';
import type { LeagueType } from '../schemas';

export function useLeague(pk: number | undefined) {
  const [league, setLeague] = useState<LeagueType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(() => {
    if (pk) {
      setIsLoading(true);
      setError(null);
      fetchLeague(pk)
        .then(setLeague)
        .catch(setError)
        .finally(() => setIsLoading(false));
    }
  }, [pk]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return {
    league,
    isLoading,
    error,
    refetch,
  };
}
```

**Step 3: Update index.ts**

```typescript
export { LeagueSchema, CreateLeagueSchema } from './schemas';
export type { LeagueType, LeaguesType, CreateLeagueInput } from './schemas';
export { useLeagues } from './hooks/useLeagues';
export { useLeague } from './hooks/useLeague';
```

**Step 4: Commit**

```bash
git add frontend/app/components/league/
git commit -m "feat: add League hooks with error handling"
```

---

### Task 9.2: Create LeagueCard Component

**Files:**
- Create: `frontend/app/components/league/LeagueCard.tsx`

**Step 1: Create component**

```typescript
import { Trophy } from 'lucide-react';
import { Link } from 'react-router';
import { Badge } from '~/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { LeagueType } from './schemas';

interface LeagueCardProps {
  league: LeagueType;
}

export function LeagueCard({ league }: LeagueCardProps) {
  return (
    <Link to={`/leagues/${league.pk}`}>
      <Card className="hover:bg-accent transition-colors cursor-pointer">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Trophy className="w-5 h-5" />
              {league.name}
            </CardTitle>
            <Badge variant="secondary">#{league.steam_league_id}</Badge>
          </div>
          <CardDescription>
            {league.tournament_count} tournament
            {league.tournament_count !== 1 ? 's' : ''}
          </CardDescription>
        </CardHeader>
        {league.description && (
          <CardContent>
            <p className="text-sm text-muted-foreground line-clamp-2">
              {league.description}
            </p>
          </CardContent>
        )}
      </Card>
    </Link>
  );
}
```

**Step 2: Export from index.ts**

Add:

```typescript
export { LeagueCard } from './LeagueCard';
```

**Step 3: Commit**

```bash
git add frontend/app/components/league/
git commit -m "feat: add LeagueCard component"
```

---

### Task 9.3: Create LeaguePopover Component

**Files:**
- Create: `frontend/app/components/league/LeaguePopover.tsx`

**Step 1: Create component**

```typescript
import { ChevronRight, Trophy } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import { Badge } from '~/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import type { LeagueType } from './schemas';

interface LeaguePopoverProps {
  league: LeagueType;
  children: React.ReactNode;
}

export function LeaguePopover({ league, children }: LeaguePopoverProps) {
  const [open, setOpen] = useState(false);

  const handleMouseEnter = useCallback(() => setOpen(true), []);
  const handleMouseLeave = useCallback(() => setOpen(false), []);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        asChild
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        role="button"
        tabIndex={0}
        aria-expanded={open}
      >
        {children}
      </PopoverTrigger>
      <PopoverContent
        className="w-80"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Trophy className="w-5 h-5" />
              <h4 className="font-semibold">{league.name}</h4>
            </div>
            <Badge variant="secondary">#{league.steam_league_id}</Badge>
          </div>

          <p className="text-sm text-muted-foreground">
            {league.tournament_count} tournaments
          </p>

          {league.description && (
            <p className="text-sm text-muted-foreground line-clamp-3">
              {league.description}
            </p>
          )}

          <Link
            to={`/leagues/${league.pk}`}
            className="flex items-center justify-between text-sm text-primary hover:underline"
          >
            View League
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
```

**Step 2: Export from index.ts**

Add:

```typescript
export { LeaguePopover } from './LeaguePopover';
```

**Step 3: Commit**

```bash
git add frontend/app/components/league/
git commit -m "feat: add LeaguePopover component with accessibility"
```

---

### Task 9.4: Create CreateLeagueModal

**Files:**
- Create: `frontend/app/components/league/forms/CreateLeagueModal.tsx`

**Step 1: Create component using FormField pattern**

```typescript
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { createLeague } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import { useUserStore } from '~/store/userStore';
import { CreateLeagueSchema, type CreateLeagueInput } from '../schemas';

interface CreateLeagueModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organizationId: number;
}

export function CreateLeagueModal({
  open,
  onOpenChange,
  organizationId,
}: CreateLeagueModalProps) {
  const getLeagues = useUserStore((state) => state.getLeagues);

  const form = useForm<CreateLeagueInput>({
    resolver: zodResolver(CreateLeagueSchema),
    defaultValues: {
      organization: organizationId,
      steam_league_id: undefined,
      name: '',
      description: '',
      rules: '',
    },
  });

  async function onSubmit(data: CreateLeagueInput) {
    toast.promise(createLeague({ ...data, organization: organizationId }), {
      loading: 'Creating league...',
      success: () => {
        getLeagues(organizationId);
        onOpenChange(false);
        form.reset();
        return 'League created successfully';
      },
      error: 'Failed to create league',
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create League</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="steam_league_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Steam League ID</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="12345"
                      {...field}
                      onChange={(e) =>
                        field.onChange(
                          e.target.value ? parseInt(e.target.value, 10) : undefined
                        )
                      }
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="League name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="League description"
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Create</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Export from index.ts**

Add:

```typescript
export { CreateLeagueModal } from './forms/CreateLeagueModal';
```

**Step 3: Commit**

```bash
git add frontend/app/components/league/
git commit -m "feat: add CreateLeagueModal with FormField pattern"
```

---

## Phase 10: Frontend Pages

### Task 10.1: Create Organizations List Page

**Files:**
- Create: `frontend/app/routes/organizations.tsx`

**Step 1: Create page in routes directory**

```typescript
import { Plus } from 'lucide-react';
import { useState } from 'react';
import {
  CreateOrganizationModal,
  OrganizationCard,
  useOrganizations,
} from '~/components/organization';
import { Button } from '~/components/ui/button';
import { useUserStore } from '~/store/userStore';

export default function OrganizationsPage() {
  const { organizations, isLoading } = useOrganizations();
  const currentUser = useUserStore((state) => state.currentUser);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Organizations</h1>
        {currentUser?.is_superuser && (
          <Button onClick={() => setCreateModalOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Organization
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Loading organizations...
        </div>
      ) : organizations.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No organizations found
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {organizations.map((org) => (
            <OrganizationCard key={org.pk} organization={org} />
          ))}
        </div>
      )}

      <CreateOrganizationModal
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
      />
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/routes/organizations.tsx
git commit -m "feat: add Organizations list page"
```

---

### Task 10.2: Create Organization Detail Page

**Files:**
- Create: `frontend/app/routes/organization.tsx`

**Step 1: Create page**

```typescript
import { Building2, Plus } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router';
import { CreateLeagueModal, LeagueCard, useLeagues } from '~/components/league';
import { useOrganization } from '~/components/organization';
import { Button } from '~/components/ui/button';
import { useUserStore } from '~/store/userStore';

export default function OrganizationDetailPage() {
  const { organizationId } = useParams();
  const pk = organizationId ? parseInt(organizationId, 10) : undefined;
  const { organization, isLoading: orgLoading } = useOrganization(pk);
  const { leagues, isLoading: leaguesLoading } = useLeagues(pk);
  const currentUser = useUserStore((state) => state.currentUser);
  const [createLeagueOpen, setCreateLeagueOpen] = useState(false);

  const isOrgAdmin =
    currentUser?.is_superuser ||
    organization?.admins?.some((a) => a.pk === currentUser?.pk);

  if (orgLoading) {
    return (
      <div className="container mx-auto p-4 text-center">
        Loading organization...
      </div>
    );
  }

  if (!organization) {
    return (
      <div className="container mx-auto p-4 text-center">
        Organization not found
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center gap-4 mb-6">
        {organization.logo ? (
          <img
            src={organization.logo}
            alt={organization.name}
            className="w-16 h-16 rounded-lg object-cover"
          />
        ) : (
          <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center">
            <Building2 className="w-8 h-8 text-muted-foreground" />
          </div>
        )}
        <div>
          <h1 className="text-2xl font-bold">{organization.name}</h1>
          {organization.description && (
            <p className="text-muted-foreground">{organization.description}</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">Leagues</h2>
        {isOrgAdmin && (
          <Button onClick={() => setCreateLeagueOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create League
          </Button>
        )}
      </div>

      {leaguesLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Loading leagues...
        </div>
      ) : leagues.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No leagues found
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {leagues.map((league) => (
            <LeagueCard key={league.pk} league={league} />
          ))}
        </div>
      )}

      {pk && (
        <CreateLeagueModal
          open={createLeagueOpen}
          onOpenChange={setCreateLeagueOpen}
          organizationId={pk}
        />
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/routes/organization.tsx
git commit -m "feat: add Organization detail page"
```

---

### Task 10.3: Create League Detail Page

**Files:**
- Create: `frontend/app/routes/league.tsx`

**Step 1: Create page**

```typescript
import { Trophy } from 'lucide-react';
import { useParams } from 'react-router';
import { Badge } from '~/components/ui/badge';
import { useLeague } from '~/components/league';

export default function LeagueDetailPage() {
  const { leagueId } = useParams();
  const pk = leagueId ? parseInt(leagueId, 10) : undefined;
  const { league, isLoading, error } = useLeague(pk);

  if (isLoading) {
    return (
      <div className="container mx-auto p-4 text-center">Loading league...</div>
    );
  }

  if (error || !league) {
    return (
      <div className="container mx-auto p-4 text-center">League not found</div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center gap-4 mb-6">
        <Trophy className="w-12 h-12" />
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{league.name}</h1>
            <Badge variant="secondary">#{league.steam_league_id}</Badge>
          </div>
          <p className="text-muted-foreground">
            {league.organization_name} &middot; {league.tournament_count}{' '}
            tournaments
          </p>
        </div>
      </div>

      {league.description && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-2">Description</h2>
          <p className="text-muted-foreground">{league.description}</p>
        </div>
      )}

      {league.rules && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-2">Rules</h2>
          <div className="prose prose-sm dark:prose-invert">
            {league.rules}
          </div>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-4">Tournaments</h2>
        <p className="text-muted-foreground">
          Tournament list will be filtered here (TODO: integrate with
          TournamentFilterBar)
        </p>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/routes/league.tsx
git commit -m "feat: add League detail page"
```

---

### Task 10.4: Add Routes Configuration

**Files:**
- Modify: `frontend/app/routes.tsx`

**Step 1: Add routes using route() function**

Find the routes array and add:

```typescript
import { type RouteConfig, route } from '@react-router/dev/routes';

export default [
  // ... existing routes
  route('organizations', 'routes/organizations.tsx'),
  route('organizations/:organizationId', 'routes/organization.tsx'),
  route('leagues/:leagueId', 'routes/league.tsx'),
] satisfies RouteConfig;
```

**Step 2: Commit**

```bash
git add frontend/app/routes.tsx
git commit -m "feat: add organization and league routes"
```

---

## Phase 11: Tournament Updates

### Task 11.1: Create TournamentFilterBar Component

**Files:**
- Create: `frontend/app/components/tournament/TournamentFilterBar.tsx`

**Step 1: Create component**

```typescript
import { ChevronDown, Filter, X } from 'lucide-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { useLeagues } from '~/components/league';
import { useOrganizations } from '~/components/organization';
import { Button } from '~/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';

export function TournamentFilterBar() {
  const [open, setOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const { organizations } = useOrganizations();

  const selectedOrgId = searchParams.get('organization');
  const selectedLeagueId = searchParams.get('league');

  const { leagues } = useLeagues(
    selectedOrgId ? parseInt(selectedOrgId, 10) : undefined,
  );

  const hasFilters = selectedOrgId || selectedLeagueId;

  function setFilter(key: string, value: string | null) {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    // Clear league if org changes
    if (key === 'organization') {
      newParams.delete('league');
    }
    setSearchParams(newParams);
  }

  function clearFilters() {
    setSearchParams(new URLSearchParams());
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-4">
      <div className="flex items-center gap-2">
        <CollapsibleTrigger asChild>
          <Button variant="outline" size="sm">
            <Filter className="w-4 h-4 mr-2" />
            Filter
            <ChevronDown
              className={`w-4 h-4 ml-2 transition-transform ${open ? 'rotate-180' : ''}`}
            />
          </Button>
        </CollapsibleTrigger>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="w-4 h-4 mr-1" />
            Clear filters
          </Button>
        )}
      </div>

      <CollapsibleContent className="mt-4">
        <div className="flex flex-wrap gap-4">
          <div className="w-48">
            <label className="text-sm font-medium mb-1 block">
              Organization
            </label>
            <Select
              value={selectedOrgId || ''}
              onValueChange={(v) => setFilter('organization', v || null)}
            >
              <SelectTrigger>
                <SelectValue placeholder="All organizations" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All organizations</SelectItem>
                {organizations.map((org) => (
                  <SelectItem key={org.pk} value={org.pk?.toString() || ''}>
                    {org.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedOrgId && (
            <div className="w-48">
              <label className="text-sm font-medium mb-1 block">League</label>
              <Select
                value={selectedLeagueId || ''}
                onValueChange={(v) => setFilter('league', v || null)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All leagues" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All leagues</SelectItem>
                  {leagues.map((league) => (
                    <SelectItem key={league.pk} value={league.pk?.toString() || ''}>
                      {league.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
```

**Step 2: Export from tournament index**

Add to `frontend/app/components/tournament/index.ts` (or create if missing):

```typescript
export { TournamentFilterBar } from './TournamentFilterBar';
```

**Step 3: Commit**

```bash
git add frontend/app/components/tournament/
git commit -m "feat: add TournamentFilterBar component"
```

---

### Task 11.2: Update Tournaments Page

**Files:**
- Modify: `frontend/app/routes/tournaments.tsx` (or wherever tournaments page is)

**Step 1: Add filter bar and update data fetching**

Import and add filter bar at top of page:

```typescript
import { useSearchParams } from 'react-router';
import { TournamentFilterBar } from '~/components/tournament/TournamentFilterBar';
```

Update data fetching to use filters:

```typescript
const [searchParams] = useSearchParams();
const orgId = searchParams.get('organization');
const leagueId = searchParams.get('league');

// In useEffect or data fetching
getTournaments({
  organizationId: orgId ? parseInt(orgId, 10) : undefined,
  leagueId: leagueId ? parseInt(leagueId, 10) : undefined,
});
```

Add `<TournamentFilterBar />` component before tournament list.

**Step 2: Commit**

```bash
git add frontend/app/routes/tournaments.tsx
git commit -m "feat: add filtering to tournaments page"
```

---

## Phase 12: Profile Steam ID Update

### Task 12.1: Add Steam ID Field to Profile

**Files:**
- Modify: `frontend/app/pages/profile/profile.tsx`

**Step 1: Add Steam ID FormField to profile form**

Add after PositionForm:

```typescript
<FormField
  control={form.control}
  name="steamid"
  rules={{
    validate: (value) => {
      if (currentUser?.steamid && !value) {
        return 'Steam ID cannot be cleared once set';
      }
      return true;
    },
  }}
  render={({ field }) => (
    <FormItem>
      <FormLabel>Steam ID</FormLabel>
      <FormControl>
        <Input
          type="number"
          placeholder="Enter your Steam ID"
          {...field}
          value={field.value ?? ''}
          onChange={(e) => {
            const val = e.target.value;
            field.onChange(val ? parseInt(val, 10) : null);
          }}
        />
      </FormControl>
      {currentUser?.steamid && (
        <FormDescription>
          Steam ID cannot be removed once set
        </FormDescription>
      )}
      <FormMessage />
    </FormItem>
  )}
/>
```

**Step 2: Initialize steamid in form**

Update `initialiazeForm`:

```typescript
form.setValue('steamid', currentUser?.steamid || null);
```

**Step 3: Commit**

```bash
git add frontend/app/pages/profile/profile.tsx
git commit -m "feat: add Steam ID editing to profile with clear protection"
```

---

## Phase 13: Final Integration

### Task 13.1: Update Navigation

**Files:**
- Modify: Navigation component (find existing nav file)

**Step 1: Add Organizations link to navigation**

Find the navigation component and add link:

```typescript
<Link to="/organizations">Organizations</Link>
```

**Step 2: Commit**

```bash
git add <navigation-file>
git commit -m "feat: add Organizations to navigation"
```

---

### Task 13.2: Run Full Test Suite

**Step 1: Run backend tests**

Run: `inv test.run --cmd 'python manage.py test app.tests -v 2'`
Expected: All tests pass

**Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Manual testing**

- Start dev environment: `inv dev.debug`
- Test organization CRUD
- Test league CRUD
- Test tournament filtering
- Test profile steam ID editing

---

### Task 13.3: Final Commit

**Step 1: Review all changes**

Run: `git status`

**Step 2: Create summary commit if needed**

```bash
git add -A
git commit -m "feat: complete organizations and leagues implementation"
```

---

## Summary

This implementation plan covers:

1. **Backend Models**: Organization, League with markdown sanitization in serializers
2. **Backend API**: Full CRUD with hierarchical permissions, annotated queries, nested caching
3. **Backend Tests**: Organization and League API tests with XSS coverage
4. **Data Migration**: Automatic linking of existing tournaments to leagues
5. **Frontend Types**: Zod schemas as single source of truth
6. **Frontend API**: Organization and League API functions
7. **Frontend State**: Zustand store updates (without persistence for freshness)
8. **Frontend Components**: Cards, popovers with accessibility, modals with FormField pattern
9. **Frontend Pages**: In `routes/` directory with proper route() syntax
10. **Tournament Updates**: Filter bar with URL params and Collapsible
11. **Profile Updates**: Steam ID editing with clear protection

Each task is atomic and can be committed independently. Follow TDD where tests are provided.

## Key Fixes Applied

- Added Task 1.6 for data migration
- Added Task 0.1 for prerequisite shadcn components
- Used FormField/FormItem pattern instead of Controller/Field
- Fixed routes to use `routes/` directory and `route()` function
- Added annotations to querysets to avoid N+1
- Used nested caching functions with cache keys
- Fixed permission classes to include `has_permission`
- Removed duplicate type definitions (Zod-only types)
- Fixed hook dependency arrays
- Removed org/leagues from store persistence
- Added Model Meta classes and updated_at fields
- Added XSS test coverage for event handlers and javascript: URLs
