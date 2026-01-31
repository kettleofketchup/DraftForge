# Dota 2 Custom Lobbies

Automated Dota 2 custom lobby creation during tournament drafts, allowing captains and spectators to seamlessly transition from drafting to in-game setup.

!!! info "GitHub Issue"
    [#56 - Lobby Handling With Tournament Game](https://github.com/kettleofketchup/DraftForge/issues/56)

## Overview

This feature integrates the `dota_lobby` service to generate and manage Dota 2 custom lobbies using league-defined rules, passwords, and settings. Lobbies are created **in parallel with drafting**, not after it.

---

## Goals

- Automatically create a Dota 2 custom lobby while captains are drafting
- Apply league-specific lobby rules consistently
- Reduce manual setup errors and delays before matches
- Allow admins to quickly restart or regenerate lobbies when needed

---

## Features

### Lobby Generation Integration

Utilizes the [dota_lobby](https://github.com/kettleofketchup/dota_lobby) service.

When a **draft game** is clicked:

- Trigger a bot/service to create a Dota 2 custom lobby
- Apply league-specific rules and settings
- Generate lobby credentials (name + password)

---

### Captain Invitations

- Automatically send lobby invites to Radiant and Dire captains
- Ensure captains can immediately join once the lobby is created

---

### League-Scoped Lobby Configuration

Leagues store custom lobby rules as a **YAML schema**:

- YAML should be versionable
- UI provides toggle options for different lobby value types
- Leagues store:
    - Lobby generation password(s)
    - Default lobby settings (game mode, series type, etc.)

---

### League Admin UI

League page controls for:

- View current lobby configuration
- Edit custom lobby settings (YAML editor)
- Update lobby passwords
- Validation for YAML schema before saving

---

### Lobby Lifecycle Controls

Buttons/actions for:

- Restart lobby
- Regenerate lobby (new password)
- Restarting does not break the active draft state

---

## Acceptance Criteria

- [ ] Draft page can trigger lobby creation via `dota_lobby`
- [ ] Draft page can view state of lobby and bot
- [ ] Lobby uses league-defined rules
- [ ] Captains receive invites automatically
- [ ] League admins can edit lobby settings from the UI
- [ ] Lobby can be restarted/regenerated safely
- [ ] Lobby state is visible to spectators

---

## Future Enhancements

- Auto-start lobby when draft completes
- Lobby status indicators (created / players joined / ready)
- Audit logs for lobby restarts and config changes
