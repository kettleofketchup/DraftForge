# Admin Team Management Design

**Date:** 2026-01-24
**Status:** Approved

## Overview

Add owner/admin/staff management for Organizations and Leagues, with audit logging and multi-organization league support.

## Data Model Changes

### Organization Model Updates

- Add `owner` field (ForeignKey to CustomUser, required)
- Keep existing `admins` and `staff` M2M fields
- Owner cannot be in admins list (separate role)

### League Model Updates

- Change `organization` from ForeignKey to ManyToManyField named `organizations`
- Keep existing `admins` and `staff` M2M fields (no owner for leagues)

### Permission Hierarchy

```
Organization:
  owner     → full control, can transfer ownership, cannot be removed
  admins    → can edit org, manage admins/staff (not owner), manage leagues
  staff     → can manage tournaments/games

League:
  org admins (any linked org) → league admin access
  league admins              → league admin access (additive)
  org staff (any linked org) → league staff access
  league staff               → league staff access (additive)
```

### New Audit Log Models

**OrgLog:**
- organization (FK)
- actor (FK to user who performed action)
- action (CharField: add_admin, remove_staff, transfer_ownership, etc.)
- target_user (FK to affected user)
- details (JSONField for extra data)
- created_at (auto timestamp)

**LeagueLog:**
- league (FK)
- actor (FK)
- action (CharField: add_admin, remove_staff, link_organization, etc.)
- target_user (FK)
- details (JSONField)
- created_at (auto timestamp)

## Backend API

### User Search Endpoint

```
GET /api/users/search/?q=discord_name
```
- Searches discordNickname and guildNickname (case-insensitive)
- Requires authentication
- Minimum 3 characters
- Returns max 20 results
- Returns: pk, username, nickname, avatar

### Organization Admin Team Endpoints

```
POST   /api/organizations/{id}/admins/                - Add admin
DELETE /api/organizations/{id}/admins/{user_id}/      - Remove admin
POST   /api/organizations/{id}/staff/                 - Add staff
DELETE /api/organizations/{id}/staff/{user_id}/       - Remove staff
POST   /api/organizations/{id}/transfer-ownership/    - Transfer ownership
```

**Permissions:**
- Add admin: owner or existing admin
- Remove admin: owner only
- Add/remove staff: owner or admin
- Transfer ownership: owner or superuser

### League Admin Team Endpoints

```
POST   /api/leagues/{id}/admins/           - Add admin
DELETE /api/leagues/{id}/admins/{user_id}/ - Remove admin
POST   /api/leagues/{id}/staff/            - Add staff
DELETE /api/leagues/{id}/staff/{user_id}/ - Remove staff
```

**Permissions:**
- Add/remove admin: org admin (from any linked org)
- Add/remove staff: org admin or league admin

## Frontend UI

### Admin Team Section (Collapsible)

Added to EditOrganizationModal and EditLeagueModal as a collapsible section.

**Organization view:**
```
┌─ Admin Team ─────────────────────────────────────┐
│ Owner                                            │
│ │ 👤 DiscordUser#1234          [Transfer]      │ │
│                                                  │
│ Admins                                           │
│ │ 👤 AdminUser#5678              [Remove]      │ │
│ [ Search Discord user...      ] [Add Admin]     │
│                                                  │
│ Staff                                            │
│ │ 👤 StaffMember#3456            [Remove]      │ │
│ [ Search Discord user...      ] [Add Staff]     │
└──────────────────────────────────────────────────┘
```

**League view:**
- Same layout but no Owner section
- Shows "Inherited from: [Org1], [Org2]" for org-level permissions
- Only league-specific admins/staff are editable

### User Search Input Component

- Debounced input (300ms)
- Minimum 3 characters to trigger search
- Dropdown shows matching users with avatars
- Searches Discord username and nickname

## Migrations

1. Add `owner` field to Organization (nullable initially)
2. Data migration: set first admin as owner for each org
3. Make `owner` field required
4. Change League.organization FK → League.organizations M2M
5. Data migration: convert existing FK relationships to M2M
6. Data migration: move orphan tournaments to first organization
7. Add OrgLog and LeagueLog models
8. Add DB indexes on CustomUser.discordNickname and guildNickname

## Implementation Order

### Backend
1. Update models and create migrations
2. Update permission helpers for multi-org leagues
3. Add user search endpoint
4. Add org admin team management endpoints
5. Add league admin team management endpoints
6. Update serializers for new fields

### Frontend
1. Update Organization and League schemas/types
2. Create AdminTeamSection component
3. Create UserSearchInput component
4. Add AdminTeamSection to EditOrganizationModal
5. Add AdminTeamSection to EditLeagueModal
6. Update permission hooks for multi-org leagues

## Future Notes

- Rename "Kettle of Tournaments" → "DraftForge" (separate task)
- Log models are placeholders for future audit logging (tournament changes, settings, etc.)
