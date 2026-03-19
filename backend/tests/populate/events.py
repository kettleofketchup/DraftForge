"""
Populate events E2E test data.

Creates a dedicated Events Test Org + League + test event for Playwright tests.
Grants admin access to EVENT_ADMIN_USER and site admin.
"""

from datetime import time, timedelta

from cacheops import invalidate_obj
from django.utils import timezone as tz

from app.models import CustomUser, GameType, League, Organization, PositionsModel
from events.models import (
    Event,
    EventRepeater,
    EventState,
    OrgEventDefaults,
    RepeatFrequency,
)
from tests.data import (
    ADMIN_USER,
    EVENT_ADMIN_USER,
    EVENTS_LEAGUE,
    EVENTS_ORG,
    EVENTS_USERS,
)
from tests.populate.utils import ensure_league_user, ensure_org_user


def populate_events_data(force=False):
    """Create dedicated Events Test Org, League, users, and a sample event."""
    print("  Populating events E2E data...")

    # 1. Create org
    org, _ = Organization.objects.update_or_create(
        name=EVENTS_ORG.name,
        defaults={
            "pk": EVENTS_ORG.pk,
            "description": EVENTS_ORG.description,
            "timezone": EVENTS_ORG.timezone,
            "discord_server_id": EVENTS_ORG.discord_server_id or "",
        },
    )

    # 2. Create league
    league, _ = League.objects.update_or_create(
        steam_league_id=EVENTS_LEAGUE.steam_league_id,
        defaults={
            "pk": EVENTS_LEAGUE.pk,
            "name": EVENTS_LEAGUE.name,
            "organization": org,
        },
    )

    # 3. Create admin user
    admin_positions = PositionsModel.objects.create(
        carry=EVENT_ADMIN_USER.positions.carry if EVENT_ADMIN_USER.positions else 3,
        mid=EVENT_ADMIN_USER.positions.mid if EVENT_ADMIN_USER.positions else 3,
        offlane=EVENT_ADMIN_USER.positions.offlane if EVENT_ADMIN_USER.positions else 3,
        soft_support=(
            EVENT_ADMIN_USER.positions.soft_support if EVENT_ADMIN_USER.positions else 3
        ),
        hard_support=(
            EVENT_ADMIN_USER.positions.hard_support if EVENT_ADMIN_USER.positions else 3
        ),
    )
    admin_user, created = CustomUser.objects.update_or_create(
        pk=EVENT_ADMIN_USER.pk,
        defaults={
            "username": EVENT_ADMIN_USER.username,
            "nickname": EVENT_ADMIN_USER.nickname,
            "discordId": EVENT_ADMIN_USER.discord_id,
            "steamid": EVENT_ADMIN_USER.steam_id_64,
            "has_active_dota_mmr": True,
            "positions": admin_positions,
        },
    )
    if created:
        admin_user.set_unusable_password()
        admin_user.save()
    admin_org_user = ensure_org_user(admin_user, org, mmr=EVENT_ADMIN_USER.mmr or 4500)
    ensure_league_user(admin_user, admin_org_user, league)

    # 3b. Create player users with varied MMR
    for i, user_data in enumerate(EVENTS_USERS):
        positions = PositionsModel.objects.create(
            carry=user_data.positions.carry if user_data.positions else 3,
            mid=user_data.positions.mid if user_data.positions else 3,
            offlane=user_data.positions.offlane if user_data.positions else 3,
            soft_support=user_data.positions.soft_support if user_data.positions else 3,
            hard_support=user_data.positions.hard_support if user_data.positions else 3,
        )
        user, created = CustomUser.objects.update_or_create(
            pk=user_data.pk,
            defaults={
                "username": user_data.username,
                "nickname": user_data.nickname,
                "discordId": user_data.discord_id,
                "steamid": user_data.steam_id_64,
                "has_active_dota_mmr": True,
                "positions": positions,
            },
        )
        if created:
            user.set_unusable_password()
            user.save()
        # Create OrgUser and LeagueUser with varied MMR (2000-5800)
        mmr = 2000 + (i * 200)
        org_user = ensure_org_user(user, org, mmr=mmr)
        ensure_league_user(user, org_user, league)

    # 4. Grant admin access
    event_admin = CustomUser.objects.filter(pk=EVENT_ADMIN_USER.pk).first()
    site_admin = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    org.admins.clear()
    if event_admin:
        org.admins.add(event_admin)
    if site_admin:
        org.admins.add(site_admin)
    invalidate_obj(org)

    # 5. Create a sample EventRepeater + Event for E2E tests
    repeater, _ = EventRepeater.objects.update_or_create(
        organization=org,
        name="Weekly Inhouse",
        defaults={
            "description": "Weekly inhouse event for E2E tests.",
            "frequency": RepeatFrequency.WEEKLY,
            "day_of_week": 2,  # Wednesday
            "time_of_day": time(20, 0),
            "starts_at": tz.now().date(),
            "generate_days_ahead": 7,
            "is_active": True,
            "created_by": event_admin or site_admin,
            "tournament_name": "Events Test Tournament",
            "tournament_league": league,
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "timezone": EVENTS_ORG.timezone,
            "auto_approve": True,
            "max_players": 10,
            "discord_notify_new_events": True,
            "discord_announcement": True,
            "discord_announcement_channel_id": "1482767177063858216",
            "discord_announcement_hours": 24,
            "discord_post_signups": True,
            "discord_post_signups_channel_id": "1482767709279096893",
        },
    )

    # Create a standalone event in signups_open state for RSVP testing
    event, _ = Event.objects.update_or_create(
        organization=org,
        name="E2E Signup Event",
        defaults={
            "description": "Standalone event for E2E signup testing.",
            "scheduled_at": tz.now() + timedelta(days=7),
            "state": EventState.SIGNUPS_OPEN,
            "created_by": event_admin or site_admin,
            "tournament_name": "E2E Signup Tournament",
            "tournament_league": league,
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "timezone": EVENTS_ORG.timezone,
            "auto_approve": True,
            "max_players": 10,
        },
    )

    # 6. Create org event defaults
    OrgEventDefaults.objects.update_or_create(
        organization=org,
        defaults={
            "tournament_league": league,
            "tournament_type": "double_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "timezone": EVENTS_ORG.timezone,
            "auto_approve": True,
            "max_players": 10,
            "discord_announcement": True,
            "discord_announcement_channel_id": "1482767177063858216",
            "discord_announcement_hours": 24,
            "discord_post_signups": True,
            "discord_post_signups_channel_id": "1482767709279096893",
        },
    )

    print(
        f"    Created org={org.name} (pk={org.pk}), league={league.name} (pk={league.pk})"
    )
    print(
        f"    Created repeater={repeater.name}, event={event.name} (state={event.state})"
    )
    print("    Created org event defaults with discord channels")
