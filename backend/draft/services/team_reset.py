"""Reset a tournament's teams in place for a fresh team draft."""

from dataclasses import dataclass, field
from enum import StrEnum

from app.models import CustomUser
from app.serializers import TournamentUserSerializer
from draft.services.hero_chat import delete_team_chat
from tournament.models import Team, Tournament
from tournament.services.team_references import TeamUsage, team_references, team_usage


class IneligibleReason(StrEnum):
    NO_CAPTAIN = "no_captain"
    CAPTAIN_NOT_IN_POOL = "captain_not_in_pool"


class DraftResetError(Exception):
    pass


class NoEligibleCaptains(DraftResetError):
    pass


class TeamsReferenced(DraftResetError):
    def __init__(self, references: dict[str, int], usage: list[TeamUsage]) -> None:
        super().__init__("Teams are used by games or other records.")
        self.references = references
        self.usage = usage


@dataclass
class DraftResetReport:
    reset_teams: list[Team] = field(default_factory=list)
    dropped_teams: list[dict[str, object]] = field(default_factory=list)
    kept_teams: list[dict[str, object]] = field(default_factory=list)
    cleared_deputies: list[dict[str, int]] = field(default_factory=list)
    removed_users: list[CustomUser] = field(default_factory=list)

    def as_dict(self) -> dict[str, list]:
        return {
            "reset_teams": [team.pk for team in self.reset_teams],
            "reset_team_names": [
                {"pk": team.pk, "name": team.name} for team in self.reset_teams
            ],
            "dropped_teams": self.dropped_teams,
            "kept_teams": self.kept_teams,
            "cleared_deputies": self.cleared_deputies,
        }


def _captain(team: Team) -> dict[str, object] | None:
    if team.captain is None:
        return None
    return dict(TournamentUserSerializer(team.captain).data)


def _ineligible_reason(team: Team) -> IneligibleReason:
    if team.captain_id is None:
        return IneligibleReason.NO_CAPTAIN
    return IneligibleReason.CAPTAIN_NOT_IN_POOL


def reset_draft_teams(tournament: Tournament, *, force: bool) -> DraftResetReport:
    """Validate, then reset eligible teams to their captains; call inside ``transaction.atomic``.

    Raises before any write: ``NoEligibleCaptains`` when no team can be drafted,
    ``TeamsReferenced`` when other records use the teams and ``force`` is False.
    """
    teams = tournament.teams.nocache().select_related("captain").order_by("pk")
    eligible_pks = set(
        tournament.draft_eligible_teams().nocache().values_list("pk", flat=True)
    )
    if not eligible_pks:
        raise NoEligibleCaptains
    references = team_references(teams)
    if references and not force:
        raise TeamsReferenced(references, team_usage(teams))

    report = DraftResetReport()
    for team in teams:
        if team.pk not in eligible_pks:
            entry: dict[str, object] = {
                "pk": team.pk,
                "name": team.name,
                "reason": _ineligible_reason(team),
                "captain": _captain(team),
            }
            usage = team_usage([team])
            if usage:
                entry["usage"] = usage
                report.kept_teams.append(entry)
            else:
                team.delete()
                report.dropped_teams.append(entry)
            continue
        if team.deputy_captain_id is not None:
            report.cleared_deputies.append(
                {"team": team.pk, "user": team.deputy_captain_id}
            )
        report.removed_users.extend(team.reset_to_captain())
        report.reset_teams.append(team)
    delete_team_chat(team.pk for team in report.reset_teams)
    return report
