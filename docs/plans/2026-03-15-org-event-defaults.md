# Organization Event Defaults Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let organizations save default event configuration so admins don't have to re-fill the same settings when creating events/repeaters.

**Architecture:** New `OrgEventDefaults` model (one-to-one with Organization) that inherits `EventConfigMixin` + `DiscordEventConfigMixin` and adds tournament defaults as nullable/optional fields. Frontend fetches defaults when opening create modal and pre-fills the form.

**Tech Stack:** Django, Django REST Framework, React, TanStack Query, TypeScript, Zod

---

### Design Notes

`TournamentTemplateMixin` cannot be inherited directly because:
- `tournament_name` (required) — meaningless as org default
- `tournament_league` (required FK, CASCADE) — needs to be nullable for defaults
- `tournament_date` — per-event, not a default

Instead, `OrgEventDefaults` inherits `EventConfigMixin` + `DiscordEventConfigMixin` and declares the useful tournament fields as nullable/optional overrides.

---

### Task 1: New `OrgEventDefaults` model

**Files:**
- Modify: `backend/events/models.py`
- Modify: `backend/backend/settings.py` — add CACHEOPS entry

Add after `RepeaterSubscription`:

```python
class OrgEventDefaults(EventConfigMixin, DiscordEventConfigMixin):
    """Organization-level default configuration for new events/repeaters."""

    organization = models.OneToOneField(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="event_defaults",
    )
    # Tournament defaults (all optional — override TournamentTemplateMixin's required fields)
    default_tournament_league = models.ForeignKey(
        "app.League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default league for new events",
    )
    default_tournament_type = models.CharField(
        max_length=30,
        choices=TOURNAMNET_TYPE_CHOICES,
        default="double_elimination",
    )
    default_game_type = models.IntegerField(
        choices=GameType.choices, default=GameType.DOTA2
    )
    default_draft_type = models.CharField(
        max_length=10,
        choices=[(s.value, s.value.title()) for s in DraftStyles],
        default=DraftStyles.shuffle.value,
    )
    default_people_per_team = models.IntegerField(default=5)
    default_number_of_teams = models.IntegerField(null=True, blank=True, default=2)
    default_game_mode = models.CharField(
        max_length=20, choices=GameMode.choices, default=GameMode.NORMAL
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Org event defaults"

    def __str__(self):
        return f"Event defaults for {self.organization.name}"
```

Add to CACHEOPS:
```python
"events.orgeventdefaults": {"ops": "all", "timeout": 60 * 60},
```

Run `just py::manage makemigrations events`.

---

### Task 2: Serializer + API endpoint

**Files:**
- Modify: `backend/events/serializers.py`
- Modify: `backend/events/views.py`
- Modify: `backend/events/urls.py`

**Step 1: Serializer**

```python
class OrgEventDefaultsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgEventDefaults
        fields = [
            "id",
            "organization",
            # EventConfig
            "timezone",
            "min_players",
            "max_players",
            "signup_deadline_hours",
            "allow_team_signups",
            "allow_user_signups",
            "auto_approve",
            "auto_confirm",
            "require_mmr_verified",
            "require_steam_id",
            "require_profile_complete",
            "roll_call_enabled",
            "roll_call_mode",
            # DiscordConfig (all fields from mixin)
            "discord_create_event",
            "discord_sync_signups",
            "discord_event_title",
            "discord_event_description",
            "discord_event_info",
            "discord_signup_reminder",
            "discord_signup_reminder_hours",
            "discord_confirm_attendance",
            "discord_confirm_attendance_hours",
            "discord_profile_reminder",
            "discord_profile_reminder_hours",
            "discord_mark_interested",
            "discord_post_signups",
            "discord_post_signups_channel_id",
            "discord_announcement",
            "discord_announcement_channel_id",
            "discord_announcement_hours",
            # Tournament defaults
            "default_tournament_league",
            "default_tournament_type",
            "default_game_type",
            "default_draft_type",
            "default_people_per_team",
            "default_number_of_teams",
            "default_game_mode",
            # Timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
```

**Step 2: ViewSet**

Simple retrieve-or-create + update pattern. Only org staff can modify.

