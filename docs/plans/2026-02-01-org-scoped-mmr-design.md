# Organization-Scoped MMR System

**Date:** 2026-02-01
**Issue:** https://github.com/kettleofketchup/DraftForge/issues/64

## Summary

Move MMR from a global user field to organization-scoped membership. Users will have different MMR values per organization, and league memberships snapshot MMR from their org membership.

## Current State

- `CustomUser.mmr` - global MMR per user
- `CustomUser.league_mmr` - global league MMR
- `CustomUser.has_active_dota_mmr`, `dota_mmr_last_verified` - verification tracking
- `TournamentUserSerializer` returns `mmr` directly from `CustomUser`

## New Data Model

### OrgUser (org/models.py)

User's membership and MMR within an organization. Admins set this value.

```python
class OrgUser(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="org_memberships",
        db_index=True
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="members"
    )
    mmr = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    # MMR verification (moved from CustomUser)
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    @property
    def needs_mmr_verification(self) -> bool:
        if not self.has_active_dota_mmr:
            return False
        if self.dota_mmr_last_verified is None:
            return True
        days_since = (timezone.now() - self.dota_mmr_last_verified).days
        return days_since > 30

    class Meta:
        unique_together = ["user", "organization"]
```

### LeagueUser (league_player/models.py)

User's membership in a league, tied to their org membership.

```python
class LeagueUser(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True
    )
    org_user = models.ForeignKey(
        OrgUser,
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True
    )
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="members"
    )
    mmr = models.IntegerField(default=0, db_index=True)  # Snapshot from org_user.mmr
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "league"]
```

### Relationship Chain

```
CustomUser → OrgUser (1:many) → LeagueUser (1:many)
                ↓                    ↓
          Organization            League
```

## Fields to Remove from CustomUser

- `mmr`
- `league_mmr`
- `has_active_dota_mmr`
- `dota_mmr_last_verified`
- `needs_mmr_verification` (property)

## Serializers

### OrgUserSerializer

Returns same schema as current `TournamentUserSerializer` but gets MMR from `OrgUser`:

```python
class OrgUserSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(source='user.pk', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    nickname = serializers.CharField(source='user.nickname', read_only=True)
    avatar = serializers.CharField(source='user.avatar', read_only=True)
    discordId = serializers.CharField(source='user.discordId', read_only=True)
    positions = PositionsSerializer(source='user.positions', read_only=True)
    steamid = serializers.IntegerField(source='user.steamid', read_only=True)
    steam_account_id = serializers.IntegerField(source='user.steam_account_id', read_only=True)
    avatarUrl = serializers.CharField(source='user.avatarUrl', read_only=True)
    mmr = serializers.IntegerField(read_only=True)  # From OrgUser.mmr

    class Meta:
        model = OrgUser
        fields = (
            "pk", "username", "nickname", "avatar", "discordId",
            "positions", "steamid", "steam_account_id", "avatarUrl", "mmr",
        )
```

### Tournament Serializer Changes

```python
class TournamentSerializerBase(serializers.ModelSerializer):
    users = serializers.SerializerMethodField()

    def get_users(self, tournament):
        league = tournament.league
        org = league.organizations.first()

        if not org:
            return TournamentUserSerializer(tournament.users.all(), many=True).data

        org_users = OrgUser.objects.filter(
            user__in=tournament.users.all(),
            organization=org
        ).select_related('user', 'user__positions')

        return OrgUserSerializer(org_users, many=True).data
```

## Migration Strategy

### Order

1. `org/0001_initial.py` - Create OrgUser table
2. `org/0002_populate_org_users.py` - Migrate ALL users to OrgUser (org pk=1)
3. `league_player/0001_initial.py` - Create LeagueUser table
4. `league_player/0002_populate_league_users.py` - Migrate tournament users to LeagueUser
5. `app/00XX_remove_user_mmr_fields.py` - Remove fields from CustomUser

### Data Migration: Users → OrgUser

```python
def migrate_mmr_to_org(apps, schema_editor):
    CustomUser = apps.get_model('app', 'CustomUser')
    OrgUser = apps.get_model('org', 'OrgUser')
    Organization = apps.get_model('app', 'Organization')

    org = Organization.objects.get(pk=1)

    for user in CustomUser.objects.all():
        OrgUser.objects.create(
            user=user,
            organization=org,
            mmr=user.mmr or 0,
            has_active_dota_mmr=user.has_active_dota_mmr,
            dota_mmr_last_verified=user.dota_mmr_last_verified,
        )
```

### Data Migration: Tournament Users → LeagueUser

```python
def migrate_tournament_users_to_league_users(apps, schema_editor):
    Tournament = apps.get_model('app', 'Tournament')
    OrgUser = apps.get_model('org', 'OrgUser')
    LeagueUser = apps.get_model('league_player', 'LeagueUser')

    for tournament in Tournament.objects.select_related('league').prefetch_related('users'):
        league = tournament.league
        if not league:
            continue

        org = league.organizations.first()
        if not org:
            continue

        for user in tournament.users.all():
            org_user = OrgUser.objects.get(user=user, organization=org)
            LeagueUser.objects.get_or_create(
                user=user,
                org_user=org_user,
                league=league,
                defaults={'mmr': org_user.mmr}
            )
```

## App Structure

```
backend/
├── app/                    # Existing - CustomUser, Organization, League, Tournament
├── org/                    # NEW
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py           # OrgUser
│   ├── serializers.py      # OrgUserSerializer
│   └── migrations/
└── league_player/          # NEW
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── models.py           # LeagueUser
    ├── serializers.py      # LeagueUserSerializer
    └── migrations/
```

## Auto-Create on Tournament Join

When a user joins a tournament, auto-create OrgUser if needed:

```python
def add_user_to_tournament(tournament, user):
    org = tournament.league.organizations.first()

    org_user, created = OrgUser.objects.get_or_create(
        user=user,
        organization=org,
        defaults={'mmr': 0}
    )

    tournament.users.add(user)
```

## Acceptance Criteria

- [ ] OrgUser model created with indexes
- [ ] LeagueUser model created with indexes
- [ ] Migration moves all existing users to OrgUser (org pk=1)
- [ ] Migration creates LeagueUser for all existing tournament users
- [ ] CustomUser.mmr and related fields removed
- [ ] TournamentUserSerializer returns MMR from OrgUser
- [ ] Auto-create OrgUser when user joins tournament
- [ ] Admin can update OrgUser.mmr
