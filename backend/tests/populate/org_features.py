"""Populate and reset the org locked features E2E data (tests.data.org_features).

populate_org_features_data creates the orgs, leagues, users, memberships and
past tournaments, then runs the reset. reset_org_features_data, behind
POST /api/tests/org-features/reset/, rebuilds everything the specs change: ledger
rows, promo sends, point values, events, templates, org settings (deleted, so
the next read gets the defaults), feature switches, role membership, org
memberships (non-seeded OrgUsers are deleted), the seeded tournaments (non-seeded
ones in the features leagues are deleted), org name and timezone, and the
conduct seed (finalized attendance outcomes on completed events, conduct
settings deleted, approved signups on the forecast event), and the leadership
seed (tournament 264 and a completed event with two closed captain snapshots,
one captained by org staff, and one open; traits and leadership settings
deleted, or recreated with the staff release gate on when asked).
org_features_test_data is the lookup the specs read.
"""

from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from league.models import League
from org.conduct.constants import Outcome, OutcomeSource
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry, sync_event_staff_entries
from org.features import FeatureKey, set_org_feature
from org.leadership.lifecycle import snapshot_event
from org.leadership.reviews import submit_review
from org.leadership.traits import effective_traits, materialize_traits
from org.models import (
    ContributionEntry,
    ContributionPointValue,
    Organization,
    OrgSettings,
    OrgUser,
    PromoSend,
)
from org.models_conduct import AttendanceOutcome, OrgConductSettings
from org.models_leadership import (
    CaptainTrait,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.models_promotion import PromoTemplate
from tests.data.models import TestLeague, TestOrganization, TestUser
from tests.data.org_features import (
    FEATURES_LEAGUE,
    FEATURES_ORG,
    FEATURES_ORG_DISCORD_LINK,
    LOCKED_FEATURES_ORG,
    OF_ADMIN,
    OF_LOCKED_ADMIN,
    OF_OWNER,
    OF_PROMOTER,
    OF_STAFF,
    ORG_FEATURES_COMPLETED_EVENT_NAME,
    ORG_FEATURES_CONDUCT_EVENT_NAME,
    ORG_FEATURES_CONDUCT_NEW_MEMBER,
    ORG_FEATURES_CONDUCT_OUTCOMES,
    ORG_FEATURES_CONDUCT_PAST_EVENT_NAMES,
    ORG_FEATURES_CONDUCT_RANKED,
    ORG_FEATURES_CONDUCT_SIGNUPS,
    ORG_FEATURES_EVENT_TOURNAMENT_NAME,
    ORG_FEATURES_LEADERSHIP_EVENT_NAME,
    ORG_FEATURES_LEADERSHIP_TEAMS,
    ORG_FEATURES_LEADERSHIP_TOURNAMENT,
    ORG_FEATURES_MANUAL_AWARDS,
    ORG_FEATURES_MEMBERS,
    ORG_FEATURES_ORG_LEAGUES,
    ORG_FEATURES_ORGS,
    ORG_FEATURES_PRIVATE_PKS,
    ORG_FEATURES_ROLE_USERS,
    ORG_FEATURES_SERVER_NICKNAMES,
    ORG_FEATURES_TEMPLATES,
    ORG_FEATURES_TOURNAMENTS,
    ORG_FEATURES_UNLOCKED_PKS,
    ORG_FEATURES_UPCOMING2_EVENT_NAME,
    ORG_FEATURES_UPCOMING_EVENT_NAME,
    ORG_FEATURES_USERS,
    PRIVATE_FEATURES_ORG,
)
from tests.populate.promotion_audiences import (
    restore_promotion_audience_settings,
    seed_promotion_audiences,
)
from tests.populate.promotion_integration import (
    restore_promotion_integration_settings,
    seed_promotion_integration,
)
from tests.populate.utils import (
    delete_events,
    delete_ledger_for_users,
    ensure_org_user,
)
from tournament.models import Team, Tournament
from user.models import PositionsModel

# (org pk, owner, admins, staff, promoters)
_ROLES: list[tuple[int, TestUser, list[TestUser], list[TestUser], list[TestUser]]] = [
    (FEATURES_ORG.pk, OF_OWNER, [OF_OWNER, OF_ADMIN], [OF_STAFF], [OF_PROMOTER]),
    (LOCKED_FEATURES_ORG.pk, OF_LOCKED_ADMIN, [OF_LOCKED_ADMIN], [], []),
    (PRIVATE_FEATURES_ORG.pk, OF_OWNER, [OF_OWNER, OF_ADMIN], [], []),
]


def _ensure_org_and_league(
    org_data: TestOrganization, league_data: TestLeague
) -> Organization:
    org, _ = Organization.objects.update_or_create(
        pk=org_data.pk,
        defaults={
            "name": org_data.name,
            "description": org_data.description,
            "logo": "",
            "timezone": org_data.timezone,
        },
    )
    League.objects.update_or_create(
        pk=league_data.pk,
        defaults={
            "steam_league_id": league_data.steam_league_id,
            "name": league_data.name,
            "organization": org,
            "timezone": league_data.timezone,
        },
    )
    return org


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.save()
    return user


def _ensure_tournaments() -> None:
    league = League.objects.nocache().get(pk=FEATURES_LEAGUE.pk)
    now = timezone.now()
    for pk, name, days_ago, players in ORG_FEATURES_TOURNAMENTS:
        tournament, _ = Tournament.objects.update_or_create(
            pk=pk,
            defaults={
                "name": name,
                "league": league,
                "steam_league_id": league.steam_league_id,
                "date_played": now - timedelta(days=days_ago),
                "state": "past",
                "tournament_type": "double_elimination",
            },
        )
        tournament.users.set([p.pk for p in players])


def populate_org_features_data(force: bool = False) -> None:
    """Create the locked features orgs, users and tournaments, then reset.

    Users are updated in place, never deleted, so `force` changes nothing.
    """
    print("  Populating org features E2E data...")
    for org_data, league_data in ORG_FEATURES_ORG_LEAGUES:
        _ensure_org_and_league(org_data, league_data)
    for data in ORG_FEATURES_USERS:
        _ensure_user(data)
    reset_org_features_data()
    print(f"    Created {', '.join(o.name for o in ORG_FEATURES_ORGS)}")


def _orgs() -> dict[int, Organization]:
    return {
        org.pk: org
        for org in Organization.objects.nocache().filter(
            pk__in=[o.pk for o in ORG_FEATURES_ORGS]
        )
    }


def _users() -> dict[int, CustomUser]:
    return {
        u.pk: u
        for u in CustomUser.objects.nocache().filter(
            pk__in=[d.pk for d in ORG_FEATURES_USERS]
        )
    }


def _reset_roles(orgs: dict[int, Organization], users: dict[int, CustomUser]) -> None:
    seeded = {o.pk: o for o in ORG_FEATURES_ORGS}
    for org_pk, owner, admins, staff, promoters in _ROLES:
        org = orgs[org_pk]
        org.owner = users[owner.pk]
        org.name = seeded[org_pk].name
        org.timezone = seeded[org_pk].timezone
        org.members_private = org_pk in ORG_FEATURES_PRIVATE_PKS
        org.discord_link = (
            FEATURES_ORG_DISCORD_LINK if org_pk == FEATURES_ORG.pk else ""
        )
        org.discord_server_id = None
        org.save(
            update_fields=[
                "owner",
                "name",
                "timezone",
                "members_private",
                "discord_link",
                "discord_server_id",
            ]
        )
        org.admins.set([users[u.pk] for u in admins])
        org.staff.set([users[u.pk] for u in staff])
        org.promoters.set([users[u.pk] for u in promoters])
        member_pks = [m.pk for m in ORG_FEATURES_MEMBERS[org_pk]]
        OrgUser.objects.nocache().filter(organization=org).exclude(
            user_id__in=member_pks
        ).delete()
        for pk in member_pks:
            ensure_org_user(
                users[pk],
                org,
                guild_nickname=ORG_FEATURES_SERVER_NICKNAMES.get((org_pk, pk)),
            )


def _reset_switches(orgs: dict[int, Organization]) -> None:
    for org in orgs.values():
        for key in FeatureKey:
            set_org_feature(
                org, key, enabled=org.pk in ORG_FEATURES_UNLOCKED_PKS, actor=None
            )


def _create_events(org: Organization, users: dict[int, CustomUser]) -> None:
    now = timezone.now()
    admin = users[OF_ADMIN.pk]
    for name, days, state in (
        (ORG_FEATURES_UPCOMING_EVENT_NAME, 3, EventState.UPCOMING),
        (ORG_FEATURES_CONDUCT_EVENT_NAME, 4, EventState.SIGNUPS_OPEN),
        (ORG_FEATURES_UPCOMING2_EVENT_NAME, 5, EventState.UPCOMING),
    ):
        start = now + timedelta(days=days)
        Event.objects.create(
            organization=org,
            name=name,
            description="Upcoming event for the locked features E2E tests.",
            tournament_name=ORG_FEATURES_EVENT_TOURNAMENT_NAME,
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            state=state,
            created_by=admin,
        )

    start = now - timedelta(days=2)
    completed = Event.objects.create(
        organization=org,
        name=ORG_FEATURES_COMPLETED_EVENT_NAME,
        description="Completed event with a host and a helper.",
        tournament_name=ORG_FEATURES_EVENT_TOURNAMENT_NAME,
        scheduled_at=start,
        ends_at=start + timedelta(hours=3),
        state=EventState.COMPLETED,
        created_by=admin,
        host=users[OF_STAFF.pk],
    )
    completed.helpers.set([users[OF_PROMOTER.pk]])
    sync_event_staff_entries(completed)
    Event.objects.nocache().filter(pk=completed.pk).update(contributions_awarded_at=now)


def _outcome_row(
    org: Organization,
    org_user: OrgUser,
    event: Event,
    outcome: str,
    *,
    admin: CustomUser,
    now: datetime,
) -> AttendanceOutcome:
    source = {
        Outcome.LATE_CANCEL: OutcomeSource.LATE_CANCEL,
        Outcome.EXCUSED: OutcomeSource.STAFF,
    }.get(Outcome(outcome), OutcomeSource.DEFAULT)
    staff = source == OutcomeSource.STAFF
    return AttendanceOutcome(
        organization=org,
        org_user=org_user,
        event=event,
        event_name=event.name,
        event_starts_at=event.scheduled_at,
        outcome=outcome,
        source=source,
        cancelled_at=(
            event.scheduled_at - timedelta(hours=1)
            if outcome == Outcome.LATE_CANCEL
            else None
        ),
        set_by=admin if staff else None,
        reason="Seeded excuse" if staff else "",
        finalized_at=now,
    )


def _seed_conduct(
    org: Organization, users: dict[int, CustomUser], now: datetime
) -> None:
    admin = users[OF_ADMIN.pk]
    org_users = {
        ou.user_id: ou for ou in OrgUser.objects.nocache().filter(organization=org)
    }
    past: list[Event] = []
    for name, days in zip(ORG_FEATURES_CONDUCT_PAST_EVENT_NAMES, (30, 60), strict=True):
        start = now - timedelta(days=days)
        past.append(
            Event.objects.create(
                organization=org,
                name=name,
                description="Past event with seeded attendance.",
                scheduled_at=start,
                ends_at=start + timedelta(hours=3),
                state=EventState.COMPLETED,
                created_by=admin,
                conduct_finalized_at=now,
            )
        )
    completed = Event.objects.nocache().get(
        organization=org, name=ORG_FEATURES_COMPLETED_EVENT_NAME
    )
    Event.objects.nocache().filter(pk=completed.pk).update(conduct_finalized_at=now)

    rows = [
        _outcome_row(org, org_users[data.pk], completed, outcome, admin=admin, now=now)
        for data, outcome in ORG_FEATURES_CONDUCT_OUTCOMES
    ]
    rows += [
        _outcome_row(
            org, org_users[data.pk], event, Outcome.ATTENDED, admin=admin, now=now
        )
        for event in past
        for data in ORG_FEATURES_CONDUCT_RANKED
    ]
    rows.append(
        _outcome_row(
            org,
            org_users[ORG_FEATURES_CONDUCT_NEW_MEMBER.pk],
            past[0],
            Outcome.ATTENDED,
            admin=admin,
            now=now,
        )
    )
    AttendanceOutcome.objects.bulk_create(rows)

    forecast_event = Event.objects.nocache().get(
        organization=org, name=ORG_FEATURES_CONDUCT_EVENT_NAME
    )
    for data in ORG_FEATURES_CONDUCT_SIGNUPS:
        EventSignup.objects.create(
            event=forecast_event, user=users[data.pk], status=SignupStatus.APPROVED
        )


def _seed_leadership(
    org: Organization, users: dict[int, CustomUser], now: datetime
) -> None:
    admin = users[OF_ADMIN.pk]
    pk, name = ORG_FEATURES_LEADERSHIP_TOURNAMENT
    # Dated before the seeded cups so it stays out of the promotion pool window.
    tournament = Tournament.objects.create(
        pk=pk,
        name=name,
        league_id=FEATURES_LEAGUE.pk,
        date_played=now - timedelta(days=60),
        state="past",
        tournament_type="double_elimination",
    )
    start = now - timedelta(days=1)
    event = Event.objects.create(
        organization=org,
        name=ORG_FEATURES_LEADERSHIP_EVENT_NAME,
        description="Completed event with captained teams for leadership reviews.",
        scheduled_at=start,
        ends_at=start + timedelta(hours=3),
        state=EventState.COMPLETED,
        created_by=admin,
        tournament=tournament,
        conduct_finalized_at=now,
    )
    org_users = {
        ou.user_id: ou for ou in OrgUser.objects.nocache().filter(organization=org)
    }
    for team_name, captain, members, placement, _, _ in ORG_FEATURES_LEADERSHIP_TEAMS:
        roster = [captain, *members]
        team = Team.objects.create(
            tournament=tournament,
            name=team_name,
            captain=users[captain.pk],
            placement=placement,
        )
        team.members.set([users[u.pk] for u in roster])
        EventSignup.objects.bulk_create(
            EventSignup(event=event, user=users[u.pk], status=SignupStatus.APPROVED)
            for u in roster
        )
        AttendanceOutcome.objects.bulk_create(
            _outcome_row(
                org, org_users[u.pk], event, Outcome.ATTENDED, admin=admin, now=now
            )
            for u in roster
        )
    snapshot_event(event, now=now)
    materialize_traits(org)
    keys = [t.key for t in effective_traits(org) if t.active]
    for _, captain, _, _, window_open, reviews in ORG_FEATURES_LEADERSHIP_TEAMS:
        captain_pk = org_users[captain.pk].pk
        for rater, score in reviews:
            submit_review(
                org,
                event_id=event.pk,
                captain_org_user_id=captain_pk,
                rater=org_users[rater.pk],
                scores=dict.fromkeys(keys, score),
                now=now,
            )
        if not window_open:
            EventCaptain.objects.nocache().filter(
                event=event, captain_id=captain_pk
            ).update(window_closes_at=now - timedelta(hours=1))


@transaction.atomic
def _rebuild() -> list[Organization]:
    orgs = _orgs()
    users = _users()
    org_pks = list(orgs)
    delete_ledger_for_users(list(users))
    AttendanceOutcome.objects.nocache().filter(organization__in=org_pks).delete()
    OrgConductSettings.objects.nocache().filter(organization__in=org_pks).delete()
    EventCaptain.objects.nocache().filter(organization__in=org_pks).delete()
    OrgLeadershipSettings.objects.nocache().filter(organization__in=org_pks).delete()
    ContributionEntry.objects.nocache().filter(organization__in=org_pks).delete()
    PromoSend.objects.nocache().filter(organization__in=org_pks).delete()
    ContributionPointValue.objects.nocache().filter(organization__in=org_pks).delete()
    delete_events(Event.objects.nocache().filter(organization__in=org_pks))
    Tournament.objects.nocache().filter(league__organization__in=org_pks).exclude(
        pk__in=[pk for pk, _, _, _ in ORG_FEATURES_TOURNAMENTS]
    ).delete()
    PromoTemplate.objects.nocache().filter(organization__in=org_pks).delete()
    CaptainTrait.objects.nocache().filter(organization__in=org_pks).delete()
    OrgSettings.objects.nocache().filter(organization__in=org_pks).delete()

    _ensure_tournaments()
    _reset_roles(orgs, users)
    for org_pk in sorted(ORG_FEATURES_UNLOCKED_PKS):
        for name, body in ORG_FEATURES_TEMPLATES:
            PromoTemplate.objects.create(
                organization=orgs[org_pk],
                name=name,
                body=body,
                created_by=users[OF_ADMIN.pk],
            )
    _reset_switches(orgs)
    _create_events(orgs[FEATURES_ORG.pk], users)
    now = timezone.now()
    _seed_conduct(orgs[FEATURES_ORG.pk], users, now)
    for org_pk, data, points, reason in ORG_FEATURES_MANUAL_AWARDS:
        award_entry(
            org=orgs[org_pk],
            user=users[data.pk],
            kind=ContributionKind.MANUAL,
            points=points,
            reason=reason,
            occurred_at=now,
            awarded_by=users[OF_ADMIN.pk],
        )
    _seed_leadership(orgs[FEATURES_ORG.pk], users, now)
    return list(orgs.values())


def reset_org_features_data(
    *,
    release_gate: bool = False,
    audiences: bool = False,
    sfg_contacts: bool = False,
) -> dict[str, Any]:
    """Put the locked features data back to the seeded state; returns the lookup.

    release_gate turns the leadership staff release gate on without stamping,
    so the closed captain snapshots stay pending release. sfg_contacts seeds
    the audiences plus synthetic imported SFG contacts on a bound event.
    """
    restore_promotion_integration_settings()
    restore_promotion_audience_settings()
    orgs = _rebuild()
    if release_gate:
        OrgLeadershipSettings.objects.create(
            organization_id=FEATURES_ORG.pk, require_staff_release=True
        )
    for model in (
        Event,
        ContributionEntry,
        PromoSend,
        PromoTemplate,
        OrgSettings,
        OrgUser,
        Tournament,
        AttendanceOutcome,
        OrgConductSettings,
        OrgLeadershipSettings,
        Team,
    ):
        invalidate_model(model)
    for org in orgs:
        invalidate_obj(org)
    data = org_features_test_data()
    if audiences or sfg_contacts:
        org = next(org for org in orgs if org.pk == FEATURES_ORG.pk)
        event = Event.objects.get(pk=data["events"]["upcoming"]["pk"])
        data["audiences"] = seed_promotion_audiences(org, event)
        if sfg_contacts:
            data["sfg_contacts"] = seed_promotion_integration(
                org, event, data["audiences"]
            )
            invalidate_model(OrgUser)
            invalidate_obj(org)
    return data


def _event_payload(org: Organization, name: str) -> dict[str, Any]:
    event = Event.objects.nocache().get(organization=org, name=name)
    return {"pk": event.pk, "name": event.name, "state": event.state}


def _conduct_payload(org: Organization) -> dict[str, Any]:
    org_user_pks = dict(
        OrgUser.objects.nocache().filter(organization=org).values_list("user_id", "pk")
    )
    attended = next(
        data
        for data, outcome in ORG_FEATURES_CONDUCT_OUTCOMES
        if outcome == Outcome.ATTENDED
    )
    return {
        "ranked_org_user_pks": [
            org_user_pks[data.pk] for data in ORG_FEATURES_CONDUCT_RANKED
        ],
        "new_member_org_user_pk": org_user_pks[ORG_FEATURES_CONDUCT_NEW_MEMBER.pk],
        "completed_event_member_org_user_pk": org_user_pks[attended.pk],
    }


def _leadership_payload(org: Organization) -> dict[str, Any]:
    org_user_pks = dict(
        OrgUser.objects.nocache().filter(organization=org).values_list("user_id", "pk")
    )
    captains = {
        team_name: org_user_pks[captain.pk]
        for team_name, captain, _, _, _, _ in ORG_FEATURES_LEADERSHIP_TEAMS
    }
    return {
        "event_pk": _event_payload(org, ORG_FEATURES_LEADERSHIP_EVENT_NAME)["pk"],
        "released_captain_org_user_pk": captains["Leaders Released"],
        "open_captain_org_user_pk": captains["Leaders Open"],
        "staff_captain_org_user_pk": captains["Leaders Staff"],
        "pending_rater_role": "promoter",
    }


def org_features_test_data() -> dict[str, Any]:
    """PKs and names the specs look up (never hardcoded there)."""
    orgs = _orgs()
    features = orgs[FEATURES_ORG.pk]

    def org_payload(org: Organization) -> dict[str, Any]:
        return {"pk": org.pk, "name": org.name}

    return {
        "orgs": {
            "features": org_payload(features),
            "locked": org_payload(orgs[LOCKED_FEATURES_ORG.pk]),
            "private": org_payload(orgs[PRIVATE_FEATURES_ORG.pk]),
        },
        "users": {
            role: {"pk": data.pk, "username": data.username}
            for role, data in ORG_FEATURES_ROLE_USERS.items()
        },
        "events": {
            "upcoming": _event_payload(features, ORG_FEATURES_UPCOMING_EVENT_NAME),
            "upcoming2": _event_payload(features, ORG_FEATURES_UPCOMING2_EVENT_NAME),
            "completed": _event_payload(features, ORG_FEATURES_COMPLETED_EVENT_NAME),
            "conduct_upcoming": _event_payload(
                features, ORG_FEATURES_CONDUCT_EVENT_NAME
            ),
        },
        "conduct": _conduct_payload(features),
        "leadership": _leadership_payload(features),
        "templates": [
            {"pk": t.pk, "name": t.name, "org_pk": t.organization_id}
            for t in PromoTemplate.objects.nocache()
            .filter(organization__in=list(orgs))
            .order_by("organization_id", "name")
        ],
        "tournaments": [
            {"pk": pk, "name": name} for pk, name, _, _ in ORG_FEATURES_TOURNAMENTS
        ],
    }
