# Planned Features

Features currently in design or development for DraftForge.

---

## Team Management & Seasons

Persistent team management within leagues, organized by seasons. Teams are formed per-season via draft or manual creation, then imported into tournaments.

[:material-arrow-right: Team Management & Seasons](team-management.md)

**Key Features:**

- Seasons as containers for teams within a league
- Player signup flow with admin review
- Per-season team formation (draft or manual)
- Team logos
- Tournament import from season teams
- Deputy captains

**Status:** :material-pencil: Design Complete

---

## League Rating System

A comprehensive rating system for tracking player skill across tournaments and leagues.

[:material-arrow-right: League Rating System](league-rating.md)

**Key Features:**

- Dual rating tracking (Elo + Glicko-2)
- MMR epoch system for skill drift
- Flexible K-factor modes
- Organization-level aggregation
- Age decay for older matches
- Uncertainty tracking and display

**Status:** :material-pencil: Design Complete

---

## Dota 2 Custom Lobbies

Automated Dota 2 custom lobby creation during tournament drafts.

[:material-arrow-right: Dota 2 Custom Lobbies](dota-lobbies.md)

**Key Features:**

- Automatic lobby creation during draft
- League-scoped YAML configuration
- Captain auto-invites
- Lobby restart/regenerate controls
- Spectator visibility

**Status:** :material-lightbulb-outline: Planned | [GitHub #56](https://github.com/kettleofketchup/DraftForge/issues/56)

---

## Discord Integration

Automated event management with Discord bot integration for tournament signups and announcements.

[:material-arrow-right: Discord Integration](discord-integration.md)

**Key Features:**

- Organization Discord server linking
- Event posting to Discord channels
- Reaction-based signup/unregister
- Scheduled announcements and reminders
- Direct message notifications

**Status:** :material-lightbulb-outline: Planned | [GitHub #52](https://github.com/kettleofketchup/DraftForge/issues/52)

---

## CSV Import

Bulk-add users to organizations and tournaments via CSV file upload, with client-side preview, conflict detection, and optional team assignment.

[:material-arrow-right: CSV Import](csv-import.md)

**Key Features:**

- Client-side CSV parsing with Papa Parse
- Steam Friend ID and Discord ID user resolution
- Stub user creation for unregistered players
- Conflict detection and per-row error reporting
- Optional team assignment for tournament imports
- Three-step modal: Upload → Preview → Results

**Status:** :material-pencil: Design Complete | [GitHub #132](https://github.com/kettleofketchup/DraftForge/issues/132)

---

## Auction House

Alternative team formation method where captains bid on players using a virtual salary cap budget, with nomination rotation and real-time WebSocket bidding.

[:material-arrow-right: Auction House](auction-house.md)

**Key Features:**

- Nomination rotation with real-time bidding via WebSocket
- Salary cap budget with configurable starting amount
- Anti-sniping bid extension timer
- Cascading AuctionConfig (org → league → season → tournament)
- Shuffle draft fallback when budget runs out
- Captain disconnect handling with pause budgets

**Status:** :material-pencil: Design Complete
