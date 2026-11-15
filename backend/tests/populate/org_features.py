"""Populate and reset the org locked features E2E data (tests.data.org_features).

populate_org_features_data creates the orgs, leagues, users, memberships and
past tournaments, then runs the reset. reset_org_features_data, behind
POST /api/tests/org-features/reset/, rebuilds everything the specs change:
ledger rows, promo sends, point values, events, templates, feature switches,
role membership, org memberships (non-seeded OrgUsers are deleted), the seeded
tournaments (non-seeded ones in the features leagues are deleted) and org name
and timezone. org_features_test_data is the lookup the specs read.
"""

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser, League, Organization, PositionsModel, Tournament
from events.constants import EventState
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry, sync_event_staff_entries
from org.features import FeatureKey, set_org_feature
from org.models import ContributionEntry, ContributionPointValue, OrgUser, PromoSend
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
    ORG_FEATURES_MANUAL_AWARDS,
    ORG_FEATURES_MEMBERS,
    ORG_FEATURES_ORG_LEAGUES,
    ORG_FEATURES_ORGS,
    ORG_FEATURES_PRIVATE_PKS,
    ORG_FEATURES_ROLE_USERS,
    ORG_FEATURES_TEMPLATES,
    ORG_FEATURES_TOURNAMENTS,
    ORG_FEATURES_UNLOCKED_PKS,
    ORG_FEATURES_UPCOMING2_EVENT_NAME,
    ORG_FEATURES_UPCOMING_EVENT_NAME,
    ORG_FEATURES_USERS,
    PRIVATE_FEATURES_ORG,
)
from tests.populate.utils import delete_ledger_for_users, ensure_org_user

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
        org.save(
            update_fields=[
                "owner",
                "name",
                "timezone",
                "members_private",
                "discord_link",
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
            ensure_org_user(users[pk], org)


def _reset_switches(orgs: dict[int, Organization]) -> None:
    for org in orgs.values():
        for key in FeatureKey:
            set_org_feature(
                org, key, enabled=org.pk in ORG_FEATURES_UNLOCKED_PKS, actor=None
            )


def _create_events(org: Organization, users: dict[int, CustomUser]) -> None:
    now = timezone.now()
    admin = users[OF_ADMIN.pk]
    for name, days in (
        (ORG_FEATURES_UPCOMING_EVENT_NAME, 3),
        (ORG_FEATURES_UPCOMING2_EVENT_NAME, 5),
    ):
        start = now + timedelta(days=days)
        Event.objects.create(
            organization=org,
            name=name,
            description="Upcoming event for the locked features E2E tests.",
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            state=EventState.UPCOMING,
            created_by=admin,
        )

    start = now - timedelta(days=2)
    completed = Event.objects.create(
        organization=org,
        name=ORG_FEATURES_COMPLETED_EVENT_NAME,
        description="Completed event with a host and a helper.",
        scheduled_at=start,
        ends_at=start + timedelta(hours=3),
        state=EventState.COMPLETED,
        created_by=admin,
        host=users[OF_STAFF.pk],
    )
    completed.helpers.set([users[OF_PROMOTER.pk]])
    sync_event_staff_entries(completed)
    Event.objects.nocache().filter(pk=completed.pk).update(contributions_awarded_at=now)


@transaction.atomic
def _rebuild() -> list[Organization]:
    orgs = _orgs()
    users = _users()
    org_pks = list(orgs)
    delete_ledger_for_users(list(users))
    ContributionEntry.objects.nocache().filter(organization__in=org_pks).delete()
    PromoSend.objects.nocache().filter(organization__in=org_pks).delete()
    ContributionPointValue.objects.nocache().filter(organization__in=org_pks).delete()
    Event.objects.nocache().filter(organization__in=org_pks).delete()
    Tournament.objects.nocache().filter(league__organization__in=org_pks).exclude(
        pk__in=[pk for pk, _, _, _ in ORG_FEATURES_TOURNAMENTS]
    ).delete()
    PromoTemplate.objects.nocache().filter(organization__in=org_pks).delete()

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
    return list(orgs.values())


def reset_org_features_data() -> dict[str, Any]:
    """Put the locked features data back to the seeded state; returns the lookup."""
    orgs = _rebuild()
    for model in (
        Event,
        ContributionEntry,
        PromoSend,
        PromoTemplate,
        OrgUser,
        Tournament,
    ):
        invalidate_model(model)
    for org in orgs:
        invalidate_obj(org)
    return org_features_test_data()


def _event_payload(org: Organization, name: str) -> dict[str, Any]:
    event = Event.objects.nocache().get(organization=org, name=name)
    return {"pk": event.pk, "name": event.name, "state": event.state}


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
        },
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
