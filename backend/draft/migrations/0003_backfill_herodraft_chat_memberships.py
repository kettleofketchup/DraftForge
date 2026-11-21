from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CLOSED_STATES = ("completed", "abandoned")


def backfill_memberships(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Open tenure at draft creation for users uniquely on one live draft team.

    Users that already have any row for a draft are left alone, so the
    backfill never rewrites tenure the signals recorded and is safe to rerun.
    """
    db = schema_editor.connection.alias
    HeroDraft = apps.get_model("draft", "HeroDraft")
    DraftTeam = apps.get_model("draft", "DraftTeam")
    Team = apps.get_model("app", "Team")
    Membership = apps.get_model("draft", "HeroDraftChatMembership")
    TeamMembers = Team._meta.get_field("members").remote_field.through

    rows = []
    drafts = (
        HeroDraft.objects.using(db)
        .exclude(state__in=CLOSED_STATES)
        .values_list("pk", "created_at")
    )
    for draft_id, created_at in drafts.iterator():
        team_ids = set(
            DraftTeam.objects.using(db)
            .filter(draft_id=draft_id)
            .values_list("tournament_team_id", flat=True)
        )
        rosters: dict[int, set[int]] = {
            team_id: {captain_id} if captain_id is not None else set()
            for team_id, captain_id in Team.objects.using(db)
            .filter(pk__in=team_ids)
            .values_list("pk", "captain_id")
        }
        for team_id, user_id in (
            TeamMembers.objects.using(db)
            .filter(team_id__in=list(rosters))
            .values_list("team_id", "customuser_id")
        ):
            rosters[team_id].add(user_id)
        owner: dict[int, int | None] = {}
        for team_id, user_ids in rosters.items():
            for user_id in user_ids:
                owner[user_id] = None if user_id in owner else team_id
        existing = set(
            Membership.objects.using(db)
            .filter(draft_id=draft_id)
            .values_list("user_id", flat=True)
        )
        rows.extend(
            Membership(
                draft_id=draft_id,
                team_id=team_id,
                user_id=user_id,
                joined_at=created_at,
            )
            for user_id, team_id in sorted(owner.items())
            if team_id is not None and user_id not in existing
        )
    Membership.objects.using(db).bulk_create(rows, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("draft", "0002_herodraftchat"),
    ]

    operations = [
        migrations.RunPython(backfill_memberships, migrations.RunPython.noop),
    ]