```python
class OrgEventDefaultsViewSet(viewsets.GenericViewSet):
    """Get or update event defaults for an organization.

    GET  /events/defaults/?organization=<pk>  — returns defaults (creates if missing)
    PATCH /events/defaults/<pk>/              — update defaults
    """
    serializer_class = OrgEventDefaultsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OrgEventDefaults.objects.select_related("organization")

    def list(self, request):
        org_id = request.query_params.get("organization")
        if not org_id:
            return Response({"error": "organization param required"}, status=400)
        try:
            org = Organization.objects.get(pk=int(org_id))
        except Organization.DoesNotExist:
            return Response({"error": "Organization not found"}, status=404)
        defaults, _ = OrgEventDefaults.objects.get_or_create(organization=org)
        return Response(OrgEventDefaultsSerializer(defaults).data)

    def partial_update(self, request, pk=None):
        defaults = self.get_object()
        if not has_org_staff_access(request.user, defaults.organization):
            raise PermissionDenied("Staff access required.")
        serializer = self.get_serializer(defaults, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_obj(defaults)
        return Response(serializer.data)
```

**Step 3: URL registration**

```python
router.register(r"defaults", OrgEventDefaultsViewSet, basename="event-defaults")
```

---

### Task 3: Frontend — API function + types

**Files:**
- Modify: `frontend/app/components/api/eventsAPI.ts`
- Modify: `frontend/app/components/api/api.tsx`

```typescript
export interface OrgEventDefaultsType {
  id: number;
  organization: number;
  // EventConfig fields
  timezone: string;
  min_players: number | null;
  max_players: number | null;
  // ... all EventConfigMixin + DiscordEventConfigMixin fields
  // Tournament defaults
  default_tournament_league: number | null;
  default_tournament_type: string;
  default_game_type: number;
  default_draft_type: string;
  default_people_per_team: number;
  default_number_of_teams: number | null;
  default_game_mode: string;
}

export async function getOrgEventDefaults(orgId: number): Promise<OrgEventDefaultsType> {
  const { data } = await axios.get<OrgEventDefaultsType>(
    `/events/defaults/?organization=${orgId}`
  );
  return data;
}

export async function updateOrgEventDefaults(
  defaultsId: number,
  payload: Partial<OrgEventDefaultsType>
): Promise<OrgEventDefaultsType> {
  const { data } = await axios.patch<OrgEventDefaultsType>(
    `/events/defaults/${defaultsId}/`,
    payload
  );
  return data;
}
```

---

### Task 4: Frontend — Pre-fill create modal from org defaults

**Files:**
- Modify: `frontend/app/components/events/CreateEventModal.tsx`

Fetch org defaults when the modal opens. Apply them as form default values (merged with hardcoded fallbacks).

```typescript
const { data: orgDefaults } = useQuery({
  queryKey: ['org-event-defaults', organizationId],
  queryFn: () => getOrgEventDefaults(organizationId),
  enabled: open,
});

// Reset form with org defaults when they load
useEffect(() => {
  if (orgDefaults && open) {
    form.reset({
      ...form.getValues(), // keep any user edits
      tournament_type: orgDefaults.default_tournament_type,
      game_type: orgDefaults.default_game_type,
      draft_type: orgDefaults.default_draft_type,
      people_per_team: orgDefaults.default_people_per_team,
      number_of_teams: orgDefaults.default_number_of_teams,
      tournament_league: orgDefaults.default_tournament_league ?? undefined,
      ...pick(orgDefaults, Object.keys(DISCORD_CONFIG_DEFAULTS)),
      // EventConfig fields
      timezone: orgDefaults.timezone,
      // ... etc
    });
  }
}, [orgDefaults, open]);
```

---

### Task 5: Frontend — Org defaults settings page/modal

**Files:**
- Create: `frontend/app/components/events/OrgEventDefaultsModal.tsx`

Reuse the same tabbed form layout (Event tab + Discord tab) but for editing org defaults. Opened from the organization page (new "Event Defaults" button for admins).

---

### Task 6: Verification + populate test data

Set defaults for Events Test Org in populate script.

---

## Files Summary

| File | Change |
|------|--------|
| `backend/events/models.py` | Add `OrgEventDefaults` model |
| `backend/events/migrations/0010_*.py` | Auto-generated |
| `backend/backend/settings.py` | Add CACHEOPS entry |
| `backend/events/serializers.py` | Add `OrgEventDefaultsSerializer` |
| `backend/events/views.py` | Add `OrgEventDefaultsViewSet` |
| `backend/events/urls.py` | Register defaults viewset |
| `frontend/app/components/api/eventsAPI.ts` | Add types + API functions |
| `frontend/app/components/api/api.tsx` | Re-export |
| `frontend/app/components/events/CreateEventModal.tsx` | Pre-fill from org defaults |
| `frontend/app/components/events/OrgEventDefaultsModal.tsx` | New: edit org defaults modal |
| `frontend/app/routes/organization.tsx` | Add "Event Defaults" button |
| `backend/tests/populate/events.py` | Set defaults for test org |
