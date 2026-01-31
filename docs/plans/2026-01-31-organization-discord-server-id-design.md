# Organization Discord Server ID Integration

## Overview

Replace hardcoded `DISCORD_GUILD_ID` in settings with a per-organization `discord_server_id` field, allowing each organization to fetch Discord members from their own server.

## Current State

- `settings.DISCORD_GUILD_ID = 734185035623825559` (hardcoded)
- Used by:
  - `discordbot/services/users.py:get_discord_members_data()` - fetches all server members
  - `discordbot/services/users.py:get_discord_voice_channel_activity()` - fetches voice channel activity
  - `discordbot/bot.py` - Discord bot initialization (keep using settings for bot)

## Design

### Backend Changes

#### 1. Organization Model Update

Add `discord_server_id` field to Organization model:

```python
# app/models.py
class Organization(models.Model):
    # ... existing fields ...
    discord_server_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Discord server (guild) ID for fetching members"
    )
```

#### 2. Update Discord Member Functions

Modify `get_discord_members_data()` to accept optional guild_id:

```python
def get_discord_members_data(guild_id=None):
    """
    Fetch discord members from a guild.

    Args:
        guild_id: Discord guild ID. Defaults to settings.DISCORD_GUILD_ID
    """
    if guild_id is None:
        guild_id = settings.DISCORD_GUILD_ID
    # ... rest of function uses guild_id variable
```

Same pattern for `get_discord_voice_channel_activity()`.

#### 3. New API Endpoint

Create organization-scoped endpoint:

```python
# GET /api/organizations/{id}/discord-members/
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_organization_discord_members(request, pk):
    org = get_object_or_404(Organization, pk=pk)

    # Check user has access to this org
    if not has_org_access(request.user, org):
        return Response(status=403)

    if not org.discord_server_id:
        return Response(
            {"error": "Organization has no Discord server configured"},
            status=400
        )

    try:
        members = get_discord_members_data(guild_id=org.discord_server_id)
        return Response({"members": members})
    except Exception as e:
        return Response({"error": str(e)}, status=500)
```

#### 4. Serializer Update

Add field to OrganizationSerializer:

```python
class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        fields = [..., 'discord_server_id']
```

### Frontend Changes

#### 1. Organization Forms

Add `discord_server_id` field to:
- `EditOrganizationModal.tsx`
- `CreateOrganizationModal.tsx` (if exists)
- `schemas.ts` - add to Zod schema

#### 2. API Function

Add new API call:

```typescript
// api.tsx
export const getOrganizationDiscordMembers = async (orgId: number) => {
  const response = await api.get(`/api/organizations/${orgId}/discord-members/`);
  return response.data;
};
```

#### 3. User Search Integration

When searching for users to add to a tournament:
1. Get the tournament's league's organization
2. If org has `discord_server_id`, enable "Search Discord" option
3. Fetch from `/api/organizations/{id}/discord-members/`
4. Allow creating users from Discord member data

## Migration

1. Add nullable `discord_server_id` field
2. Existing orgs will have null (use fallback to settings)
3. Admins can configure their org's Discord server ID

## Backwards Compatibility

- Default guild_id parameter ensures existing code keeps working
- Bot continues using `settings.DISCORD_GUILD_ID` for its own server
- Endpoints without org context fall back to settings

## Files to Modify

### Backend
- `app/models.py` - Add field to Organization
- `app/serializers.py` - Add field to OrganizationSerializer
- `discordbot/services/users.py` - Update functions to accept guild_id
- `backend/urls.py` - Add new endpoint route
- New migration file

### Frontend
- `components/organization/schemas.ts` - Add to Zod schema
- `components/organization/forms/EditOrganizationModal.tsx` - Add form field
- `components/api/api.tsx` - Add API function
