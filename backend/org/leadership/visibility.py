from typing import Final

from org.leadership.kinds import LeadershipKind
from org.leadership.settings import get_leadership_settings
from org.models import Organization, OrgUser
from org.models_leadership import OrgLeadershipSettings

REVIEW_DERIVED_KINDS: Final[frozenset[LeadershipKind]] = frozenset(
    {LeadershipKind.CAPTAIN_RATING}
)


def own_feedback_hidden(settings: OrgLeadershipSettings, *, own: bool) -> bool:
    return own and not settings.captain_feedback_visible


def feedback_hidden(
    org: Organization | int, *, viewer: OrgUser | None, subject: OrgUser
) -> bool:
    if viewer is None or viewer.pk != subject.pk:
        return False
    return own_feedback_hidden(get_leadership_settings(org), own=True)
