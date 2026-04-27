"""
Populate events E2E test data.

Creates a dedicated Events Test Org + League + test event for Playwright tests.
Grants admin access to EVENT_ADMIN_USER and site admin.
"""

from datetime import time, timedelta

from cacheops import invalidate_obj
from django.utils import timezone as tz

from app.models import CustomUser, GameType, League, Organization, PositionsModel
from discordbot.models import DiscordEvent
from events.constants import EventState, RepeatFrequency, SignupStatus
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    OrgEventDefaults,
    RepeaterSubscription,
)
from org.models_profiles import PlayerDotaProfile
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

    # 3c. Create DotaProfiles for first 4 players with varied rank data
    dota_profiles = [
        {
            "rank_status": "active",
            "rank_medal": "Legend 3",
            "mmr": 3200,
            "pos_1": True,
            "pos_3": True,
            "pos_5": True,
            "rank_screenshot": "https://assets.kettle.sh/draftforge/discord/rank/dota2/dota2_rank.png",
        },
        {
            "rank_status": "active",
            "rank_medal": "Ancient 1",
            "mmr": 3800,
            "pos_2": True,
            "pos_4": True,
            "rank_screenshot": "https://i.imgur.com/example1.png",
        },
        {
            "rank_status": "previous",
            "rank_medal": "Divine 2",
            "mmr": None,
            "pos_1": True,
            "pos_2": True,
            "pos_5": True,
        },
        {
            "rank_status": "never",
            "battle_cup_tier": 5,
            "mmr": None,
            "pos_3": True,
            "pos_4": True,
            "pos_5": True,
            "battlecup_screenshot": "https://assets.kettle.sh/draftforge/discord/rank/dota2/battlecup_ticket.png",
        },
    ]

    for i, user_data in enumerate(EVENTS_USERS[:4]):
        profile_data = dota_profiles[i]
        user = CustomUser.objects.get(pk=user_data.pk)
        ou = ensure_org_user(user, org, mmr=2000 + (i * 200))
        PlayerDotaProfile.objects.update_or_create(
            org_user=ou,
            defaults={
                "rank_status": profile_data.get("rank_status", "never"),
                "rank_medal": profile_data.get("rank_medal", ""),
                "mmr": profile_data.get("mmr"),
                "battle_cup_tier": profile_data.get("battle_cup_tier"),
                "rank_screenshot": profile_data.get("rank_screenshot", ""),
                "battlecup_screenshot": profile_data.get("battlecup_screenshot", ""),
                "pos_1": profile_data.get("pos_1", False),
                "pos_2": profile_data.get("pos_2", False),
                "pos_3": profile_data.get("pos_3", False),
                "pos_4": profile_data.get("pos_4", False),
                "pos_5": profile_data.get("pos_5", False),
            },
        )
    print(f"    Created {len(dota_profiles)} Dota 2 profiles with rank data")

    # 4. Grant admin access
    event_admin = CustomUser.objects.filter(pk=EVENT_ADMIN_USER.pk).first()
    site_admin = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    org.admins.clear()
    if event_admin:
        org.admins.add(event_admin)
    if site_admin:
        org.admins.add(site_admin)
        ensure_org_user(site_admin, org, mmr=5000)
    invalidate_obj(org)

    # 4b. Add event_league_staff_tester as staff of league 7 ONLY (never of org 7)
    # This user is created in populate_test_auth_users (step 3); the league
    # assignment is deferred to here because league pk=7 is created above.
    from tests.data.users import EVENT_LEAGUE_STAFF_USER

    event_league_staff = CustomUser.objects.filter(
        pk=EVENT_LEAGUE_STAFF_USER.pk
    ).first()
    if event_league_staff:
        if event_league_staff not in league.staff.all():
            league.staff.add(event_league_staff)
            print(
                f"    Added {event_league_staff.username} as staff of {league.name}"
            )
        invalidate_obj(league)

    # 5. Create a sample EventRepeater + Event for E2E tests
    repeater, _ = EventRepeater.objects.update_or_create(
        organization=org,
        name="Weekly Inhouse",
        defaults={
            "description": "Weekly inhouse event for E2E tests.",
            "frequency": RepeatFrequency.WEEKLY,
            "day_of_week": 3,  # Wednesday (Sunday=0 convention)
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

    # 5b. Demo events with signups (persist across test::setup for UI testing)
    demo_signup_event, _ = Event.objects.update_or_create(
        organization=org,
        name="Demo Signup Event",
        defaults={
            "description": "Event with active signups for UI viewing.",
            "scheduled_at": tz.now() + timedelta(hours=6),
            "state": EventState.SIGNUPS_OPEN,
            "created_by": event_admin or site_admin,
            "event_repeater": repeater,
            "tournament_name": "Demo Signup Tournament",
            "tournament_league": league,
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "timezone": EVENTS_ORG.timezone,
            "auto_approve": True,
            "max_players": 10,
            "discord_announcement": True,
            "discord_announcement_channel_id": "1482767177063858216",
            "discord_post_signups": True,
            "discord_post_signups_channel_id": "1482767709279096893",
            "discord_create_event": True,
            "discord_signup_reminder": True,
            "discord_signup_reminder_hours": 24,
        },
    )
    # Create DiscordEvent so the Discord tab works
    DiscordEvent.objects.update_or_create(
        event=demo_signup_event,
        defaults={"guild_id": EVENTS_ORG.discord_server_id},
    )
    # Add signups from first 6 players
    for user_data in EVENTS_USERS[:6]:
        user = CustomUser.objects.get(pk=user_data.pk)
        EventSignup.objects.update_or_create(
            event=demo_signup_event,
            user=user,
            defaults={"status": SignupStatus.APPROVED},
        )
    # Subscribe site admin (kettleofketchup) to the Weekly Inhouse repeater
    if site_admin:
        RepeaterSubscription.objects.update_or_create(
            event_repeater=repeater,
            user=site_admin,
        )

    demo_rollcall_event, _ = Event.objects.update_or_create(
        organization=org,
        name="Demo Roll Call Event",
        defaults={
            "description": "Event in roll call for UI viewing.",
            "scheduled_at": tz.now() + timedelta(hours=4),
            "state": EventState.ROLL_CALL,
            "created_by": event_admin or site_admin,
            "tournament_name": "Demo Rollcall Tournament",
            "tournament_league": league,
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "timezone": EVENTS_ORG.timezone,
            "roll_call_enabled": True,
            "max_players": 10,
            "discord_announcement": True,
            "discord_announcement_channel_id": "1482767177063858216",
        },
    )
    DiscordEvent.objects.update_or_create(
        event=demo_rollcall_event,
        defaults={"guild_id": EVENTS_ORG.discord_server_id},
    )
    # Add signups — 6 confirmed, 4 approved (waiting)
    for i, user_data in enumerate(EVENTS_USERS[:10]):
        user = CustomUser.objects.get(pk=user_data.pk)
        status = SignupStatus.CONFIRMED if i < 6 else SignupStatus.APPROVED
        EventSignup.objects.update_or_create(
            event=demo_rollcall_event,
            user=user,
            defaults={"status": status},
        )

    demo_past_event, _ = Event.objects.update_or_create(
        organization=org,
        name="Demo Completed Event",
        defaults={
            "description": "Past event that completed successfully.",
            "scheduled_at": tz.now() - timedelta(days=3),
            "state": EventState.COMPLETED,
            "created_by": event_admin or site_admin,
            "tournament_name": "Demo Completed Tournament",
            "tournament_league": league,
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "timezone": EVENTS_ORG.timezone,
            "max_players": 10,
        },
    )
    DiscordEvent.objects.update_or_create(
        event=demo_past_event,
        defaults={"guild_id": EVENTS_ORG.discord_server_id},
    )
    # Add past signups — all confirmed
    for user_data in EVENTS_USERS[:8]:
        user = CustomUser.objects.get(pk=user_data.pk)
        EventSignup.objects.update_or_create(
            event=demo_past_event,
            user=user,
            defaults={"status": SignupStatus.CONFIRMED},
        )

    print(f"    Created 3 demo events with signups")

    # 5c. Draft Test Tournament — ready for draft start, stable PK for browser testing
    from app.models import Team, Tournament

    draft_tournament, _ = Tournament.objects.update_or_create(
        pk=100,
        defaults={
            "name": "Draft Test Tournament",
            "league": league,
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
            "draft_type": "shuffle",
            "people_per_team": 5,
            "number_of_teams": 2,
            "date_played": tz.now() + timedelta(hours=2),
            "timezone": EVENTS_ORG.timezone,
            "state": "in_progress",
            "discord_send_draft_link": True,
            "discord_send_herodraft_link": True,
        },
    )
    # Add 10 players (you + 9 event players)
    draft_players = [site_admin] + [
        CustomUser.objects.get(pk=u.pk) for u in EVENTS_USERS[:9]
    ]
    draft_tournament.users.set([p for p in draft_players if p])
    # Create 2 teams with captains (you + event_player_1)
    team_a, _ = Team.objects.update_or_create(
        tournament=draft_tournament,
        name="Team Alpha",
        defaults={"captain": site_admin, "draft_order": 1},
    )
    team_b, _ = Team.objects.update_or_create(
        tournament=draft_tournament,
        name="Team Beta",
        defaults={
            "captain": CustomUser.objects.get(pk=EVENTS_USERS[0].pk),
            "draft_order": 2,
        },
    )
    # Add captains as team members
    team_a.members.add(site_admin)
    team_b.members.add(CustomUser.objects.get(pk=EVENTS_USERS[0].pk))
    print(f"    Created Draft Test Tournament (pk=100) with 10 players, 2 captains")

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
