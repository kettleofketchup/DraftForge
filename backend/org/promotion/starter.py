from django.db import transaction

from app.models import CustomUser, Organization
from org.models_promotion import PromoTemplate
from telemetry.logging import get_logger

log = get_logger(__name__)

STARTER_TEMPLATE_NAME = "First invite"
STARTER_TEMPLATE_BODY = (
    "Hey {player}! {promoter} from {org} here.\n\n"
    "We're running **{event}** on {event_time} ({event_time_relative}) "
    "and we'd love to have you play.\n\n"
    "Details and sign-up: {event_link}\n\n"
    "Hope to see you there!"
)


def seed_starter_template(
    org: Organization, actor: CustomUser | None
) -> PromoTemplate | None:
    if PromoTemplate.objects.filter(organization=org).exists():
        return None
    template = PromoTemplate.objects.create(
        organization=org,
        name=STARTER_TEMPLATE_NAME,
        body=STARTER_TEMPLATE_BODY,
        created_by=actor,
    )
    transaction.on_commit(
        lambda: log.info(
            "promo_starter_template_seeded",
            system="org",
            subsystem="promotion",
            org_id=org.pk,
            template_id=template.pk,
            actor_id=actor.pk if actor else None,
        )
    )
    return template
