from app.models import CustomUser
from org.models import OrgFeature, PromoTemplate


def repoint_org_attribution(drop: CustomUser, keep: CustomUser) -> int:
    return OrgFeature.objects.nocache().filter(enabled_by=drop).update(
        enabled_by=keep
    ) + PromoTemplate.objects.nocache().filter(created_by=drop).update(created_by=keep)
